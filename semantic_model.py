"""Multi-CSV analyst copilot: profile each table, classify its role,
suggest cross-table relationships with evidence + confidence, generate
analyst-style clarification questions, and execute safe cross-table
queries that refuse to fabricate joined rows.

Pure-Python (no FastAPI / SQLAlchemy imports). The API router and
chat tools wrap these primitives. All inputs are pandas DataFrames
plus lightweight dicts, so the module is unit-testable in isolation.

Vocabulary
----------
Table role
    fact      — long, transactional, narrow grain (one row per
                event/transaction). Has FK columns into dimensions.
    dimension — descriptive lookup table (one row per entity). PK is
                stable and unique.
    summary   — pre-aggregated table (one row per period/segment). NOT
                joinable to detail rows; warn when the user tries.
    bridge    — many-to-many junction table (mostly two FK columns).

Confidence band
    high      — auto-confirm candidate (≥ 0.85, strong overlap + name +
                dtype agreement, no fan-out trap).
    medium    — propose with evidence, ask user.
    low       — surface in clarification questions only.
    inferred  — used at query time but explicitly labelled "inferred"
                in chat replies; never persisted as confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from data_modelling import (
    RelationshipSuggestion,
    suggest_relationships,
    materialize_join,
    validate_relationship,
)


# --------------------------------------------------------------------------
# Profiling
# --------------------------------------------------------------------------

_ID_HINT_TOKENS = ("id", "key", "code", "uuid", "guid", "ref", "no", "num")
_DATE_HINT_TOKENS = ("date", "month", "year", "quarter", "week", "day",
                     "time", "timestamp", "period", "fiscal")
_MEASURE_HINT_TOKENS = ("amount", "amt", "revenue", "price", "cost",
                        "qty", "quantity", "count", "total", "sum",
                        "value", "spend", "budget", "actual", "sales",
                        "profit", "margin", "kpi", "rate", "ratio",
                        "score", "balance", "fee")


def _name_has_token(name: str, tokens: Iterable[str]) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return False
    parts = []
    cur = ""
    # split on common separators + camelCase boundaries
    for ch in n:
        if ch in ("_", " ", "-", ".", "/"):
            if cur:
                parts.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    parts = parts or [n]
    for tok in tokens:
        if tok in parts:
            return True
        if n.endswith(tok) or n.startswith(tok):
            return True
    return False


def _is_datetime_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if pd.api.types.is_object_dtype(series):
        sample = series.dropna().head(50)
        if sample.empty:
            return False
        try:
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore", UserWarning)
                parsed = pd.to_datetime(sample, errors="coerce", utc=False)
            return parsed.notna().mean() >= 0.85
        except Exception:
            return False
    return False


def _column_kind(name: str, series: pd.Series, n_rows: int) -> str:
    """Classify a single column into id | date | measure | category | text."""
    if _is_datetime_like(series) or _name_has_token(name, _DATE_HINT_TOKENS):
        return "date"
    nunique = int(series.nunique(dropna=True))
    if pd.api.types.is_numeric_dtype(series):
        # If a numeric column is mostly unique it's an id; if it has a
        # measure-y name treat as measure; otherwise "measure" by default.
        if _name_has_token(name, _ID_HINT_TOKENS) and nunique >= max(5, n_rows * 0.5):
            return "id"
        if _name_has_token(name, _MEASURE_HINT_TOKENS):
            return "measure"
        return "measure"
    if pd.api.types.is_bool_dtype(series):
        return "category"
    # Object dtype
    if _name_has_token(name, _ID_HINT_TOKENS):
        return "id"
    if n_rows > 0 and nunique / max(1, n_rows) >= 0.9 and nunique >= 5:
        return "id"
    if n_rows > 0 and nunique / max(1, n_rows) <= 0.5:
        return "category"
    return "text"


def _detect_pk_candidates(df: pd.DataFrame, n_rows: int) -> list[str]:
    """Columns whose values are unique and non-null across the table.
    Composite PKs are not detected here — handled in role classification."""
    out: list[str] = []
    if n_rows == 0:
        return out
    for c in df.columns:
        s = df[c]
        try:
            non_null = int(s.notna().sum())
            uniq = int(s.nunique(dropna=True))
        except Exception:
            continue
        if non_null == n_rows and uniq == n_rows:
            out.append(str(c))
    return out


def _detect_grain(df: pd.DataFrame, n_rows: int,
                  pk_candidates: list[str],
                  column_kinds: dict[str, str]) -> dict[str, Any]:
    """Best-effort guess of the table's grain (one row per …).

    Strategy:
      • If a single column is the PK → grain = that column.
      • Else if (date_col, id_col) together are unique → composite grain.
      • Else fall back to "row"."""
    if pk_candidates:
        return {"kind": "single", "columns": pk_candidates[:1],
                "label": f"one row per {pk_candidates[0]}"}
    date_cols = [c for c, k in column_kinds.items() if k == "date"]
    id_cols = [c for c, k in column_kinds.items() if k == "id"]
    cat_cols = [c for c, k in column_kinds.items() if k == "category"]
    candidates: list[tuple[str, ...]] = []
    for d in date_cols[:2]:
        for i in id_cols[:3]:
            candidates.append((d, i))
        for cc in cat_cols[:3]:
            candidates.append((d, cc))
    for combo in candidates:
        try:
            if df[list(combo)].dropna().drop_duplicates().shape[0] == n_rows:
                label = " × ".join(combo)
                return {"kind": "composite", "columns": list(combo),
                        "label": f"one row per {label}"}
        except Exception:
            continue
    return {"kind": "row", "columns": [],
            "label": "no obvious grain (one row per record)"}


def _classify_role(name: str, df: pd.DataFrame, n_rows: int,
                   column_kinds: dict[str, str],
                   pk_candidates: list[str]) -> tuple[str, list[str]]:
    """Return (role, signals_list) where role is fact/dimension/summary/bridge."""
    n_cols = int(df.shape[1])
    id_cols = [c for c, k in column_kinds.items() if k == "id"]
    date_cols = [c for c, k in column_kinds.items() if k == "date"]
    measure_cols = [c for c, k in column_kinds.items() if k == "measure"]
    signals: list[str] = []

    name_lower = (name or "").lower()
    if any(tok in name_lower for tok in ("kpi", "summary", "agg", "rollup",
                                          "monthly", "quarterly", "weekly",
                                          "report", "dashboard")):
        signals.append(f"name '{name}' suggests pre-aggregated rollup")
        if measure_cols and n_rows < 2000:
            return "summary", signals

    if 2 <= n_cols <= 4 and len(id_cols) >= 2 and not measure_cols:
        signals.append("two id-like columns and no measures → bridge")
        return "bridge", signals

    if pk_candidates and n_rows < 5000 and len(measure_cols) <= 1:
        signals.append(f"primary key '{pk_candidates[0]}' is unique across all rows")
        return "dimension", signals

    if measure_cols and (date_cols or len(id_cols) >= 2 or n_rows >= 1000):
        signals.append(
            f"{len(measure_cols)} measure column(s) and "
            f"{len(date_cols)} date column(s) → fact"
        )
        return "fact", signals

    if pk_candidates:
        signals.append("unique primary key but no measures → dimension")
        return "dimension", signals

    signals.append("default classification (no strong signals)")
    return "fact" if n_rows >= 500 else "dimension", signals


def _suspicious_columns(df: pd.DataFrame, n_rows: int,
                        column_kinds: dict[str, str]) -> list[dict]:
    """Lightweight quality flags so the model is honest about what it
    just inferred. Each flag becomes a chip in the UI and a sentence in
    the system prompt."""
    flags: list[dict] = []
    if n_rows == 0:
        return flags
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        miss = n_rows - non_null
        if n_rows > 0 and miss / n_rows >= 0.3:
            flags.append({
                "column": str(c),
                "kind": "missingness",
                "detail": f"{miss / n_rows * 100:.0f}% missing",
            })
        if column_kinds.get(str(c)) == "id":
            try:
                uniq = int(s.nunique(dropna=True))
                if uniq < non_null and non_null > 0:
                    dup_share = (non_null - uniq) / non_null
                    if dup_share >= 0.05:
                        flags.append({
                            "column": str(c),
                            "kind": "duplicate_ids",
                            "detail": f"{dup_share * 100:.0f}% duplicate keys",
                        })
            except Exception:
                pass
    return flags[:8]


def profile_table(name: str, df: pd.DataFrame) -> dict[str, Any]:
    """Build the structured table profile used by the semantic model.

    Returns a dict with: name, rows, cols, columns (each with kind),
    pk_candidates, grain, role, role_signals, suspicious."""
    if df is None:
        return {"name": name, "rows": 0, "cols": 0, "columns": [],
                "pk_candidates": [], "grain": {"kind": "row", "columns": [],
                                               "label": "empty"},
                "role": "dimension", "role_signals": ["empty table"],
                "suspicious": [], "fk_candidates": []}
    n_rows = int(len(df))
    column_kinds: dict[str, str] = {}
    columns_info: list[dict] = []
    for c in df.columns:
        s = df[c]
        kind = _column_kind(str(c), s, n_rows)
        column_kinds[str(c)] = kind
        try:
            non_null = int(s.notna().sum())
            uniq = int(s.nunique(dropna=True))
        except Exception:
            non_null = n_rows
            uniq = 0
        columns_info.append({
            "name": str(c),
            "dtype": str(s.dtype),
            "kind": kind,
            "non_null": non_null,
            "missing": n_rows - non_null,
            "unique": uniq,
        })
    pk_candidates = _detect_pk_candidates(df, n_rows)
    grain = _detect_grain(df, n_rows, pk_candidates, column_kinds)
    role, signals = _classify_role(name, df, n_rows, column_kinds, pk_candidates)
    suspicious = _suspicious_columns(df, n_rows, column_kinds)
    fk_candidates = [c for c in df.columns
                     if column_kinds[str(c)] == "id" and str(c) not in pk_candidates]
    return {
        "name": name,
        "rows": n_rows,
        "cols": int(df.shape[1]),
        "columns": columns_info,
        "pk_candidates": pk_candidates,
        "fk_candidates": [str(c) for c in fk_candidates],
        "grain": grain,
        "role": role,
        "role_signals": signals,
        "suspicious": suspicious,
    }


# --------------------------------------------------------------------------
# Relationship proposals
# --------------------------------------------------------------------------

HIGH_BAND = 0.85
MEDIUM_BAND = 0.65
LOW_BAND = 0.45


def confidence_band(score: float, overlap: float, dtype: float) -> str:
    """Map a numeric confidence to one of high / medium / low / inferred.

    A pair only earns "high" when overlap is also strong — name/dtype
    agreement alone never auto-confirms a join."""
    if score >= HIGH_BAND and overlap >= 0.6 and dtype >= 0.9:
        return "high"
    if score >= MEDIUM_BAND:
        return "medium"
    if score >= LOW_BAND:
        return "low"
    return "inferred"


def _evidence_for(s: RelationshipSuggestion) -> list[str]:
    bits: list[str] = []
    if s.name_score >= 0.9:
        bits.append("identical column names")
    elif s.name_score >= 0.6:
        bits.append("similar column names")
    if s.dtype_score >= 0.9:
        bits.append("matching dtypes")
    elif s.dtype_score >= 0.4:
        bits.append("compatible dtypes (text↔numeric)")
    if s.overlap_score >= 0.85:
        bits.append("nearly all values overlap")
    elif s.overlap_score >= 0.55:
        bits.append("strong value overlap")
    elif s.overlap_score >= 0.25:
        bits.append("partial value overlap")
    else:
        bits.append("weak value overlap")
    bits.append(f"cardinality {s.cardinality}")
    return bits


@dataclass
class ProposedRelationship:
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: str
    confidence: float
    band: str
    evidence: list[str]
    overlap_score: float
    name_score: float
    dtype_score: float

    def to_dict(self) -> dict:
        return {
            "left_table": self.left_table,
            "left_column": self.left_column,
            "right_table": self.right_table,
            "right_column": self.right_column,
            "cardinality": self.cardinality,
            "confidence": round(float(self.confidence), 3),
            "band": self.band,
            "evidence": list(self.evidence),
            "overlap_score": round(float(self.overlap_score), 3),
            "name_score": round(float(self.name_score), 3),
            "dtype_score": round(float(self.dtype_score), 3),
        }


def propose_relationships_for_project(
    profiles: list[dict],
    frames: dict[str, pd.DataFrame],
    max_per_pair: int = 3,
) -> list[ProposedRelationship]:
    """Score every cross-table column pair and return ranked proposals.

    `profiles` is the list returned by ``profile_table`` for each table.
    `frames` maps table name → dataframe. Pairs the same table only with
    other tables (no self-join proposals)."""
    out: list[ProposedRelationship] = []
    by_name = {p["name"]: p for p in profiles}
    names = [p["name"] for p in profiles]
    for i, ln in enumerate(names):
        for rn in names[i + 1:]:
            ldf = frames.get(ln)
            rdf = frames.get(rn)
            if ldf is None or rdf is None or ldf.empty or rdf.empty:
                continue
            try:
                suggestions = suggest_relationships(
                    ldf, rdf, sample_size=1000, max_results=max_per_pair * 2,
                )
            except Exception:
                continue
            for s in suggestions[:max_per_pair]:
                band = confidence_band(s.confidence, s.overlap_score, s.dtype_score)
                evidence = _evidence_for(s)
                out.append(ProposedRelationship(
                    left_table=ln, left_column=s.left_column,
                    right_table=rn, right_column=s.right_column,
                    cardinality=s.cardinality,
                    confidence=float(s.confidence), band=band,
                    evidence=evidence,
                    overlap_score=float(s.overlap_score),
                    name_score=float(s.name_score),
                    dtype_score=float(s.dtype_score),
                ))
    out.sort(key=lambda r: r.confidence, reverse=True)
    return out


# --------------------------------------------------------------------------
# Clarification questions for the proactive question bar
# --------------------------------------------------------------------------

@dataclass
class ClarifyQuestion:
    id: str
    kind: str  # "weak_join" | "ambiguous_grain" | "summary_link" | "role_pick"
    prompt: str
    target: dict[str, Any] = field(default_factory=dict)
    options: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "prompt": self.prompt,
            "target": self.target, "options": list(self.options),
        }


def generate_clarification_questions(
    profiles: list[dict],
    proposals: list[ProposedRelationship],
) -> list[ClarifyQuestion]:
    """Decide which open questions to push into the proactive question bar.

    Rules:
      • Every "low" or "inferred" proposal becomes a weak-join question.
      • Every summary↔fact proposal raises a summary-link warning.
      • Tables whose grain is "row" (no obvious PK) ask the user to
        confirm what each row represents.
      • Tables with a default (auto-fallback) role ask the user to confirm.
    """
    out: list[ClarifyQuestion] = []
    by_name = {p["name"]: p for p in profiles}

    for idx, p in enumerate(proposals):
        left_role = (by_name.get(p.left_table) or {}).get("role")
        right_role = (by_name.get(p.right_table) or {}).get("role")
        roles = {left_role, right_role}
        if "summary" in roles and ("fact" in roles or "dimension" in roles):
            out.append(ClarifyQuestion(
                id=f"summary_link_{idx}",
                kind="summary_link",
                prompt=(
                    f"`{p.left_table}.{p.left_column}` ↔ "
                    f"`{p.right_table}.{p.right_column}` joins a summary "
                    f"table to detail rows. This usually fan-traps. Should "
                    f"I treat the summary as authoritative for its grain "
                    f"and refuse to row-join?"
                ),
                target=p.to_dict(),
                options=[
                    {"label": "Yes, keep them separate", "value": "keep_separate"},
                    {"label": "Allow inferred join (mark as inferred)", "value": "inferred_join"},
                ],
            ))
            continue
        if p.band in ("medium", "low", "inferred"):
            out.append(ClarifyQuestion(
                id=f"weak_join_{idx}",
                kind="weak_join",
                prompt=(
                    f"I'm not sure `{p.left_table}.{p.left_column}` joins to "
                    f"`{p.right_table}.{p.right_column}`. Evidence: "
                    + "; ".join(p.evidence)
                    + ". Confirm or pick a different column?"
                ),
                target=p.to_dict(),
                options=[
                    {"label": "Confirm this join", "value": "confirm"},
                    {"label": "Reject — these tables don't link", "value": "reject"},
                ],
            ))

    for p in profiles:
        grain = p.get("grain", {})
        if grain.get("kind") == "row" and p.get("rows", 0) > 0:
            out.append(ClarifyQuestion(
                id=f"grain_{p['name']}",
                kind="ambiguous_grain",
                prompt=(
                    f"What does each row of `{p['name']}` represent? I "
                    f"couldn't find a clear primary key."
                ),
                target={"table": p["name"]},
                options=[],
            ))
        signals = p.get("role_signals", [])
        if signals and "default classification" in (signals[0] or ""):
            out.append(ClarifyQuestion(
                id=f"role_{p['name']}",
                kind="role_pick",
                prompt=(
                    f"I tagged `{p['name']}` as a {p['role']} based on size "
                    f"alone. Is it really a fact, dimension, summary, or bridge?"
                ),
                target={"table": p["name"], "current_role": p["role"]},
                options=[
                    {"label": "Fact", "value": "fact"},
                    {"label": "Dimension", "value": "dimension"},
                    {"label": "Summary", "value": "summary"},
                    {"label": "Bridge", "value": "bridge"},
                ],
            ))
    return out[:12]


# --------------------------------------------------------------------------
# Safe cross-table query
# --------------------------------------------------------------------------

@dataclass
class SafeQueryResult:
    rows: list[dict]
    columns: list[str]
    used_relationships: list[dict]
    warnings: list[str]
    refusals: list[str]
    inferred_joins: list[dict]
    sql_like: str

    def to_dict(self) -> dict:
        return {
            "rows": list(self.rows),
            "columns": list(self.columns),
            "used_relationships": list(self.used_relationships),
            "warnings": list(self.warnings),
            "refusals": list(self.refusals),
            "inferred_joins": list(self.inferred_joins),
            "sql_like": self.sql_like,
        }


def _build_join_path(
    requested_tables: list[str],
    confirmed: list[dict],
    inferred: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Pick a chain of relationships that connects the requested tables.

    Performs a true breadth-first search over the relationship graph
    so we can chain through intermediate (bridge / shared-dimension)
    tables that the user didn't explicitly request. For example, if
    the user asks about ``orders`` and ``regions`` and the graph
    only has ``orders.customer_id ↔ customers.id`` and
    ``customers.region_id ↔ regions.id``, the BFS will pull both
    edges into the path even though ``customers`` wasn't requested.

    Confirmed edges are explored before inferred ones, and the BFS
    is restarted from each newly-reached requested table so we
    accumulate the union of shortest paths to all targets. Inferred
    edges that end up in the path are returned in a separate bucket
    so the caller can label the answer's provenance.
    """
    if len(requested_tables) <= 1:
        return [], []

    # Build adjacency: tables -> list of (neighbor, rel, is_inferred)
    adjacency: dict[str, list[tuple[str, dict, bool]]] = {}
    for rel in confirmed:
        lt, rt = rel.get("left_table"), rel.get("right_table")
        if not lt or not rt:
            continue
        adjacency.setdefault(lt, []).append((rt, rel, False))
        adjacency.setdefault(rt, []).append((lt, rel, False))
    for rel in inferred:
        lt, rt = rel.get("left_table"), rel.get("right_table")
        if not lt or not rt:
            continue
        adjacency.setdefault(lt, []).append((rt, rel, True))
        adjacency.setdefault(rt, []).append((lt, rel, True))

    # Use rel identity (object id) as the dedupe key so a single
    # relationship dict is never returned twice.
    used_keys: set[int] = set()
    used: list[dict] = []
    used_inferred: list[dict] = []

    def _bfs(start: str, targets: set[str]) -> list[tuple[dict, bool]]:
        if not targets or start not in adjacency:
            return []
        # Each frontier entry: (current_table, path_of_(rel,inferred))
        from collections import deque
        queue = deque([(start, [])])
        visited = {start}
        # Prefer confirmed edges first by sorting neighbors per node.
        while queue:
            node, path = queue.popleft()
            if node in targets and path:
                return path
            neighbors = sorted(adjacency.get(node, []),
                               key=lambda t: (t[2], t[0]))  # confirmed first
            for nbr, rel, inferred_flag in neighbors:
                if nbr in visited:
                    continue
                visited.add(nbr)
                queue.append((nbr, path + [(rel, inferred_flag)]))
        return []

    seen = {requested_tables[0]}
    needed = set(requested_tables[1:])

    # Greedy: repeatedly find a shortest path from any seen table to
    # any needed table, add all its edges, mark all visited tables
    # as seen. Continue until all targets reached or unreachable.
    progress = True
    while needed and progress:
        progress = False
        best_path: list[tuple[dict, bool]] = []
        best_src: str | None = None
        for src in sorted(seen):
            path = _bfs(src, needed)
            if path and (not best_path or len(path) < len(best_path)):
                best_path = path
                best_src = src
                if len(path) == 1:
                    break  # can't beat 1 hop
        if not best_path or best_src is None:
            break
        # Materialize edges in order; mark every traversed table as seen.
        cur = best_src
        for rel, inferred_flag in best_path:
            key = id(rel)
            if key not in used_keys:
                used_keys.add(key)
                (used_inferred if inferred_flag else used).append(rel)
            nxt = (rel.get("right_table")
                   if rel.get("left_table") == cur
                   else rel.get("left_table"))
            seen.add(nxt)
            needed.discard(nxt)
            cur = nxt
        progress = True

    return used, used_inferred


