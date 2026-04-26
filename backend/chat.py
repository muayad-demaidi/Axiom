"""Streaming chat endpoint — project-aware, session-anchored, tool-calling.

Each turn:
  * resolves the chat session (and therefore the owning project)
  * loads **all** datasets attached to that project so the model can
    cross-reference them, not just the one the user "selected"
  * builds a structured methodology system prompt + per-dataset summary
  * runs an OpenAI chat-completion loop with tool calls so the assistant
    can actually invoke ``make_chart`` / ``predict_column`` /
    ``cluster_dataset`` / ``profile_dataset`` and persist the results
    as ChatArtifact rows
  * streams an NDJSON event channel back to the browser so the UI can
    show skeleton loaders, then patch in chart/prediction/cluster cards
    the moment the tool finishes
"""
from __future__ import annotations

import io
import json
import os
from typing import Any, Iterator

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import models  # type: ignore
import ai_assistant  # type: ignore
import semantic_model as sm  # type: ignore
from context.type_inference import to_numeric_canonical as _canonical_num  # type: ignore

from .auth import get_current_user, get_db_session
from .insights import build_profile, surprise_insights, suggested_questions

router = APIRouter(prefix="/api/chat", tags=["chat"])


METHODOLOGY_PROMPT = """
You are AXIOM's project-aware senior data analyst. Inside an open
project you can see **all** datasets the user uploaded — treat them as
one connected workspace. Every reply must follow a professional
methodology (CRISP-DM-aligned) and make the steps visible to the user.

──────────────────────────────────────────────────────────────────────
A. ANSWER STRUCTURE — always use these five short sections, in order:

  1. Understand — restate the user's question in one line.
  2. Identify data — name the exact dataset(s) and column(s) you will
     use, and how they relate.
  3. Plan — 2–5 bullets describing the analytical steps you'll take
     (clean → aggregate → compare → model → evaluate).
  4. Result — deliver the finding. Quote real numbers from the artifact
     payloads the tools returned. Never invent a number.
  5. Caveats — flag missing data, small samples, biased sampling,
     broken joins, or assumptions.

──────────────────────────────────────────────────────────────────────
B. TOOL USAGE — when the user asks for analysis, prefer to **invoke a
   tool** instead of describing what you would do:

  • profile_dataset(dataset_id) — column-by-column profile + surprise
    insights. Call it on first contact with a dataset.
  • make_chart(dataset_id, chart, x?, y?, bins?) — build any of
    bar / line / scatter / pie / histogram / box / heatmap.
  • predict_column(dataset_id, target) — fit a linear regression on
    numeric features; returns metrics and feature importance plus
    enough info to power a what-if slider.
  • cluster_dataset(dataset_id, k?) — KMeans on numeric columns;
    returns cluster sizes and centroids.
  • list_model() — return the project's semantic model (table roles,
    grains, primary keys, confirmed and proposed relationships, open
    clarification questions, business description). Call this on first
    contact when a project has ≥2 datasets so you understand how they
    fit together.
  • query_model(spec) — run a safe cross-table aggregation against the
    semantic model. The engine refuses to row-join summary tables onto
    detail tables, caps row output, warns on N:N fan-out and weak
    overlap, and labels inferred (unconfirmed) joins. Always pass a
    full ``spec`` ({tables, metrics:[{table,column,agg,alias}],
    group_by:[{table,column}], filters, limit}). Never hand-write the
    join — this tool picks it from the confirmed relationships first
    and falls back to inferred only when the user has not confirmed
    one. Quote the warnings/refusals in your reply verbatim.
  • explain_model() — return a plain-language summary of the semantic
    model. Useful when the user asks "what's in my data" or "how do
    these tables connect".

Each tool persists an artifact in the session, which the UI shows in a
right-side drawer. After a tool returns, summarise its result in plain
language. Always pick the tool that matches the question; chain
multiple tools when it makes sense (e.g. profile then chart then
predict).

──────────────────────────────────────────────────────────────────────
B.1 MULTI-TABLE SAFETY RULES — when the project has more than one
dataset, you MUST follow these rules:

  • Prefer **confirmed** relationships from list_model when joining
    tables. If only an inferred (unconfirmed) join is available, use
    it but PREFIX your final answer with the literal phrase
    "Using inferred link …" and name the columns.
  • REFUSE to row-join a summary table (role='summary') with a fact
    or dimension table. Aggregate the detail table to the summary
    grain first, or query the summary on its own. If the user insists,
    quote the refusal text returned by query_model.
  • If query_model returns warnings (low overlap, fan-out, truncation),
    surface them in your "Caveats" section verbatim — never hide them.
  • NEVER fabricate joined rows or invented totals. If the engine
    returns no rows, say "no matching rows" and recommend the next
    step (confirm a join, fix a column, broaden a filter).
  • When a clarification question is open against the join you'd need,
    ASK the user to answer it before running the analysis.

──────────────────────────────────────────────────────────────────────
C. STYLE RULES:
  • Answer in the same language as the user's last message
    (Arabic Levantine ↔ English as appropriate). Do not use emojis.
  • Refer to datasets by their `dataset_name` exactly as listed below.
  • Refer to columns by their real names, in backticks.
  • If the question can't be answered from the project's data, say so
    and tell the user what to upload or which column is missing.
  • Keep prose tight; prefer short bullets over paragraphs.
"""


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

