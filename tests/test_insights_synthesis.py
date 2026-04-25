"""Smoke tests for Task #158 helpers: insight ribbon, suggestions,
LLM-synthesis fallback (no API key path), what-if recommendations."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from backend.insights import (
    build_profile,
    surprise_insights,
    suggested_questions,
    synthesize_session_insights,
    what_if_recommendations,
)


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 200
    return pd.DataFrame(
        {
            "region": np.random.choice(["NA", "EU", "APAC"], size=n),
            "revenue": rng.normal(120, 30, size=n).round(2),
            "units": rng.integers(1, 50, size=n),
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
        }
    )


def test_profile_shape():
    p = build_profile(_df())
    assert p["rows"] == 200
    assert p["cols"] == 4
    names = [c["name"] for c in p["columns"]]
    assert {"region", "revenue", "units", "ts"} <= set(names)


def test_surprise_insights_returns_items_with_severity():
    items = surprise_insights(_df(), max_items=8)
    assert isinstance(items, list)
    for it in items:
        assert {"headline", "severity"} <= set(it)
        assert it["severity"] in ("info", "warn", "good", "critical")


def test_suggested_questions_have_crisp_dm_phrasing():
    qs = suggested_questions(_df(), max_items=8)
    assert qs and all(isinstance(q, str) and q for q in qs)
    # CRISP-DM stages should be reflected somewhere in the deck.
    blob = " ".join(qs).lower()
    assert any(k in blob for k in ("trend", "predict", "cluster", "distribution", "compare", "why"))


def test_synthesize_session_insights_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    by_kind = {
        "profile": [{"id": 1, "title": "Profile — sales.csv", "result": {"rows": 100, "cols": 5, "missing_total": 0, "duplicate_rows": 0}}],
        "insight": [{"id": 2, "title": "Insights — sales.csv", "result": {"items": [{"headline": "Revenue up 12% in EU", "severity": "info"}]}}],
        "chart": [],
        "prediction": [],
        "cluster": [],
    }
    out = synthesize_session_insights(by_kind)
    assert "executive_summary" in out
    assert isinstance(out.get("key_findings"), list) and out["key_findings"]
    assert isinstance(out.get("recommendations"), list) and out["recommendations"]


def test_what_if_recommendations_produces_four_rows_per_feature():
    pred_result = {
        "target": "revenue",
        "baseline_prediction": 100.0,
        "feature_means": {"units": 25.0, "discount": 0.10},
        "linear_coefs": {"units": 2.0, "discount": -300.0},
        "top_features": [
            {"feature": "units", "importance": 0.7},
            {"feature": "discount", "importance": 0.3},
        ],
    }
    rows = what_if_recommendations(pred_result)
    assert len(rows) == 2
    for feat in rows:
        assert {"feature", "baseline_value", "rows"} <= set(feat)
        assert len(feat["rows"]) == 4
        shifts = sorted(r["shift_pct"] for r in feat["rows"])
        assert shifts == [-25, -10, 10, 25]


def test_what_if_skips_features_without_means_or_coefs():
    pred_result = {
        "target": "revenue",
        "baseline_prediction": 0,
        "feature_means": {"units": 25.0},  # discount missing
        "linear_coefs": {"units": 2.0},
        "top_features": [
            {"feature": "units", "importance": 0.7},
            {"feature": "discount", "importance": 0.3},
        ],
    }
    rows = what_if_recommendations(pred_result)
    assert len(rows) == 1 and rows[0]["feature"] == "units"
