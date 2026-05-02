"""Daily Pulse scheduler (Task #248).

A lightweight in-process job scheduler (APScheduler ``BackgroundScheduler``)
that runs once a day, iterates every active project, and persists a
``DailyPulseSnapshot`` row per project capturing:

* Headline auto-profile metrics (``backend.insights.build_profile``).
* The mode-aware predictions engine output
  (``backend.predictions_engine.run_prediction``).
* Per-metric deltas vs. the previous snapshot
  (``today / yesterday / change_pct``).
* Z-score anomaly flags (``predictions.detect_anomalies_zscore``) for
  the same numeric columns.
* A small ``recommendations`` list lifted from the predictions engine.

The whole job is best-effort and isolated per project — any single
project failure is logged and skipped so one bad dataset can't block
the others.

Single-worker assumption
~~~~~~~~~~~~~~~~~~~~~~~~
This is an in-process ``BackgroundScheduler``. With more than one
uvicorn worker the same job would fire once per worker; the unique
``(project_id, snapshot_date)`` constraint dedupes the writes (the
losers raise ``IntegrityError`` and roll back), so correctness is
preserved, but the redundant work is wasted.

Design notes
~~~~~~~~~~~~
* No FastAPI imports here — pure logic + a SQLAlchemy session.
* The job hour is configurable via the ``AXIOM_DAILY_PULSE_HOUR``
  environment variable (default ``2``).
* The endpoint at ``/api/projects/{project_id}/daily-pulse`` falls
  back to a synchronous ``build_pulse_snapshot`` call when no row
  exists yet, so first-load isn't a 404.
"""
from __future__ import annotations

import io
import logging
import math
import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

import models  # type: ignore

log = logging.getLogger("axiom.daily_pulse")

# Single module-level scheduler instance. ``start()`` is idempotent so
# repeated calls (e.g. test fixtures) don't spawn multiple schedulers.
_SCHEDULER: Any = None
_JOB_ID = "axiom_daily_pulse"
_ACTIVE_WINDOW_DAYS = 60
DEFAULT_HOUR = 2
ANOMALY_THRESHOLD = 3.0


# ---------------------------------------------------------------------------
# Public scheduler controls
# ---------------------------------------------------------------------------

def start() -> bool:
    """Boot the BackgroundScheduler if it isn't already running.

    Returns ``True`` when the scheduler is live (or was already live)
    and ``False`` when APScheduler couldn't be initialised — callers
    log the failure but should keep going so the on-demand endpoint
    still works.
    """
    global _SCHEDULER
    if _SCHEDULER is not None and getattr(_SCHEDULER, "running", False):
        return True
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except Exception as exc:  # pragma: no cover - import guard
        log.warning("apscheduler unavailable: %s", exc)
        return False

    try:
        hour = int(os.environ.get("AXIOM_DAILY_PULSE_HOUR") or DEFAULT_HOUR)
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    hour = max(0, min(23, hour))

    try:
        sched = BackgroundScheduler(timezone="UTC")
        sched.add_job(
            run_daily_pulse_for_all_projects,
            trigger=CronTrigger(hour=hour, minute=0),
            id=_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )
        sched.start()
        _SCHEDULER = sched
        log.info("Daily Pulse scheduler started (hour=%d UTC)", hour)
        return True
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Daily Pulse scheduler failed to start: %s", exc)
        _SCHEDULER = None
        return False


def shutdown() -> None:
    """Stop the BackgroundScheduler if it is running. Best-effort."""
    global _SCHEDULER
    sched = _SCHEDULER
    _SCHEDULER = None
    if sched is None:
        return
    try:
        sched.shutdown(wait=False)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Daily Pulse scheduler shutdown failed: %s", exc)


def is_running() -> bool:
    """Whether the BackgroundScheduler is currently running."""
    return _SCHEDULER is not None and bool(getattr(_SCHEDULER, "running", False))


# ---------------------------------------------------------------------------
# Job entrypoint
# ---------------------------------------------------------------------------