TOOL_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "profile_dataset",
            "description": (
                "Build a column-by-column profile of a dataset (dtype, "
                "missingness, uniques, basic stats) and a list of "
                "surprise insights (correlations, outliers, Pareto, "
                "missingness hotspots, time-series cadence)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer"},
                },
                "required": ["dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_chart",
            "description": (
                "Render a chart over a dataset. Returns aggregated points "
                "ready for the frontend. Use 'histogram' for one numeric "
                "column, 'pie'/'bar' for category breakdowns, 'line' for "
                "time-series, 'scatter' for two numeric columns, 'box' "
                "for spread, 'heatmap' for the correlation matrix."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer"},
                    "chart": {
                        "type": "string",
                        "enum": [
                            "bar", "line", "scatter", "pie",
                            "histogram", "box", "heatmap",
                        ],
                    },
                    "x": {"type": "string"},
                    "y": {"type": "string"},
                    "aggregation": {
                        "type": "string",
                        "description": (
                            "How to aggregate Y for bar/line charts. "
                            "Defaults to the field's role-aware default "
                            "(SUM for additive measures like revenue, "
                            "AVG for percentages, COUNT for "
                            "non-numeric)."
                        ),
                        "enum": [
                            "sum", "avg", "count", "count_distinct",
                            "min", "max", "median",
                        ],
                    },
                    "bins": {"type": "integer", "default": 20},
                    "title": {"type": "string"},
                },
                "required": ["dataset_id", "chart"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "predict_column",
            "description": (
                "Fit a linear regression on the numeric columns of a "
                "dataset to predict the target column. Returns R², MAE, "
                "coefficients, feature ranges, and intercept. The "
                "coefficient/range payload is enough for the frontend to "
                "render a what-if slider — recommend slider settings in "
                "your prose."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer"},
                    "target": {"type": "string"},
                },
                "required": ["dataset_id", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cluster_dataset",
            "description": (
                "KMeans-cluster the numeric columns of a dataset. Returns "
                "cluster sizes and centroids so the user can interpret each "
                "segment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer"},
                    "k": {"type": "integer", "default": 3},
                },
                "required": ["dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_model",
            "description": (
                "Return the project's semantic model: every dataset's "
                "role (fact/dimension/summary/bridge), grain, primary "
                "key, confirmed and proposed cross-table relationships "
                "with confidence + evidence, open clarification "
                "questions, and the user-supplied business description. "
                "Call this once on first turn when the project has more "
                "than one dataset."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_model",
            "description": (
                "Run a safe cross-table aggregation against the semantic "
                "model. Returns rows + warnings + refusals. Refuses to "
                "row-join summary tables onto detail tables and labels "
                "inferred (unconfirmed) joins so you can prefix the "
                "answer with 'Using inferred link …'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Dataset names involved in the query. The "
                            "first entry is the FROM table; the rest "
                            "are joined."
                        ),
                    },
                    "metrics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "table": {"type": "string"},
                                "column": {"type": "string"},
                                "agg": {
                                    "type": "string",
                                    "enum": ["sum", "mean", "avg", "count",
                                             "min", "max", "median", "nunique"],
                                },
                                "alias": {"type": "string"},
                            },
                            "required": ["table", "column", "agg"],
                        },
                    },
                    "group_by": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "table": {"type": "string"},
                                "column": {"type": "string"},
                            },
                            "required": ["table", "column"],
                        },
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "table": {"type": "string"},
                                "column": {"type": "string"},
                                "op": {"type": "string"},
                                "value": {},
                            },
                            "required": ["column", "op"],
                        },
                    },
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["tables"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_model",
            "description": (
                "Return a plain-language summary of the semantic model — "
                "table list, roles, grains, joins, and any open "
                "questions. Use when the user asks 'what's in my data', "
                "'how do these tables connect', or wants an overview."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _load_df(
    db, dataset_id: int, user_id: int, project_id: int | None = None
) -> tuple[Any, pd.DataFrame]:
    """Load a dataset for use inside a chat tool call.

    Strict access control: the dataset must be owned by the calling
    user *and*, when a project context is supplied, must belong to
    that project. Prevents the model from cross-loading a dataset
    from another project (or any legacy `user_id IS NULL` row) just
    because it can guess the integer id.
    """
    record = models.get_dataset_record_strict(
        db, dataset_id, user_id=user_id, project_id=project_id
    )
    if not record or not record.source_parquet:
        raise ValueError(f"dataset {dataset_id} not found or has no bytes")
    df = pd.read_parquet(io.BytesIO(record.source_parquet))
    return record, df


def _run_profile(db, args: dict, ctx: dict) -> tuple[dict, list[dict]]:
    rec, df = _load_df(db, int(args["dataset_id"]), ctx["user_id"], project_id=ctx.get("project_id"))
    profile = build_profile(df)
    insights = surprise_insights(df)
    title = f"Profile — {rec.dataset_name or rec.filename}"
    artifacts: list[dict] = []
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=ctx["project_id"],
        kind="profile",
        title=title,
        params={"dataset_id": rec.id},
        result=profile,
        dataset_id=rec.id,
        pinned=True,
    )
    artifacts.append(_artifact_view(a))
    if insights:
        ins = models.save_chat_artifact(
            db,
            session_id=ctx["session_id"],
            user_id=ctx["user_id"],
            project_id=ctx["project_id"],
            kind="insight",
            title=f"Insights — {rec.dataset_name or rec.filename}",
            params={"dataset_id": rec.id},
            result={"items": insights},
            dataset_id=rec.id,
            pinned=True,
        )
        artifacts.append(_artifact_view(ins))
    summary = {
        "rows": profile["rows"],
        "cols": profile["cols"],
        "duplicate_rows": profile["duplicate_rows"],
        "top_insights": [i.get("headline") for i in insights[:5]],
    }
    return summary, artifacts


def _run_make_chart(db, args: dict, ctx: dict) -> tuple[dict, list[dict]]:
    rec, df = _load_df(db, int(args["dataset_id"]), ctx["user_id"], project_id=ctx.get("project_id"))
    chart = str(args.get("chart") or "bar").lower()
    aggregation = (args.get("aggregation") or "").lower() or None
    payload = _compute_chart_payload(
        df, chart, args.get("x"), args.get("y"),
        int(args.get("bins") or 20),
        aggregation=aggregation,
        record=rec,
    )
    title = args.get("title") or _default_chart_title(chart, args, payload)
    payload["title"] = title
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=ctx["project_id"],
        kind="chart",
        title=title,
        params={
            "dataset_id": rec.id,
            "chart": chart,
            "x": args.get("x"),
            "y": args.get("y"),
            "aggregation": payload.get("aggregation"),
            "bins": args.get("bins"),
        },
        result=payload,
        dataset_id=rec.id,
        pinned=False,
    )
    summary = {
        "chart": chart,
        "x": args.get("x"),
        "y": args.get("y"),
        "aggregation": payload.get("aggregation"),
        "y_label": payload.get("y_label"),
        "warnings": payload.get("warnings") or [],
        "calc_trace": payload.get("calc_trace") or [],
        "blocked": bool(payload.get("blocked")),
        "error": payload.get("error"),
        "points_count": len(payload.get("points") or payload.get("matrix") or []),
    }
    return summary, [_artifact_view(a)]


def _default_chart_title(chart: str, args: dict, payload: dict | None = None) -> str:
    x = args.get("x")
    y = args.get("y")
    y_label = (payload or {}).get("y_label") or y
    if chart == "scatter" and x and y:
        return f"{y} vs {x}"
    if chart in ("bar", "line") and x and y:
        return f"{y_label} by {x}"
    if chart == "histogram" and (x or y):
        return f"Distribution of {x or y}"
    if chart == "pie" and x:
        return f"Share of {x}"
    if chart == "heatmap":
        return "Correlation heatmap"
    if chart == "box":
        return "Numeric spread"
    return chart.title()


