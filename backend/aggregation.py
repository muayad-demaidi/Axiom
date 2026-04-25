"""Centralised BI aggregation engine + field metadata inference.

Single source of truth for how AXIOM aggregates a dataset for charts,
pivots, KPI cards and dashboards.  All BI surfaces (the visualize
endpoint, the chat ``make_chart`` tool, the pivot endpoint, the
dashboard endpoint) call into :func:`aggregate` instead of rolling
their own ``mean()`` defaults so chat answers, the pivot table and the
dashboard always agree on the numbers.

Two halves:

* **Field metadata inference** (:func:`infer_field_meta`) — classifies
  each column by name + dtype + cardinality and produces sensible BI
  defaults (role, default aggregation, format kind).  Additive measures
  (revenue/quantity/sessions/clicks/leads/…) default to **SUM**, IDs
  default to **none** ("Do Not Summarize"), and rate/percentage-named
  columns default to **AVG with a warning**.
* **Aggregation engine** (:func:`aggregate`) — takes a dataframe plus a
  fully-resolved BI request (rows, cols, values+aggregation, filters,
  date grain, top-N, sort) and returns a tidy dict with rows, totals,
  the resolved aggregation label per measure, plus warnings.  Supports
  Sum / Average / Count / Distinct Count / Min / Max / Median / None,
  ratio measures (``sum(numerator)/sum(denominator)``), date grouping
  (day/week/month/quarter/year) and grand/sub-totals.

Both halves are deliberately Streamlit-free + side-effect-free so the
unit tests in ``tests/`` and every BI surface can call them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Aggregations the engine accepts.  ``none`` means "do not summarize" —
# the column is treated as a raw passthrough (used for IDs, codes, etc).
AGGREGATIONS = (
    "sum", "avg", "count", "count_distinct", "min", "max", "median", "none",
)

# Friendly labels we surface back to the UI ("Sum of revenue").
AGG_LABELS = {
    "sum": "Sum",
    "avg": "Average",
    "count": "Count",
    "count_distinct": "Distinct count",
    "min": "Min",
    "max": "Max",
    "median": "Median",
    "none": "Do not summarize",
}

# Field roles drive what the column is allowed to be in a pivot.
ROLES = ("dimension", "measure", "key", "date")

# Format kinds drive how we render the value in tables / charts / KPIs.
FORMAT_KINDS = ("number", "integer", "currency", "percent", "date", "text")

# Date grains supported by ``aggregate``.
DATE_GRAINS = ("day", "week", "month", "quarter", "year")


# ---------------------------------------------------------------------------
# Heuristics for field metadata inference
# ---------------------------------------------------------------------------

# Words in a column name that strongly suggest an additive business
# measure (default aggregation = SUM).  Lower-cased, partial match.
_ADDITIVE_MEASURE_KEYWORDS = (
    "revenue", "sales", "amount", "value", "total", "subtotal", "gross", "net",
    "cost", "expense", "expenses", "spend", "spent", "budget", "profit",
    "margin_amount", "income", "deal_value", "opportunity_value", "pipeline",
    "won_amount", "lost_amount", "qty", "quantity", "units", "count",
    "sessions", "clicks", "impressions", "views", "visits", "pageviews",
    "leads", "conversions", "signups", "subscribers", "downloads",
    "orders", "transactions", "tickets", "calls", "messages", "emails",
)

# Words that indicate an ID-like / key column — never summed, never
# averaged.  Default aggregation = ``none`` (used for "Do not summarize").
_KEY_KEYWORDS = (
    "id", "uuid", "guid", "code", "sku", "ean", "isbn", "asin",
    "phone", "zip", "postal", "ip", "mac", "url", "slug",
    "account_number", "account_id", "user_id", "customer_id", "order_id",
    "product_id", "session_id", "transaction_id",
)

# Words indicating a rate / ratio / percentage column.  These should NOT
# be silently summed; default aggregation = AVG with a warning that
# averaging row-level percentages is usually wrong.
_RATE_KEYWORDS = (
    "rate", "pct", "percent", "ratio", "share", "proportion",
    "ctr", "cvr", "cpa", "cpl", "cpc", "cpm", "roas", "roi", "aov",
    "margin_pct", "growth", "churn", "retention",
)

_DATE_KEYWORDS = (
    "date", "time", "timestamp", "datetime", "month", "year", "week", "day",
    "created_at", "updated_at", "occurred_at", "started_at", "completed_at",
    "period",
)

_CURRENCY_KEYWORDS = (
    "revenue", "sales", "amount", "value", "total", "subtotal", "gross", "net",
    "cost", "expense", "spend", "spent", "budget", "profit", "income",
    "price", "fee", "rate_usd", "deal_value", "opportunity_value",
    "won_amount", "lost_amount", "pipeline",
)


def _name_has(name: str, words: Iterable[str]) -> bool:
    n = (name or "").lower()
    if not n:
        return False
    # Match either a substring or an underscore-tokenised word so
    # ``customer_id`` hits ``id`` but ``identity`` doesn't.
    tokens = set()
    for sep in ("_", "-", " ", ".", "/"):
        for piece in n.split(sep):
            tokens.add(piece)
    tokens.add(n)
    for w in words:
        wl = w.lower()
        if wl in tokens:
            return True
        if wl in n and len(wl) >= 4:
            return True
    return False


def infer_field_meta(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Classify each column and return sensible BI defaults.

    Output shape::

        {
            "revenue": {
                "role": "measure",          # dimension|measure|key|date
                "default_agg": "sum",       # sum|avg|count|count_distinct|min|max|median|none
                "format_kind": "currency",  # number|integer|currency|percent|date|text
                "precision": 2,
                "label": "Revenue",
                "description": "...",
                "visible": True,
                "sort_by": null,
                "warnings": ["..."],
                "inferred": true,
            },
            ...
        }

    The frontend's *Field settings* panel writes user overrides on top
    of this dict and persists the result on
    ``DatasetRecord.summary_stats["_axiom_field_meta"]``.
    """
    n_rows = max(1, int(len(df)))
    out: dict[str, dict[str, Any]] = {}
    for col in df.columns:
        s = df[col]
        nun = int(s.nunique(dropna=True))
        cardinality_ratio = nun / n_rows if n_rows else 0.0
        warnings: list[str] = []
        name = str(col)

        is_dt = pd.api.types.is_datetime64_any_dtype(s) or _name_has(name, _DATE_KEYWORDS)
        is_bool = pd.api.types.is_bool_dtype(s)
        is_numeric = pd.api.types.is_numeric_dtype(s) and not is_bool

        role: str
        default_agg: str
        format_kind: str
        precision = 2
        label = name.replace("_", " ").strip().title() if name else name

        if is_dt and pd.api.types.is_datetime64_any_dtype(s):
            role = "date"
            default_agg = "none"
            format_kind = "date"
            precision = 0
        elif is_dt and not is_numeric:
            role = "date"
            default_agg = "none"
            format_kind = "date"
            precision = 0
        elif is_numeric and _name_has(name, _KEY_KEYWORDS) and cardinality_ratio > 0.5:
            # Numeric but reads as an ID — refuse to sum.
            role = "key"
            default_agg = "none"
            format_kind = "integer"
            precision = 0
            warnings.append(
                "Looks like an identifier; default aggregation is "
                "'Do not summarize' (summing IDs is rarely meaningful)."
            )
        elif is_numeric and _name_has(name, _RATE_KEYWORDS):
            role = "measure"
            default_agg = "avg"
            format_kind = "percent" if "percent" in name.lower() or "pct" in name.lower() or "rate" in name.lower() else "number"
            precision = 2
            warnings.append(
                "Looks like a rate/percentage. Averaging row-level "
                "percentages is usually wrong — consider re-deriving as "
                "sum(numerator) / sum(denominator)."
            )
        elif is_numeric and _name_has(name, _ADDITIVE_MEASURE_KEYWORDS):
            role = "measure"
            default_agg = "sum"
            format_kind = "currency" if _name_has(name, _CURRENCY_KEYWORDS) else "number"
            lname = name.lower()
            if format_kind == "number" and (
                "count" in lname or "qty" in lname or "quantity" in lname
            ):
                format_kind = "integer"
                precision = 0
            else:
                precision = 2
        elif is_numeric:
            # Generic numeric — default to SUM if it looks additive
            # (small range, large count), otherwise AVG.
            role = "measure"
            default_agg = "sum" if cardinality_ratio < 0.5 else "avg"
            format_kind = "number"
            if pd.api.types.is_integer_dtype(s):
                format_kind = "integer"
                precision = 0
        elif is_bool:
            role = "dimension"
            default_agg = "count"
            format_kind = "text"
            precision = 0
        else:
            role = "dimension"
            default_agg = "count_distinct"
            format_kind = "text"
            precision = 0
            if cardinality_ratio > 0.85 and n_rows > 20:
                # Mostly unique strings — flag as a likely ID.
                role = "key"
                default_agg = "none"
                warnings.append(
                    "Almost every value is unique — looks like an "
                    "identifier."
                )

        out[name] = {
            "role": role,
            "default_agg": default_agg,
            "format_kind": format_kind,
            "precision": precision,
            "label": label,
            "description": "",
            "visible": True,
            "sort_by": None,
            "warnings": warnings,
            "inferred": True,
            "dtype": str(s.dtype),
            "unique": nun,
            "cardinality_ratio": round(cardinality_ratio, 4),
        }
    return out