def run_daily_pulse_for_all_projects() -> dict[str, Any]:
    """Iterate every active project and persist its snapshot.

    "Active" means: project has at least one dataset and
    ``last_opened_at`` is within the last 60 days. Archived projects
    are always skipped. Returns a small accounting dict — useful for
    test assertions and for log lines in production.
    """
    db = models.SessionLocal()
    processed: list[int] = []
    skipped: list[int] = []
    errors: list[dict[str, Any]] = []
    try:
        project_ids = _list_active_project_ids(db)
        for pid in project_ids:
            try:
                build_pulse_snapshot(db, pid)
                processed.append(pid)
            except SkipProject as exc:
                skipped.append(pid)
                log.info("Daily Pulse skipped project %s: %s", pid, exc)
            except Exception as exc:  # pragma: no cover - defensive logging
                errors.append({"project_id": pid, "error": str(exc)})
                log.exception("Daily Pulse failed for project %s", pid)
                try:
                    db.rollback()
                except Exception:
                    pass
    finally:
        try:
            db.close()
        except Exception:
            pass
    return {"processed": processed, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

class SkipProject(RuntimeError):
    """Raised when a project should be silently skipped (e.g. no data)."""


def build_pulse_snapshot(
    db, project_id: int, *, snapshot_date: date | None = None,
) -> dict[str, Any]:
    """Build, persist, and return a single project's daily snapshot.

    When ``snapshot_date`` is omitted we use today's UTC date — which
    is what the cron job and the on-demand endpoint both want. Tests
    pass an explicit date when they need determinism.

    The function is idempotent for the same ``(project_id,
    snapshot_date)`` pair: a second call updates the existing row in
    place rather than inserting a duplicate.
    """
    snapshot_date = snapshot_date or _today()
    project = (
        db.query(models.Project)
          .filter(models.Project.id == project_id)
          .first()
    )
    if project is None:
        raise SkipProject(f"project {project_id} does not exist")

    df, dataset_meta = _resolve_project_frame(db, project_id)
    if df is None or df.empty:
        raise SkipProject(f"project {project_id} has no usable data")

    profile = _safe_call(_build_profile, df) or {}
    predictions = _safe_call(_build_predictions, df) or {}
    anomalies = _safe_call(_build_anomalies, df) or []

    previous = _previous_snapshot(db, project_id, snapshot_date)
    top_changes = _diff_against(previous, profile)

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "snapshot_date": snapshot_date.isoformat(),
        "project_id": project_id,
        "dataset": dataset_meta,
        "profile": profile,
        "top_changes": top_changes,
        "anomalies": anomalies,
        "predictions": predictions,
        "recommendations": _extract_recommendations(predictions),
    }

    _upsert_snapshot(db, project_id, snapshot_date, payload)

    # Recommendations engine (Task #251) feeds off the snapshot we
    # just persisted, so chain it here. Best-effort — a recommendations
    # failure must not block the snapshot itself.
    try:
        from . import recommendations as _recs
        _recs.generate_for_project(db, project_id, today=snapshot_date)
    except Exception as exc:  # pragma: no cover - defensive
        log.info("recommendations engine skipped for project %s: %s",
                 project_id, exc)
        try:
            db.rollback()
        except Exception:
            pass

    return payload


# ---------------------------------------------------------------------------
# Helpers (project + dataset selection)
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.utcnow().date()


def _list_active_project_ids(db) -> list[int]:
    """Active = ≥1 dataset AND ``last_opened_at`` within the last 60d.

    Archived projects are always excluded.
    """
    cutoff = datetime.utcnow() - timedelta(days=_ACTIVE_WINDOW_DAYS)
    rows = (
        db.query(models.Project.id)
          .join(
              models.DatasetRecord,
              models.DatasetRecord.project_id == models.Project.id,
          )
          .filter(
              models.Project.archived_at.is_(None),
              models.Project.last_opened_at.isnot(None),
              models.Project.last_opened_at >= cutoff,
          )
          .group_by(models.Project.id)
          .order_by(models.Project.id.asc())
          .all()
    )
    return [int(r[0]) for r in rows]


def _project_dataset_records(db, project_id: int) -> list[Any]:
    return (
        db.query(models.DatasetRecord)
          .filter(models.DatasetRecord.project_id == project_id)
          .order_by(models.DatasetRecord.upload_date.desc().nullslast(),
                    models.DatasetRecord.id.desc())
          .all()
    )


def _resolve_project_frame(
    db, project_id: int,
) -> tuple[pd.DataFrame | None, dict[str, Any]]:
    """Pick the dataframe the snapshot will analyse.

    Strategy:
      1. List every dataset on the project.
      2. If a single relationship can be applied to two of them, run
         the merge so the snapshot reflects the joined view.
      3. Otherwise fall back to the most-recently uploaded dataset.

    Returns ``(df, meta)`` where ``meta`` describes which dataset(s)
    we ended up using — embedded in the snapshot for traceability.
    """
    records = _project_dataset_records(db, project_id)
    if not records:
        return None, {}

    if len(records) >= 2:
        merged = _try_merge(db, project_id, records)
        if merged is not None:
            return merged

    # Fall back to the most-recent dataset that has actual bytes.
    for rec in records:
        if not rec.source_parquet:
            continue
        try:
            df = pd.read_parquet(io.BytesIO(rec.source_parquet))
        except Exception as exc:
            log.warning(
                "could not load dataset %s for project %s: %s",
                rec.id, project_id, exc,
            )
            continue
        meta = {
            "kind": "single",
            "dataset_id": int(rec.id),
            "dataset_name": rec.dataset_name or rec.filename,
            "rows": int(len(df)),
            "cols": int(df.shape[1]),
        }
        return df, meta
    return None, {}