def _compute_chart_payload(df: pd.DataFrame, chart: str,
                           x: str | None, y: str | None,
                           bins: int,
                           aggregation: str | None = None,
                           record: Any | None = None) -> dict:
    """Reuses the same aggregation rules as /api/visualize.

    For ``bar`` and ``line`` charts this delegates to the central
    :mod:`backend.aggregation` engine so the chosen aggregation
    matches the field's role-aware default (SUM for additive
    measures, AVG for percentages with a warning, COUNT for
    non-numeric).  Histograms / pies / scatters / box / heatmap keep
    their existing inline logic since none of them aggregate a
    measure across categories.
    """
    import numpy as np
    from . import aggregation as _agg

    def _ensure(col: str | None) -> str:
        if not col or col not in df.columns:
            raise ValueError(f"column '{col}' not in dataset")
        return col

    field_meta: dict[str, dict[str, Any]] = {}
    if record is not None:
        try:
            field_meta = _agg.merge_field_meta(
                _agg.infer_field_meta(df),
                (record.summary_stats or {}).get("_axiom_field_meta") or {},
            )
        except Exception:
            field_meta = {}

    if chart == "histogram":
        col = _ensure(x or y)
        s = _canonical_num(df[col]).dropna()
        if s.empty:
            raise ValueError(f"column '{col}' has no numeric values")
        h, edges = np.histogram(s, bins=max(2, min(bins, 50)))
        return {
            "chart": "histogram",
            "x": col,
            "points": [
                {"bin": f"{edges[i]:.2f}–{edges[i+1]:.2f}", "count": int(h[i])}
                for i in range(len(h))
            ],
        }
    if chart == "pie":
        col = _ensure(x)
        c = df[col].dropna().astype(str).value_counts().head(30)
        return {
            "chart": "pie", "x": col,
            "points": [{"name": str(k), "value": int(v)} for k, v in c.items()],
        }
    if chart == "box":
        if x and x in df.columns and pd.api.types.is_numeric_dtype(df[x]):
            cols = [x]
        else:
            cols = df.select_dtypes(include="number").columns.tolist()[:6]
        if not cols:
            raise ValueError("no numeric columns available for box plot")
        pts = []
        for c in cols:
            s = _canonical_num(df[c]).dropna()
            if s.empty:
                continue
            q1, m, q3 = (float(s.quantile(q)) for q in (0.25, 0.5, 0.75))
            pts.append({
                "column": c, "min": float(s.min()), "q1": q1,
                "median": m, "q3": q3, "max": float(s.max()),
                "count": int(s.size),
            })
        return {"chart": "box", "points": pts}
    if chart == "heatmap":
        from . import aggregation as _agg
        nd = _agg.numeric_frame_for_correlation(df)
        if nd.shape[1] > 12:
            nd = nd.iloc[:, :12]
        if nd.shape[1] < 2:
            raise ValueError("need at least 2 numeric columns for heatmap")
        corr = nd.corr(numeric_only=True).fillna(0.0)
        return {
            "chart": "heatmap",
            "columns": [str(c) for c in corr.columns],
            "matrix": [[float(v) for v in row] for row in corr.values.tolist()],
        }
    # bar/line/scatter need both axes — except `bar` with no y, which
    # the model often requests as "bar chart of region counts" → fall
    # back to a value_counts of x.
    xc = _ensure(x)
    if chart == "bar" and (not y or y not in df.columns):
        c = df[xc].dropna().astype(str).value_counts().head(30)
        return {
            "chart": "bar", "x": xc, "y": "count",
            "y_label": "Count", "aggregation": "count",
            "points": [{"x": str(k), "y": int(v)} for k, v in c.items()],
            "warnings": [],
        }
    yc = _ensure(y)
    if chart == "scatter":
        pair = pd.DataFrame({"x": df[xc].values, "y": df[yc].values}).dropna()
        px = _canonical_num(pair["x"])
        py = _canonical_num(pair["y"])
        sub = pd.DataFrame({"x": px, "y": py}).dropna()
        if sub.empty:
            raise ValueError("scatter needs numeric x and y")
        if len(sub) > 500:
            sub = sub.sample(500, random_state=42)
        return {
            "chart": "scatter", "x": xc, "y": yc,
            "points": [{"x": float(rx), "y": float(ry)}
                       for rx, ry in sub.itertuples(index=False, name=None)],
        }
    if chart in ("bar", "line"):
        # Route through the central aggregation engine so the chat
        # answer matches the pivot table & dashboard for the same
        # (x, y) pair.
        y_meta = field_meta.get(yc) or {}
        if aggregation and aggregation in _agg.AGGREGATIONS and aggregation != "none":
            agg_kind = aggregation
        else:
            agg_kind = (y_meta.get("default_agg") or "sum")
            if agg_kind == "none":
                agg_kind = "sum"
        date_grains: dict[str, str] = {}
        if chart == "line":
            xm = field_meta.get(xc) or {}
            if xm.get("role") == "date" or xm.get("format_kind") == "date":
                date_grains[xc] = "month"
        # Pre-flight validation routes through the same engine as the
        # pivot + dashboard endpoints — every BI surface emits the same
        # "you're summing a percentage" warnings.
        pre = _agg.validate_request(
            [xc], [],
            [{"column": yc, "aggregation": agg_kind}],
            field_meta, df.columns,
        )
        result = _agg.aggregate(
            df,
            rows=[xc],
            cols=[],
            measures=[{"column": yc, "aggregation": agg_kind}],
            date_grains=date_grains,
            field_meta=field_meta,
        )
        max_pts = 30 if chart == "bar" else 500
        rows = result["rows"][:max_pts]
        m0 = result["measures"][0] if result["measures"] else {}
        warnings = list(dict.fromkeys((pre or []) + (result.get("warnings") or [])))
        # Pull the calc trace for the measure column so the chart-level
        # explainer can cite parser diagnostics (valid_rows, parse_mode,
        # implied per-row magnitude) the same way the pivot table does.
        calc_trace = result.get("calc_trace") or []
        return {
            "chart": chart, "x": xc, "y": yc,
            "y_label": m0.get("label") or yc,
            "aggregation": agg_kind,
            "format_kind": m0.get("format_kind"),
            "points": [
                {"x": r["_dims"].get(xc), "y": r.get("m0")}
                for r in rows if r.get("m0") is not None
            ],
            "warnings": warnings,
            "grand_total": result.get("grand_total", {}).get("m0"),
            "calc_trace": calc_trace,
            "blocked": bool(result.get("blocked")),
            "error": result.get("error"),
        }
    raise ValueError(f"unknown chart '{chart}'")


