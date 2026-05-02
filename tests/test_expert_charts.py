"""Tests for the Expert-mode diagnostic charts endpoint (Task #250).

Covers all four chart types — residuals, qq, acf, pacf — and asserts
each returns a valid Plotly JSON spec plus the documented numerical
``summary`` block.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest


def _csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def linear_csv() -> bytes:
    rng = np.random.default_rng(3)
    n = 60
    x = np.linspace(0, 10, n)
    y = 2.5 * x + 1.0 + rng.normal(0, 0.5, size=n)
    return _csv(pd.DataFrame({"x": x.round(4), "y": y.round(4)}))


@pytest.fixture
def normal_csv() -> bytes:
    rng = np.random.default_rng(13)
    return _csv(pd.DataFrame({
        "value": rng.normal(0, 1, size=120).round(4),
    }))


@pytest.fixture
def timeseries_value_csv() -> bytes:
    """A sine-wave series with clear lag-12 autocorrelation."""
    n = 96
    t = np.arange(n)
    series = np.sin(2 * np.pi * t / 12) + 0.05 * t
    return _csv(pd.DataFrame({"value": series.round(4)}))


def _is_plotly_spec(spec) -> bool:
    """A Plotly figure JSON has at least 'data' and 'layout' keys."""
    if not isinstance(spec, dict):
        return False
    return "data" in spec and "layout" in spec and isinstance(spec["data"], list)


def _post(client, headers, body):
    return client.post(
        "/api/visualize/expert-charts", json=body, headers=headers,
    )


def test_residuals_chart_returns_spec_and_summary(
    client, project, upload_dataset, linear_csv,
):
    u, pid = project("resid")
    dsid = upload_dataset(u["headers"], pid, "lin", linear_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "chart": "residuals",
        "x_col": "x", "y_col": "y",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chart"] == "residuals"
    assert _is_plotly_spec(body["spec"]), body
    summary = body["summary"]
    for k in ("mean_residual", "std_residual", "max_abs_residual",
              "n", "slope", "intercept"):
        assert k in summary, summary
    # Residuals should be roughly mean-zero on a linear fit.
    assert abs(summary["mean_residual"]) < 0.5
    # Slope close to the true 2.5.
    assert 2.0 < summary["slope"] < 3.0


def test_qq_chart_flags_normal_data(
    client, project, upload_dataset, normal_csv,
):
    u, pid = project("qq")
    dsid = upload_dataset(u["headers"], pid, "norm", normal_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "chart": "qq", "x_col": "value",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chart"] == "qq"
    assert _is_plotly_spec(body["spec"]), body
    summary = body["summary"]
    for k in ("n", "slope", "intercept", "r_squared", "normality"):
        assert k in summary, summary
    assert summary["n"] == 120
    # Normal data should land on the reference line — r² near 1.
    assert summary["r_squared"] > 0.9
    assert summary["normality"] == "looks normal"


def test_acf_chart_returns_spec_values_and_top_lag(
    client, project, upload_dataset, timeseries_value_csv,
):
    u, pid = project("acf")
    dsid = upload_dataset(u["headers"], pid, "ts", timeseries_value_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "chart": "acf",
        "x_col": "value", "lags": 24,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chart"] == "acf"
    assert _is_plotly_spec(body["spec"]), body
    assert isinstance(body["values"], list) and len(body["values"]) == 25
    # Lag 0 always equals 1 for ACF.
    assert abs(body["values"][0] - 1.0) < 1e-6
    summary = body["summary"]
    assert summary["n_lags"] == 24
    assert isinstance(summary["top_lag"], int)


def test_pacf_chart_returns_spec_and_summary(
    client, project, upload_dataset, timeseries_value_csv,
):
    u, pid = project("pacf")
    dsid = upload_dataset(u["headers"], pid, "ts", timeseries_value_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "chart": "pacf",
        "x_col": "value", "lags": 20,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chart"] == "pacf"
    assert _is_plotly_spec(body["spec"]), body
    assert isinstance(body["values"], list) and len(body["values"]) == 21
    assert body["summary"]["n_lags"] == 20


def test_unknown_chart_returns_400(
    client, project, upload_dataset, normal_csv,
):
    u, pid = project("badchart")
    dsid = upload_dataset(u["headers"], pid, "norm", normal_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "chart": "violin", "x_col": "value",
    })
    assert r.status_code == 400, r.text
