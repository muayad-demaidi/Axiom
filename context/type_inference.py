"""Power Query-style automatic data type inference.

For each column we score it against a set of candidate types and pick the
most likely one. The output is consumable by the cleaner (to actually
cast values) and by the UI (to show the user the inferred schema with a
confidence score, just like Power Query's "Detected Types" step).

Detected types:
    integer, decimal, currency, percentage,
    date, datetime, time,
    boolean, text, id, categorical, empty
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Regexes & lookup tables
# --------------------------------------------------------------------------

_BOOL_TRUE = {"true", "false", "yes", "no", "y", "n", "0", "1",
              "نعم", "لا", "صح", "خطأ"}
# Empty/missing-value markers — these are *expected* sparse cells and
# get classified as ``null_token`` so they don't trip the validation
# gate.  An optional surcharge column where 90% of rows are blank is
# fine; only truly broken rows should hurt parse-success.
_NULL_TOKENS = {"", "nan", "na", "n/a", "null", "none", "-", "--", "?",
                "missing", "unknown"}
# Spreadsheet/system error markers — distinct from missing values.
# These signal a known fault upstream and get classified as
# ``unparseable`` so the validation gate flags the column.
_ERROR_TOKENS = {"error", "err", "#n/a", "#error", "#null!", "#div/0!",
                 "#value!", "#ref!", "#name?", "#num!"}
# Backwards-compatibility alias used by callers that just want "is this
# token non-numeric junk of any kind" without caring about the
# null-vs-error distinction.
_JUNK_TOKENS = _NULL_TOKENS | _ERROR_TOKENS
_CURRENCY_SYMBOLS = "$€£¥₪₺₩₽﷼"
_CURRENCY_CODES = {"USD", "EUR", "GBP", "SAR", "AED", "JPY", "CNY",
                   "KWD", "QAR", "BHD", "OMR", "JOD", "EGP", "ILS", "TRY"}
_RE_CURRENCY_TOKEN = re.compile(
    rf"(?P<sym>[{re.escape(_CURRENCY_SYMBOLS)}])|(?P<code>\b[A-Z]{{3}}\b)"
)

_RE_INT = re.compile(r"^[+-]?\d{1,3}(?:[,\s]?\d{3})*$|^[+-]?\d+$")
_RE_DEC = re.compile(r"^[+-]?\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?$|^[+-]?\d+\.\d+$|^[+-]?\.\d+$")
_RE_PCT = re.compile(r"^[+-]?\d+(?:\.\d+)?\s*%$")
_RE_CURR = re.compile(
    rf"^\s*(?:[{re.escape(_CURRENCY_SYMBOLS)}]|[A-Z]{{3}})?\s*"
    rf"[+-]?\d{{1,3}}(?:[,\s]?\d{{3}})*(?:\.\d+)?"
    rf"\s*(?:[{re.escape(_CURRENCY_SYMBOLS)}]|[A-Z]{{3}})?\s*$"
)
_RE_TIME = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm])?$")
_RE_DATETIME_HINT = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[ T]\d{1,2}:\d{2}")
_RE_DATE_HINT = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|^\d{8}$")

_NAME_HINTS_DATE = ("date", "dob", "birth", "created", "updated",
                    "تاريخ", "ميلاد", "إنشاء")
_NAME_HINTS_TIME = ("time", "hour", "وقت")
_NAME_HINTS_PCT = ("rate", "ratio", "pct", "percent", "نسبة", "معدل")
_NAME_HINTS_CURR = ("price", "cost", "amount", "salary", "revenue",
                    "balance", "total", "سعر", "تكلفة", "مبلغ", "راتب")
_NAME_HINTS_ID = ("id", "code", "sku", "ref", "رقم", "كود")


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------

@dataclass
class ColumnType:
    column: str
    inferred_type: str
    confidence: float
    sample_values: list
    notes: str = ""
    currency_code: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = round(float(self.confidence), 3)
        return d


# --------------------------------------------------------------------------
# Scorers
# --------------------------------------------------------------------------

def _strip(v: str) -> str:
    return str(v).strip()


def _score_against(values: pd.Series, predicate) -> float:
    if values.empty:
        return 0.0
    hits = sum(1 for v in values if predicate(v))
    return hits / len(values)


def _is_int(v: str) -> bool:
    return bool(_RE_INT.match(_strip(v)))


def _is_dec(v: str) -> bool:
    """A 'decimal' covers any well-formed number (integer or fractional). The
    integer/decimal split is decided downstream by a tie-break — this lets a
    column with a mix of '4886' and '3534.86' score as numeric overall."""
    s = _strip(v)
    return bool(_RE_DEC.match(s) or _RE_INT.match(s))


def _is_pct(v: str) -> bool:
    return bool(_RE_PCT.match(_strip(v)))


def _is_curr(v: str) -> bool:
    s = _strip(v)
    if not s:
        return False
    has_symbol = any(sym in s for sym in _CURRENCY_SYMBOLS)
    has_code = any(code in s.upper().split() for code in _CURRENCY_CODES)
    if not (has_symbol or has_code):
        return False
    return bool(_RE_CURR.match(s))


def _is_time(v: str) -> bool:
    return bool(_RE_TIME.match(_strip(v)))


def _is_bool(v: str) -> bool:
    return _strip(v).lower() in _BOOL_TRUE


def _is_datetime_str(v: str) -> bool:
    return bool(_RE_DATETIME_HINT.search(_strip(v)))


def _is_date_str(v: str) -> bool:
    s = _strip(v)
    if _RE_DATETIME_HINT.search(s):
        return False
    return bool(_RE_DATE_HINT.search(s))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _is_junk(v) -> bool:
    try:
        if v is None:
            return True
        s = str(v).strip().lower()
        return s in _JUNK_TOKENS
    except Exception:
        return False


def _dominant_currency_token(values) -> Optional[str]:
    """Return the most common currency symbol or ISO code seen in the values.
    Symbols (e.g. '$', '€') are preferred when present; otherwise an ISO code
    such as 'USD' is returned. Returns ``None`` when no marker is detected."""
    from collections import Counter
    counts: Counter = Counter()
    for v in values:
        s = str(v)
        for m in _RE_CURRENCY_TOKEN.finditer(s):
            tok = m.group("sym")
            if tok:
                counts[tok] += 1
            else:
                code = m.group("code")
                if code and code in _CURRENCY_CODES:
                    counts[code] += 1
    if not counts:
        return None
    # Prefer a symbol over an ISO code when both occur: symbols render more
    # compactly in the preview ("€ 1234.50" vs "1234.50 EUR"). Within each
    # group we still pick the most frequent token.
    sym_counts = {k: v for k, v in counts.items() if k in _CURRENCY_SYMBOLS}
    if sym_counts:
        return max(sym_counts, key=sym_counts.get)
    return counts.most_common(1)[0][0]


def infer_column_type(series: pd.Series, name_hint: str = "") -> ColumnType:
    """Infer the most likely Power Query-style type for a single column."""
    name_l = (name_hint or series.name or "").lower() if hasattr(series, "name") else ""
    raw = series.dropna()
    if not raw.empty and raw.dtype == object:
        raw = raw[~raw.map(_is_junk)]
    sample_values = [str(x) for x in raw.head(5).tolist()]

    if raw.empty:
        return ColumnType(str(series.name), "empty", 1.0, [], "Column is empty")

    # Already-typed pandas dtypes win immediately
    if pd.api.types.is_datetime64_any_dtype(series):
        kind = "datetime" if (raw.dt.time != pd.Timestamp("00:00:00").time()).any() else "date"
        return ColumnType(str(series.name), kind, 1.0, sample_values, "Native datetime dtype")
    if pd.api.types.is_bool_dtype(series):
        return ColumnType(str(series.name), "boolean", 1.0, sample_values, "Native bool dtype")
    if pd.api.types.is_integer_dtype(series):
        nunique = series.nunique(dropna=True)
        if any(h in name_l for h in _NAME_HINTS_ID) and nunique == series.dropna().shape[0]:
            return ColumnType(str(series.name), "id", 1.0, sample_values, "Unique integer ID")
        return ColumnType(str(series.name), "integer", 1.0, sample_values, "Native int dtype")
    if pd.api.types.is_float_dtype(series):
        if any(h in name_l for h in _NAME_HINTS_PCT):
            return ColumnType(str(series.name), "percentage", 0.95, sample_values, "Float + name hint")
        if any(h in name_l for h in _NAME_HINTS_CURR):
            return ColumnType(str(series.name), "currency", 0.9, sample_values,
                              "Float + name hint",
                              currency_code=_dominant_currency_token(sample_values))
        return ColumnType(str(series.name), "decimal", 1.0, sample_values, "Native float dtype")

    # Object / string columns — score against each candidate
    str_vals = raw.astype(str).head(200)

    scores = {
        "boolean":    _score_against(str_vals, _is_bool),
        "percentage": _score_against(str_vals, _is_pct),
        "currency":   _score_against(str_vals, _is_curr),
        "integer":    _score_against(str_vals, _is_int),
        "decimal":    _score_against(str_vals, _is_dec),
        "datetime":   _score_against(str_vals, _is_datetime_str),
        "date":       _score_against(str_vals, _is_date_str),
        "time":       _score_against(str_vals, _is_time),
    }

    # Apply name-hint boosts (small, never override a strong signal)
    if any(h in name_l for h in _NAME_HINTS_DATE):
        scores["date"] = min(1.0, scores["date"] + 0.15)
        scores["datetime"] = min(1.0, scores["datetime"] + 0.10)
    if any(h in name_l for h in _NAME_HINTS_TIME):
        scores["time"] = min(1.0, scores["time"] + 0.15)
    if any(h in name_l for h in _NAME_HINTS_PCT):
        scores["percentage"] = min(1.0, scores["percentage"] + 0.15)
    if any(h in name_l for h in _NAME_HINTS_CURR):
        scores["currency"] = min(1.0, scores["currency"] + 0.15)

    best = max(scores, key=scores.get)
    best_score = scores[best]

    # Numeric tie-break: integer beats decimal only if (almost) all values fit int
    if best == "decimal" and scores["integer"] >= 0.95:
        best = "integer"
        best_score = scores["integer"]

    if best_score < 0.70:
        # Categorical vs free text
        nunique = raw.nunique()
        ratio = nunique / len(raw)
        if nunique <= 25 and ratio < 0.5:
            return ColumnType(str(series.name), "categorical",
                              round(1.0 - ratio, 3), sample_values,
                              f"{nunique} unique values")
        if any(h in name_l for h in _NAME_HINTS_ID) and ratio > 0.95:
            return ColumnType(str(series.name), "id", 0.9, sample_values, "High-cardinality identifier")
        return ColumnType(str(series.name), "text", 1.0, sample_values, "Free-form text")

    cur = _dominant_currency_token(str_vals) if best == "currency" else None
    return ColumnType(str(series.name), best, best_score, sample_values,
                      "Pattern match", currency_code=cur)


def infer_schema(df: pd.DataFrame) -> list[ColumnType]:
    """Run inference on every column. Returns a list of ColumnType."""
    return [infer_column_type(df[c], name_hint=str(c)) for c in df.columns]


def schema_to_dataframe(schema: list[ColumnType]) -> pd.DataFrame:
    """For showing the inferred schema in the UI as a table."""
    if not schema:
        return pd.DataFrame(columns=["column", "inferred_type", "confidence", "sample_values", "notes"])
    rows = [s.to_dict() for s in schema]
    out = pd.DataFrame(rows)
    out["sample_values"] = out["sample_values"].apply(lambda xs: ", ".join(map(str, xs[:3])))
    return out[["column", "inferred_type", "confidence", "sample_values", "notes"]]


# --------------------------------------------------------------------------
# Casting
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Canonical numeric parser
#
# Single deterministic entry point used by every BI consumer (aggregation,
# pivot, charts, KPIs, chat, insights).  Mixed-locale safe: a value like
# ``"1,583"`` (no decimal point) is treated as the integer 1583, not the
# decimal 1.583, because rows in the same column also carry plain decimals
# like ``3378.49`` — silently swapping the comma to a dot would give wildly
# inconsistent magnitudes.  Rules (auto / mixed_smart):
#
#   * Strip currency symbols / ISO codes / NBSPs / percent signs / parens.
#   * If the cleaned token matches a junk literal (``NaN``, ``ERROR``, ``-``…)
#     → null with status ``null_token``.
#   * Both ``,`` and ``.`` present → the rightmost one is the decimal,
#     the other is a thousands grouping (Excel rule).
#   * Only ``,`` present:
#         - if there's exactly one comma followed by 1 or 2 digits → decimal
#           comma (European style), e.g. ``"1,5"`` → 1.5
#         - otherwise treat every ``,`` as a thousands grouping, e.g.
#           ``"1,583"`` → 1583, ``"865,518"`` → 865518.
#   * Only ``.`` present:
#         - if there's exactly one dot followed by 1 or 2 digits → decimal
#         - if multiple dots, all groups of 3 → thousands dots
#         - otherwise → decimal point
#   * Negative sign anywhere is preserved (``"-1,200"`` → -1200,
#     ``"(123.45)"`` → -123.45).
#
# Explicit modes bypass the heuristics:
#   ``decimal_point``     — ``,`` is thousands, ``.`` is decimal.
#   ``decimal_comma``     — ``.`` is thousands, ``,`` is decimal.
#   ``thousands_comma``   — every ``,`` is stripped, ``.`` is decimal.
#   ``thousands_dot``     — every ``.`` is stripped, ``,`` is decimal.
#   ``mixed_smart``/``auto`` — the rules above.
# --------------------------------------------------------------------------

PARSE_MODES = (
    "auto", "mixed_smart", "decimal_point", "decimal_comma",
    "thousands_comma", "thousands_dot",
)
PARSE_STATUS_OK = "ok"
PARSE_STATUS_NULL = "null_token"
PARSE_STATUS_BAD = "unparseable"

_NBSP = "\u00a0"
_RE_PARENS_NEG = re.compile(r"^\((.+)\)$")
_RE_NON_NUMERIC = re.compile(r"[^0-9,.\-+eE]")


def _strip_currency(token: str) -> str:
    out = token
    for sym in _CURRENCY_SYMBOLS:
        out = out.replace(sym, "")
    # Strip ISO codes only when bracketed by spaces / start / end so we
    # don't eat the ``E`` of ``1e3``.
    for code in _CURRENCY_CODES:
        out = re.sub(rf"(?<![A-Za-z0-9]){code}(?![A-Za-z0-9])", "", out)
    return out


def parse_numeric_value(value: Any, mode: str = "auto") -> tuple[Optional[float], str]:
    """Parse a single value into (float|None, status).

    ``status`` is one of ``ok`` / ``null_token`` / ``unparseable`` and
    lets callers explain *why* a row was excluded.
    """
    if value is None:
        return None, PARSE_STATUS_NULL
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None, PARSE_STATUS_BAD
        if not np.isfinite(f):
            return None, PARSE_STATUS_NULL
        return f, PARSE_STATUS_OK

    s = str(value).strip().replace(_NBSP, "").replace(" ", "")
    if not s or s.lower() in _NULL_TOKENS:
        return None, PARSE_STATUS_NULL
    if s.lower() in _ERROR_TOKENS:
        return None, PARSE_STATUS_BAD

    is_neg = False
    m = _RE_PARENS_NEG.match(s)
    if m:
        is_neg = True
        s = m.group(1)
    if s.startswith("-"):
        is_neg = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]

    is_pct = False
    if s.endswith("%"):
        is_pct = True
        s = s[:-1]

    s = _strip_currency(s).strip()
    if not s or s.lower() in _NULL_TOKENS:
        return None, PARSE_STATUS_NULL
    if s.lower() in _ERROR_TOKENS:
        return None, PARSE_STATUS_BAD

    if _RE_NON_NUMERIC.search(s):
        return None, PARSE_STATUS_BAD

    m = (mode or "auto").lower()
    has_comma = "," in s
    has_dot = "." in s

    try:
        if m == "decimal_point":
            normalized = s.replace(",", "")
        elif m == "decimal_comma":
            normalized = s.replace(".", "").replace(",", ".")
        elif m == "thousands_comma":
            normalized = s.replace(",", "")
        elif m == "thousands_dot":
            normalized = s.replace(".", "").replace(",", ".")
        else:
            # mixed_smart / auto
            if has_comma and has_dot:
                if s.rfind(".") > s.rfind(","):
                    normalized = s.replace(",", "")
                else:
                    normalized = s.replace(".", "").replace(",", ".")
            elif has_comma:
                # Single comma followed by 1 or 2 digits → decimal comma
                comma_count = s.count(",")
                last = s.rsplit(",", 1)[-1]
                if comma_count == 1 and 1 <= len(last) <= 2 and last.isdigit():
                    normalized = s.replace(",", ".")
                else:
                    normalized = s.replace(",", "")
            elif has_dot:
                dot_count = s.count(".")
                last = s.rsplit(".", 1)[-1]
                head_before_last_dot = s.rsplit(".", 1)[0]
                if dot_count == 1:
                    # Mirror the comma logic so the dot-only branch is
                    # symmetric.  A single dot followed by *exactly* 3
                    # digits (and a digit head) is a thousands separator
                    # in the EU convention — "1.583" means 1583, not
                    # 1.583 — unless the user explicitly picked
                    # ``decimal_point``/``thousands_dot``.  1- or 2-digit
                    # tails stay as decimal ("123.45" → 123.45, "1.5" →
                    # 1.5).  Heads like "0.583" stay decimal because a
                    # leading zero with thousands grouping would be
                    # written as "0" with no dot.
                    if (
                        len(last) == 3
                        and last.isdigit()
                        and head_before_last_dot.isdigit()
                        and head_before_last_dot not in ("0", "")
                    ):
                        normalized = head_before_last_dot + last
                    else:
                        normalized = s
                else:
                    # Multiple dots — likely European thousands dots if every
                    # non-leading group is exactly 3 digits.
                    parts = s.split(".")
                    if all(len(p) == 3 for p in parts[1:]) and parts[0].isdigit():
                        normalized = "".join(parts)
                    else:
                        # fall back to using the rightmost dot as decimal
                        head, _, tail = s.rpartition(".")
                        normalized = head.replace(".", "") + "." + tail
            else:
                normalized = s

        f = float(normalized)
    except (TypeError, ValueError):
        return None, PARSE_STATUS_BAD
    if not np.isfinite(f):
        return None, PARSE_STATUS_NULL
    if is_neg:
        f = -f
    if is_pct:
        f = f / 100.0
    return f, PARSE_STATUS_OK


def parse_numeric_series(
    series: pd.Series, mode: str = "auto",
) -> tuple[pd.Series, pd.Series]:
    """Vectorised wrapper around :func:`parse_numeric_value`.

    Returns ``(values, statuses)`` aligned to the input index.  ``values``
    is a ``float64`` Series with NaN for any non-OK row; ``statuses`` is an
    object Series with one of the ``PARSE_STATUS_*`` constants.
    """
    if series is None or len(series) == 0:
        return pd.Series([], dtype="float64"), pd.Series([], dtype="object")

    # Fast path: already numeric, no parsing needed.  We still emit a
    # status series so callers get a uniform shape.
    #
    # Edge case: if pandas already coerced ambiguous locale strings to
    # floats during CSV ingestion (e.g. read_csv saw "1,583" with
    # ``thousands=","`` and stored 1583.0), the user's later
    # ``parse_mode`` override has no string left to reinterpret — the
    # original lexical form is gone.  In practice this does not arise
    # for AXIOM uploads because we do not pass ``thousands=`` to
    # ``read_csv``, so any locale-mixed amount column stays as
    # ``object`` dtype and reaches the slow path.  Callers who want to
    # honor a parse-mode override on already-numeric data must round-
    # trip through ``astype(str)`` first.
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        vals = series.astype("float64")
        status = pd.Series(
            np.where(vals.notna(), PARSE_STATUS_OK, PARSE_STATUS_NULL),
            index=series.index, dtype="object",
        )
        return vals, status

    parsed_values: list[Optional[float]] = []
    statuses: list[str] = []
    for v in series.tolist():
        f, st = parse_numeric_value(v, mode=mode)
        parsed_values.append(f if f is not None else np.nan)
        statuses.append(st)
    return (
        pd.Series(parsed_values, index=series.index, dtype="float64"),
        pd.Series(statuses, index=series.index, dtype="object"),
    )


def to_numeric_canonical(series: pd.Series, mode: str = "auto") -> pd.Series:
    """Drop-in replacement for ``pd.to_numeric(series, errors='coerce')``.

    Routes through the canonical parser so every BI surface (chart, pivot,
    KPI, chat, insight) interprets locale-mixed values the same way.
    """
    vals, _ = parse_numeric_series(series, mode=mode)
    return vals


def _clean_numeric(s: pd.Series) -> pd.Series:
    """Legacy helper kept for backward compat — delegates to the canonical
    parser and returns a *string* series so existing callers that still
    pipe through ``pd.to_numeric`` get the correct value."""
    vals, _ = parse_numeric_series(s)
    out = vals.astype(object).where(vals.notna(), other="")
    return out.astype(str)


def cast_column(series: pd.Series, target_type: str) -> pd.Series:
    """Coerce a single column to its inferred type. Uncoercible cells become NaN/NaT.

    Numeric branches (``integer``/``decimal``/``percentage``/``currency``)
    route through the canonical :func:`parse_numeric_series` so casts
    here see the same mixed-locale rules as aggregation/pivot/KPI/chat.
    """
    t = (target_type or "text").lower()
    try:
        if t == "integer":
            vals, _ = parse_numeric_series(series)
            return vals.astype("Int64")
        if t == "decimal":
            vals, _ = parse_numeric_series(series)
            return vals
        if t == "percentage":
            cleaned = series.astype(str).str.replace("%", "", regex=False)
            vals, _ = parse_numeric_series(cleaned)
            return vals / 100.0
        if t == "currency":
            cleaned = series.astype(str)
            for sym in _CURRENCY_SYMBOLS:
                cleaned = cleaned.str.replace(sym, "", regex=False)
            for code in _CURRENCY_CODES:
                cleaned = cleaned.str.replace(rf"\b{code}\b", "", regex=True)
            vals, _ = parse_numeric_series(cleaned)
            return vals
        if t in ("date", "datetime"):
            s = series.astype(str).str.strip()
            s = s.where(~s.str.lower().isin(_JUNK_TOKENS), other=pd.NA)
            ymd_mask = s.str.match(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", na=False)
            try:
                out = pd.to_datetime(s.where(ymd_mask), errors="coerce", format="mixed", yearfirst=True)
            except Exception:
                out = pd.to_datetime(s.where(ymd_mask), errors="coerce", yearfirst=True)
            try:
                rest = pd.to_datetime(s.where(~ymd_mask), errors="coerce", format="mixed", dayfirst=True)
            except Exception:
                rest = pd.to_datetime(s.where(~ymd_mask), errors="coerce", dayfirst=True)
            return out.fillna(rest)
        if t == "time":
            return pd.to_datetime(series, errors="coerce", format=None).dt.time
        if t == "boolean":
            mapping = {"true": True, "yes": True, "y": True, "1": True, "نعم": True, "صح": True,
                       "false": False, "no": False, "n": False, "0": False, "لا": False, "خطأ": False}
            return series.astype(str).str.strip().str.lower().map(mapping)
        return series.astype(str)
    except Exception:
        return series


def apply_schema(df: pd.DataFrame, schema: list[ColumnType]) -> pd.DataFrame:
    """Return a copy of df with every column cast to its inferred type."""
    out = df.copy()
    for s in schema:
        if s.column in out.columns and s.inferred_type not in ("text", "empty", "id", "categorical"):
            out[s.column] = cast_column(out[s.column], s.inferred_type)
    return out