PREDICT_MIN_ROWS = 10


def _small_sample_predict_notice(
    rows_available: int,
    target: str,
    min_required: int = PREDICT_MIN_ROWS,
) -> dict:
    """Friendly bilingual (EN + Levantine Arabic) note explaining why the
    prediction tool can't run on a tiny dataset. Returned in place of an
    exception so the chat surfaces a calm assistant message instead of a
    red "Fit prediction model failed: ..." stack-trace box.
    """
    rows_available = int(rows_available)
    min_required = int(min_required)
    en = (
        f"I can't fit a prediction model for `{target}` on this dataset — "
        f"only {rows_available} usable row"
        f"{'s' if rows_available != 1 else ''} are left after dropping "
        f"missing values, and the model needs at least {min_required}. "
        "Try uploading a larger dataset, or pick another tool — for "
        "example, profile the dataset or build a chart to explore what "
        "you have."
    )
    ar = (
        f"ما فيني أبني موديل تنبؤ لـ `{target}` على هاي الداتا — "
        f"في {rows_available} صفّ مفيد بس بعد ما شِلنا القيم الناقصة، "
        f"والموديل بدّو على الأقل {min_required} صفّ. "
        "جرّب ترفع داتاسِت أكبر، أو استخدم أداة تانية متل عمل بروفايل "
        "للداتاسِت أو رسم تشارت لتستكشف اللي عندك."
    )
    return {
        "kind": "small_sample_notice",
        "target": target,
        "rows_available": rows_available,
        "rows_required": min_required,
        "message_en": en,
        "message_ar": ar,
        "suggested_tools": ["profile_dataset", "make_chart"],
    }


def _run_predict(db, args: dict, ctx: dict) -> tuple[dict, list[dict]]:
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    rec, df = _load_df(db, int(args["dataset_id"]), ctx["user_id"], project_id=ctx.get("project_id"))
    target = str(args["target"])
    if target not in df.columns:
        raise ValueError(f"column '{target}' not in dataset")
    if not pd.api.types.is_numeric_dtype(df[target]):
        raise ValueError(f"column '{target}' is not numeric")
    numeric = df.select_dtypes(include="number").dropna()
    if target not in numeric.columns:
        raise ValueError(f"target '{target}' lost all values after dropna")
    feats = [c for c in numeric.columns if c != target]
    if not feats:
        raise ValueError("need at least one other numeric column")
    X = numeric[feats]
    y = numeric[target]
    if len(X) < PREDICT_MIN_ROWS:
        # Don't raise — a "tiny sample" is a user-input issue, not a bug.
        # Return a friendly bilingual notice (and no artifact) so the
        # chat shows a readable assistant note instead of a red error.
        notice = _small_sample_predict_notice(len(X), target, PREDICT_MIN_ROWS)
        return (
            {
                "ok": True,
                "skipped": "small_sample",
                "kind": "small_sample_notice",
                "target": target,
                "rows_available": notice["rows_available"],
                "rows_required": notice["rows_required"],
                "notice": notice,
            },
            [],
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    model = LinearRegression()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    r2 = float(r2_score(y_test, y_pred))
    mae = float(mean_absolute_error(y_test, y_pred))

    coefs = list(zip(feats, model.coef_.tolist()))
    importance = sorted(
        ({"feature": f, "importance": round(abs(c), 5), "coefficient": round(c, 5)}
         for f, c in coefs),
        key=lambda r: r["importance"],
        reverse=True,
    )
    feature_ranges = {
        f: {
            "min": float(X[f].min()),
            "max": float(X[f].max()),
            "mean": float(X[f].mean()),
        }
        for f in feats
    }
    feature_means = {f: float(X[f].mean()) for f in feats}
    linear_coefs = {f: float(c) for f, c in coefs}
    intercept_f = float(model.intercept_)
    baseline_prediction = intercept_f + sum(
        linear_coefs[f] * feature_means[f] for f in feats
    )
    payload = {
        "target": target,
        "model": "LinearRegression",
        "metrics": {"r2": round(r2, 4), "mae": round(mae, 4),
                    "n_train": int(len(X_train)), "n_test": int(len(X_test))},
        "intercept": intercept_f,
        "feature_importance": importance[:25],
        "feature_ranges": feature_ranges,
        # The next three are what `what_if_recommendations()` needs to
        # synthesise the deterministic ±10/±25 % "if X changes by Δ,
        # predicted Y becomes…" table in the Final Report + PDF.
        "feature_means": feature_means,
        "linear_coefs": linear_coefs,
        "baseline_prediction": float(baseline_prediction),
        "top_features": importance[:8],
    }
    title = f"Predict {target} — {rec.dataset_name or rec.filename}"
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=ctx["project_id"],
        kind="prediction",
        title=title,
        params={"dataset_id": rec.id, "target": target},
        result=payload,
        dataset_id=rec.id,
        pinned=False,
    )
    return {
        "target": target,
        "r2": round(r2, 4),
        "mae": round(mae, 4),
        "top_features": [r["feature"] for r in importance[:5]],
    }, [_artifact_view(a)]