def merge_field_meta(
    inferred: dict[str, dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Layer user overrides on top of the inferred defaults."""
    if not overrides:
        return inferred
    out = {k: dict(v) for k, v in inferred.items()}
    for col, ov in overrides.items():
        if col not in out:
            # Column dropped — skip, but keep the override so it
            # rematerialises if the column comes back later.
            out[col] = {**(ov or {}), "inferred": False}
            continue
        merged = dict(out[col])
        for k, v in (ov or {}).items():
            if v is None:
                continue
            merged[k] = v
        merged["inferred"] = False
        out[col] = merged
    return out


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _coerce_filter_value(series: pd.Series, value: Any) -> Any:
    """Best-effort coerce ``value`` into the dtype of ``series`` so that
    "100" matches integer 100 and "2024-01-01" matches a real datetime.
    """
    if value is None:
        return None
    if pd.api.types.is_numeric_dtype(series):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if pd.api.types.is_datetime64_any_dtype(series):
        try:
            return pd.to_datetime(value)
        except Exception:
            return value
    return value


def apply_filters(df: pd.DataFrame, filters: list[dict[str, Any]] | None) -> pd.DataFrame:
    """Apply Power BI-style filters to a dataframe.

    Each filter is a dict with at least a ``column`` and an ``op``::

        {"column": "region", "op": "in", "values": ["EMEA", "APAC"]}
        {"column": "revenue", "op": "between", "min": 100, "max": 5000}
        {"column": "date", "op": ">=", "value": "2024-01-01"}
    """
    if not filters:
        return df
    out = df
    for f in filters:
        col = f.get("column")
        op = (f.get("op") or "").lower()
        if not col or col not in out.columns:
            continue
        s = out[col]
        try:
            if op == "in":
                vals = [_coerce_filter_value(s, v) for v in (f.get("values") or [])]
                if not vals:
                    continue
                out = out[s.isin(vals)]
            elif op == "not_in":
                vals = [_coerce_filter_value(s, v) for v in (f.get("values") or [])]
                if not vals:
                    continue
                out = out[~s.isin(vals)]
            elif op == "between":
                lo = _coerce_filter_value(s, f.get("min"))
                hi = _coerce_filter_value(s, f.get("max"))
                if lo is not None:
                    out = out[s >= lo]
                if hi is not None:
                    out = out[s <= hi]
            elif op in ("=", "=="):
                out = out[s == _coerce_filter_value(s, f.get("value"))]
            elif op == "!=":
                out = out[s != _coerce_filter_value(s, f.get("value"))]
            elif op == ">":
                out = out[s > _coerce_filter_value(s, f.get("value"))]
            elif op == ">=":
                out = out[s >= _coerce_filter_value(s, f.get("value"))]
            elif op == "<":
                out = out[s < _coerce_filter_value(s, f.get("value"))]
            elif op == "<=":
                out = out[s <= _coerce_filter_value(s, f.get("value"))]
            elif op == "contains":
                v = str(f.get("value") or "")
                out = out[s.astype(str).str.contains(v, case=False, na=False)]
            elif op == "is_null":
                out = out[s.isna()]
            elif op == "not_null":
                out = out[s.notna()]
        except Exception:
            # A bad filter shouldn't crash the whole BI surface; skip it.
            continue
    return out


# ---------------------------------------------------------------------------
# Date grouping
# ---------------------------------------------------------------------------

def date_grain_series(s: pd.Series, grain: str | None) -> pd.Series:
    """Bucket a datetime series by the requested grain.

    Returns a string series so the value lands cleanly in the JSON
    payload that the frontend renders.  Falls back to the raw series if
    the grain is unknown or the column isn't datetime-like.
    """
    if grain is None or grain == "" or grain == "none":
        return s
    g = grain.lower()
    if g not in DATE_GRAINS:
        return s
    dt = pd.to_datetime(s, errors="coerce")
    if dt.notna().sum() == 0:
        return s
    if g == "day":
        return dt.dt.strftime("%Y-%m-%d")
    if g == "week":
        # ISO week — anchor to the Monday so charts read left-to-right.
        return dt.dt.to_period("W-MON").astype(str)
    if g == "month":
        return dt.dt.strftime("%Y-%m")
    if g == "quarter":
        return dt.dt.to_period("Q").astype(str)
    if g == "year":
        return dt.dt.strftime("%Y")
    return s


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

@dataclass
class MeasureSpec:
    """One measure to compute in :func:`aggregate`.

    A ratio measure is expressed by setting ``aggregation='ratio'`` and
    populating ``numerator`` / ``denominator`` (each may carry their own
    aggregation, defaulting to SUM).  Everything else uses ``column`` +
    ``aggregation``.
    """
    column: str | None = None
    aggregation: str = "sum"
    label: str | None = None
    format_kind: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    numerator_agg: str = "sum"
    denominator_agg: str = "sum"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MeasureSpec":
        return cls(
            column=d.get("column"),
            aggregation=(d.get("aggregation") or d.get("agg") or "sum").lower(),
            label=d.get("label"),
            format_kind=d.get("format_kind"),
            numerator=d.get("numerator"),
            denominator=d.get("denominator"),
            numerator_agg=(d.get("numerator_agg") or "sum").lower(),
            denominator_agg=(d.get("denominator_agg") or "sum").lower(),
        )


def _agg_key(name: str) -> str:
    return (name or "sum").lower()


def _apply_single_agg(series: pd.Series, agg: str) -> Any:
    """Apply one aggregation to a (sub-)series, returning a scalar."""
    a = _agg_key(agg)
    if a == "none":
        # "Do not summarize" — return the first value if it's a single
        # group, otherwise NaN.  This matches Power BI behaviour where
        # "do not summarize" effectively forces the column off a measure
        # well.
        return series.iloc[0] if len(series) == 1 else float("nan")
    if a == "count":
        return int(series.shape[0])
    if a == "count_distinct":
        return int(series.nunique(dropna=True))
    numeric = pd.to_numeric(series, errors="coerce")
    if a == "sum":
        return float(numeric.sum(skipna=True))
    if a == "avg":
        return float(numeric.mean(skipna=True))
    if a == "min":
        return float(numeric.min(skipna=True))
    if a == "max":
        return float(numeric.max(skipna=True))
    if a == "median":
        return float(numeric.median(skipna=True))
    return float(numeric.sum(skipna=True))


def _resolve_label(spec: MeasureSpec) -> str:
    if spec.label:
        return spec.label
    if spec.aggregation == "ratio":
        return f"{spec.numerator or 'numerator'} / {spec.denominator or 'denominator'}"
    pretty = AGG_LABELS.get(_agg_key(spec.aggregation), spec.aggregation.title())
    return f"{pretty} of {spec.column}"


def _measure_warnings(
    spec: MeasureSpec,
    field_meta: dict[str, dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if spec.aggregation == "ratio":
        for col in (spec.numerator, spec.denominator):
            if col and col not in field_meta:
                warnings.append(f"Ratio component '{col}' has no field metadata.")
        return warnings
    col = spec.column
    if not col:
        return warnings
    meta = field_meta.get(col) or {}
    role = meta.get("role")
    default_agg = meta.get("default_agg")
    fmt = meta.get("format_kind")
    a = _agg_key(spec.aggregation)
    if role == "key" and a in ("sum", "avg", "median"):
        warnings.append(
            f"`{col}` is configured as an identifier — summing/averaging "
            "an ID is rarely meaningful."
        )
    if fmt == "percent" and a == "sum":
        warnings.append(
            f"`{col}` is a percentage — summing percentages double-counts."
            " Consider re-deriving as sum(numerator)/sum(denominator)."
        )
    if fmt == "percent" and a == "avg":
        warnings.append(
            f"Averaging the row-level percentage `{col}` is usually wrong."
            " Use a ratio measure (sum of numerator / sum of denominator)"
            " for a true rate."
        )
    if default_agg and default_agg != a and not meta.get("inferred", True) is False:
        # User explicitly overrode the default — quiet info note.
        warnings.append(
            f"`{col}` defaults to {AGG_LABELS.get(default_agg, default_agg)};"
            f" you've chosen {AGG_LABELS.get(a, a)}."
        )
    return warnings


def _format_for_meta(field_meta: dict[str, dict[str, Any]], col: str | None) -> dict[str, Any]:
    if not col:
        return {"format_kind": "number", "precision": 2}
    meta = field_meta.get(col) or {}
    return {
        "format_kind": meta.get("format_kind") or "number",
        "precision": meta.get("precision", 2),
    }


def _normalise_dim_value(v: Any) -> Any:
    """Make sure a dimension value lands cleanly in JSON."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return str(v)


def aggregate(
    df: pd.DataFrame,
    *,
    rows: list[str] | None = None,
    cols: list[str] | None = None,
    measures: list[dict[str, Any] | MeasureSpec] | None = None,
    filters: list[dict[str, Any]] | None = None,
    date_grains: dict[str, str] | None = None,
    top_n: int | None = None,
    sort: list[dict[str, Any]] | None = None,
    field_meta: dict[str, dict[str, Any]] | None = None,
    include_grand_total: bool = True,
    include_subtotals: bool = False,
    drop_nulls_in_dims: bool = False,
) -> dict[str, Any]:
    """Compute a tidy aggregated result for a BI surface.

    Returns a dict with::

        {
          "rows": [{"_dims": {row1, row2, ...}, "_cols": {...}, m1: v, m2: v}],
          "row_dims": [...], "col_dims": [...],
          "measures": [{"key": str, "label": str, "aggregation": str, ...}],
          "grand_total": {m: v, ...},
          "subtotals": [{ ... }],
          "warnings": [str, ...],
          "row_count": int,         # input rows after filters
          "result_count": int,      # output cells
        }
    """
    rows = list(rows or [])
    cols = list(cols or [])
    raw_measures = list(measures or [])
    field_meta = field_meta or {}
    date_grains = date_grains or {}
    warnings: list[str] = []

    # Parse measure specs.
    parsed: list[MeasureSpec] = []
    for m in raw_measures:
        if isinstance(m, MeasureSpec):
            parsed.append(m)
        else:
            parsed.append(MeasureSpec.from_dict(m))

    # If no measures provided and we have row dims, fall back to a count
    # so the result still says something.
    if not parsed and rows:
        parsed = [MeasureSpec(column=rows[0], aggregation="count", label="Count")]

    # Apply filters first.
    work = apply_filters(df, filters)

    # Apply date grains by replacing the dim column with its bucketed
    # version.
    for col, grain in date_grains.items():
        if col in work.columns and grain:
            work = work.assign(**{col: date_grain_series(work[col], grain)})

    # Drop rows where any dim is null if requested (mirrors Power BI's
    # "Show items with no data" being off by default).
    dim_cols = [c for c in (rows + cols) if c in work.columns]
    if drop_nulls_in_dims and dim_cols:
        work = work.dropna(subset=dim_cols)

    # Validate measures and resolve labels / formats.
    measure_views: list[dict[str, Any]] = []
    for i, spec in enumerate(parsed):
        key = f"m{i}"
        is_ratio = (
            spec.aggregation == "ratio"
            or (spec.numerator is not None and spec.denominator is not None)
        )
        label = _resolve_label(spec)
        fmt: dict[str, Any]
        if is_ratio:
            fmt = {"format_kind": spec.format_kind or "percent", "precision": 2}
        else:
            fmt = _format_for_meta(field_meta, spec.column)
            if spec.format_kind:
                fmt["format_kind"] = spec.format_kind
        warnings.extend(_measure_warnings(spec, field_meta))
        measure_views.append(
            {
                "key": key,
                "label": label,
                "aggregation": "ratio" if is_ratio else _agg_key(spec.aggregation),
                "column": spec.column,
                "numerator": spec.numerator,
                "denominator": spec.denominator,
                "format_kind": fmt["format_kind"],
                "precision": fmt["precision"],
                "spec": spec,
            }
        )

    # Compute one cell per (row dims, col dims) tuple.
    result_rows: list[dict[str, Any]] = []
    grand_total: dict[str, Any] = {}

    if not dim_cols:
        # No dims → single-row scalar result (KPI).
        cell = {"_dims": {}, "_cols": {}}
        for mv in measure_views:
            cell[mv["key"]] = _compute_measure(work, mv)
        result_rows.append(cell)
        for mv in measure_views:
            grand_total[mv["key"]] = cell[mv["key"]]
    else:
        grouped = work.groupby(dim_cols, dropna=False, sort=False)
        for key, sub in grouped:
            if not isinstance(key, tuple):
                key = (key,)
            dims_dict = {col: _normalise_dim_value(v) for col, v in zip(dim_cols, key)}
            row_dims_dict = {c: dims_dict[c] for c in rows if c in dims_dict}
            col_dims_dict = {c: dims_dict[c] for c in cols if c in dims_dict}
            cell = {"_dims": row_dims_dict, "_cols": col_dims_dict}
            for mv in measure_views:
                cell[mv["key"]] = _compute_measure(sub, mv)
            result_rows.append(cell)

        # Grand totals across the whole filtered frame.
        if include_grand_total:
            for mv in measure_views:
                grand_total[mv["key"]] = _compute_measure(work, mv)

    # Sort + Top/Bottom N.
    #
    # Three layered defaults — explicit user sort always wins:
    #   1. If any *row* dim is a date, sort chronologically by that
    #      date (ascending).  A line chart that walks
    #      Feb → Mar → Jan because Feb has the highest sales is the
    #      classic "broken trend" bug, so dates are special-cased.
    #   2. Else if subtotals are requested, sort hierarchically by
    #      the row-dim prefixes so each detail group is contiguous —
    #      otherwise the subtotal interleave below would duplicate
    #      and misplace subtotal rows.
    #   3. Else fall back to descending by the first measure (the
    #      Power BI-style "biggest bar first" default).
    def _row_dim_kind(c: str) -> str:
        return ((field_meta or {}).get(c) or {}).get("role", "")

    if sort:
        result_rows = _apply_sort(result_rows, sort, measure_views)
    elif rows and any(_row_dim_kind(c) == "date" for c in rows):
        date_cols = [c for c in rows if _row_dim_kind(c) == "date"]
        result_rows.sort(
            key=lambda r: tuple(
                str((r.get("_dims") or {}).get(c) or "") for c in date_cols
            )
        )
    elif include_subtotals and rows and len(rows) > 1:
        # Hierarchical sort so subtotal groups are contiguous; tie-break
        # within the deepest level on the first measure (desc) to keep
        # the Power-BI feel.
        primary = measure_views[0]["key"] if measure_views else None
        def _hier_key(r: dict[str, Any]):
            d = r.get("_dims") or {}
            return tuple(str(d.get(c) or "") for c in rows) + (
                (-(_safe_num(r.get(primary)) or 0.0),) if primary else ()
            )
        result_rows.sort(key=_hier_key)
    elif measure_views and dim_cols:
        primary = measure_views[0]["key"]
        result_rows.sort(
            key=lambda r: -(_safe_num(r.get(primary)) or 0.0),
        )
    if top_n and top_n > 0 and len(result_rows) > top_n:
        result_rows = result_rows[:top_n]

    subtotals: list[dict[str, Any]] = []
    if include_subtotals and rows and len(rows) > 1:
        # Subtotal at every row-dim prefix length.
        for prefix_len in range(1, len(rows)):
            prefix_cols = rows[:prefix_len]
            sub = work.groupby(prefix_cols, dropna=False, sort=False)
            for key, group in sub:
                if not isinstance(key, tuple):
                    key = (key,)
                dims_dict = {c: _normalise_dim_value(v) for c, v in zip(prefix_cols, key)}
                row = {"_subtotal_level": prefix_len, "_dims": dims_dict, "_cols": {}}
                for mv in measure_views:
                    row[mv["key"]] = _compute_measure(group, mv)
                subtotals.append(row)
        # Interleave subtotal rows into ``result_rows`` so the
        # frontend can render them inline (the public API contract is
        # "rows is the renderable list, in display order").  Each
        # subtotal row appears *after* the last detail row that shares
        # its prefix.  The standalone ``subtotals`` array is preserved
        # for back-compat consumers that need them broken out.
        if result_rows and subtotals:
            def _prefix(r: dict[str, Any], n: int) -> tuple[Any, ...]:
                d = r.get("_dims") or {}
                return tuple(d.get(c) for c in rows[:n])

            merged: list[dict[str, Any]] = []
            # Walk detail rows; whenever the prefix at level `lvl` is
            # about to change, emit subtotals for that prefix at every
            # sub-level (largest prefix → smallest, like Power BI).
            for i, dr in enumerate(result_rows):
                merged.append(dr)
                next_dr = result_rows[i + 1] if i + 1 < len(result_rows) else None
                for lvl in range(len(rows) - 1, 0, -1):
                    cur = _prefix(dr, lvl)
                    nxt = _prefix(next_dr, lvl) if next_dr else None
                    if cur != nxt:
                        # Find the matching subtotal row.
                        for s in subtotals:
                            if s["_subtotal_level"] != lvl:
                                continue
                            sd = s.get("_dims") or {}
                            if tuple(sd.get(c) for c in rows[:lvl]) == cur:
                                merged.append(s)
                                break
            result_rows = merged

    # Strip the spec object from the response (not JSON-serialisable).
    public_measures = [
        {k: v for k, v in mv.items() if k != "spec"} for mv in measure_views
    ]

    return {
        "rows": result_rows,
        "row_dims": rows,
        "col_dims": cols,
        "measures": public_measures,
        "grand_total": grand_total,
        "subtotals": subtotals,
        "warnings": _dedupe(warnings),
        "row_count": int(len(work)),
        "result_count": len(result_rows),
    }


def _compute_measure(sub: pd.DataFrame, mv: dict[str, Any]) -> Any:
    spec: MeasureSpec = mv["spec"]
    if mv["aggregation"] == "ratio":
        num_col = spec.numerator
        den_col = spec.denominator
        if not num_col or not den_col or num_col not in sub.columns or den_col not in sub.columns:
            return None
        num = _apply_single_agg(sub[num_col], spec.numerator_agg)
        den = _apply_single_agg(sub[den_col], spec.denominator_agg)
        try:
            if not den or (isinstance(den, float) and (np.isnan(den) or den == 0)):
                return None
            return float(num) / float(den)
        except Exception:
            return None
    col = spec.column
    if not col or col not in sub.columns:
        # Allow count without a column → row count.
        if _agg_key(spec.aggregation) == "count":
            return int(len(sub))
        return None
    return _apply_single_agg(sub[col], spec.aggregation)


def _safe_num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if not np.isfinite(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _apply_sort(
    rows: list[dict[str, Any]],
    sort: list[dict[str, Any]],
    measures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply a list of sort specs.  Latest spec takes priority."""
    label_to_key = {m["label"]: m["key"] for m in measures}
    column_to_key = {m["column"]: m["key"] for m in measures if m.get("column")}
    out = list(rows)
    for spec in reversed(sort):
        col = spec.get("by") or spec.get("column")
        direction = (spec.get("dir") or spec.get("direction") or "desc").lower()
        if not col:
            continue
        key = column_to_key.get(col) or label_to_key.get(col) or col
        reverse = direction in ("desc", "descending", "down")

        def _sort_key(r, k=key):
            if k.startswith("m") and k in r:
                return _safe_num(r.get(k)) or 0.0
            return r.get("_dims", {}).get(k) or r.get("_cols", {}).get(k) or ""

        out.sort(key=_sort_key, reverse=reverse)
    return out


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Chart suggestion
# ---------------------------------------------------------------------------

def suggest_chart_type(
    rows: list[str],
    cols: list[str],
    measures: list[dict[str, Any]],
    field_meta: dict[str, dict[str, Any]],
) -> str:
    """Pick a sensible chart type for a pivot result.

    Rules (in order):
      * No row dims, single measure → KPI card.
      * One row dim that's a date / datetime → line.
      * Two measures, no col dim → scatter (relationship between them).
      * One row dim with a column dim → stacked bar.
      * One row dim, ≤ 6 unique values, single measure → pie.
      * One row dim that contains "stage" → funnel.
      * Default → bar.
    """
    n_meas = len(measures)
    if not rows and not cols:
        return "kpi"
    if not rows and cols:
        rows = cols
        cols = []
    if rows and len(rows) == 1:
        col = rows[0]
        meta = field_meta.get(col) or {}
        if meta.get("role") == "date" or meta.get("format_kind") == "date":
            return "line"
        if "stage" in col.lower():
            return "funnel"
    if not cols and n_meas == 2:
        return "scatter"
    if cols:
        return "stacked_bar"
    return "bar"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_request(
    rows: list[str],
    cols: list[str],
    measures: list[dict[str, Any] | MeasureSpec],
    field_meta: dict[str, dict[str, Any]],
    df_columns: Iterable[str],
) -> list[str]:
    """Cheap pre-flight checks before running ``aggregate``.

    Returns a list of human-readable warnings — never raises.  Real
    column-not-found errors are surfaced by ``aggregate`` itself when it
    tries to access a missing column.

    Catches the classic BI bear-traps before they show up in a chart:
      * Aggregating an identifier (``sum`` of a customer-id).
      * Summing a percentage / rate column (the famous ratio-of-ratios
        bug — averaging a column that is itself already a ratio is
        flagged here too).
      * Charting two measures with no row dim (no x-axis).
      * Including a key column in the rows well alongside any other
        dimension — that defeats the grouping on the other dim.
    """
    warnings: list[str] = []
    cols_set = set(df_columns)
    for c in (rows or []) + (cols or []):
        if c not in cols_set:
            warnings.append(f"Column '{c}' is not in the dataset.")
    # Identifier in rows alongside other dims — this turns the pivot
    # back into a row dump (every row is unique on the ID).
    if rows:
        id_in_rows = [c for c in rows if (field_meta.get(c) or {}).get("role") == "key"]
        if id_in_rows and len(rows) > 1:
            warnings.append(
                "Identifier column "
                + ", ".join(f"`{c}`" for c in id_in_rows)
                + " is in Rows alongside other dimensions — every row will "
                "be unique, defeating the grouping. Move the ID to a tooltip."
            )
    for m in measures or []:
        if isinstance(m, MeasureSpec):
            spec = m
        else:
            spec = MeasureSpec.from_dict(m)
        if spec.aggregation == "ratio":
            for c in (spec.numerator, spec.denominator):
                if c and c not in cols_set:
                    warnings.append(f"Ratio component '{c}' is not in the dataset.")
            # Ratio-of-ratios: numerator or denominator already a percent.
            for c in (spec.numerator, spec.denominator):
                if c:
                    cmeta = field_meta.get(c) or {}
                    if cmeta.get("format_kind") == "percent":
                        warnings.append(
                            f"Ratio uses `{c}` which is itself a percentage — "
                            "this is a ratio-of-ratios and rarely correct. "
                            "Use the underlying numerator/denominator counts."
                        )
            continue
        if spec.column and spec.column not in cols_set:
            warnings.append(f"Measure column '{spec.column}' is not in the dataset.")
        if spec.column and spec.aggregation in ("sum", "avg", "min", "max", "median"):
            meta = field_meta.get(spec.column) or {}
            if meta.get("role") == "key":
                warnings.append(
                    f"`{spec.column}` is an identifier; "
                    f"{AGG_LABELS.get(spec.aggregation, spec.aggregation)} "
                    "is rarely meaningful for IDs."
                )
            if meta.get("format_kind") == "percent" and spec.aggregation == "sum":
                warnings.append(
                    f"`{spec.column}` is a percentage; summing percentages "
                    "double-counts. Consider a ratio measure."
                )
            if meta.get("format_kind") == "percent" and spec.aggregation == "avg":
                # Averaging an already-aggregated rate is a ratio-of-ratios.
                warnings.append(
                    f"`{spec.column}` is a percentage / rate; averaging it "
                    "weights every group equally regardless of size. For a "
                    "true overall rate use a ratio measure of the underlying "
                    "counts."
                )
    if not (rows or cols) and len(measures or []) >= 2:
        warnings.append(
            "Two or more measures with no row or column dimension — "
            "the chart has no x-axis. Pick a dimension or use a KPI tile."
        )
    return warnings


# ---------------------------------------------------------------------------
# Multi-table modeling — grain-aware join validation
# ---------------------------------------------------------------------------

def validate_join(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    on: list[str],
    left_meta: dict[str, dict[str, Any]] | None = None,
    right_meta: dict[str, dict[str, Any]] | None = None,
    left_name: str = "left",
    right_name: str = "right",
) -> dict[str, Any]:
    """Validate a join between two datasets before it explodes.

    Power BI's modeling layer refuses to build a relationship that would
    silently double-count.  We do the same: detect each side's grain
    (uniqueness on the join key), classify the join cardinality, and
    flag fan-out + summary↔summary joins.

    Returns ``{ok, cardinality, left_grain, right_grain, fanout,
    warnings, errors}``.  ``ok`` is False when the join is unsafe to
    pre-aggregate either side.
    """
    if not on:
        return {
            "ok": False,
            "cardinality": "unknown",
            "left_grain": False, "right_grain": False,
            "fanout": None, "warnings": [],
            "errors": ["No join key supplied."],
        }
    missing_left = [c for c in on if c not in left_df.columns]
    missing_right = [c for c in on if c not in right_df.columns]
    if missing_left or missing_right:
        return {
            "ok": False,
            "cardinality": "unknown",
            "left_grain": False, "right_grain": False,
            "fanout": None, "warnings": [],
            "errors": [
                f"Join key {missing_left or missing_right} missing from "
                f"{left_name if missing_left else right_name}.",
            ],
        }
    left_grain = bool(left_df.dropna(subset=on).duplicated(subset=on).sum() == 0)
    right_grain = bool(right_df.dropna(subset=on).duplicated(subset=on).sum() == 0)
    if left_grain and right_grain:
        cardinality = "one_to_one"
    elif left_grain and not right_grain:
        cardinality = "one_to_many"
    elif not left_grain and right_grain:
        cardinality = "many_to_one"
    else:
        cardinality = "many_to_many"

    warnings: list[str] = []
    errors: list[str] = []
    # Fan-out estimate — how many right rows does the average left row
    # match?  >5x ⇒ measures from the left will be materially
    # double-counted after the join.
    matching = right_df.dropna(subset=on).groupby(on).size()
    fanout = float(matching.mean()) if len(matching) else 1.0

    if cardinality == "many_to_many":
        errors.append(
            "Many-to-many join — neither side is unique on the key. "
            "Pre-aggregate one side to its grain before joining."
        )
    if not left_grain and (left_meta is not None):
        # Left side is the "fact" — check whether any right-side measure
        # would be double-counted by the join (fact has multiple rows
        # per dimension key).
        for col, info in (right_meta or {}).items():
            if info.get("role") == "measure" and info.get("default_agg") == "sum":
                warnings.append(
                    f"`{col}` from {right_name} would be double-counted "
                    f"by the join (left side has multiple rows per "
                    f"{', '.join(on)})."
                )
    if fanout > 5:
        warnings.append(
            f"High fan-out: each {left_name} row matches ~{fanout:.1f} "
            f"{right_name} rows. Consider aggregating before joining."
        )

    return {
        "ok": cardinality != "many_to_many" and not errors,
        "cardinality": cardinality,
        "left_grain": left_grain,
        "right_grain": right_grain,
        "fanout": fanout,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Result explanation — the "why is this number what it is" panel
# ---------------------------------------------------------------------------

def explain_cell(
    df: pd.DataFrame,
    measure: dict[str, Any],
    filters: list[dict[str, Any]] | None,
    coordinate: dict[str, Any] | None,
    field_meta: dict[str, dict[str, Any]],
    sample_rows: int = 20,
) -> dict[str, Any]:
    """Explain one cell / KPI value the engine produced.

    Returns the formula, the active filters, the contributing-row count,
    a sample of the underlying rows, and any ratio-of-ratios / fan-out
    warnings — i.e. everything the user needs to answer "where did this
    number come from?".
    """
    spec = MeasureSpec.from_dict(measure)
    work = df
    if filters:
        work = apply_filters(work, filters)
    coordinate = coordinate or {}
    coord_filters: list[dict[str, Any]] = []
    if coordinate:
        for col, val in coordinate.items():
            if col in work.columns:
                coord_filters.append({"column": col, "op": "=", "value": val})
        if coord_filters:
            work = apply_filters(work, coord_filters)
    contributing = int(len(work))
    if spec.aggregation == "ratio":
        n = _apply_single_agg(work[spec.numerator], spec.numerator_agg) if spec.numerator and spec.numerator in work.columns else None
        d = _apply_single_agg(work[spec.denominator], spec.denominator_agg) if spec.denominator and spec.denominator in work.columns else None
        try:
            value = float(n) / float(d) if d not in (None, 0) else None
        except Exception:
            value = None
        formula = (
            f"{spec.numerator_agg.upper()}({spec.numerator}) / "
            f"{spec.denominator_agg.upper()}({spec.denominator})"
        )
    else:
        col = spec.column
        if col and col in work.columns:
            value = _apply_single_agg(work[col], spec.aggregation)
        else:
            value = None
        formula = f"{spec.aggregation.upper()}({col or '*'})"

    # Show a small, deterministic sample of the underlying rows so the
    # user can sanity-check what landed in the bucket.
    sample = work.head(sample_rows).to_dict(orient="records") if contributing else []
    warnings = _measure_warnings(spec, field_meta) or []

    # Build a flat human-readable filter summary the UI can render
    # without re-implementing the filter dialect.
    summary_parts: list[str] = []
    for f in (filters or []) + coord_filters:
        col = f.get("column", "?")
        op = f.get("op", "=")
        if op in ("is_null", "not_null"):
            summary_parts.append(f"{col} {op}")
        elif op in ("in", "not_in"):
            vals = f.get("values") or []
            summary_parts.append(f"{col} {op} ({', '.join(str(v) for v in vals)})")
        elif op == "between":
            summary_parts.append(f"{col} between {f.get('min')} and {f.get('max')}")
        else:
            summary_parts.append(f"{col} {op} {f.get('value')}")

    return {
        "formula": formula,
        "value": _safe_num(value),
        "aggregation": spec.aggregation,
        "column": spec.column,
        "filters": (filters or []) + coord_filters,
        "filter_summary": summary_parts,
        "contributing_rows": contributing,
        "total_rows": int(len(df)),
        "sample": sample,
        "sample_rows": sample,
        "warnings": warnings,
    }
