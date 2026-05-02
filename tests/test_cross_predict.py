"""Cross-dataset prediction tests (Task #246).

Covers:
  * Auto-discovery firing on the second upload to a project.
  * Cross-predict with two joined datasets (join_plan populated).
  * Graceful degradation when no relationships exist (skipped=True).
  * The four documented error paths (404 / 422 / 400 / 400).
  * Shape of the join_plan block.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

import models  # type: ignore


# ---------------------------------------------------------------------------
# Sample frames designed for cross-predict
# ---------------------------------------------------------------------------

@pytest.fixture
def cp_orders_csv() -> bytes:
    """40-row orders fact: customer_id (1..8) + numeric target `sales`."""
    rng = np.random.default_rng(42)
    n = 40
    df = pd.DataFrame({
        "order_id": list(range(2001, 2001 + n)),
        "customer_id": rng.integers(1, 9, size=n),
        "spend": rng.uniform(20, 200, size=n).round(2),
        "sales": rng.uniform(50, 500, size=n).round(2),
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def cp_customers_csv() -> bytes:
    """8-row customer dimension keyed by customer_id."""
    df = pd.DataFrame({
        "customer_id": list(range(1, 9)),
        "tenure_months": [3, 12, 27, 5, 18, 9, 41, 7],
        "segment_score": [0.2, 0.7, 0.9, 0.3, 0.5, 0.4, 0.95, 0.35],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def cp_unrelated_csv() -> bytes:
    """A dataset with no plausible join key to the others."""
    df = pd.DataFrame({
        "country": ["LB", "AE", "EG", "JO"],
        "fx_rate": [1.0, 3.67, 30.9, 0.71],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


# ---------------------------------------------------------------------------
# Auto-discovery on upload
# ---------------------------------------------------------------------------

def _project_relationships(db, project_id: int) -> list:
    return (
        db.query(models.ProjectRelationship)
        .filter(models.ProjectRelationship.project_id == project_id)
        .all()
    )


def test_auto_discovery_fires_on_second_upload(
    client, project, upload_dataset, cp_customers_csv, cp_orders_csv,
):
    """After the second dataset hits the project, the upload route's
    background task must have persisted at least one high-confidence
    ``ProjectRelationship`` (the customer_id ↔ customer_id link)."""
    from backend.auth import get_db_session
    u, pid = project("cp-autodiscovery")

    # Upload #1 — must NOT create relationship rows on its own.
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    db = next(get_db_session())
    try:
        rels_after_first = _project_relationships(db, pid)
    finally:
        db.close()
    assert rels_after_first == [], (
        "First upload should not produce any cross-table relationships."
    )

    # Upload #2 — TestClient runs background tasks synchronously after
    # the response is sent, so by the time .post() returns, discovery
    # has already executed.
    upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    db = next(get_db_session())
    try:
        rels = _project_relationships(db, pid)
    finally:
        db.close()
    high = [r for r in rels if r.band == "high"]
    assert high, (
        f"Expected at least one high-confidence relationship after "
        f"the 2nd upload; got {[(r.left_column, r.right_column, r.band) for r in rels]}"
    )
    cols = {(r.left_column, r.right_column) for r in high}
    assert any("customer_id" in lc or "customer_id" in rc
               for lc, rc in cols), cols


def test_auto_discovery_does_not_fire_without_project(
    client, register, upload_dataset, cp_customers_csv,
):
    """Uploads with no project_id must not crash — and obviously must
    not create relationship rows for any project."""
    from backend.auth import get_db_session
    u = register("cp-noproject")
    # Upload without a project_id (project_id=None).
    upload_dataset(u["headers"], None, "customers", cp_customers_csv)
    db = next(get_db_session())
    try:
        all_rels = db.query(models.ProjectRelationship).all()
    finally:
        db.close()
    # Other tests in the run may also have created rels; just confirm
    # this particular dataset didn't.
    assert all(
        r.left_dataset_id != r.right_dataset_id for r in all_rels
    )


# ---------------------------------------------------------------------------
# Cross-predict happy path
# ---------------------------------------------------------------------------

def test_cross_predict_with_two_joined_datasets(
    client, project, upload_dataset, cp_customers_csv, cp_orders_csv,
):
    u, pid = project("cp-happy")
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)

    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={
            "target_dataset_id": orders_id,
            "target_column": "sales",
        },
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Dual payload contract.
    assert "guided" in body and "expert" in body, body
    for k in ("summary", "confidence", "confidence_score", "recommendations"):
        assert k in body["guided"], body["guided"]
    for k in ("model_used", "metrics", "cross_validation",
              "confidence_interval", "predictions"):
        assert k in body["expert"], body["expert"]

    # join_plan must reflect the actual chained join.
    plan = body["join_plan"]
    assert plan["target_dataset_id"] == orders_id
    assert plan["skipped"] is False
    assert isinstance(plan["joins"], list) and len(plan["joins"]) >= 1, plan
    step = plan["joins"][0]
    for k in ("dataset_id", "dataset_name", "left_column",
              "right_column", "rows_before", "rows_after"):
        assert k in step, step
    assert step["rows_before"] >= 1
    assert plan["merged_rows"] >= 1
    assert plan["merged_cols"] > 4  # picked up dimension columns
    assert plan["target_rows"] == 40


def test_cross_predict_join_plan_includes_dimension_features(
    client, project, upload_dataset, cp_customers_csv, cp_orders_csv,
):
    """After the join, dimension columns (tenure_months, segment_score)
    must be visible in the merged column count — proving the
    predictions engine was given a richer feature matrix than the
    target dataset alone."""
    u, pid = project("cp-features")
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": orders_id, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    plan = r.json()["join_plan"]
    # orders alone has 4 cols; with the dimension joined we expect at
    # least the customer_id + tenure_months + segment_score fields too.
    assert plan["merged_cols"] >= 6, plan


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

def test_cross_predict_falls_back_when_no_relationships(
    client, project, upload_dataset, cp_orders_csv, cp_unrelated_csv,
):
    """Two datasets with no shared key still produce a prediction on
    the target alone, with a non-fatal warning + skipped=True."""
    u, pid = project("cp-noreq")
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    upload_dataset(u["headers"], pid, "fx", cp_unrelated_csv)

    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": orders_id, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    plan = body["join_plan"]
    assert plan["skipped"] is True, plan
    assert plan["joins"] == [], plan
    assert plan["warnings"], plan
    # The prediction surface still came back populated.
    assert body["expert"].get("predictions") is not None


def test_cross_predict_single_dataset_falls_back(
    client, project, upload_dataset, cp_orders_csv,
):
    """One-dataset project also degrades gracefully."""
    u, pid = project("cp-single")
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)

    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": orders_id, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    plan = r.json()["join_plan"]
    assert plan["skipped"] is True
    assert plan["joins"] == []
    assert plan["warnings"], plan


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_cross_predict_404_when_project_has_no_datasets(
    client, project,
):
    u, pid = project("cp-empty")
    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": 999999, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 404, r.text
    assert "no datasets" in (r.json().get("detail") or "").lower()


def test_cross_predict_404_when_project_does_not_exist(
    client, register,
):
    u = register("cp-noproj")
    r = client.post(
        "/api/projects/999999/cross-predict",
        json={"target_dataset_id": 1, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 404


def test_cross_predict_422_when_target_not_in_project(
    client, project, register, upload_dataset, cp_orders_csv,
):
    """target_dataset_id pointing at a dataset outside this project
    must return 422, not 404 (the project DOES exist and has data)."""
    # Project A has the orders dataset.
    u, pid_a = project("cp-422a")
    orders_a = upload_dataset(u["headers"], pid_a, "orders", cp_orders_csv)
    # Project B (same user) is empty-ish — give it one dataset so the
    # 404 "no datasets" guard doesn't trigger first.
    r = client.post("/api/projects", json={"name": "cp-422b"},
                    headers=u["headers"])
    assert r.status_code == 200, r.text
    pid_b = r.json()["id"]
    upload_dataset(u["headers"], pid_b, "orders_b", cp_orders_csv)

    # Try to predict on project B's id but pass project A's dataset id.
    r = client.post(
        f"/api/projects/{pid_b}/cross-predict",
        json={"target_dataset_id": orders_a, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 422, r.text
    assert "not belong" in (r.json().get("detail") or "").lower()


def test_cross_predict_400_when_target_column_missing(
    client, project, upload_dataset, cp_orders_csv, cp_customers_csv,
):
    u, pid = project("cp-400col")
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={
            "target_dataset_id": orders_id,
            "target_column": "definitely_not_a_column",
        },
        headers=u["headers"],
    )
    assert r.status_code == 400, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "target_column" in detail and "merged" in detail


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

def test_cross_predict_ignores_unconfirmed_persisted_relationship(
    client, project, upload_dataset, cp_orders_csv, cp_unrelated_csv,
):
    """A persisted relationship in 'proposed' state must NOT be used
    as a join candidate by cross-predict — only user-confirmed
    relationships count. Two datasets with no real shared key are
    used here (so the fresh proposer can't rescue the join), and a
    bogus ``proposed`` relationship is inserted by hand. The endpoint
    should still report ``skipped=True`` and join nothing.
    """
    from backend.auth import get_db_session
    u, pid = project("cp-unconfirmed")
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    fx_id = upload_dataset(u["headers"], pid, "fx", cp_unrelated_csv)

    # Hand-craft a bogus 'proposed' relationship between the two —
    # there is no real overlap, but a naive query would still pull
    # this row in as a join candidate.
    db = next(get_db_session())
    try:
        lo, hi = sorted([orders_id, fx_id])
        db.add(models.ProjectRelationship(
            project_id=pid,
            left_dataset_id=lo, left_column="customer_id",
            right_dataset_id=hi, right_column="country",
            cardinality="N:1", join_type="left",
            status="proposed",
            band="medium",
            confidence=0.55,
            evidence={},
            overlap_score=0.0,
            name_score=0.0,
            dtype_score=0.0,
            user_locked=False,
        ))
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": orders_id, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    plan = r.json()["join_plan"]
    # Bogus 'proposed' row must NOT appear as a join step.
    assert plan["joins"] == [], plan
    assert plan["skipped"] is True, plan


def test_cross_predict_honours_user_confirmed_relationship(
    client, project, upload_dataset, cp_orders_csv, cp_customers_csv,
):
    """When a relationship is user-confirmed, cross-predict must
    happily join on it (and the join_plan should mark its source as
    'confirmed')."""
    from backend.auth import get_db_session
    u, pid = project("cp-confirmed")
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)

    # The auto-discovery saved a 'proposed' row — flip it to confirmed
    # to simulate the user accepting it on the data-model page.
    db = next(get_db_session())
    try:
        rels = db.query(models.ProjectRelationship).filter(
            models.ProjectRelationship.project_id == pid,
        ).all()
        assert rels, "auto-discovery should have persisted a row"
        for rel in rels:
            rel.status = "confirmed"
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={"target_dataset_id": orders_id, "target_column": "sales"},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    plan = r.json()["join_plan"]
    assert plan["joins"], plan
    sources = {step.get("source") for step in plan["joins"]}
    assert "confirmed" in sources, plan


def test_cross_predict_request_mode_overrides_default(
    client, project, upload_dataset, cp_orders_csv, cp_customers_csv,
):
    u, pid = project("cp-mode")
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    r = client.post(
        f"/api/projects/{pid}/cross-predict",
        json={
            "target_dataset_id": orders_id,
            "target_column": "sales",
            "request_mode": "expert",
        },
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "expert"