def _run_cluster(db, args: dict, ctx: dict) -> tuple[dict, list[dict]]:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    rec, df = _load_df(db, int(args["dataset_id"]), ctx["user_id"], project_id=ctx.get("project_id"))
    k = max(2, min(int(args.get("k") or 3), 10))
    numeric = df.select_dtypes(include="number").dropna()
    if numeric.shape[1] < 2:
        raise ValueError("need at least 2 numeric columns for clustering")
    if len(numeric) < k * 5:
        raise ValueError(f"need at least {k*5} rows for {k} clusters")
    X = StandardScaler().fit_transform(numeric)
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)
    sizes: dict[str, int] = {}
    for lbl in labels:
        key = str(int(lbl))
        sizes[key] = sizes.get(key, 0) + 1
    centroids = []
    for i, c in enumerate(km.cluster_centers_):
        # report centroids back in original units (un-standardised)
        centroids.append(
            {
                "cluster": i,
                "size": sizes.get(str(i), 0),
                "values": {
                    col: round(float(numeric.iloc[labels == i][col].mean()), 4)
                    for col in numeric.columns[:8]
                },
            }
        )
    # 2D PCA projection so the drawer can render a real cluster
    # scatter plot instead of just numeric centroid tables. Down-
    # sample to ~400 points to keep the JSON payload tiny.
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(X)
    n_pts = len(coords)
    if n_pts > 400:
        rng = np.random.default_rng(42)
        idx = rng.choice(n_pts, size=400, replace=False)
    else:
        idx = np.arange(n_pts)
    scatter = [
        {
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "cluster": int(labels[i]),
        }
        for i in idx
    ]
    explained = pca.explained_variance_ratio_.tolist()
    payload = {
        "method": "kmeans",
        "k": k,
        "cluster_sizes": sizes,
        "centroids": centroids,
        "features_used": list(numeric.columns),
        "scatter": scatter,
        "pca": {
            "explained_variance_ratio": [round(float(v), 4) for v in explained],
            "sampled": int(len(scatter)),
            "total": int(n_pts),
        },
    }
    title = f"Cluster (k={k}) — {rec.dataset_name or rec.filename}"
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=ctx["project_id"],
        kind="cluster",
        title=title,
        params={"dataset_id": rec.id, "k": k},
        result=payload,
        dataset_id=rec.id,
        pinned=False,
    )
    return {"k": k, "sizes": sizes}, [_artifact_view(a)]


def _semantic_bundle(db, project_id: int, user_id: int) -> dict:
    """Local re-export of the data_model bundle so we don't have to
    pull a router import into chat.py. Mirrors the GET endpoint."""
    from .data_model import _bundle, refresh_project_model
    bundle = _bundle(db, project_id, user_id)
    if not bundle.get("tables"):
        # First-touch: profile the project so the assistant has
        # something to work with.
        bundle = refresh_project_model(db, project_id, user_id)
    return bundle


def _run_list_model(db, args: dict, ctx: dict) -> tuple[dict, list]:
    project_id = ctx.get("project_id")
    if not project_id:
        raise ValueError("list_model requires a project context")
    bundle = _semantic_bundle(db, project_id, ctx["user_id"])
    title = "Data model"
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=project_id,
        kind="data_model",
        title=title,
        params={},
        result=bundle,
        dataset_id=None,
        pinned=False,
    )
    summary = {
        "tables": [
            {"name": t["dataset_name"], "role": t["role"],
             "rows": t["rows"], "grain": (t.get("grain") or {}).get("label"),
             "confirmed": t["confirmed"]}
            for t in bundle.get("tables", [])
        ],
        "relationships": [
            {"left": f"{r['left_table']}.{r['left_column']}",
             "right": f"{r['right_table']}.{r['right_column']}",
             "status": r["status"], "band": r["band"],
             "confidence": r["confidence"], "evidence": r["evidence"]}
            for r in bundle.get("relationships", [])
        ],
        "questions": [
            {"id": q["id"], "kind": q["kind"], "prompt": q["prompt"]}
            for q in bundle.get("questions", [])
        ],
        "description": bundle.get("description"),
    }
    return summary, [_artifact_view(a)]


def _run_query_model(db, args: dict, ctx: dict) -> tuple[dict, list]:
    project_id = ctx.get("project_id")
    if not project_id:
        raise ValueError("query_model requires a project context")
    bundle = _semantic_bundle(db, project_id, ctx["user_id"])
    name_by_id = {d["id"]: d["name"] for d in bundle.get("datasets", [])}

    # Load frames for every dataset in the project so the join planner
    # can chain through intermediates if needed.
    records = (
        db.query(models.DatasetRecord)
        .filter(models.DatasetRecord.project_id == project_id,
                models.DatasetRecord.user_id == ctx["user_id"])
        .all()
    )
    frames_by_name: dict[str, pd.DataFrame] = {}
    for r in records:
        if not r.source_parquet:
            continue
        try:
            frames_by_name[r.dataset_name or r.filename or f"dataset_{r.id}"] = \
                pd.read_parquet(io.BytesIO(r.source_parquet))
        except Exception:
            continue

    confirmed = [
        {
            "left_table": r["left_table"], "left_column": r["left_column"],
            "right_table": r["right_table"], "right_column": r["right_column"],
            "cardinality": r["cardinality"], "overlap_score": r["overlap_score"],
            "confidence": r.get("confidence"), "band": r.get("band"),
            "status": r.get("status"),
        }
        for r in bundle.get("relationships", [])
        if r["status"] == "confirmed"
    ]
    inferred = [
        {
            "left_table": r["left_table"], "left_column": r["left_column"],
            "right_table": r["right_table"], "right_column": r["right_column"],
            "cardinality": r["cardinality"], "overlap_score": r["overlap_score"],
            "confidence": r.get("confidence"), "band": r.get("band"),
            "status": r.get("status"),
        }
        for r in bundle.get("relationships", [])
        if r["status"] == "proposed" and r["band"] in ("high", "medium", "low", "inferred")
    ]
    profiles_for_query = [
        {
            "name": t["dataset_name"],
            "role": t["role"],
            "grain": t.get("grain") or {},
            "rows": t["rows"], "cols": t["cols"],
        }
        for t in bundle.get("tables", [])
    ]

    spec = dict(args or {})
    result = sm.safe_query_model(
        spec=spec,
        profiles=profiles_for_query,
        confirmed=confirmed,
        inferred=inferred,
        frames=frames_by_name,
    )
    payload = result.to_dict()

    title = "Cross-table query"
    if spec.get("tables"):
        title = "Query: " + " + ".join(str(t) for t in spec["tables"])
    a = models.save_chat_artifact(
        db,
        session_id=ctx["session_id"],
        user_id=ctx["user_id"],
        project_id=project_id,
        kind="data_model_query",
        title=title,
        params=spec,
        result=payload,
        dataset_id=None,
        pinned=False,
    )
    # Build a join-path summary the assistant MUST cite verbatim per
    # the methodology prompt's safety rules. Each entry includes the
    # exact left/right pair, the cardinality, status, and the
    # confidence band so the answer can label its provenance.
    def _path_entry(r: dict, kind: str) -> dict:
        return {
            "kind": kind,  # "confirmed" or "inferred"
            "left": f"{r.get('left_table')}.{r.get('left_column')}",
            "right": f"{r.get('right_table')}.{r.get('right_column')}",
            "cardinality": r.get("cardinality"),
            "confidence": r.get("confidence"),
            "band": r.get("band"),
            "status": r.get("status"),
        }
    used_path = (
        [_path_entry(r, "confirmed") for r in payload.get("used_relationships", [])]
        + [_path_entry(r, "inferred") for r in payload.get("inferred_joins", [])]
    )
    summary = {
        "row_count": len(payload["rows"]),
        "columns": payload["columns"],
        "warnings": payload["warnings"],
        "refusals": payload["refusals"],
        "join_path": used_path,
        "uses_inferred_join": bool(payload.get("inferred_joins")),
        "inferred_joins": [
            f"{r['left_table']}.{r['left_column']} ↔ {r['right_table']}.{r['right_column']}"
            for r in payload["inferred_joins"]
        ],
        "preview": payload["rows"][:10],
        "sql_like": payload["sql_like"],
    }
    return summary, [_artifact_view(a)]


