"""Tests for the guided predictive flow (Task #212).

Covers:
  • happy-path time-series analyse + run via Prophet (or the linear
    trend fallback if Prophet isn't importable in this environment)
  • happy-path driver-based regression analyse + run
  • small-dataset notice path (analyze refuses, no model fit)
  • "LLM returned no questions" fallback (deterministic Arabic
    questions are produced instead)
  • narrative LLM is constrained to quote provided numbers verbatim
    and falls back to a deterministic template when the LLM is offline
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backend import predict_guided_service as svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch):
    """Default: pretend the LLM has no API key configured.

    Individual tests can override this by re-monkeypatching
    ``svc._chat_completion`` with a deterministic stub.
    """
    monkeypatch.setattr(svc, "_chat_completion", lambda *a, **kw: "")
    yield


def _timeseries_df(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    trend = np.linspace(100, 200, n)
    noise = rng.normal(0, 5, size=n)
    return pd.DataFrame({"date": dates, "revenue": trend + noise})


def _driver_df(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(13)
    spend = rng.uniform(10, 100, size=n)
    units = rng.uniform(1, 50, size=n)
    noise = rng.normal(0, 1.5, size=n)
    sales = 2.0 * spend + 0.5 * units + noise
    return pd.DataFrame(
        {"marketing_spend": spend, "units": units, "sales": sales}
    )


# ---------------------------------------------------------------------------
# Profile detection
# ---------------------------------------------------------------------------

def test_detect_time_column_picks_named_date_column():
    df = _timeseries_df(20)
    assert svc.detect_time_column(df) == "date"


def test_detect_target_prefers_revenue_like_name():
    df = _timeseries_df(20)
    target = svc.detect_target_column(df, exclude=["date"])
    assert target == "revenue"


def test_rank_drivers_orders_by_correlation():
    df = _driver_df(40)
    drivers = svc.rank_drivers(df, target="sales", time_column=None, top_k=5)
    assert drivers, "expected at least one driver"
    assert drivers[0]["column"] == "marketing_spend"
    assert drivers[0]["abs_correlation"] >= drivers[-1]["abs_correlation"]


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------

def test_analyze_returns_questions_for_timeseries_dataset():
    df = _timeseries_df(30)
    result = svc.analyze_dataset(df)
    assert result["ok"] is True
    assert result["target"] == "revenue"
    assert result["time_column"] == "date"
    assert result["flow"] == "guided"
    assert isinstance(result["questions"], list) and result["questions"]
    # Default question set always contains an Arabic-script string.
    assert any(
        any("\u0600" <= ch <= "\u06ff" for ch in q["text"])
        for q in result["questions"]
    )
    # Partial confidence preview must be present so the wizard can show
    # "where confidence will come from" before the user runs the model.
    pc = result["partial_confidence"]
    assert pc["preliminary"] is True
    assert 0.0 <= pc["score"] <= 100.0
    assert pc["band"] in ("low", "medium", "high")
    assert set(pc["sub_scores"].keys()) == {
        "data_volume", "data_quality", "signal_strength", "time_coverage"
    }


def test_analyze_refuses_small_dataset():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=4),
                       "revenue": [10, 20, 30, 40]})
    result = svc.analyze_dataset(df)
    assert result["ok"] is False
    assert result["kind"] == "small_sample"
    assert result["rows_required"] == svc.MIN_ROWS_REGRESSION
    assert any("\u0600" <= ch <= "\u06ff" for ch in result["message_ar"])


def test_analyze_returns_no_target_when_no_numeric_columns():
    df = pd.DataFrame({
        "name": [f"x{i}" for i in range(20)],
        "tag": ["a"] * 20,
    })
    result = svc.analyze_dataset(df)
    assert result["ok"] is False
    assert result["kind"] == "no_target"


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------

def test_llm_no_questions_falls_back_to_default_set(monkeypatch):
    # LLM returns garbage that won't parse → wizard must still ship
    # at least 3 deterministic Arabic questions.
    monkeypatch.setattr(svc, "_chat_completion", lambda *a, **kw: "not-json")
    df = _timeseries_df(30)
    result = svc.analyze_dataset(df)
    assert result["ok"] is True
    assert len(result["questions"]) >= 3
    assert any(q["id"] == "horizon_periods" for q in result["questions"])


def test_llm_well_formed_questions_are_used(monkeypatch):
    payload = (
        '{"questions":['
        '{"id":"q1","text":"هل تخطط لزيادة الإنفاق؟","kind":"yesno"},'
        '{"id":"q2","text":"ما النسبة المتوقعة للنمو؟","kind":"slider",'
        '"min":-50,"max":50,"default":10,"unit":"%"},'
        '{"id":"q3","text":"اختر الموسم","kind":"dropdown",'
        '"options":["شتاء","ربيع","صيف"]}]}'
    )
    monkeypatch.setattr(svc, "_chat_completion", lambda *a, **kw: payload)
    df = _timeseries_df(30)
    result = svc.analyze_dataset(df)
    qs = result["questions"]
    assert len(qs) == 3
    assert qs[0]["id"] == "q1"
    assert qs[1]["kind"] == "slider"
    assert qs[2]["options"] == ["شتاء", "ربيع", "صيف"]


# ---------------------------------------------------------------------------
# Run prediction — happy paths
# ---------------------------------------------------------------------------

def test_run_prediction_timeseries_returns_forecast_and_confidence():
    df = _timeseries_df(60)
    out = svc.run_prediction(
        df,
        target="revenue",
        time_column="date",
        drivers=[],
        answers={"horizon_periods": 14},
        periods=14,
    )
    assert out["flow"] == "guided"
    assert out["is_timeseries"] is True
    assert out["horizon_periods"] == 14
    forecast = out["model"]["forecast"]
    assert len(forecast) == 14
    for pt in forecast:
        assert pt["lower"] <= pt["yhat"] <= pt["upper"]
    conf = out["confidence"]
    assert 0.0 <= conf["score"] <= 100.0
    assert conf["band"] in ("low", "medium", "high")
    assert set(conf["sub_scores"].keys()) == {
        "data_volume", "data_quality", "signal_strength", "time_coverage"
    }
    # Numbers must appear pre-formatted as strings for the narrative to quote.
    assert isinstance(out["formatted_numbers"]["next_period_forecast"], str)
    # Default narrative falls back when LLM is offline; must reuse the
    # exact formatted number string verbatim (no LLM hallucination).
    assert (
        out["formatted_numbers"]["next_period_forecast"]
        in out["narrative"]["conditional"]
    )


def test_run_prediction_driver_returns_feature_importance():
    df = _driver_df(80)
    out = svc.run_prediction(
        df,
        target="sales",
        time_column=None,
        drivers=["marketing_spend", "units"],
        answers={},
    )
    assert out["is_timeseries"] is False
    assert out["model"]["engine"] in ("linear_regression", "random_forest")
    importance = out["feature_importance"]
    assert importance and importance[0]["feature"] in ("marketing_spend", "units")
    # marketing_spend has the larger coefficient by construction.
    assert importance[0]["feature"] == "marketing_spend"
    formatted = out["formatted_numbers"]
    assert "baseline" in formatted
    assert "r2" in formatted


def test_run_prediction_driver_refuses_when_no_drivers():
    df = pd.DataFrame({"sales": np.linspace(1, 100, 30)})
    with pytest.raises(ValueError):
        svc.run_prediction(
            df, target="sales", time_column=None, drivers=[], answers={}
        )


# ---------------------------------------------------------------------------
# Confidence math
# ---------------------------------------------------------------------------

def test_confidence_band_thresholds():
    high = svc.compute_confidence({
        "data_volume": 1.0, "data_quality": 1.0,
        "signal_strength": 1.0, "time_coverage": 1.0,
    })
    assert high["band"] == "high"
    assert high["score"] == pytest.approx(100.0)

    low = svc.compute_confidence({
        "data_volume": 0.0, "data_quality": 0.0,
        "signal_strength": 0.0, "time_coverage": 0.0,
    })
    assert low["band"] == "low"
    assert low["score"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Narrative LLM constraints
# ---------------------------------------------------------------------------

def test_narrative_uses_llm_payload_when_available(monkeypatch):
    payload = (
        '{"context":"السياق هنا","conditional":"إذا قمت بـ X ← نتوقع 123",'
        '"recommendations":["أ","ب"]}'
    )
    monkeypatch.setattr(svc, "_chat_completion", lambda *a, **kw: payload)
    out = svc._arabic_narrative(
        target="revenue",
        formatted_numbers={"next_period_forecast": "123"},
        drivers_summary=[],
        confidence_band="medium",
    )
    assert out["context"] == "السياق هنا"
    assert "123" in out["conditional"]
    assert out["recommendations"] == ["أ", "ب"]


def test_narrative_falls_back_when_llm_returns_invalid():
    out = svc._arabic_narrative(
        target="revenue",
        formatted_numbers={
            "next_period_forecast": "987",
            "forecast_average": "950",
        },
        drivers_summary=[{"feature": "marketing_spend"}],
        confidence_band="high",
    )
    # The fallback narrative must quote the supplied number verbatim.
    assert "987" in out["conditional"]
    assert any("\u0600" <= ch <= "\u06ff" for ch in out["context"])
    assert len(out["recommendations"]) >= 2
