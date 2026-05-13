"""Tests for the Expert-mode statistical tests endpoint (Task #250).

Covers all four families — t-test, ANOVA, chi-square, ADF — on tiny
deterministic fixtures and asserts each returns the documented
numeric block plus a ``plain_language`` line.
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
def two_sample_csv() -> bytes:
    """Two clearly-different numeric columns: t-test should reject H0."""
    rng = np.random.default_rng(7)
    a = rng.normal(loc=10.0, scale=1.0, size=40)
    b = rng.normal(loc=15.0, scale=1.0, size=40)
    return _csv(pd.DataFrame({"group_a": a.round(3), "group_b": b.round(3)}))


@pytest.fixture
def anova_csv() -> bytes:
    """Three numeric columns with separated means → ANOVA rejects H0."""
    rng = np.random.default_rng(11)
    return _csv(pd.DataFrame({
        "g1": rng.normal(5, 1, 30).round(3),
        "g2": rng.normal(8, 1, 30).round(3),
        "g3": rng.normal(11, 1, 30).round(3),
    }))


@pytest.fixture
def chi_square_csv() -> bytes:
    """Two categorical columns with strong association."""
    rows = []
    for _ in range(30):
        rows.append({"region": "north", "buyer": "yes"})
    for _ in range(20):
        rows.append({"region": "north", "buyer": "no"})
    for _ in range(10):
        rows.append({"region": "south", "buyer": "yes"})
    for _ in range(40):
        rows.append({"region": "south", "buyer": "no"})
    return _csv(pd.DataFrame(rows))


@pytest.fixture
def stationary_csv() -> bytes:
    """Stationary series (white noise) — ADF should reject H0."""
    rng = np.random.default_rng(99)
    return _csv(pd.DataFrame({"value": rng.normal(0, 1, size=120).round(4)}))


@pytest.fixture
def nonstationary_csv() -> bytes:
    """Random-walk series — ADF should fail to reject H0."""
    rng = np.random.default_rng(42)
    walk = np.cumsum(rng.normal(0, 1, size=120))
    return _csv(pd.DataFrame({"value": walk.round(4)}))


def _post(client, headers, body):
    return client.post(
        "/api/analysis/statistical-tests", json=body, headers=headers,
    )


def test_t_test_rejects_for_clearly_different_means(
    client, project, upload_dataset, two_sample_csv,
):
    u, pid = project("ttest")
    dsid = upload_dataset(u["headers"], pid, "two_sample", two_sample_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid,
        "test": "t_test",
        "columns": ["group_a", "group_b"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["test"] == "t_test"
    for k in ("t_stat", "p_value", "df", "mean_a", "mean_b",
              "interpretation", "plain_language"):
        assert k in body, body
    assert body["p_value"] < 0.001, body
    assert body["interpretation"] == "reject H0"
    assert body["mean_a"] < body["mean_b"]
    assert "t-test" in body["plain_language"].lower()


def test_anova_rejects_for_separated_groups(
    client, project, upload_dataset, anova_csv,
):
    u, pid = project("anova")
    dsid = upload_dataset(u["headers"], pid, "anova", anova_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid,
        "test": "anova",
        "columns": ["g1", "g2", "g3"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["test"] == "anova"
    for k in ("f_stat", "p_value", "df_between", "df_within",
              "group_means", "interpretation", "plain_language"):
        assert k in body, body
    assert body["df_between"] == 2.0
    assert body["p_value"] < 0.001
    assert body["interpretation"] == "reject H0"
    assert set(body["group_means"].keys()) == {"g1", "g2", "g3"}


def test_chi_square_detects_association(
    client, project, upload_dataset, chi_square_csv,
):
    u, pid = project("chi")
    dsid = upload_dataset(u["headers"], pid, "chi_sq", chi_square_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid,
        "test": "chi_square",
        "columns": ["region", "buyer"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["test"] == "chi_square"
    for k in ("chi2", "p_value", "dof", "expected",
              "interpretation", "plain_language"):
        assert k in body, body
    assert body["dof"] == 1
    assert body["p_value"] < 0.001
    assert body["interpretation"] == "reject H0"


def test_adf_marks_white_noise_as_stationary(
    client, project, upload_dataset, stationary_csv,
):
    u, pid = project("adf-stat")
    dsid = upload_dataset(u["headers"], pid, "stationary", stationary_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid,
        "test": "adf",
        "columns": ["value"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["test"] == "adf"
    for k in ("adf_stat", "p_value", "lags", "critical_values",
              "interpretation", "plain_language", "stationarity"):
        assert k in body, body
    assert body["stationarity"] == "stationary"
    # Critical values dict has the standard 1%/5%/10% thresholds.
    assert {"1%", "5%", "10%"}.issubset(body["critical_values"].keys())


def test_adf_marks_random_walk_as_nonstationary(
    client, project, upload_dataset, nonstationary_csv,
):
    u, pid = project("adf-walk")
    dsid = upload_dataset(u["headers"], pid, "walk", nonstationary_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid,
        "test": "adf",
        "columns": ["value"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stationarity"] == "non-stationary"
    assert body["interpretation"] == "fail to reject H0"


def test_unknown_test_returns_400(
    client, project, upload_dataset, two_sample_csv,
):
    u, pid = project("unknown")
    dsid = upload_dataset(u["headers"], pid, "ts", two_sample_csv)
    r = _post(client, u["headers"], {
        "dataset_id": dsid, "test": "mann_whitney",
        "columns": ["group_a", "group_b"],
    })
    assert r.status_code == 400, r.text