_AGG_FUNCS = {"sum", "mean", "avg", "count", "min", "max", "median", "nunique"}


def _resolve_agg(name: str) -> str:
    n = (name or "sum").strip().lower()
    if n == "avg":
        return "mean"
    if n in _AGG_FUNCS:
        return n
    return "sum"


def safe_query_model(
    spec: dict,
    profiles: list[dict],
    confirmed: list[dict],
    inferred: list[dict],
    frames: dict[str, pd.DataFrame],
    row_cap: int = 5000,
) -> SafeQueryResult:
    """Execute an aggregation across one or more tables with guardrails.

    `spec` shape::

        {
            "tables": ["sales_transactions", "customers"],
            "metrics": [{"table": "sales_transactions",
                         "column": "amount", "agg": "sum",
                         "alias": "revenue"}],
            "group_by": [{"table": "customers", "column": "country"}],
            "filters": [{"table": "sales_transactions",
                         "column": "status", "op": "==",
                         "value": "paid"}],
            "limit": 100
        }

    Guardrails enforced:
      • Reject join between summary and fact/dimension (refusal text).
      • Cap output rows at ``row_cap``.
      • Warn when the chosen join's overlap is < 30% (low match).
      • Warn when cardinality is N:N (fan-out).
      • Label inferred joins so the chat can prefix the answer.
    """
    by_name = {p["name"]: p for p in profiles}
    requested_tables: list[str] = []
    for t in (spec.get("tables") or []):
        if t in by_name and t not in requested_tables:
            requested_tables.append(str(t))
    if not requested_tables:
        for m in (spec.get("metrics") or []):
            t = m.get("table")
            if t in by_name and t not in requested_tables:
                requested_tables.append(str(t))
        for g in (spec.get("group_by") or []):
            t = g.get("table")
            if t in by_name and t not in requested_tables:
                requested_tables.append(str(t))

    warnings: list[str] = []
    refusals: list[str] = []

    # Refuse summary↔detail row joins outright.
    if len(requested_tables) >= 2:
        roles = {by_name[t]["role"] for t in requested_tables if t in by_name}
        if "summary" in roles and (roles & {"fact", "dimension"}):
            refusals.append(
                "Refusing to row-join a summary table with detail tables. "
                "Summary tables are pre-aggregated; joining them onto rows "
                "double-counts. Query the summary table on its own grain, "
                "or aggregate the detail table to the summary's grain first."
            )
            return SafeQueryResult(
                rows=[], columns=[], used_relationships=[],
                warnings=warnings, refusals=refusals,
                inferred_joins=[], sql_like="",
            )

    used, used_inferred = _build_join_path(requested_tables, confirmed, inferred)
    if len(requested_tables) >= 2 and not (used or used_inferred):
        refusals.append(
            f"No relationship connects {' and '.join(requested_tables)}. "
            f"Confirm a join first or rephrase the question on a single table."
        )
        return SafeQueryResult(
            rows=[], columns=[], used_relationships=[],
            warnings=warnings, refusals=refusals,
            inferred_joins=[], sql_like="",
        )

    # Materialise the joined frame.
    base_name = requested_tables[0] if requested_tables else next(iter(frames), "")
    base = frames.get(base_name)
    if base is None or base.empty:
        refusals.append(f"Table `{base_name}` is empty or missing.")
        return SafeQueryResult([], [], [], warnings, refusals, [], "")

    work = base.copy()
    join_label = base_name
    # Track tables that have been merged into `work` so we can pick
    # the correct "other side" for each subsequent join. We can NOT
    # rely on `requested_tables` membership here: with a multi-hop
    # path through an intermediary like `customers`, the relationship
    # `customers.region_id ↔ regions.id` has both sides outside of
    # `requested_tables` for an "orders ↔ regions" question, and we
    # need to know that `customers` is already in `work` to merge in
    # `regions`. Similarly the relationship may be stored with the
    # base table on the right rather than the left.
    joined_tables: set[str] = {base_name}
    used_rel_payload: list[dict] = []
    inferred_payload: list[dict] = []

    # Order the edges so each one connects to a table already in
    # `joined_tables`. _build_join_path already returns them in
    # rough traversal order, but a defensive sort keeps us safe
    # against accidental reordering.
    pending = list(used) + list(used_inferred)
    is_inferred = {id(r): (i >= len(used)) for i, r in enumerate(pending)}
    ordered: list[dict] = []
    while pending:
        progress = False
        for idx, rel in enumerate(pending):
            lt = rel.get("left_table")
            rt = rel.get("right_table")
            if lt in joined_tables or rt in joined_tables:
                ordered.append(rel)
                # Mark the not-yet-joined side so the next iteration
                # of the outer loop sees it as available.
                joined_tables.add(rt if lt in joined_tables else lt)
                pending.pop(idx)
                progress = True
                break
        if not progress:
            # Edge can't be linked into the current cluster — leave
            # it; the join loop below will warn for each leftover.
            ordered.extend(pending)
            break

    # Reset joined_tables now that we have the materialization order.
    joined_tables = {base_name}

    for rel in ordered:
        lt, lc = rel["left_table"], rel["left_column"]
        rt, rc = rel["right_table"], rel["right_column"]
        # Choose the side already merged into `work` as "this" and
        # the other side as the table to merge in next.
        if lt in joined_tables and rt not in joined_tables:
            this_col, other_table, other_col = lc, rt, rc
        elif rt in joined_tables and lt not in joined_tables:
            this_col, other_table, other_col = rc, lt, lc
        elif lt in joined_tables and rt in joined_tables:
            warnings.append(
                f"Skipping redundant edge {lt}.{lc} ↔ {rt}.{rc} "
                f"(both tables already joined)."
            )
            continue
        else:
            warnings.append(
                f"Skipping edge {lt}.{lc} ↔ {rt}.{rc}: neither side "
                f"is connected to `{join_label}` yet."
            )
            continue
        other_df = frames.get(other_table)
        if other_df is None or other_df.empty:
            warnings.append(f"Skipping join to `{other_table}` (empty).")
            continue
        # ---- Fan-trap mitigation -------------------------------------
        # When the *current* working frame is unique on the join key
        # (the "one" side) and the table we're about to merge in has
        # duplicates on its join key (the "many" side), a naive LEFT
        # JOIN inflates `work`'s rows and any SUM/MEAN over its measures
        # double-counts. We pre-aggregate the many side at the join
        # key BEFORE merging:
        #   • metric columns from the many side keep the requested agg,
        #   • columns referenced by filters / group_by take `first`,
        #   • everything else is dropped to keep the join clean.
        # This collapses the many side to one row per key so the join
        # stays 1:1 from `work`'s perspective.
        try:
            this_unique = (
                this_col in work.columns
                and work[this_col].notna().any()
                and work[this_col].nunique(dropna=True) == work[this_col].notna().sum()
            )
            other_unique = (
                other_col in other_df.columns
                and other_df[other_col].notna().any()
                and other_df[other_col].nunique(dropna=True) == other_df[other_col].notna().sum()
            )
        except Exception:
            this_unique = other_unique = False

        if this_unique and not other_unique:
            metric_aggs_for_other: dict[str, str] = {}
            for m in (spec.get("metrics") or []):
                if m.get("table") == other_table:
                    mc = m.get("column")
                    if mc and mc in other_df.columns and mc != other_col:
                        metric_aggs_for_other[mc] = _resolve_agg(
                            str(m.get("agg") or "sum")
                        )
            keep_first: set[str] = set()
            for f in (spec.get("filters") or []):
                if f.get("table") == other_table:
                    c = f.get("column")
                    if c and c in other_df.columns and c != other_col:
                        keep_first.add(c)
            for g in (spec.get("group_by") or []):
                if g.get("table") == other_table:
                    c = g.get("column")
                    if c and c in other_df.columns and c != other_col:
                        keep_first.add(c)
            agg_dict: dict[str, str] = dict(metric_aggs_for_other)
            for c in keep_first:
                if c not in agg_dict:
                    agg_dict[c] = "first"
            try:
                if agg_dict:
                    cols_needed = [other_col] + list(agg_dict.keys())
                    other_df = (
                        other_df[cols_needed]
                        .groupby(other_col, dropna=False)
                        .agg(agg_dict)
                        .reset_index()
                    )
                    warnings.append(
                        f"Pre-aggregated `{other_table}` on `{other_col}` to "
                        f"avoid a fan trap (1:N join into `{join_label}` "
                        f"would have inflated rows). Measures from "
                        f"`{other_table}` were computed BEFORE the join."
                    )
                else:
                    other_df = other_df.drop_duplicates(subset=[other_col])
                    warnings.append(
                        f"Deduplicated `{other_table}` on `{other_col}` to "
                        f"avoid a fan trap (1:N join into `{join_label}`)."
                    )
            except Exception as exc:
                warnings.append(
                    f"Fan-trap mitigation on `{other_table}` failed: {exc}; "
                    f"results may be inflated."
                )

        try:
            work = materialize_join(
                work, other_df, this_col, other_col,
                join_type="left",
                left_label=join_label.replace(" ", "_"),
                right_label=other_table.replace(" ", "_"),
            )
        except Exception as exc:
            warnings.append(f"Join {join_label}↔{other_table} failed: {exc}")
            continue
        join_label = f"{join_label}+{other_table}"
        joined_tables.add(other_table)
        if rel.get("cardinality") == "N:N":
            warnings.append(
                f"Many-to-many join {lt}.{lc} ↔ {rt}.{rc}; rows may be inflated."
            )
        overlap = float(rel.get("overlap_score", 0.0))
        if overlap and overlap < 0.3:
            warnings.append(
                f"Low value overlap ({overlap*100:.0f}%) on "
                f"{lt}.{lc} ↔ {rt}.{rc}; many rows will not match."
            )
        if rel in used:
            used_rel_payload.append(rel)
        else:
            inferred_payload.append(rel)
            warnings.append(
                f"Using inferred link `{lt}.{lc}` ↔ `{rt}.{rc}` "
                f"(not yet confirmed)."
            )

    # Apply filters.
    for f in (spec.get("filters") or []):
        col = str(f.get("column") or "")
        op = str(f.get("op") or "==")
        val = f.get("value")
        if col not in work.columns:
            warnings.append(f"Filter column `{col}` not found; skipping.")
            continue
        try:
            series = work[col]
            if op == "==":
                work = work[series == val]
            elif op == "!=":
                work = work[series != val]
            elif op == ">":
                work = work[series > val]
            elif op == ">=":
                work = work[series >= val]
            elif op == "<":
                work = work[series < val]
            elif op == "<=":
                work = work[series <= val]
            elif op in ("in",):
                vals = val if isinstance(val, (list, tuple, set)) else [val]
                work = work[series.isin(list(vals))]
            elif op in ("contains",):
                work = work[series.astype(str).str.contains(str(val), case=False, na=False)]
            else:
                warnings.append(f"Unknown filter op `{op}`; skipping.")
        except Exception as exc:
            warnings.append(f"Filter on `{col}` failed: {exc}")

    # Compute aggregation.
    metrics = spec.get("metrics") or []
    group_cols_raw = spec.get("group_by") or []
    group_cols: list[str] = []
    for g in group_cols_raw:
        c = str(g.get("column") or "")
        if c and c in work.columns and c not in group_cols:
            group_cols.append(c)

    if metrics:
        agg_map: dict[str, list[str]] = {}
        rename_map: dict[tuple[str, str], str] = {}
        for m in metrics:
            col = str(m.get("column") or "")
            if not col or col not in work.columns:
                warnings.append(f"Metric column `{col}` not found; skipping.")
                continue
            agg = _resolve_agg(str(m.get("agg") or "sum"))
            agg_map.setdefault(col, []).append(agg)
            alias = str(m.get("alias") or f"{agg}_{col}")
            rename_map[(col, agg)] = alias
        if not agg_map:
            refusals.append("No usable metrics provided.")
            return SafeQueryResult([], [], used_rel_payload, warnings, refusals,
                                   inferred_payload, "")
        try:
            if group_cols:
                grp = work.groupby(group_cols, dropna=False).agg(agg_map)
            else:
                grp = work.agg(agg_map)
                if isinstance(grp, pd.Series):
                    grp = grp.to_frame().T
            # Flatten MultiIndex columns and rename per alias.
            if isinstance(grp.columns, pd.MultiIndex):
                grp.columns = [
                    rename_map.get((c[0], c[1]), f"{c[1]}_{c[0]}")
                    for c in grp.columns
                ]
            else:
                grp.columns = [
                    rename_map.get((c, agg_map[c][0]), f"{agg_map[c][0]}_{c}")
                    for c in grp.columns
                ]
            if group_cols:
                grp = grp.reset_index()
            out_df = grp
        except Exception as exc:
            refusals.append(f"Aggregation failed: {exc}")
            return SafeQueryResult([], [], used_rel_payload, warnings, refusals,
                                   inferred_payload, "")
    else:
        # No metrics: just project the requested columns (or first 25).
        proj_cols = group_cols or list(work.columns)[:25]
        out_df = work[proj_cols].copy()

    # Sort by first numeric metric desc for readability.
    numeric_cols = out_df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        try:
            out_df = out_df.sort_values(numeric_cols[0], ascending=False)
        except Exception:
            pass

    # Apply limit.
    limit = int(spec.get("limit") or 100)
    limit = max(1, min(limit, row_cap))
    if len(out_df) > limit:
        warnings.append(
            f"Result truncated to {limit:,} rows (had {len(out_df):,})."
        )
        out_df = out_df.head(limit)

    # Build a SQL-ish string for the explain panel.
    sql_like = _spec_to_sql_like(spec, used_rel_payload + inferred_payload)

    rows = out_df.where(out_df.notna(), None).to_dict(orient="records")
    return SafeQueryResult(
        rows=rows,
        columns=[str(c) for c in out_df.columns],
        used_relationships=used_rel_payload,
        warnings=warnings,
        refusals=refusals,
        inferred_joins=inferred_payload,
        sql_like=sql_like,
    )


