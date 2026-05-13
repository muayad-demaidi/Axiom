"""BI routes — field metadata, pivot table, dashboard.

These endpoints share the central :mod:`backend.aggregation` engine
with the visualize endpoint and the chat ``make_chart`` tool so the
chat answer, the pivot table and the dashboard always agree on the
numbers.

Field metadata is persisted on
``DatasetRecord.summary_stats["_axiom_field_meta"]`` (no schema
migration required — same trick used for ``_axiom_profile`` and
``_axiom_insights``).
"""
from __future__ import annotations

import csv
import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import models  # type: ignore

from context.type_inference import (  # type: ignore
    PARSE_MODES,
    PARSE_STATUS_OK,
    parse_numeric_series,
    to_numeric_canonical as _canonical,
)

from . import aggregation as agg
from ._json import jsonify
from .auth import get_current_user, get_db_session
from .datasets import load_dataset_dataframe


router = APIRouter(prefix="/api/bi", tags=["bi"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_dataset(db, dataset_id: int, user_id: int):
    record = models.get_dataset_record(db, dataset_id, user_id=user_id)
    if not record:
        raise HTTPException(404, "Dataset not found")
    df = load_dataset_dataframe(record)
    return record, df


def _stored_meta(record) -> dict[str, dict[str, Any]]:
    ss = record.summary_stats or {}
    raw = ss.get("_axiom_field_meta") or {}
    return raw if isinstance(raw, dict) else {}


def _resolved_meta(record, df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Inferred defaults merged with whatever the user has overridden."""
    inferred = agg.infer_field_meta(df)
    return agg.merge_field_meta(inferred, _stored_meta(record))


def _save_meta(db, record, overrides: dict[str, dict[str, Any]]) -> None:
    ss = dict(record.summary_stats or {})
    ss["_axiom_field_meta"] = overrides
    record.summary_stats = ss
    db.add(record)
    db.commit()


# ---------------------------------------------------------------------------
# Field metadata CRUD
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/field-meta")
async def get_field_meta(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Return the resolved field metadata (inferred + user overrides).

    Includes a ``_overrides`` block so the UI can show which fields the
    user has explicitly customised.
    """
    record, df = _require_dataset(db, dataset_id, user.id)
    resolved = _resolved_meta(record, df)
    overrides = _stored_meta(record)
    return jsonify({
        "dataset_id": dataset_id,
        "fields": resolved,
        "overrides": overrides,
        "vocab": {
            "aggregations": list(agg.AGGREGATIONS),
            "agg_labels": agg.AGG_LABELS,
            "roles": list(agg.ROLES),
            "format_kinds": list(agg.FORMAT_KINDS),
            "parse_modes": list(PARSE_MODES),
        },
    })


class FieldMetaUpdate(BaseModel):
    """Partial update for one column's metadata."""
    role: str | None = None
    default_agg: str | None = None
    format_kind: str | None = None
    precision: int | None = None
    label: str | None = None
    description: str | None = None
    visible: bool | None = None
    sort_by: str | None = None
    # Per-column override that forces the canonical numeric parser into
    # a specific locale interpretation (auto / decimal_point /
    # decimal_comma / thousands_comma / thousands_dot / mixed_smart).
    parse_mode: str | None = None


class FieldMetaPatch(BaseModel):
    """Map of column -> partial overrides.  Send only fields that change."""
    fields: dict[str, FieldMetaUpdate]


@router.patch("/{dataset_id}/field-meta")
async def patch_field_meta(
    dataset_id: int,
    req: FieldMetaPatch,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record, df = _require_dataset(db, dataset_id, user.id)
    overrides = dict(_stored_meta(record))
    cols = set(df.columns.astype(str))
    for col, patch in req.fields.items():
        if col not in cols:
            continue
        existing = dict(overrides.get(col) or {})
        for k, v in patch.model_dump(exclude_unset=True).items():
            if v is None:
                continue
            if k == "default_agg" and v not in agg.AGGREGATIONS:
                raise HTTPException(400, f"Invalid aggregation '{v}' for column '{col}'")
            if k == "role" and v not in agg.ROLES:
                raise HTTPException(400, f"Invalid role '{v}' for column '{col}'")
            if k == "format_kind" and v not in agg.FORMAT_KINDS:
                raise HTTPException(400, f"Invalid format_kind '{v}' for column '{col}'")
            if k == "parse_mode" and v not in PARSE_MODES:
                raise HTTPException(
                    400,
                    f"Invalid parse_mode '{v}' for column '{col}'."
                    f" Allowed: {', '.join(PARSE_MODES)}",
                )
            existing[k] = v
        overrides[col] = existing
    _save_meta(db, record, overrides)
    resolved = _resolved_meta(record, df)
    return jsonify({"dataset_id": dataset_id, "fields": resolved, "overrides": overrides})


@router.delete("/{dataset_id}/field-meta/{column}")
async def reset_field_meta(
    dataset_id: int,
    column: str,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Reset one column to its inferred default."""
    record, df = _require_dataset(db, dataset_id, user.id)
    overrides = dict(_stored_meta(record))
    overrides.pop(column, None)
    _save_meta(db, record, overrides)
    return jsonify({"dataset_id": dataset_id, "column": column, "reset": True})


# ---------------------------------------------------------------------------
# Reconciliation view — raw vs canonical-parsed numbers
# ---------------------------------------------------------------------------

@router.get("/{dataset_id}/reconciliation")
async def reconciliation(
    dataset_id: int,
    column: str | None = None,
    sample: int = 25,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Return a side-by-side view of raw vs parsed numeric columns.

    The shape is intentionally compact so the UI can render it inside
    the existing pivot ``calc_trace`` panel without new components::

        {
          "dataset_id": 7,
          "columns": [
            {
              "column": "DMBTR",
              "parse_mode": "auto",
              "total_rows": 1200, "valid_rows": 1200,
              "invalid_rows": 0, "null_rows": 0,
              "raw_sum": null, "parsed_sum": 4241288.49,
              "min": 107.22, "max": 9977.0,
              "samples": [{"row": 0, "raw": "1,583", "parsed": 1583.0,
                           "status": "ok"}, ...],
              "excluded": [{"row": 42, "raw": "ERROR",
                            "status": "null_token"}, ...],
              "duplicates_in_raw": 18
            }, ...
          ]
        }
    """
    record, df = _require_dataset(db, dataset_id, user.id)
    meta = _resolved_meta(record, df)
    sample = max(1, min(int(sample or 25), 200))

    if column:
        targets = [column] if column in df.columns else []
    else:
        # Default to every column that the engine considers a measure
        # (or whose name reads like an amount).  This keeps the response
        # bounded while still surfacing every numeric column the user
        # actually relies on for totals.
        targets = [
            c for c, m in meta.items()
            if (m or {}).get("role") == "measure"
        ]

    cols_out: list[dict[str, Any]] = []
    for col in targets:
        if col not in df.columns:
            continue
        m = meta.get(col) or {}
        mode = (m.get("parse_mode") or "auto")
        raw = df[col]
        parsed, status = parse_numeric_series(raw, mode=mode)
        ok_mask = status == PARSE_STATUS_OK
        bad_mask = ~ok_mask

        # `raw_sum` is *intentionally* computed with the legacy
        # `pd.to_numeric` path — it exists to expose what naive
        # pre-canonical-parser code would have summed so the
        # reconciliation view can show the diff side-by-side with
        # `parsed_sum`.  Replacing this with the canonical parser would
        # make the two columns always equal and erase the whole point
        # of the reconciliation diagnostic.  This is the only
        # `pd.to_numeric` call left in the BI surface and it is
        # diagnostic-only, never feeding aggregation/pivot/KPI/chat.
        #
        # We deliberately compute it for *every* dtype (not just
        # already-numeric).  Object-typed mixed-locale amount columns
        # are the headline failure class — restricting `raw_sum` to
        # numeric dtypes would hide the diff in exactly the cases
        # users care about.  `pd.to_numeric(errors="coerce")` silently
        # NaN-drops mixed-locale strings, which is the legacy bug
        # behaviour we want to surface.
        raw_sum: float | None = None
        try:
            raw_sum = float(
                pd.to_numeric(raw, errors="coerce").sum(skipna=True)
            )
        except Exception:
            raw_sum = None

        def _row_payload(label: Any) -> dict[str, Any]:
            rv = raw.at[label]
            pv = parsed.at[label]
            return {
                "row": int(label) if hasattr(label, "__int__") else str(label),
                "raw": None if pd.isna(rv) else str(rv),
                "parsed": None if pd.isna(pv) else float(pv),
                "status": str(status.at[label]),
            }

        sample_rows = [_row_payload(i) for i in raw.head(sample).index]
        excluded: list[dict[str, Any]] = []
        if bad_mask.any():
            for label in raw[bad_mask].head(sample).index:
                excluded.append({
                    "row": int(label) if hasattr(label, "__int__") else str(label),
                    "raw": (None if pd.isna(raw.at[label])
                            else str(raw.at[label])),
                    "status": str(status.at[label]),
                })

        try:
            duplicates = int(int(len(raw)) - int(raw.nunique(dropna=True)))
        except Exception:
            duplicates = 0

        parsed_ok = parsed[ok_mask]
        cols_out.append({
            "column": col,
            "parse_mode": mode,
            "total_rows": int(len(raw)),
            "valid_rows": int(ok_mask.sum()),
            "invalid_rows": int(bad_mask.sum()),
            "null_rows": int((status == "null_token").sum()),
            "raw_sum": raw_sum,
            "parsed_sum": (float(parsed_ok.sum()) if not parsed_ok.empty else None),
            "min": (float(parsed_ok.min()) if not parsed_ok.empty else None),
            "max": (float(parsed_ok.max()) if not parsed_ok.empty else None),
            "samples": sample_rows,
            "excluded": excluded,
            "duplicates_in_raw": duplicates,
        })

    return jsonify({
        "dataset_id": dataset_id,
        "columns": cols_out,
    })


# ---------------------------------------------------------------------------
# Modeling safeguards: grain + fan-out detection
# ---------------------------------------------------------------------------

def _detect_grain(df: pd.DataFrame, meta: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Heuristic grain inference: smallest set of columns whose values
    are unique across the table.  Caps at 3 columns and bails if no
    candidate is found.
    """
    n = len(df)
    if n == 0:
        return {"keys": [], "is_unique": True, "duplicate_count": 0}
    # Single column unique?
    candidates: list[str] = []
    for col in df.columns:
        info = meta.get(str(col)) or {}
        if info.get("role") in ("key", "date") or info.get("format_kind") == "date":
            candidates.append(str(col))
    for col in candidates:
        try:
            if int(df[col].nunique(dropna=False)) == n:
                return {"keys": [col], "is_unique": True, "duplicate_count": 0}
        except Exception:
            continue
    # Try pairs.
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            pair = [candidates[i], candidates[j]]
            try:
                if int(df.duplicated(subset=pair).sum()) == 0:
                    return {"keys": pair, "is_unique": True, "duplicate_count": 0}
            except Exception:
                continue
    # Couldn't find a unique grain — surface the duplicate count.
    return {
        "keys": [],
        "is_unique": False,
        "duplicate_count": int(df.duplicated().sum()),
    }


def _detect_fanout(df: pd.DataFrame, meta: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag columns whose grouping fans out the additive measures.

    For each candidate dimension, compare the SUM of every additive
    measure with grouping vs. without grouping.  If the grouped sum is
    materially different from the row count × per-row contribution, the
    dimension is at a different grain than the measures and we flag it.
    """
    out: list[dict[str, Any]] = []
    n = len(df)
    if n == 0:
        return out
    measures = [
        col for col, info in meta.items()
        if info.get("role") == "measure"
        and info.get("default_agg") == "sum"
        and col in df.columns
        and pd.api.types.is_numeric_dtype(df[col])
    ]
    if not measures:
        return out
    dim_cols = [
        col for col, info in meta.items()
        if info.get("role") in ("dimension", "key")
        and col in df.columns
        and 1 < int(df[col].nunique(dropna=True)) < min(50, max(2, n // 2))
    ]
    if not dim_cols:
        return out
    base_sums = {m: float(_canonical(df[m]).sum()) for m in measures}
    for d in dim_cols:
        try:
            grouped = df.groupby(d, dropna=False).agg({m: lambda s: _canonical(s).sum() for m in measures})
        except Exception:
            continue
        # If joining a dim row in causes some measures to repeat
        # (fan-out), the per-group totals will not sum back to the
        # dataset total.  Pandas itself will sum them back exactly when
        # there's no fan-out, so detect by total row count change:
        dim_n = int(df[d].nunique(dropna=True))
        if dim_n == n:  # 1:1 with the table — definitely no fan-out
            continue
        for m in measures:
            grouped_total = float(grouped[m].sum())
            base = base_sums[m]
            if base == 0:
                continue
            ratio = grouped_total / base
            if abs(ratio - 1.0) > 0.01:
                out.append({
                    "dimension": d,
                    "measure": m,
                    "ratio": round(ratio, 4),
                    "warning": (
                        f"Grouping `{m}` by `{d}` changes the total by "
                        f"{(ratio - 1) * 100:+.1f}%. This usually means "
                        "the table fans out — check your joins."
                    ),
                })
    return out


@router.get("/{dataset_id}/modeling")
async def modeling_safeguards(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Return grain + fan-out warnings for the dataset."""
    record, df = _require_dataset(db, dataset_id, user.id)
    meta = _resolved_meta(record, df)
    grain = _detect_grain(df, meta)
    fanout = _detect_fanout(df, meta)
    return jsonify({
        "dataset_id": dataset_id,
        "row_count": int(len(df)),
        "grain": grain,
        "fanout": fanout,
    })


# ---------------------------------------------------------------------------
# Pivot
# ---------------------------------------------------------------------------

class MeasurePayload(BaseModel):
    column: str | None = None
    aggregation: str = "sum"
    label: str | None = None
    format_kind: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    numerator_agg: str = "sum"
    denominator_agg: str = "sum"


class PivotRequest(BaseModel):
    dataset_id: int
    rows: list[str] = []
    cols: list[str] = []
    measures: list[MeasurePayload] = []
    filters: list[dict[str, Any]] = []
    date_grains: dict[str, str] = {}
    top_n: int | None = None
    sort: list[dict[str, Any]] = []
    include_subtotals: bool = False
    include_grand_total: bool = True
    drop_nulls_in_dims: bool = False


@router.post("/pivot")
async def pivot(
    req: PivotRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record, df = _require_dataset(db, req.dataset_id, user.id)
    meta = _resolved_meta(record, df)
    measures = [m.model_dump() for m in req.measures]

    # If no measures sent, fall back to the row count.
    if not measures and req.rows:
        measures = [{"column": req.rows[0], "aggregation": "count", "label": "Row count"}]

    # Hard refuse summing / averaging identifier columns — the engine
    # would still emit a warning but the resulting number is almost
    # always meaningless and is one of the classic Power BI footguns.
    for m in measures:
        col = m.get("column")
        a = (m.get("aggregation") or "").lower()
        if col and a in ("sum", "avg") and (meta.get(col) or {}).get("role") == "key":
            raise HTTPException(
                400,
                f"`{col}` is an identifier — {a.upper()} of an ID is rarely meaningful. "
                f"Either pick a real measure or change `{col}`'s role on the Field settings page.",
            )

    pre_warnings = agg.validate_request(req.rows, req.cols, measures, meta, df.columns)
    result = agg.aggregate(
        df,
        rows=req.rows,
        cols=req.cols,
        measures=measures,
        filters=req.filters,
        date_grains=req.date_grains,
        top_n=req.top_n,
        sort=req.sort,
        field_meta=meta,
        include_subtotals=req.include_subtotals,
        include_grand_total=req.include_grand_total,
        drop_nulls_in_dims=req.drop_nulls_in_dims,
    )
    result["warnings"] = list(dict.fromkeys((pre_warnings or []) + (result.get("warnings") or [])))
    result["chart_suggestion"] = agg.suggest_chart_type(req.rows, req.cols, result["measures"], meta)
    result["dataset_id"] = req.dataset_id
    return jsonify(result)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DEFAULT_KPI_AGG = "sum"


def _auto_dashboard(meta: dict[str, dict[str, Any]], df: pd.DataFrame) -> dict[str, Any]:
    """Heuristically pick KPIs + charts for a fresh dataset.

    The output mirrors a Power BI page layout, grouped into named
    sections the frontend renders as collapsible blocks:

      * ``executive`` — 1–4 KPI cards from additive measures.
      * ``trend``     — line chart over the most-populated date column.
      * ``segmentation`` — categorical breakdown of the top measure by
        the lowest-cardinality dimension.
      * ``operational`` — Top-N table of the highest-cardinality
        dimension by the top measure.

    Tiles for sections that don't apply (e.g. no date column → no
    trend) are simply omitted; the frontend renders only the sections
    it actually receives.  The dashboard also publishes a ``slicers``
    block with the primary date column and the most useful categorical
    dimension so the frontend can render a date-range picker + a
    categorical filter that apply across every tile.
    """
    measures = [
        (col, info) for col, info in meta.items()
        if info.get("role") == "measure"
        and info.get("default_agg") in ("sum", "avg")
        and info.get("visible", True)
        and col in df.columns
    ]
    # Sort additive (SUM) measures first so KPIs are likely revenue/etc.
    measures.sort(key=lambda x: (x[1].get("default_agg") != "sum", x[0]))
    kpi_measures = measures[:4]

    dims = [
        (col, info) for col, info in meta.items()
        if info.get("role") == "dimension" and info.get("visible", True)
        and col in df.columns
    ]
    dims.sort(key=lambda x: int(df[x[0]].nunique(dropna=True)))

    dates = [
        (col, info) for col, info in meta.items()
        if info.get("role") == "date" and col in df.columns
    ]
    dates.sort(key=lambda x: -int(pd.to_datetime(df[x[0]], errors="coerce").notna().sum()))

    tiles: list[dict[str, Any]] = []

    # Executive KPIs.
    for col, info in kpi_measures:
        tiles.append({
            "id": f"kpi_{col}",
            "section": "executive",
            "kind": "kpi",
            "title": info.get("label") or col,
            "rows": [],
            "cols": [],
            "measures": [{"column": col, "aggregation": info.get("default_agg", "sum")}],
        })

    # Trend.
    if dates and kpi_measures:
        dcol = dates[0][0]
        mcol, minfo = kpi_measures[0]
        tiles.append({
            "id": f"trend_{mcol}_{dcol}",
            "section": "trend",
            "kind": "line",
            "title": f"{minfo.get('label') or mcol} over time",
            "rows": [dcol],
            "cols": [],
            "date_grains": {dcol: "month"},
            "measures": [{"column": mcol, "aggregation": minfo.get("default_agg", "sum")}],
        })

    # Segmentation: categorical breakdown of the top measure by the
    # lowest-cardinality dimension.
    if dims and kpi_measures:
        dcol, _ = dims[0]
        mcol, minfo = kpi_measures[0]
        tiles.append({
            "id": f"bar_{mcol}_by_{dcol}",
            "section": "segmentation",
            "kind": "bar",
            "title": f"{minfo.get('label') or mcol} by {dcol}",
            "rows": [dcol],
            "cols": [],
            "measures": [{"column": mcol, "aggregation": minfo.get("default_agg", "sum")}],
            "top_n": 10,
        })

    # Operational: Top-N table of a finer-grained dimension.
    if dims and kpi_measures and len(dims) > 1:
        dcol, _ = dims[-1]
        mcol, minfo = kpi_measures[0]
        tiles.append({
            "id": f"top_{dcol}",
            "section": "operational",
            "kind": "table",
            "title": f"Top {dcol} by {minfo.get('label') or mcol}",
            "rows": [dcol],
            "cols": [],
            "measures": [{"column": mcol, "aggregation": minfo.get("default_agg", "sum")}],
            "top_n": 10,
        })

    # Slicers — page-level filters the frontend applies to every tile.
    slicers: list[dict[str, Any]] = []
    if dates:
        slicers.append({"kind": "date_range", "column": dates[0][0]})
    if dims:
        slicers.append({"kind": "categorical", "column": dims[0][0]})

    return {"tiles": tiles, "slicers": slicers}


def _stored_dashboard(record) -> dict[str, Any] | None:
    ss = record.summary_stats or {}
    raw = ss.get("_axiom_dashboard")
    if isinstance(raw, dict):
        return raw
    return None


def _save_dashboard(db, record, dashboard: dict[str, Any]) -> None:
    ss = dict(record.summary_stats or {})
    ss["_axiom_dashboard"] = dashboard
    record.summary_stats = ss
    db.add(record)
    db.commit()


@router.get("/{dataset_id}/dashboard")
async def get_dashboard(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
    date_from: str | None = None,
    date_to: str | None = None,
    slicer_column: str | None = None,
    slicer_values: str | None = None,
):
    """Return the saved dashboard spec, computing one if missing.

    Optional query parameters apply page-level slicers across every
    tile so the same filter affects every KPI / chart / table — the
    Power BI page-filter behaviour.  ``slicer_values`` is a
    comma-separated list of values for the ``slicer_column``.
    """
    record, df = _require_dataset(db, dataset_id, user.id)
    meta = _resolved_meta(record, df)
    spec = _stored_dashboard(record) or _auto_dashboard(meta, df)
    # Page-level slicer filters merged into every tile's own filters.
    slicer_filters: list[dict[str, Any]] = []
    if (date_from or date_to) and spec.get("slicers"):
        date_slicer = next((s for s in spec["slicers"] if s.get("kind") == "date_range"), None)
        if date_slicer:
            col = date_slicer["column"]
            if date_from:
                slicer_filters.append({"column": col, "op": ">=", "value": date_from})
            if date_to:
                slicer_filters.append({"column": col, "op": "<=", "value": date_to})
    if slicer_column and slicer_values:
        vals = [v for v in slicer_values.split(",") if v]
        if vals:
            slicer_filters.append({"column": slicer_column, "op": "in", "values": vals})

    tiles_out: list[dict[str, Any]] = []
    for tile in spec.get("tiles", []):
        try:
            measures = tile.get("measures") or []
            tile_filters = (tile.get("filters") or []) + slicer_filters
            pre = agg.validate_request(
                tile.get("rows") or [], tile.get("cols") or [],
                measures, meta, df.columns,
            )
            result = agg.aggregate(
                df,
                rows=tile.get("rows") or [],
                cols=tile.get("cols") or [],
                measures=measures,
                filters=tile_filters,
                date_grains=tile.get("date_grains") or {},
                top_n=tile.get("top_n"),
                sort=tile.get("sort") or [],
                field_meta=meta,
                include_subtotals=False,
                include_grand_total=True,
            )
            result["tile"] = tile
            result["warnings"] = list(dict.fromkeys((pre or []) + (result.get("warnings") or [])))
            tiles_out.append(result)
        except Exception as e:
            tiles_out.append({"tile": tile, "error": str(e), "rows": [], "measures": []})
    return jsonify({
        "dataset_id": dataset_id,
        "spec": spec,
        "tiles": tiles_out,
        "applied_slicers": slicer_filters,
    })


class DashboardSaveRequest(BaseModel):
    tiles: list[dict[str, Any]]
    # Slicers are optional in the request — if the caller (the
    # frontend dashboard editor) doesn't send them we keep whatever
    # is already saved on the dataset, so editing tiles never
    # silently nukes the page-level slicers configured at auto-gen
    # time.
    slicers: list[dict[str, Any]] | None = None


@router.put("/{dataset_id}/dashboard")
async def save_dashboard(
    dataset_id: int,
    req: DashboardSaveRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record, _ = _require_dataset(db, dataset_id, user.id)
    existing = _stored_dashboard(record) or {}
    slicers = req.slicers if req.slicers is not None else existing.get("slicers", [])
    payload = {"tiles": req.tiles, "slicers": slicers}
    _save_dashboard(db, record, payload)
    return jsonify({"dataset_id": dataset_id, "saved": True, **payload})


@router.delete("/{dataset_id}/dashboard")
async def reset_dashboard(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record, _ = _require_dataset(db, dataset_id, user.id)
    ss = dict(record.summary_stats or {})
    ss.pop("_axiom_dashboard", None)
    record.summary_stats = ss
    db.add(record)
    db.commit()
    return jsonify({"dataset_id": dataset_id, "reset": True})


# ---------------------------------------------------------------------------
# Explanation panel — "where did this number come from?"
# ---------------------------------------------------------------------------

class ExplainRequest(BaseModel):
    dataset_id: int
    measure: dict[str, Any]
    filters: list[dict[str, Any]] = []
    coordinate: dict[str, Any] = {}
    sample_rows: int = 20


@router.post("/explain")
async def explain(
    req: ExplainRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Return a structured explanation for one cell / KPI value.

    The pivot and dashboard pages call this when the user clicks
    ``Explain this number`` — same payload regardless of which surface
    asked.
    """
    record, df = _require_dataset(db, req.dataset_id, user.id)
    meta = _resolved_meta(record, df)
    out = agg.explain_cell(
        df,
        measure=req.measure,
        filters=req.filters,
        coordinate=req.coordinate,
        field_meta=meta,
        sample_rows=req.sample_rows,
    )
    return jsonify({"dataset_id": req.dataset_id, **out})


# ---------------------------------------------------------------------------
# CSV export — one click "download what I see"
# ---------------------------------------------------------------------------

@router.post("/export/csv")
async def export_csv(
    req: PivotRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Run the pivot and stream the result back as CSV.

    The pivot page and per-tile dashboard menu both call this so the
    user can drop the same numbers straight into a spreadsheet.
    """
    record, df = _require_dataset(db, req.dataset_id, user.id)
    meta = _resolved_meta(record, df)
    measures = [m.model_dump() for m in req.measures]
    if not measures and req.rows:
        measures = [{"column": req.rows[0], "aggregation": "count", "label": "Row count"}]
    result = agg.aggregate(
        df,
        rows=req.rows, cols=req.cols, measures=measures,
        filters=req.filters, date_grains=req.date_grains,
        top_n=req.top_n, sort=req.sort,
        field_meta=meta,
        include_subtotals=req.include_subtotals,
        include_grand_total=req.include_grand_total,
        drop_nulls_in_dims=req.drop_nulls_in_dims,
    )
    # Flatten to a CSV writer.  Row dims first, then col dim columns,
    # then measure columns (cross-tab style).
    buf = io.StringIO()
    writer = csv.writer(buf)
    col_dim = req.cols[0] if req.cols else None
    if col_dim:
        col_keys: list[str] = []
        for r in result["rows"]:
            ck = r.get("_cols", {}).get(col_dim)
            if ck not in col_keys:
                col_keys.append(str(ck) if ck is not None else "")
        writer.writerow(list(req.rows) + col_keys)
        # Group cells by row dims.
        groups: dict[tuple, dict[str, Any]] = {}
        m = result["measures"][0] if result["measures"] else None
        for r in result["rows"]:
            key = tuple(r.get("_dims", {}).get(d, "") for d in req.rows)
            groups.setdefault(key, {})
            ck = str(r.get("_cols", {}).get(col_dim) or "")
            if m:
                groups[key][ck] = r.get(m["key"])
        for key, vals in groups.items():
            writer.writerow(list(key) + [vals.get(c, "") for c in col_keys])
    else:
        headers = list(req.rows) + [m["label"] for m in result["measures"]]
        writer.writerow(headers)
        for r in result["rows"]:
            row = [r.get("_dims", {}).get(d, "") for d in req.rows]
            for m in result["measures"]:
                row.append(r.get(m["key"]))
            writer.writerow(row)
        if req.include_grand_total and result.get("grand_total"):
            writer.writerow(["Total"] + [""] * (len(req.rows) - 1) + [result["grand_total"].get(m["key"]) for m in result["measures"]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="dataset_{req.dataset_id}_pivot.csv"'
        },
    )


# ---------------------------------------------------------------------------
# Multi-table modeling — relationship / join validation
# ---------------------------------------------------------------------------

class JoinValidateRequest(BaseModel):
    left_dataset_id: int
    right_dataset_id: int
    on: list[str]


@router.post("/relationships/validate")
async def validate_relationship(
    req: JoinValidateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Refuse silent double-counting before two datasets are joined.

    Inspired by Power BI's modeling layer: detects each side's grain on
    the supplied join keys, classifies the join cardinality, and flags
    summary↔detail joins that would fan-out a SUM measure.
    """
    if req.left_dataset_id == req.right_dataset_id:
        raise HTTPException(400, "Left and right datasets must differ.")
    left_record, left_df = _require_dataset(db, req.left_dataset_id, user.id)
    right_record, right_df = _require_dataset(db, req.right_dataset_id, user.id)
    left_meta = _resolved_meta(left_record, left_df)
    right_meta = _resolved_meta(right_record, right_df)
    out = agg.validate_join(
        left_df, right_df, req.on,
        left_meta=left_meta, right_meta=right_meta,
        left_name=left_record.dataset_name,
        right_name=right_record.dataset_name,
    )
    payload = {
        "left_dataset_id": req.left_dataset_id,
        "right_dataset_id": req.right_dataset_id,
        "on": req.on,
        **out,
    }
    # Power-BI–style enforcement: refuse to publish a relationship that
    # is provably unsafe (many-to-many on these keys, or any hard error
    # such as missing columns).  The caller still sees the full
    # diagnostic payload in the response body so the UI can render it.
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=payload)
    return jsonify(payload)