def _try_merge(
    db, project_id: int, records: list[Any],
) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """If a confirmed cross-dataset relationship exists, merge two
    frames and return ``(merged_df, meta)``. Returns ``None`` when no
    usable relationship is found."""
    by_id = {int(r.id): r for r in records}
    rels = (
        db.query(models.ProjectRelationship)
          .filter(models.ProjectRelationship.project_id == project_id,
                  models.ProjectRelationship.status == "confirmed")
          .order_by(models.ProjectRelationship.updated_at.desc().nullslast(),
                    models.ProjectRelationship.id.desc())
          .all()
    )
    for rel in rels:
        left_rec = by_id.get(int(rel.left_dataset_id))
        right_rec = by_id.get(int(rel.right_dataset_id))
        if not left_rec or not right_rec:
            continue
        if not left_rec.source_parquet or not right_rec.source_parquet:
            continue
        try:
            left_df = pd.read_parquet(io.BytesIO(left_rec.source_parquet))
            right_df = pd.read_parquet(io.BytesIO(right_rec.source_parquet))
            merged = pd.merge(
                left_df, right_df,
                how=rel.join_type or "left",
                left_on=rel.left_column, right_on=rel.right_column,
                suffixes=("_left", "_right"),
            )
        except Exception as exc:
            log.warning(
                "merge failed for project %s relationship %s: %s",
                project_id, rel.id, exc,
            )
            continue
        meta = {
            "kind": "merged",
            "left_dataset_id": int(left_rec.id),
            "right_dataset_id": int(right_rec.id),
            "left_dataset_name": left_rec.dataset_name or left_rec.filename,
            "right_dataset_name": right_rec.dataset_name or right_rec.filename,
            "join_type": rel.join_type or "left",
            "left_column": rel.left_column,
            "right_column": rel.right_column,
            "rows": int(len(merged)),
            "cols": int(merged.shape[1]),
        }
        return merged, meta
    return None


# ---------------------------------------------------------------------------
# Per-snapshot computations
# ---------------------------------------------------------------------------

def _build_profile(df: pd.DataFrame) -> dict[str, Any]:
    from backend import insights as ins  # local import to avoid cycles

    return ins.build_profile(df)


def _build_predictions(df: pd.DataFrame) -> dict[str, Any]:
    """Run the predictions engine; downgrade gracefully on failure."""
    try:
        from backend import predictions_engine as pe
        return pe.run_prediction(df)
    except Exception as exc:
        log.info("predictions engine skipped: %s", exc)
        return {"error": str(exc)}


