"""Proactive Question Bar — rule-based detectors that surface DataVision's
own doubts during cleaning / transformation, instead of silently picking
a default.

Each detector is a small pure function: it receives the active dataframe
(and, optionally, the inferred schema) and returns zero or more
``Question`` records. The renderer in ``app.py`` shows them as a stacked
panel at the top of the Cleaning section and inside the Transform
expander.

The set of detectors is intentionally fixed (rule-based, not LLM):

  * ``mixed_dtypes_in_column``  — an object column where a strong
    minority of cells parse as one numeric type while the rest don't,
    indicating a real mix rather than a typo or stray junk row.
  * ``ambiguous_date_format``  — an object column whose values parse as
    dates under both DD/MM/YYYY and MM/DD/YYYY interpretations.
  * ``multi_currency_in_column`` — a single column carrying values in
    more than one currency (e.g. ``$120`` and ``EUR 90``).
  * ``hijri_dates_flagged``     — an upstream cleaning step has tagged a
    column as Hijri / non-Gregorian; surface so the user picks an
    explicit policy (convert vs leave as text).
  * ``near_duplicate_rows``     — pairs of rows that match on ≥ 95% of
    columns but aren't byte-identical, suggesting the same entity
    recorded twice with small variations.

Every question carries a stable ``id`` derived from the dataset key and
question kind/target, so the UI can mark answered questions and stop
re-rendering them after the user has decided.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Public types
# --------------------------------------------------------------------------

@dataclass
class QuestionOption:
    """A single button the user can pick to answer a question."""
    label: str            # button label shown in the UI
    action: str           # handler key — see ANSWER_HANDLERS below
    payload: dict = field(default_factory=dict)
    is_default: bool = False


@dataclass
class Question:
    id: str               # stable per (dataset, kind, target)
    kind: str             # e.g. "mixed_dtypes", "ambiguous_date"
    prompt: str           # one-line headline
    context: str          # short explanatory line
    options: list[QuestionOption]
    target_column: Optional[str] = None
    severity: str = "info"  # "info" | "warn" | "high"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind,
            "prompt": self.prompt, "context": self.context,
            "target_column": self.target_column,
            "severity": self.severity,
            "options": [
                {"label": o.label, "action": o.action,
                 "payload": o.payload, "is_default": o.is_default}
                for o in self.options
            ],
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"^[+-]?\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?$|^[+-]?\d+\.\d+$|^[+-]?\d+$")
_CURRENCY_TOKEN_RE = re.compile(
    r"(?P<sym>[$€£¥₪₺₩₽﷼])|(?P<code>\b(?:USD|EUR|GBP|SAR|AED|JPY|CNY|"
    r"KWD|QAR|BHD|OMR|JOD|EGP|ILS|TRY)\b)"
)
_DATE_DDMM_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\s*$")


def _qid(ds_key: str, kind: str, target: str = "") -> str:
    """Stable, dataset-scoped question id used as session-state key."""
    raw = f"{ds_key}::{kind}::{target}".encode()
    return hashlib.md5(raw).hexdigest()[:16]


def _stringy_sample(series: pd.Series, n: int = 200) -> pd.Series:
    """Trimmed string sample with junk/null tokens dropped."""
    s = series.dropna()
    if s.empty:
        return s
    s = s.astype(str).str.strip()
    s = s[s.ne("") & ~s.str.lower().isin({"nan", "null", "none", "n/a", "na", "-"})]
    if len(s) > n:
        s = s.head(n)
    return s


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------

def _detect_mixed_dtypes(df: pd.DataFrame, ds_key: str) -> list[Question]:
    """Object column with both numeric and non-numeric values above a
    noise floor. We deliberately ignore columns where the non-numeric
    share is tiny (< 8%) — those are typo rows the cleaner already
    handles. Targets the case where the mix is intentional ambiguity
    (e.g. "Pending" mixed in with prices)."""
    out: list[Question] = []
    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_object_dtype(s):
            continue
        sample = _stringy_sample(s)
        if len(sample) < 20:
            continue
        is_num = sample.str.match(_NUMERIC_RE, na=False)
        num_share = float(is_num.mean())
        # Mix is interesting when 25-92% of values are numeric — outside
        # that band the column is "basically numeric with garbage" or
        # "basically text", neither of which deserves a question.
        if not (0.25 <= num_share <= 0.92):
            continue
        non_num_examples = sample[~is_num].head(3).tolist()
        out.append(Question(
            id=_qid(ds_key, "mixed_dtypes", col),
            kind="mixed_dtypes",
            target_column=col,
            severity="warn",
            prompt=f"Column `{col}` mixes numbers and text — how should I treat it?",
            context=(f"{int(num_share * 100)}% of values look numeric; the rest are "
                     f"text such as: {', '.join(repr(x) for x in non_num_examples)}."),
            options=[
                QuestionOption(
                    label="Coerce to number (text → blank)",
                    action="cast_column", is_default=True,
                    payload={"column": col, "target_type": "decimal"},
                ),
                QuestionOption(
                    label="Keep as text",
                    action="record_decision",
                    payload={"column": col, "decision": "keep_as_text"},
                ),
                QuestionOption(
                    label="Drop this column",
                    action="drop_column",
                    payload={"column": col},
                ),
                QuestionOption(label="Skip", action="skip"),
            ],
        ))
    return out


def _detect_ambiguous_dates(df: pd.DataFrame, ds_key: str) -> list[Question]:
    """An object column where most values match the ``\\d{1,2}/\\d{1,2}/\\d{2,4}``
    shape AND have at least one row where the first part is > 12 (so
    we know which interpretation is which) — but ALSO at least one
    row where the second part is > 12. That's the only situation where
    the format is genuinely ambiguous; otherwise one interpretation is
    forced by the data itself."""
    out: list[Question] = []
    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_object_dtype(s):
            continue
        sample = _stringy_sample(s)
        if len(sample) < 10:
            continue
        matches = sample.str.match(_DATE_DDMM_RE, na=False)
        if matches.mean() < 0.7:
            continue
        first_parts: list[int] = []
        second_parts: list[int] = []
        for v in sample[matches].head(200):
            m = _DATE_DDMM_RE.match(v)
            if not m:
                continue
            try:
                first_parts.append(int(m.group(1)))
                second_parts.append(int(m.group(2)))
            except ValueError:
                continue
        if not first_parts:
            continue
        first_over_12 = any(p > 12 for p in first_parts)
        second_over_12 = any(p > 12 for p in second_parts)
        # Ambiguous only when neither side is forced. If first > 12
        # appears we already know it's DD/MM; if second > 12 appears
        # alone we already know MM/DD.
        if first_over_12 == second_over_12 and (first_over_12 is False):
            out.append(Question(
                id=_qid(ds_key, "ambiguous_date", col),
                kind="ambiguous_date",
                target_column=col,
                severity="warn",
                prompt=f"Column `{col}` has dates I can't read both ways the same.",
                context=(f"Every value fits both DD/MM/YYYY and MM/DD/YYYY — "
                         f"e.g. `{sample[matches].iloc[0]}`. Which is it?"),
                options=[
                    QuestionOption(
                        label="DD/MM/YYYY (European)",
                        action="cast_column", is_default=True,
                        payload={"column": col, "target_type": "date",
                                 "date_order": "DMY"},
                    ),
                    QuestionOption(
                        label="MM/DD/YYYY (US)",
                        action="cast_column",
                        payload={"column": col, "target_type": "date",
                                 "date_order": "MDY"},
                    ),
                    QuestionOption(label="Keep as text", action="record_decision",
                                   payload={"column": col, "decision": "keep_text"}),
                    QuestionOption(label="Skip", action="skip"),
                ],
            ))
    return out


def _detect_multi_currency(df: pd.DataFrame, schema, ds_key: str) -> list[Question]:
    """One currency column carrying more than one distinct currency."""
    out: list[Question] = []
    schema_by_col: dict[str, Any] = {}
    if schema:
        for s in schema:
            col = s.get("column") if isinstance(s, dict) else getattr(s, "column", None)
            t = (s.get("inferred_type") if isinstance(s, dict)
                 else getattr(s, "inferred_type", "")) or ""
            if col:
                schema_by_col[col] = t
    for col in df.columns:
        s = df[col]
        if not pd.api.types.is_object_dtype(s):
            # Schema-flagged currency columns are usually still object;
            # numeric ones can't carry currency markers, so skip them.
            continue
        # Only look at columns the schema thinks are currency, OR where
        # name strongly hints at money.
        is_currency = (schema_by_col.get(col, "").lower() == "currency")
        name_hints_money = any(h in str(col).lower()
                               for h in ("price", "amount", "cost", "salary",
                                         "revenue", "balance", "total", "سعر"))
        if not (is_currency or name_hints_money):
            continue
        sample = _stringy_sample(s)
        if len(sample) < 10:
            continue
        tokens: dict[str, int] = {}
        for v in sample:
            for m in _CURRENCY_TOKEN_RE.finditer(v):
                tok = m.group("sym") or m.group("code")
                if tok:
                    tokens[tok] = tokens.get(tok, 0) + 1
        if len(tokens) < 2:
            continue
        # Stable order for the prompt — biggest first.
        ordered = sorted(tokens.items(), key=lambda kv: kv[1], reverse=True)
        total = sum(tokens.values())
        breakdown = ", ".join(f"{tok} ({int(n / total * 100)}%)"
                              for tok, n in ordered[:4])
        primary = ordered[0][0]
        out.append(Question(
            id=_qid(ds_key, "multi_currency", col),
            kind="multi_currency",
            target_column=col,
            severity="warn",
            prompt=f"Column `{col}` has more than one currency.",
            context=f"Currency tokens detected: {breakdown}.",
            options=[
                QuestionOption(
                    label=f"Treat all as {primary}",
                    action="record_decision", is_default=True,
                    payload={"column": col, "decision": f"treat_as_{primary}"},
                ),
                QuestionOption(
                    label="Split by currency into separate columns",
                    action="record_decision",
                    payload={"column": col, "decision": "split_by_currency"},
                ),
                QuestionOption(
                    label="Drop this column",
                    action="drop_column",
                    payload={"column": col},
                ),
                QuestionOption(label="Skip", action="skip"),
            ],
        ))
    return out


def _detect_hijri_dates(df: pd.DataFrame, schema, ds_key: str) -> list[Question]:
    """Surface Hijri/non-Gregorian columns flagged earlier in the pipeline.

    The cleaner / type inference attaches a ``calendar`` note or sets
    ``inferred_type`` to ``"date_hijri"`` when it sees Umm al-Qura / Hijri
    dates. We don't try to detect these afresh here — we just react to
    the schema flag so the user picks an explicit policy."""
    out: list[Question] = []
    if not schema:
        return out
    for s in schema:
        col = s.get("column") if isinstance(s, dict) else getattr(s, "column", None)
        t = (s.get("inferred_type") if isinstance(s, dict)
             else getattr(s, "inferred_type", "")) or ""
        notes = (s.get("notes") if isinstance(s, dict)
                 else getattr(s, "notes", "")) or ""
        if not col or col not in df.columns:
            continue
        is_hijri = (t.lower() == "date_hijri") or ("hijri" in notes.lower())
        if not is_hijri:
            continue
        out.append(Question(
            id=_qid(ds_key, "hijri_dates", col),
            kind="hijri_dates",
            target_column=col,
            severity="info",
            prompt=f"Column `{col}` looks like Hijri dates.",
            context="What should I do with the non-Gregorian dates?",
            options=[
                QuestionOption(
                    label="Convert to Gregorian (best effort)",
                    action="record_decision", is_default=True,
                    payload={"column": col, "decision": "convert_to_gregorian"},
                ),
                QuestionOption(
                    label="Keep as text", action="record_decision",
                    payload={"column": col, "decision": "keep_as_text"},
                ),
                QuestionOption(label="Skip", action="skip"),
            ],
        ))
    return out


def _detect_near_duplicates(df: pd.DataFrame, ds_key: str) -> list[Question]:
    """Pairs of rows matching on ≥ 95% of columns but not byte-identical.

    Strict deduplication is already handled by ``remove_duplicates`` —
    this surfaces the *near* matches the cleaner won't touch. We sample
    up to 5,000 rows to keep this O(n) on big frames."""
    if len(df) < 4 or len(df.columns) < 3:
        return []
    sample = df.head(5000).reset_index(drop=True)
    # Compare raw stringified cells — no strip / lowercase. Whitespace
    # and casing differences are exactly the kind of "near but not
    # identical" we want to surface so the user can decide whether to
    # normalize-then-dedupe.
    norm = sample.astype(str)
    n_cols = len(norm.columns)
    # 95% of columns must match; we also cap so the rule degenerates to
    # "differ in exactly one column" on narrow tables where 95% rounds
    # up to the full width and makes the condition unsatisfiable.
    threshold = min(int(n_cols * 0.95), n_cols - 1)
    if threshold < 1:
        return []
    # Direct pairwise scan with a hard cap so the worst case stays
    # bounded even on the 5,000-row sample. We stop as soon as we have
    # enough evidence to surface the question — the user only needs to
    # know it's happening, not the full count.
    rows = norm.values
    n = len(rows)
    near_pairs = 0
    matched_j: set[int] = set()
    cap = min(n, 400)
    for i in range(cap):
        if near_pairs >= 25:
            break
        for j in range(i + 1, n):
            if j in matched_j:
                continue
            matches = int(np.sum(rows[i] == rows[j]))
            if threshold <= matches < n_cols:
                near_pairs += 1
                matched_j.add(j)
                if near_pairs >= 25:
                    break
    if near_pairs == 0:
        return []
    return [Question(
        id=_qid(ds_key, "near_duplicates", "_rows"),
        kind="near_duplicates",
        target_column=None,
        severity="warn",
        prompt="I found rows that look like duplicates with small differences.",
        context=(f"At least {near_pairs} pair(s) of rows match on ≥ 95% of columns "
                 f"but aren't byte-identical (e.g. trailing spaces, casing)."),
        options=[
            QuestionOption(
                label="Normalize then re-deduplicate",
                action="insert_substep", is_default=True,
                payload={"substep_key": "trim_whitespace"},
            ),
            QuestionOption(
                label="Keep them — they're really different",
                action="record_decision",
                payload={"decision": "keep_near_duplicates"},
            ),
            QuestionOption(label="Skip", action="skip"),
        ],
    )]


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def detect_questions(
    df: pd.DataFrame,
    schema: Optional[Iterable] = None,
    ds_key: str = "default",
) -> list[Question]:
    """Run every detector and return the combined question list.

    The function is pure — it never touches Streamlit state. Callers
    are responsible for filtering out questions whose ids appear in
    their answered/skipped set.
    """
    if df is None or df.empty:
        return []
    qs: list[Question] = []
    qs.extend(_detect_mixed_dtypes(df, ds_key))
    qs.extend(_detect_ambiguous_dates(df, ds_key))
    qs.extend(_detect_multi_currency(df, schema, ds_key))
    qs.extend(_detect_hijri_dates(df, schema, ds_key))
    qs.extend(_detect_near_duplicates(df, ds_key))
    # High-severity first so the most important doubts surface at the top
    # of the panel even when the panel scrolls.
    qs.sort(key=lambda q: {"high": 0, "warn": 1, "info": 2}.get(q.severity, 3))
    return qs


# --------------------------------------------------------------------------
# Answer handlers — small mappers from a chosen option to a Step record
# --------------------------------------------------------------------------

# Each handler returns a dict the UI inserts into the cleaning plan
# (alongside the answered-question record), or ``None`` to indicate
# "no plan change, just remember the answer".
def resolve_answer(question: "Question", option: "QuestionOption") -> Optional[dict]:
    """Translate a chosen option into a substep insertion request, or
    ``None`` for record-only decisions.

    The returned dict, when present, has the shape:
        {"substep_key": <str>, "params": <dict>}
    """
    a = option.action
    p = option.payload or {}
    if a == "skip":
        return None
    if a == "drop_column":
        return {"substep_key": "drop_column", "params": {"column": p["column"]}}
    if a == "insert_substep":
        return {"substep_key": p["substep_key"], "params": p.get("params", {})}
    if a == "record_decision":
        # No concrete transform — emit a Record Decision step so the
        # answer is still visible and reversible from Applied Steps.
        return {"substep_key": "record_decision",
                "params": {"column": p.get("column"),
                           "decision": p.get("decision") or option.label}}
    if a == "cast_column":
        # No generic 'cast column' substep exists in the registry yet
        # (the Changed Type panel handles casts explicitly). Per the
        # task spec — "if none exists, store the decision and surface a
        # TODO step rather than crashing" — we emit a Record Decision
        # step carrying the desired column + target type so the answer
        # appears in Applied Steps.
        decision = f"cast → {p.get('target_type', '?')}"
        if p.get("date_order"):
            decision += f" ({p['date_order']})"
        return {"substep_key": "record_decision",
                "params": {"column": p.get("column"),
                           "decision": decision,
                           "note": "TODO: apply via Changed Type"}}
    return None
