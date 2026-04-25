"""Deterministic dataset insights, profile, and CRISP-DM suggested questions.

These helpers run in pure pandas/numpy — no LLM call — so the
Julius.ai-style "as soon as the file lands" experience stays cheap and
fast. They return JSON-friendly dicts that the frontend renders
straight into the chat panel and the right-side artifact drawer.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def build_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Per-column profile: dtype, missingness, uniques, top values, basic stats.

    Mirrors what a "Profile" tab in a Julius/Hex-style notebook shows
    when you first land in a dataset — the headline numbers per column
    without the user having to ask.
    """
    n_rows = int(len(df))
    cols: list[dict[str, Any]] = []
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        col: dict[str, Any] = {
            "name": str(c),
            "dtype": str(s.dtype),
            "non_null": non_null,
            "missing": int(n_rows - non_null),
            "missing_pct": round((n_rows - non_null) / n_rows * 100, 2) if n_rows else 0.0,
            "unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            x = pd.to_numeric(s, errors="coerce").dropna()
            if not x.empty:
                col.update(
                    {
                        "kind": "numeric",
                        "min": _safe_float(x.min()),
                        "max": _safe_float(x.max()),
                        "mean": _safe_float(x.mean()),
                        "median": _safe_float(x.median()),
                        "std": _safe_float(x.std()),
                        "p05": _safe_float(x.quantile(0.05)),
                        "p95": _safe_float(x.quantile(0.95)),
                    }
                )
            else:
                col["kind"] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(s):
            x = pd.to_datetime(s, errors="coerce").dropna()
            col["kind"] = "datetime"
            if not x.empty:
                col.update(
                    {
                        "min": x.min().isoformat(),
                        "max": x.max().isoformat(),
                    }
                )
        else:
            vc = s.dropna().astype(str).value_counts().head(5)
            col["kind"] = "categorical"
            col["top_values"] = [
                {"value": str(k), "count": int(v)} for k, v in vc.items()
            ]
        cols.append(col)

    return {
        "rows": n_rows,
        "cols": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()) if n_rows else 0,
        "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "columns": cols,
    }


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        if not np.isfinite(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Surprise insights ribbon
# ---------------------------------------------------------------------------

def surprise_insights(df: pd.DataFrame, max_items: int = 8) -> list[dict[str, Any]]:
    """Surface the most "huh, look at this" facts about the dataset.

    Each insight is a small dict with severity (info|warn|good), a one-line
    headline, an optional subtitle, and machine-friendly fields the chat
    can later quote. Ordering is roughly by importance.
    """
    out: list[dict[str, Any]] = []
    n = int(len(df))
    if n == 0:
        return out

    # 1. Missingness hotspot
    miss = df.isna().sum()
    miss = miss[miss > 0].sort_values(ascending=False)
    if not miss.empty:
        worst_col = str(miss.index[0])
        worst_pct = round(int(miss.iloc[0]) / n * 100, 1)
        sev = "warn" if worst_pct >= 20 else "info"
        out.append(
            {
                "kind": "missingness",
                "severity": sev,
                "headline": f"{worst_col} is missing {worst_pct}% of values",
                "subtitle": (
                    f"{int(len(miss))} columns have gaps — biggest is "
                    f"{worst_col}."
                ),
                "column": worst_col,
                "value": worst_pct,
            }
        )

    # 2. Duplicate rows
    dup = int(df.duplicated().sum())
    if dup:
        out.append(
            {
                "kind": "duplicates",
                "severity": "warn" if dup / n > 0.05 else "info",
                "headline": f"{dup:,} duplicate rows ({round(dup / n * 100, 1)}%)",
                "subtitle": "Consider de-duplicating before modelling.",
                "value": dup,
            }
        )

    # 3. Strong correlations between numeric pairs
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] >= 2:
        try:
            corr = numeric.corr(numeric_only=True)
            best: tuple[str, str, float] | None = None
            for i in range(corr.shape[0]):
                for j in range(i + 1, corr.shape[1]):
                    v = corr.iat[i, j]
                    if pd.isna(v):
                        continue
                    if best is None or abs(v) > abs(best[2]):
                        best = (str(corr.columns[i]), str(corr.columns[j]), float(v))
            if best and abs(best[2]) >= 0.7:
                sign = "positively" if best[2] > 0 else "negatively"
                out.append(
                    {
                        "kind": "correlation",
                        "severity": "good",
                        "headline": (
                            f"{best[0]} and {best[1]} are strongly {sign} "
                            f"correlated (r = {round(best[2], 2)})"
                        ),
                        "subtitle": "Could anchor a regression or feature cut.",
                        "columns": [best[0], best[1]],
                        "value": round(best[2], 3),
                    }
                )
        except Exception:
            pass

    # 4. Pareto check on a numeric "value-like" column
    pareto_cands = [
        c for c in numeric.columns
        if any(t in str(c).lower() for t in ("amount", "revenue", "sales", "price",
                                              "value", "total", "count"))
    ] or list(numeric.columns[:1])
    cat_cands = [
        c for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c])
        and not pd.api.types.is_datetime64_any_dtype(df[c])
        and df[c].nunique() <= 100
    ]
    if pareto_cands and cat_cands:
        v_col, k_col = pareto_cands[0], cat_cands[0]
        try:
            grp = (
                pd.to_numeric(df[v_col], errors="coerce")
                .groupby(df[k_col].astype(str)).sum()
                .sort_values(ascending=False)
            )
            total = float(grp.sum())
            if total > 0:
                cum = grp.cumsum() / total
                hits = int((cum <= 0.8).sum()) + 1
                if hits and hits <= max(1, int(0.3 * len(grp))):
                    pct = round(hits / max(1, len(grp)) * 100, 1)
                    out.append(
                        {
                            "kind": "pareto",
                            "severity": "good",
                            "headline": (
                                f"{hits} of {len(grp)} {k_col} values "
                                f"({pct}%) drive 80% of {v_col}"
                            ),
                            "subtitle": "Classic Pareto signal — focus efforts there.",
                            "columns": [k_col, v_col],
                        }
                    )
        except Exception:
            pass

    # 5. Outlier hot column (z-score)
    for c in numeric.columns[:6]:
        x = pd.to_numeric(df[c], errors="coerce").dropna()
        if x.size < 8 or x.std() == 0:
            continue
        z = ((x - x.mean()) / x.std()).abs()
        ratio = float((z > 3).mean())
        if ratio >= 0.02:
            out.append(
                {
                    "kind": "outliers",
                    "severity": "warn",
                    "headline": (
                        f"{round(ratio * 100, 1)}% of {c} look like outliers (|z|>3)"
                    ),
                    "subtitle": "Cap or investigate before modelling.",
                    "column": str(c),
                    "value": round(ratio * 100, 2),
                }
            )
            break

    # 6. Time-series cadence detection
    dt_col = _detect_datetime_column(df)
    if dt_col:
        try:
            ts = pd.to_datetime(df[dt_col], errors="coerce").dropna().sort_values()
            if ts.size >= 3:
                span_days = (ts.iloc[-1] - ts.iloc[0]).days
                cadence = "daily" if span_days <= 366 else "monthly+"
                out.append(
                    {
                        "kind": "timeseries",
                        "severity": "info",
                        "headline": (
                            f"Time column `{dt_col}` covers {span_days:,} days — "
                            f"looks {cadence}."
                        ),
                        "subtitle": "Forecasts and trend analysis are on the table.",
                        "column": dt_col,
                    }
                )
        except Exception:
            pass

    # 7. Class imbalance for a likely target categorical
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            continue
        nun = int(df[c].nunique(dropna=True))
        if 2 <= nun <= 6:
            vc = df[c].value_counts(normalize=True, dropna=True)
            if not vc.empty and float(vc.iloc[0]) >= 0.8:
                out.append(
                    {
                        "kind": "imbalance",
                        "severity": "warn",
                        "headline": (
                            f"`{c}` is dominated by one class "
                            f"({round(float(vc.iloc[0]) * 100, 1)}%)"
                        ),
                        "subtitle": "Watch for biased classifiers; consider rebalancing.",
                        "column": str(c),
                    }
                )
                break

    return out[:max_items]