def _build_anomalies(df: pd.DataFrame) -> list[dict[str, Any]]:
    try:
        from predictions import detect_anomalies_zscore  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        log.warning("anomaly detector unavailable: %s", exc)
        return []
    try:
        raw = detect_anomalies_zscore(df, threshold=ANOMALY_THRESHOLD)
    except Exception as exc:
        log.info("anomaly detector failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for col, info in (raw or {}).items():
        if not isinstance(info, dict):
            continue
        out.append({
            "column": str(col),
            "count": int(info.get("count") or 0),
            "indices": [int(i) for i in (info.get("indices") or [])][:10],
            "values": [
                _safe_float(v) for v in (info.get("values") or [])
            ][:10],
        })
    out.sort(key=lambda r: r["count"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------

def _diff_against(
    previous: dict[str, Any] | None, current: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Compare two profile dicts and return per-metric change rows.

    Each row is ``{column, metric, today, yesterday, change_pct}``.
    Top-level dataset metrics (``rows``, ``cols``, ``duplicate_rows``,
    ``memory_kb``) appear with ``column == "__dataset__"``. Per-column
    numeric stats use the column name. Sorted by absolute
    ``change_pct`` descending so the most volatile metrics float to
    the top.
    """
    current = current or {}
    previous = previous or {}
    rows: list[dict[str, Any]] = []

    # ---- Dataset-level scalars ----------------------------------------
    for key in ("rows", "cols", "duplicate_rows", "memory_kb"):
        today_val = _safe_float(current.get(key))
        prev_val = _safe_float(previous.get(key))
        rows.append(_change_row("__dataset__", key, today_val, prev_val))

    # ---- Per-column numeric metrics -----------------------------------
    prev_cols = {
        str(c.get("name")): c
        for c in (previous.get("columns") or [])
        if isinstance(c, dict)
    }
    metric_keys = ("mean", "median", "std", "min", "max",
                   "missing", "missing_pct", "unique")
    for col in (current.get("columns") or []):
        if not isinstance(col, dict):
            continue
        name = str(col.get("name"))
        prev_col = prev_cols.get(name) or {}
        for metric in metric_keys:
            if metric not in col and metric not in prev_col:
                continue
            today_val = _safe_float(col.get(metric))
            prev_val = _safe_float(prev_col.get(metric))
            if today_val is None and prev_val is None:
                continue
            rows.append(_change_row(name, metric, today_val, prev_val))

    rows.sort(key=lambda r: abs(r.get("change_pct") or 0.0), reverse=True)
    return rows


def _change_row(
    column: str, metric: str, today: float | None, yesterday: float | None,
) -> dict[str, Any]:
    return {
        "column": column,
        "metric": metric,
        "today": today,
        "yesterday": yesterday,
        "change_pct": _change_pct(today, yesterday),
    }


def _change_pct(today: float | None, yesterday: float | None) -> float | None:
    if today is None or yesterday is None:
        return None
    if yesterday == 0:
        if today == 0:
            return 0.0
        return None  # undefined % change against a zero baseline
    try:
        return round((float(today) - float(yesterday)) / float(yesterday) * 100, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _extract_recommendations(predictions: dict[str, Any]) -> list[str]:
    if not isinstance(predictions, dict):
        return []
    guided = predictions.get("guided") or {}
    recs = guided.get("recommendations") or []
    if not isinstance(recs, list):
        return []
    return [str(r) for r in recs if r][:5]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _previous_snapshot(
    db, project_id: int, snapshot_date: date,
) -> dict[str, Any] | None:
    """The most recent profile (as a plain dict) prior to ``snapshot_date``.

    Returns the ``profile`` slice of the previous snapshot's payload,
    which is what :func:`_diff_against` consumes. Returns ``None``
    when no earlier snapshot exists.
    """
    row = (
        db.query(models.DailyPulseSnapshot)
          .filter(models.DailyPulseSnapshot.project_id == project_id,
                  models.DailyPulseSnapshot.snapshot_date < snapshot_date)
          .order_by(models.DailyPulseSnapshot.snapshot_date.desc(),
                    models.DailyPulseSnapshot.id.desc())
          .first()
    )
    if row is None:
        return None
    payload = row.snapshot_json or {}
    profile = payload.get("profile")
    return profile if isinstance(profile, dict) else None


def _upsert_snapshot(
    db, project_id: int, snapshot_date: date, payload: dict[str, Any],
) -> models.DailyPulseSnapshot:
    """Insert a snapshot row, or update the existing one for the same day.

    The unique ``(project_id, snapshot_date)`` constraint guarantees
    only one row per day; this helper makes the same-day re-run a
    safe in-place update instead of an ``IntegrityError``.
    """
    existing = (
        db.query(models.DailyPulseSnapshot)
          .filter(models.DailyPulseSnapshot.project_id == project_id,
                  models.DailyPulseSnapshot.snapshot_date == snapshot_date)
          .first()
    )
    if existing is not None:
        existing.snapshot_json = payload
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    row = models.DailyPulseSnapshot(
        project_id=project_id,
        snapshot_date=snapshot_date,
        snapshot_json=payload,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        # Another worker raced us to the same (project_id, date). Roll
        # back, fetch, and update in-place so the result is identical.
        db.rollback()
        existing = (
            db.query(models.DailyPulseSnapshot)
              .filter(models.DailyPulseSnapshot.project_id == project_id,
                      models.DailyPulseSnapshot.snapshot_date == snapshot_date)
              .first()
        )
        if existing is None:
            raise
        existing.snapshot_json = payload
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    db.refresh(row)
    return row


def latest_snapshot(db, project_id: int) -> models.DailyPulseSnapshot | None:
    return (
        db.query(models.DailyPulseSnapshot)
          .filter(models.DailyPulseSnapshot.project_id == project_id)
          .order_by(models.DailyPulseSnapshot.snapshot_date.desc(),
                    models.DailyPulseSnapshot.id.desc())
          .first()
    )


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        log.info("%s failed: %s", getattr(fn, "__name__", "fn"), exc)
        return None