def _spec_to_sql_like(spec: dict, rels: list[dict]) -> str:
    metrics = spec.get("metrics") or []
    selects = []
    for m in metrics:
        agg = _resolve_agg(str(m.get("agg") or "sum")).upper()
        col = m.get("column")
        alias = m.get("alias") or f"{agg.lower()}_{col}"
        selects.append(f"{agg}({m.get('table')}.{col}) AS {alias}")
    for g in (spec.get("group_by") or []):
        selects.append(f"{g.get('table')}.{g.get('column')}")
    select_clause = ", ".join(selects) if selects else "*"
    from_table = (spec.get("tables") or [""])[0]
    parts = [f"SELECT {select_clause}", f"FROM {from_table}"]
    for r in rels:
        parts.append(
            f"LEFT JOIN {r.get('right_table')} ON "
            f"{r.get('left_table')}.{r.get('left_column')} = "
            f"{r.get('right_table')}.{r.get('right_column')}"
        )
    filters = spec.get("filters") or []
    if filters:
        wh = " AND ".join(
            f"{f.get('table','')}.{f.get('column')} {f.get('op','==')} "
            f"{repr(f.get('value'))}" for f in filters
        )
        parts.append(f"WHERE {wh}")
    if spec.get("group_by"):
        gcols = ", ".join(f"{g.get('table')}.{g.get('column')}"
                           for g in spec["group_by"])
        parts.append(f"GROUP BY {gcols}")
    if spec.get("limit"):
        parts.append(f"LIMIT {int(spec['limit'])}")
    return " ".join(parts)