def _detect_datetime_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            return str(c)
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            continue
        sample = df[c].dropna().astype(str).head(20)
        if sample.empty:
            continue
        parsed = pd.to_datetime(sample, errors="coerce")
        if parsed.notna().sum() >= max(3, int(0.6 * len(sample))):
            return str(c)
    return None


# ---------------------------------------------------------------------------
# Suggested CRISP-DM-aligned questions
# ---------------------------------------------------------------------------

def suggested_questions(df: pd.DataFrame, max_items: int = 8) -> list[str]:
    """Return 5-8 CRISP-DM-aligned starter questions tailored to the data.

    The questions phrase concrete actions the chat can perform via its
    tool-calls (visualize, predict, cluster) so each chip is one click
    away from a real artifact.
    """
    qs: list[str] = []
    numeric = df.select_dtypes(include="number").columns.tolist()
    cats = [
        c for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c])
        and not pd.api.types.is_datetime64_any_dtype(df[c])
        and 2 <= df[c].nunique(dropna=True) <= 100
    ]
    dt_col = _detect_datetime_column(df)

    qs.append("Profile this dataset and call out the biggest data-quality issues.")

    if numeric:
        target = _pick_target_column(numeric)
        qs.append(f"Show the distribution of {target}.")
        if cats:
            qs.append(f"Compare average {target} across {cats[0]}.")
        if len(numeric) >= 2:
            qs.append(
                f"Is {numeric[0]} correlated with {numeric[1]}? Plot a scatter."
            )
        qs.append(f"Build a model to predict {target} from the other columns.")

    if dt_col and numeric:
        qs.append(
            f"Forecast {numeric[0]} over time using {dt_col}."
        )

    if numeric and len(numeric) >= 2:
        qs.append("Cluster the rows into 3 segments and describe each one.")

    if cats:
        qs.append(
            f"Which {cats[0]} categories drive 80% of the rows? Apply a Pareto cut."
        )

    # De-dupe while preserving order, cap to max.
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
        if len(out) >= max_items:
            break
    return out


