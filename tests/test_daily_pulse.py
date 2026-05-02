"""Tests for the Daily Pulse cron + endpoint (Task #248).

Coverage:
  * Snapshot creation persists exactly one ``daily_pulse_snapshots``
    row with the documented response shape.
  * Same-day re-runs are idempotent — the unique
    ``(project_id, snapshot_date)`` constraint dedupes via in-place
    update rather than raising or duplicating.
  * Day-over-day deltas appear in ``top_changes`` with the right
    sign and magnitude.
  * The ``/api/projects/{project_id}/daily-pulse`` endpoint synthesises
    a snapshot on the fly when none exists yet (on-demand fallback).
  * Active-project filter respects ``last_opened_at`` window and
    archived flag.
  * ``response_shape`` exposes the four documented top-level keys.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
from freezegun import freeze_time

import models  # type: ignore
from backend import scheduler as sched


def _seed_dataset(db, project_id: int, df: pd.DataFrame, name: str = "ds") -> int:
    """Materialise a parquet-backed DatasetRecord directly via SQLAlchemy.

    Skips the upload endpoint (which is heavier and exercises plenty
    of unrelated code) — we only need a row whose ``source_parquet``
    bytes round-trip back into the same dataframe.
    """
    import hashlib as _hl
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    parquet_bytes = buf.getvalue()
    rec = models.DatasetRecord(
        user_id=db.query(models.Project)
                  .filter(models.Project.id == project_id)
                  .first().user_id,
        project_id=project_id,
        filename=f"{name}.parquet",
        dataset_name=name,
        row_count=int(len(df)),
        column_count=int(df.shape[1]),
        data_hash=_hl.sha256(parquet_bytes).hexdigest(),
        source_parquet=parquet_bytes,
        upload_date=datetime.utcnow(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return int(rec.id)


def _make_project(db, user_id: int, name: str = "pulse_proj") -> int:
    proj = models.Project(user_id=user_id, name=name,
                          last_opened_at=datetime.utcnow())
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return int(proj.id)


@pytest.fixture
def pulse_user(register):
    return register("pulse")


@pytest.fixture
def pulse_project(pulse_user):
    db = models.SessionLocal()
    try:
        pid = _make_project(db, pulse_user["user"]["id"], name="pulse_proj")
    finally:
        db.close()
    return pulse_user, pid


@pytest.fixture
def df_v1() -> pd.DataFrame:
    return pd.DataFrame({
        "id": list(range(1, 21)),
        "amount": [10.0 + i for i in range(20)],
        "category": ["a", "b"] * 10,
    })


@pytest.fixture
def df_v2(df_v1) -> pd.DataFrame:
    """Same shape as df_v1, but ``amount`` is doubled — perfect for
    asserting a clean +100% delta in the snapshot diff."""
    df = df_v1.copy()
    df["amount"] = df["amount"] * 2
    return df


# ---------------------------------------------------------------------------
# Snapshot creation + idempotency
# ---------------------------------------------------------------------------

def test_build_pulse_snapshot_creates_row_with_expected_shape(
    pulse_project, df_v1,
):
    user, pid = pulse_project
    db = models.SessionLocal()
    try:
        _seed_dataset(db, pid, df_v1, name="seed")
        payload = sched.build_pulse_snapshot(db, pid, snapshot_date=date(2024, 1, 1))

        for key in ("generated_at", "snapshot_date", "top_changes",
                    "anomalies", "predictions", "recommendations",
                    "profile", "dataset"):
            assert key in payload, f"missing key {key!r} in snapshot"
        assert payload["snapshot_date"] == "2024-01-01"
        assert payload["profile"]["rows"] == 20
        assert payload["profile"]["cols"] == 3
        assert isinstance(payload["top_changes"], list)
        assert isinstance(payload["anomalies"], list)
        assert isinstance(payload["recommendations"], list)

        rows = (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == pid)
              .all()
        )
        assert len(rows) == 1
        assert rows[0].snapshot_date == date(2024, 1, 1)
    finally:
        db.close()


def test_build_pulse_snapshot_is_idempotent_per_day(pulse_project, df_v1):
    """Two calls on the same date must keep exactly one row."""
    user, pid = pulse_project
    db = models.SessionLocal()
    try:
        _seed_dataset(db, pid, df_v1, name="seed")
        sched.build_pulse_snapshot(db, pid, snapshot_date=date(2024, 1, 5))
        sched.build_pulse_snapshot(db, pid, snapshot_date=date(2024, 1, 5))

        rows = (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == pid)
              .all()
        )
        assert len(rows) == 1, "second same-day call must update in place"
    finally:
        db.close()


def test_build_pulse_snapshot_keeps_history_across_days(
    pulse_project, df_v1, df_v2,
):
    user, pid = pulse_project
    db = models.SessionLocal()
    try:
        ds_id = _seed_dataset(db, pid, df_v1, name="seed")

        # Day 1 — original data.
        sched.build_pulse_snapshot(db, pid, snapshot_date=date(2024, 2, 1))

        # Day 2 — replace dataset content with df_v2 (same row count,
        # double-amount). New parquet bytes, same id.
        rec = (
            db.query(models.DatasetRecord)
              .filter(models.DatasetRecord.id == ds_id)
              .first()
        )
        buf = io.BytesIO()
        df_v2.to_parquet(buf, index=False)
        rec.source_parquet = buf.getvalue()
        db.commit()

        payload = sched.build_pulse_snapshot(
            db, pid, snapshot_date=date(2024, 2, 2),
        )

        rows = (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == pid)
              .order_by(models.DailyPulseSnapshot.snapshot_date.asc())
              .all()
        )
        assert [r.snapshot_date for r in rows] == [date(2024, 2, 1),
                                                    date(2024, 2, 2)]

        amount_means = [
            row for row in payload["top_changes"]
            if row["column"] == "amount" and row["metric"] == "mean"
        ]
        assert amount_means, "expected an amount/mean delta row"
        delta = amount_means[0]
        assert delta["yesterday"] is not None
        assert delta["today"] is not None
        # df_v2 = 2 * df_v1 → mean exactly doubles → +100% change.
        assert delta["change_pct"] == pytest.approx(100.0, rel=1e-3)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Active-project filter
# ---------------------------------------------------------------------------

def test_active_project_filter_skips_archived_and_stale(register):
    user = register("active")
    db = models.SessionLocal()
    try:
        uid = user["user"]["id"]
        # Active: opened today + has dataset.
        active_id = _make_project(db, uid, name="active")
        _seed_dataset(db, active_id, pd.DataFrame({"x": [1, 2, 3]}), name="a")

        # Archived: skipped even with a dataset and recent open.
        archived_id = _make_project(db, uid, name="archived")
        _seed_dataset(db, archived_id, pd.DataFrame({"x": [1, 2, 3]}), name="b")
        proj = (db.query(models.Project)
                  .filter(models.Project.id == archived_id).first())
        proj.archived_at = datetime.utcnow()
        db.commit()

        # Stale: last_opened > 60 days ago → out of window.
        stale_id = _make_project(db, uid, name="stale")
        _seed_dataset(db, stale_id, pd.DataFrame({"x": [1, 2, 3]}), name="c")
        proj = (db.query(models.Project)
                  .filter(models.Project.id == stale_id).first())
        proj.last_opened_at = datetime.utcnow() - timedelta(days=120)
        db.commit()

        # No-data: opened today but zero datasets → skipped.
        empty_id = _make_project(db, uid, name="empty")

        ids = sched._list_active_project_ids(db)
        assert active_id in ids
        assert archived_id not in ids
        assert stale_id not in ids
        assert empty_id not in ids
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoint: response shape + on-demand fallback
# ---------------------------------------------------------------------------

def test_endpoint_on_demand_fallback_when_no_snapshot_exists(
    client, pulse_project, df_v1,
):
    """Hitting the endpoint with zero stored rows must synthesise one."""
    user, pid = pulse_project
    db = models.SessionLocal()
    try:
        _seed_dataset(db, pid, df_v1, name="seed")
        # Sanity: nothing persisted yet for THIS project.
        assert (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == pid)
              .count()
        ) == 0
    finally:
        db.close()

    r = client.get(
        f"/api/projects/{pid}/daily-pulse", headers=user["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Strict response envelope: exactly the five documented keys.
    assert set(body.keys()) == {
        "generated_at", "top_changes", "anomalies",
        "predictions", "recommendations",
    }
    assert isinstance(body["top_changes"], list)
    assert isinstance(body["anomalies"], list)
    assert isinstance(body["recommendations"], list)
    assert isinstance(body["predictions"], dict)

    db = models.SessionLocal()
    try:
        # On-demand path persisted exactly one row for THIS project.
        assert (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == pid)
              .count()
        ) == 1
    finally:
        db.close()


def test_endpoint_returns_persisted_snapshot_unchanged(
    client, pulse_project, df_v1,
):
    """If a snapshot already exists, the endpoint returns it without
    rebuilding (same generated_at across two calls)."""
    user, pid = pulse_project
    db = models.SessionLocal()
    try:
        _seed_dataset(db, pid, df_v1, name="seed")
        sched.build_pulse_snapshot(db, pid, snapshot_date=date.today())
    finally:
        db.close()

    r1 = client.get(f"/api/projects/{pid}/daily-pulse",
                    headers=user["headers"])
    r2 = client.get(f"/api/projects/{pid}/daily-pulse",
                    headers=user["headers"])
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["generated_at"] == r2.json()["generated_at"]


def test_endpoint_rejects_other_users_project(
    client, register, pulse_project, df_v1,
):
    """Cross-user access must 404 — the snapshot is project-scoped."""
    _, pid = pulse_project
    db = models.SessionLocal()
    try:
        _seed_dataset(db, pid, df_v1, name="seed")
    finally:
        db.close()

    intruder = register("intruder")
    r = client.get(f"/api/projects/{pid}/daily-pulse",
                   headers=intruder["headers"])
    assert r.status_code == 404


def test_endpoint_409_when_project_has_no_data(client, pulse_project):
    """Empty project + no snapshot → 409 (the docs promise no data)."""
    user, pid = pulse_project
    r = client.get(f"/api/projects/{pid}/daily-pulse",
                   headers=user["headers"])
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Cron entrypoint
# ---------------------------------------------------------------------------

def test_run_daily_pulse_for_all_projects_processes_active_projects(
    register, df_v1,
):
    user = register("cron")
    db = models.SessionLocal()
    try:
        uid = user["user"]["id"]
        active_id = _make_project(db, uid, name="cron_active")
        _seed_dataset(db, active_id, df_v1, name="seed")

        empty_id = _make_project(db, uid, name="cron_empty")  # no data
    finally:
        db.close()

    with freeze_time("2024-03-15 02:00:00"):
        result = sched.run_daily_pulse_for_all_projects()

    assert active_id in result["processed"]
    # Empty project doesn't even reach build (no dataset → not active).
    assert empty_id not in result["processed"]
    assert empty_id not in result["skipped"]

    db = models.SessionLocal()
    try:
        rows = (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == active_id)
              .all()
        )
        assert len(rows) == 1
        assert rows[0].snapshot_date == date(2024, 3, 15)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_change_pct_handles_zero_and_none():
    assert sched._change_pct(None, None) is None
    assert sched._change_pct(10, None) is None
    assert sched._change_pct(None, 10) is None
    assert sched._change_pct(10, 0) is None  # undefined % vs 0 baseline
    assert sched._change_pct(0, 0) == 0.0
    assert sched._change_pct(20, 10) == pytest.approx(100.0)
    assert sched._change_pct(5, 10) == pytest.approx(-50.0)