def _run_explain_model(db, args: dict, ctx: dict) -> tuple[dict, list]:
    project_id = ctx.get("project_id")
    if not project_id:
        raise ValueError("explain_model requires a project context")
    bundle = _semantic_bundle(db, project_id, ctx["user_id"])
    profiles = [
        {
            "name": t["dataset_name"],
            "role": t["role"],
            "rows": t["rows"], "cols": t["cols"],
            "grain": t.get("grain") or {},
            "suspicious": t.get("suspicious") or [],
        }
        for t in bundle.get("tables", [])
    ]
    rels = [
        {
            "left_table": r["left_table"], "left_column": r["left_column"],
            "right_table": r["right_table"], "right_column": r["right_column"],
            "cardinality": r["cardinality"],
            "status": r["status"], "band": r["band"],
            "confidence": r["confidence"],
        }
        for r in bundle.get("relationships", [])
    ]
    text = sm.explain_model_text(profiles, rels, bundle.get("description"))
    return {"explanation": text}, []


_TOOL_HANDLERS = {
    "profile_dataset": _run_profile,
    "make_chart": _run_make_chart,
    "predict_column": _run_predict,
    "cluster_dataset": _run_cluster,
    "list_model": _run_list_model,
    "query_model": _run_query_model,
    "explain_model": _run_explain_model,
}


def _artifact_view(a) -> dict:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "project_id": a.project_id,
        "dataset_id": a.dataset_id,
        "kind": a.kind,
        "title": a.title,
        "params": a.params or {},
        "result": a.result or {},
        "pinned": bool(a.pinned),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    messages: list[ChatMessage]
    session_id: int | None = None
    dataset_id: int | None = None
    project_id: int | None = None
    # API vocabulary ("guided" / "expert"). When provided, the chat
    # stream forwards it through ai_assistant._apply_mode_directive so
    # the assistant follows the matching response format. Falls back to
    # the user's preference when omitted.
    assistant_mode: str | None = None


# ---------------------------------------------------------------------------
# Helpers (data context, KB, learned notes, auto-title)
# ---------------------------------------------------------------------------