def _pick_target_column(numeric_cols: list[str]) -> str:
    priority = ("revenue", "sales", "amount", "price", "total", "value", "score",
                "rating", "count", "quantity")
    lower = {c: str(c).lower() for c in numeric_cols}
    for key in priority:
        for c, lc in lower.items():
            if key in lc:
                return c
    return numeric_cols[0]


# ---------------------------------------------------------------------------
# Session-wide LLM synthesis (Final Report "Insights" section)
# ---------------------------------------------------------------------------

def _summarize_artifacts_for_llm(by_kind: dict[str, list]) -> str:
    """Compress a session's artifacts into a short, token-cheap brief."""
    lines: list[str] = []
    for kind in ("profile", "insight", "chart", "prediction", "cluster"):
        items = by_kind.get(kind) or []
        for a in items[:6]:
            t = a.get("title") or kind
            r = a.get("result") or {}
            if kind == "profile":
                lines.append(
                    f"- profile: {t} — rows={r.get('rows')}, cols={r.get('cols')}, "
                    f"missing_total={r.get('missing_total')}, dups={r.get('duplicate_rows')}"
                )
            elif kind == "insight":
                heads = [i.get("headline") for i in (r.get("items") or [])[:5]]
                lines.append(f"- insights: {t} — " + " | ".join(filter(None, heads)))
            elif kind == "chart":
                p = a.get("params") or {}
                lines.append(
                    f"- chart: {t} (chart={p.get('chart')} x={p.get('x')} y={p.get('y')})"
                )
            elif kind == "prediction":
                m = (r.get("metrics") or {})
                top = ", ".join(
                    f"{f.get('feature')}:{round(float(f.get('importance') or 0), 3)}"
                    for f in (r.get("top_features") or [])[:5]
                )
                lines.append(
                    f"- prediction: target={r.get('target')} model={r.get('model')} "
                    f"r2={m.get('r2')} mae={m.get('mae')} top_features=[{top}]"
                )
            elif kind == "cluster":
                lines.append(
                    f"- cluster: k={r.get('k')} sizes={r.get('sizes')}"
                )
    return "\n".join(lines) if lines else "(no artifacts in this session yet)"