def explain_model_text(profiles: list[dict],
                       relationships: list[dict],
                       description: str | None = None) -> str:
    """Plain-language summary of the semantic model for the chat tool."""
    lines: list[str] = []
    if description:
        lines.append(f"Business description: {description.strip()}")
        lines.append("")
    lines.append(f"This project has {len(profiles)} table(s):")
    for p in profiles:
        grain = (p.get("grain") or {}).get("label") or "unknown grain"
        lines.append(
            f"  • `{p['name']}` — {p.get('role','?')} table, "
            f"{p.get('rows',0):,} rows × {p.get('cols',0)} cols, {grain}"
        )
        susp = p.get("suspicious") or []
        if susp:
            chips = ", ".join(f"{s['column']} ({s['detail']})" for s in susp[:3])
            lines.append(f"      ⚠ data quality: {chips}")
    confirmed_rels = [r for r in relationships
                      if r.get("status") == "confirmed"]
    pending_rels = [r for r in relationships
                    if r.get("status") not in ("confirmed", "rejected")]
    if confirmed_rels:
        lines.append("")
        lines.append("Confirmed joins:")
        for r in confirmed_rels:
            lines.append(
                f"  • {r['left_table']}.{r['left_column']} ↔ "
                f"{r['right_table']}.{r['right_column']} ({r.get('cardinality','?')})"
            )
    if pending_rels:
        lines.append("")
        lines.append("Proposed (not yet confirmed):")
        for r in pending_rels[:6]:
            lines.append(
                f"  • {r['left_table']}.{r['left_column']} ↔ "
                f"{r['right_table']}.{r['right_column']} "
                f"[{r.get('band','?')}, {int(round(float(r.get('confidence',0))*100))}%]"
            )
    return "\n".join(lines)