def _df_block(name: str, df: pd.DataFrame, dataset_id: int) -> dict:
    if df is None or df.empty:
        return {"id": dataset_id, "name": name, "rows": 0, "cols": 0, "columns": [], "head": []}
    return {
        "id": dataset_id,
        "name": name,
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "columns": [{"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
        "head": df.head(5).to_dict(orient="records"),
    }


def _load_project_datasets(db, project_id: int, user_id: int) -> list[dict]:
    rows = (
        db.query(models.DatasetRecord)
        .filter(
            models.DatasetRecord.project_id == project_id,
            models.DatasetRecord.user_id == user_id,
        )
        .order_by(models.DatasetRecord.id.asc())
        .all()
    )
    out: list[dict] = []
    for r in rows:
        df = None
        try:
            if r.source_parquet:
                df = pd.read_parquet(io.BytesIO(r.source_parquet))
        except Exception:
            df = None
        out.append(_df_block(r.dataset_name or r.filename or f"dataset_{r.id}",
                             df, r.id))
    return out


def _load_relationships(db, dataset_ids: list[int]) -> list[dict]:
    if not dataset_ids:
        return []
    rels = (
        db.query(models.DatasetRelationship)
        .filter(
            models.DatasetRelationship.left_dataset_id.in_(dataset_ids)
            | models.DatasetRelationship.right_dataset_id.in_(dataset_ids)
        )
        .all()
    )
    return [
        {
            "left_dataset_id": r.left_dataset_id,
            "left_column": r.left_column,
            "right_dataset_id": r.right_dataset_id,
            "right_column": r.right_column,
            "cardinality": r.cardinality,
            "join_type": r.join_type,
        }
        for r in rels
    ]


def _project_knowledge(db, project_id: int, user_id: int) -> str | None:
    proj = models.get_project(db, project_id, user_id)
    if not proj:
        return None
    try:
        from knowledge_base import build_context_block
    except Exception:
        return None
    try:
        ctx = models.get_project_ai_context(db, project_id)
        return build_context_block(ctx) if ctx else None
    except Exception:
        return None


def _recent_learned_notes(db, project_id: int, user_id: int, limit: int = 6) -> list[str]:
    notes = (
        db.query(models.ProjectLearnedNote)
        .join(models.Project, models.Project.id == models.ProjectLearnedNote.project_id)
        .filter(
            models.ProjectLearnedNote.project_id == project_id,
            models.Project.user_id == user_id,
        )
        .order_by(models.ProjectLearnedNote.created_at.desc())
        .limit(limit)
        .all()
    )
    return [n.content[:600] for n in notes]


def _auto_title(text: str) -> str:
    snippet = " ".join((text or "").split())
    if not snippet:
        return "New chat"
    return snippet[:60] + ("…" if len(snippet) > 60 else "")


def _event(obj: dict) -> bytes:
    return (json.dumps(obj, default=str) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/stream")
async def stream(
    req: ChatStreamRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    if not req.messages:
        raise HTTPException(400, "messages required")
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if last_user is None:
        raise HTTPException(400, "no user message")

    session = None
    project_id: int | None = None
    if req.session_id:
        session = models.get_chat_session(db, req.session_id, user.id)
        if not session:
            raise HTTPException(404, "Chat session not found")
        project_id = session.project_id
    elif req.project_id:
        proj = models.get_project(db, req.project_id, user.id)
        if not proj:
            raise HTTPException(404, "Project not found")
        project_id = req.project_id

    datasets_ctx: list[dict] = []
    if project_id:
        datasets_ctx = _load_project_datasets(db, project_id, user.id)
    elif req.dataset_id:
        record = models.get_dataset_record(db, req.dataset_id, user_id=user.id)
        if record and record.source_parquet:
            df = pd.read_parquet(io.BytesIO(record.source_parquet))
            datasets_ctx = [
                _df_block(record.dataset_name or record.filename or "dataset",
                          df, record.id)
            ]

    relationships = _load_relationships(
        db, [d.get("id") for d in datasets_ctx if d.get("id")]
    )
    kb_text = _project_knowledge(db, project_id, user.id) if project_id else None
    learned = _recent_learned_notes(db, project_id, user.id) if project_id else []

    user_lang = ai_assistant.detect_language(last_user.content)

    # Resolve effective Guided/Expert mode: per-project override beats
    # the request-supplied mode beats the user-level preference. Defaults
    # to Guided when nothing is set. We then map back to the legacy
    # "simple" / "expert" labels that ai_assistant._apply_mode_directive
    # understands.
    def _normalize_api_mode(value: str | None) -> str | None:
        cleaned = (str(value or "")).strip().lower()
        if cleaned in ("guided", "simple"):
            return "guided"
        if cleaned == "expert":
            return "expert"
        return None

    effective_mode = None
    if project_id:
        proj_obj = models.get_project(db, project_id, user.id)
        effective_mode = _normalize_api_mode(getattr(proj_obj, "mode", None))
    if effective_mode is None:
        effective_mode = _normalize_api_mode(req.assistant_mode)
    if effective_mode is None:
        effective_mode = _normalize_api_mode(getattr(user, "assistant_mode", None))
    if effective_mode is None:
        effective_mode = "guided"
    storage_mode = "simple" if effective_mode == "guided" else "expert"

    system_parts = [
        ai_assistant._apply_mode_directive(ai_assistant.SYSTEM_PROMPT, storage_mode),
        METHODOLOGY_PROMPT,
    ]
    # Behavioural deltas the chat UX is built around.
    if effective_mode == "guided":
        system_parts.append(
            "## ACTIVE WORKSPACE MODE — GUIDED\n"
            "The user is in Guided Mode. Speak like a calm, friendly\n"
            "human analyst — NOT like a textbook, NOT like a chatbot.\n"
            "\n"
            "### Tone & voice\n"
            "  • Mirror the user's language exactly: if they wrote in\n"
            "    Arabic, reply in simple Levantine Arabic (لهجة شامية\n"
            "    سهلة، كأنك بتحكي مع صديق); if they wrote in English,\n"
            "    reply in plain English at roughly an 8th-grade reading\n"
            "    level. Never mix languages mid-sentence.\n"
            "  • Length sweet-spot: 1–2 short paragraphs OR 3–5 bullet\n"
            "    points. Aim for ~80–150 words. Skip the preamble — open\n"
            "    on the answer, not on 'Great question!' or 'Sure, let\n"
            "    me…'.\n"
            "  • Use concrete, everyday words. Replace statistics jargon\n"
            "    with the human meaning:\n"
            "      - say 'how spread out the values are' not 'variance'\n"
            "      - say 'unusual values' not 'outliers'\n"
            "      - say 'how strongly two columns move together' not\n"
            "        'correlation coefficient'\n"
            "      - say 'a guess based on patterns' not 'prediction\n"
            "        from the model'\n"
            "    If you absolutely must use a technical term, put a one\n"
            "    line plain-language definition right after it in\n"
            "    parentheses.\n"
            "  • Always anchor numbers to something the user cares about.\n"
            "    Instead of 'mean income = 64,231', say 'on average each\n"
            "    person earns about 64K — roughly the middle of the\n"
            "    pack'. Compare, don't just report.\n"
            "  • No code blocks, no JSON, no SQL, no formulas, no Greek\n"
            "    letters, no p-values, no model names. If a chart or\n"
            "    table answers the question better than words, just say\n"
            "    'I'll show you on a chart' and trigger the right tool.\n"
            "  • End every reply with exactly one short, plain-language\n"
            "    next-step suggestion phrased as an offer (e.g. 'Want me\n"
            "    to break this down by region?' / 'بدّك أقسّملك\n"
            "    الأرقام حسب المنطقة؟'), NOT a command.\n"
            "\n"
            "### Expert-mode handoff (IMPORTANT — overrides any earlier\n"
            "'do not offer to switch modes' instruction)\n"
            "Guided Mode cannot express genuinely advanced asks. When the\n"
            "user clearly wants something Guided can't deliver, you MUST\n"
            "still answer their question in plain language first, then\n"
            "append — on a single final line, with no other text after it —\n"
            "the literal sentinel:\n"
            "    [switch_to_expert] <one short reason, ≤ 90 chars>\n"
            "The sentinel is NOT a verbal question to the user; the UI\n"
            "parses it and renders an inline 'Open in Expert Mode' button.\n"
            "Never wrap it in quotes, code fences, or markdown. Never put\n"
            "anything on the line after it. Emit it at most once per reply.\n"
            "\n"
            "Trigger the handoff when the user asks for any of these:\n"
            "  • Specific algorithms or libraries (XGBoost, LightGBM, ARIMA,\n"
            "    Prophet, SARIMA, Random Forest, SVM, GLM, GBM, statsmodels,\n"
            "    PyTorch, TensorFlow, sklearn pipelines).\n"
            "  • Hyperparameter tuning, grid/random/Bayesian search, learning\n"
            "    rate / max_depth / regularisation / kernel choice, manual\n"
            "    train/test split, cross-validation folds, early stopping.\n"
            "  • Statistical tests by name (t-test, ANOVA, chi-square,\n"
            "    Ljung–Box, Dickey–Fuller / ADF / KPSS, Shapiro–Wilk,\n"
            "    Mann–Whitney, Kolmogorov–Smirnov, Granger causality).\n"
            "  • Raw metric numbers as the deliverable (R², adjusted R²,\n"
            "    p-values, AIC/BIC, RMSE/MAPE/MAE breakdowns by fold,\n"
            "    confusion matrix, ROC AUC, log-loss, residual diagnostics).\n"
            "  • Custom feature engineering, encoding schemes (one-hot vs\n"
            "    target vs ordinal), scaling choices, PCA components, SHAP\n"
            "    values, partial-dependence plots.\n"
            "  • Writing or editing Python / SQL / R / pandas / numpy code,\n"
            "    or asking for a notebook / script / JSON config.\n"
            "  • Time-series concepts the chat tools don't cover (seasonal\n"
            "    decomposition, residual autocorrelation, stationarity).\n"
            "\n"
            "Do NOT trigger the handoff for ordinary business questions\n"
            "such as 'show me top customers', 'plot revenue by month',\n"
            "'what's the average order value', 'are there missing values',\n"
            "'cluster my customers into 3 groups' — Guided handles those.\n"
            "\n"
            "Examples (assistant's final line only):\n"
            "  User: 'Tune the XGBoost learning rate on my churn data.'\n"
            "  → [switch_to_expert] Hyperparameter tuning needs Expert Mode.\n"
            "\n"
            "  User: 'Run a Ljung–Box test on the residuals.'\n"
            "  → [switch_to_expert] Statistical tests by name live in Expert Mode.\n"
            "\n"
            "  User: 'Give me R², adjusted R² and AIC for the regression.'\n"
            "  → [switch_to_expert] Switch to Expert Mode for the full metric breakdown.\n"
            "\n"
            "  User: 'Write the Python code for the KMeans pipeline.'\n"
            "  → [switch_to_expert] Code is only emitted in Expert Mode.\n"
            "\n"
            "  User: 'Show me revenue by region.' → no sentinel."
        )
    else:
        system_parts.append(
            "## ACTIVE WORKSPACE MODE — EXPERT\n"
            "The user is in Expert Mode. Use full technical vocabulary —\n"
            "name the algorithm, list its parameters, quote real metrics, and\n"
            "show JSON / code where it helps. If the user asks a broad or\n"
            "business-flavoured question, lead with a one-paragraph plain-\n"
            "language summary, then continue with the technical breakdown."
        )
    if user_lang == "ar":
        system_parts.append(
            "The user is writing in Arabic; reply in clear Levantine Arabic."
        )
    elif user_lang and user_lang != "en":
        system_parts.append(
            f"The user is writing in {user_lang}; reply in the same language."
        )
    if datasets_ctx:
        ds_summary = {
            "project_id": project_id,
            "dataset_count": len(datasets_ctx),
            "datasets": datasets_ctx,
            "relationships": relationships,
        }
        system_parts.append(
            "Project data context (JSON):\n" + json.dumps(ds_summary, default=str)[:9000]
        )
    else:
        system_parts.append(
            "This project currently has no uploaded datasets. Ask the user "
            "to upload data before attempting numeric analysis."
        )
    if kb_text:
        system_parts.append(
            "Project knowledge base (user-attached reference text):\n" + kb_text
        )
    if learned:
        system_parts.append(
            "Recent project notes (most recent first):\n- " + "\n- ".join(learned)
        )

    system = "\n\n".join(system_parts)

    msgs: list[dict] = [{"role": "system", "content": system}]
    if session is not None:
        history = models.get_session_messages(db, session.id)
        for h in history:
            if h.user_message:
                msgs.append({"role": "user", "content": h.user_message})
            if h.ai_response:
                msgs.append({"role": "assistant", "content": h.ai_response})
        msgs.append({"role": "user", "content": last_user.content})
    else:
        for m in req.messages:
            if m.role in ("user", "assistant"):
                msgs.append({"role": m.role, "content": m.content})

    api_key = (
        os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    if not api_key:
        async def fallback() -> Iterator[bytes]:
            yield _event(
                {"type": "text", "data": "OpenAI key is not configured on the backend; chat is offline."}
            )
            yield _event({"type": "done"})
        return StreamingResponse(fallback(), media_type="application/x-ndjson")

    from openai import OpenAI

    client = (
        OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    )

    will_auto_title = False
    if session is not None and (session.title or "").strip().lower() in ("", "new chat"):
        prior = models.get_session_messages(db, session.id, limit=1)
        if not prior:
            will_auto_title = True

    tool_ctx = {
        "user_id": user.id,
        "project_id": project_id,
        "session_id": session.id if session else None,
    }
    tools_enabled = session is not None and project_id is not None and bool(datasets_ctx)

    def producer() -> Iterator[bytes]:
        final_text = ""
        try:
            for hop in range(4):
                kwargs: dict[str, Any] = {
                    "model": "gpt-4o",
                    "messages": msgs,
                    "temperature": 0.4,
                }
                if tools_enabled:
                    kwargs["tools"] = TOOL_SCHEMA
                    kwargs["tool_choice"] = "auto"
                resp = client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []

                if tool_calls and tools_enabled:
                    msgs.append(
                        {
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments or "{}",
                                    },
                                }
                                for tc in tool_calls
                            ],
                        }
                    )
                    if msg.content:
                        yield _event({"type": "text", "data": msg.content})
                        final_text += msg.content
                    for tc in tool_calls:
                        name = tc.function.name
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        yield _event(
                            {
                                "type": "tool_started",
                                "tool": name,
                                "params": args,
                                "call_id": tc.id,
                            }
                        )
                        handler = _TOOL_HANDLERS.get(name)
                        try:
                            if not handler:
                                raise ValueError(f"unknown tool '{name}'")
                            summary, artifacts = handler(db, args, tool_ctx)
                            tool_payload = {"ok": True, "summary": summary}
                            yield _event(
                                {
                                    "type": "tool_finished",
                                    "tool": name,
                                    "call_id": tc.id,
                                    "ok": True,
                                    "summary": summary,
                                    "artifacts": artifacts,
                                }
                            )
                        except Exception as e:
                            tool_payload = {"ok": False, "error": str(e)}
                            yield _event(
                                {
                                    "type": "tool_finished",
                                    "tool": name,
                                    "call_id": tc.id,
                                    "ok": False,
                                    "error": str(e),
                                }
                            )
                        msgs.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": json.dumps(tool_payload, default=str)[:6000],
                            }
                        )
                    continue
                # No tool calls — final text response.
                if msg.content:
                    final_text += msg.content
                    yield _event({"type": "text", "data": msg.content})
                break
        except Exception as e:
            yield _event({"type": "error", "data": f"chat error: {e}"})
        finally:
            try:
                if session is not None:
                    models.save_chat_message(
                        db,
                        session_id=session.id,
                        user_message=last_user.content,
                        ai_response=final_text,
                    )
                    if will_auto_title:
                        models.rename_chat_session(
                            db, session.id, user.id, _auto_title(last_user.content)
                        )
                    if project_id:
                        try:
                            note = models.ProjectLearnedNote(
                                project_id=project_id,
                                kind="chat",
                                content=f"Q: {last_user.content[:300]}\nA: {final_text[:600]}",
                            )
                            db.add(note)
                            db.commit()
                        except Exception:
                            db.rollback()
                elif req.dataset_id:
                    models.save_chat_message(
                        db,
                        dataset_id=req.dataset_id,
                        user_message=last_user.content,
                        ai_response=final_text,
                    )
            except Exception:
                pass
            yield _event({"type": "done"})

    return StreamingResponse(producer(), media_type="application/x-ndjson")