def synthesize_session_insights(by_kind: dict[str, list]) -> dict[str, Any]:
    """One LLM call that turns this session's artifacts into a narrative.

    Returns ``{"executive_summary": str, "key_findings": [str], "recommendations": [str]}``.
    Falls back to a deterministic template if the OpenAI key is missing or
    the call fails — the report must always render.
    """
    brief = _summarize_artifacts_for_llm(by_kind)
    fallback = {
        "executive_summary": (
            "This report compiles the artifacts pinned during the session. "
            "See per-section detail below."
        ),
        "key_findings": [
            (a.get("title") or "Artifact")
            for a in (by_kind.get("insight") or [])[:5]
        ] or ["No insight artifacts were pinned for synthesis."],
        "recommendations": [
            "Pin the most important charts and predictions to refine this summary.",
        ],
    }

    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = (
            "You are AXIOM's senior data analyst. Given this brief of one user's "
            "analysis session, write a JSON object with exactly these keys: "
            "executive_summary (1-3 sentences), key_findings (3-6 bullet strings), "
            "recommendations (3-5 bullet strings, each actionable). "
            "Be specific to the artifacts; do not invent numbers that are not in the brief.\n\n"
            f"BRIEF:\n{brief}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return only valid JSON, no prose."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        import json
        out = json.loads(resp.choices[0].message.content or "{}")
        # Normalise keys / types.
        return {
            "executive_summary": str(out.get("executive_summary") or fallback["executive_summary"]).strip(),
            "key_findings": [str(x) for x in (out.get("key_findings") or fallback["key_findings"])][:8],
            "recommendations": [str(x) for x in (out.get("recommendations") or fallback["recommendations"])][:8],
        }
    except Exception:
        return fallback


# ---------------------------------------------------------------------------
# What-if recommendations (deterministic ±10% / ±25% feature shifts)
# ---------------------------------------------------------------------------

def what_if_recommendations(prediction_result: dict[str, Any]) -> list[dict[str, Any]]:
    """For each top numeric feature, compute the predicted target shift
    when that feature is moved ±10% and ±25% from its mean (holding all
    other features at their mean).  Pure, deterministic, no LLM."""
    feats = (prediction_result or {}).get("top_features") or []
    means = (prediction_result or {}).get("feature_means") or {}
    coefs = (prediction_result or {}).get("linear_coefs") or {}
    base = float((prediction_result or {}).get("baseline_prediction") or 0.0)
    out: list[dict[str, Any]] = []
    for f in feats[:5]:
        name = f.get("feature")
        if name is None:
            continue
        mean = means.get(name)
        coef = coefs.get(name)
        if mean is None or coef is None:
            continue
        try:
            mean_f = float(mean)
            coef_f = float(coef)
        except Exception:
            continue
        rows = []
        for pct in (-0.25, -0.10, 0.10, 0.25):
            delta_x = mean_f * pct
            delta_y = coef_f * delta_x
            rows.append({
                "shift_pct": int(round(pct * 100)),
                "new_value": round(mean_f + delta_x, 4),
                "predicted_delta": round(delta_y, 4),
                "predicted_value": round(base + delta_y, 4),
            })
        out.append({"feature": name, "baseline_value": round(mean_f, 4), "rows": rows})
    return out
