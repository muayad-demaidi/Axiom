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

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import models  # type: ignore
import ai_assistant  # type: ignore

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

Each tool persists an artifact in the session, which the UI shows in a
right-side drawer. After a tool returns, summarise its result in plain
language. Always pick the tool that matches the question; chain
multiple tools when it makes sense (e.g. profile then chart then
predict).

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
    payload = _compute_chart_payload(df, chart, args.get("x"), args.get("y"),
                                     int(args.get("bins") or 20))
    title = args.get("title") or _default_chart_title(chart, args)
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
        "points_count": len(payload.get("points") or payload.get("matrix") or []),
    }
    return summary, [_artifact_view(a)]


def _default_chart_title(chart: str, args: dict) -> str:
    x = args.get("x")
    y = args.get("y")
    if chart == "scatter" and x and y:
        return f"{y} vs {x}"
    if chart in ("bar", "line") and x and y:
        return f"{y} by {x}"
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
                           bins: int) -> dict:
    """Reuses the same aggregation rules as /api/visualize."""
    import numpy as np

    def _ensure(col: str | None) -> str:
        if not col or col not in df.columns:
            raise ValueError(f"column '{col}' not in dataset")
        return col

    if chart == "histogram":
        col = _ensure(x or y)
        s = pd.to_numeric(df[col], errors="coerce").dropna()
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
            s = pd.to_numeric(df[c], errors="coerce").dropna()
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
        nd = df.select_dtypes(include="number")
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
            "points": [{"x": str(k), "y": int(v)} for k, v in c.items()],
        }
    yc = _ensure(y)
    pair = pd.DataFrame({"x": df[xc].values, "y": df[yc].values}).dropna()
    if chart == "scatter":
        px = pd.to_numeric(pair["x"], errors="coerce")
        py = pd.to_numeric(pair["y"], errors="coerce")
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
    if chart == "bar":
        if pair.empty:
            raise ValueError("no rows after dropping nulls")
        yn = pd.to_numeric(pair["y"], errors="coerce")
        if yn.notna().any():
            sub = pair.assign(_y=yn).dropna(subset=["_y"])
            g = sub.groupby(sub["x"].astype(str))["_y"].mean().sort_values(ascending=False).head(30)
            return {"chart": "bar", "x": xc, "y": f"mean({yc})",
                    "points": [{"x": str(k), "y": float(v)} for k, v in g.items()]}
        c = pair["x"].astype(str).value_counts().head(30)
        return {"chart": "bar", "x": xc, "y": "count",
                "points": [{"x": str(k), "y": int(v)} for k, v in c.items()]}
    if chart == "line":
        if pair.empty:
            raise ValueError("no rows after dropping nulls")
        yn = pd.to_numeric(pair["y"], errors="coerce")
        if not yn.notna().any():
            raise ValueError("line chart needs numeric y")
        sub = pair.assign(_y=yn).dropna(subset=["_y"])
        x_dt = pd.to_datetime(sub["x"], errors="coerce")
        x_num = pd.to_numeric(sub["x"], errors="coerce")
        thr = max(3, int(0.6 * len(sub)))
        if x_dt.notna().sum() >= thr:
            ord_ = sub.assign(_x=x_dt).dropna(subset=["_x"]).sort_values("_x")
            pts = [{"x": d.isoformat(), "y": float(v)}
                   for d, v in zip(ord_["_x"], ord_["_y"])]
        elif x_num.notna().sum() >= thr:
            ord_ = sub.assign(_x=x_num).dropna(subset=["_x"]).sort_values("_x")
            pts = [{"x": float(d), "y": float(v)}
                   for d, v in zip(ord_["_x"], ord_["_y"])]
        else:
            g = sub.groupby(sub["x"].astype(str))["_y"].mean()
            pts = [{"x": str(k), "y": float(v)} for k, v in g.items()]
        if len(pts) > 500:
            step = max(1, len(pts) // 500)
            pts = pts[::step]
        return {"chart": "line", "x": xc, "y": yc, "points": pts}
    raise ValueError(f"unknown chart '{chart}'")


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
    if len(X) < 10:
        raise ValueError("need at least 10 rows after dropna")

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
    payload = {
        "method": "kmeans",
        "k": k,
        "cluster_sizes": sizes,
        "centroids": centroids,
        "features_used": list(numeric.columns),
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


_TOOL_HANDLERS = {
    "profile_dataset": _run_profile,
    "make_chart": _run_make_chart,
    "predict_column": _run_predict,
    "cluster_dataset": _run_cluster,
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
    system_parts = [ai_assistant.SYSTEM_PROMPT, METHODOLOGY_PROMPT]
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
