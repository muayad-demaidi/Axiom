"""Rule-based recommendation engine (Task #251).

Produces structured, actionable suggestions a project owner can act on
directly. Each recommendation is anchored on one of six rule types:

  * ``investigate`` — declining sales (slope < 0).
  * ``reorder`` — at risk of stockout within the horizon.
  * ``discount`` — aged inventory in the light/deep discount tiers.
  * ``bundle`` — very aged inventory still moving (avg outflow > 0).
  * ``clearance`` — very aged inventory that has stopped moving.
  * ``promote`` — strong, consistent sellers worth amplifying.

The rules feed off the inventory block already produced by
:func:`backend.predictions_engine.run_prediction` so we don't redo the
heavy lifting — the engine reuses what the daily pulse computed.

The HTTP surface mounted under
``/api/projects/{project_id}/recommendations`` is intentionally tiny:

  * ``GET ?status=open|dismissed|applied|all`` — list the project's
    recommendations, sorted by priority then created_at.
  * ``POST /{rec_id}/dismiss`` — mark a recommendation as dismissed.
  * ``POST /{rec_id}/apply`` — mark a recommendation as applied. The
    endpoint has **no external side-effects** — it only flips the flag
    + stamps the timestamp so the user can keep a clean inbox.

Mode (Guided/Expert) is a frontend concern; the API always returns the
same payload and ``ModeAwareSection`` on the dashboard picks the
right rendering. The backend exposes ``mode_dependency`` only for
audit/logging completeness.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func

import models  # type: ignore

from .auth import get_current_user, get_db_session
from .mode_resolver import mode_dependency, resolve_mode


# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------

class Recommendation(BaseModel):
    """API-shaped recommendation. Mirrors the SQLAlchemy row but with
    ISO-8601 datetimes and the dismissed/applied state fully expanded."""

    id: int
    type: str = Field(..., description="One of discount/reorder/bundle/"
                                       "clearance/promote/investigate")
    product: str
    reason: str
    suggested_action: str
    expected_impact: Optional[str] = None
    priority: str = "medium"
    deadline: Optional[datetime] = None
    confidence: float = 0.5
    dismissed: bool = False
    dismissed_at: Optional[datetime] = None
    applied: bool = False
    applied_at: Optional[datetime] = None
    created_at: datetime


def _to_response(row: models.Recommendation) -> Recommendation:
    """Convert a SQLAlchemy row to the API response shape."""
    return Recommendation(
        id=int(row.id),
        type=str(row.type),
        product=str(row.product),
        reason=str(row.reason or ""),
        suggested_action=str(row.suggested_action or ""),
        expected_impact=row.expected_impact,
        priority=str(row.priority or "medium"),
        deadline=row.deadline,
        confidence=float(row.confidence or 0.0),
        dismissed=bool(row.dismissed),
        dismissed_at=row.dismissed_at,
        applied=bool(row.applied),
        applied_at=row.applied_at,
        created_at=row.created_at or datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

# Priority ordering used wherever we sort. ``high`` first so the most
# urgent items float to the top of the list / cards.
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Promote rule thresholds: a product is a "strong seller" when it has
# been seen recently and is trending up.
_PROMOTE_RECENT_DAYS = 7
_PROMOTE_MIN_HISTORY = 7

# Stockout rule: how many days of headroom turn an item into a
# medium-priority reorder vs the high-priority "<3 days" alert.
_REORDER_URGENT_DAYS = 3


def _project_inventory(db, project_id: int) -> dict[str, Any] | None:
    """Pull the inventory block from the most recent pulse snapshot.

    The daily pulse persists ``snapshot_json.predictions`` which carries
    the dual ``{guided, expert}`` payload. We read the expert side
    because it is the one that always carries the ``inventory`` dict.
    Returns ``None`` when the snapshot doesn't exist yet or doesn't
    expose an inventory block — the caller falls back to a fresh run.
    """
    row = (
        db.query(models.DailyPulseSnapshot)
          .filter(models.DailyPulseSnapshot.project_id == project_id)
          .order_by(models.DailyPulseSnapshot.snapshot_date.desc(),
                    models.DailyPulseSnapshot.id.desc())
          .first()
    )
    if row is None:
        return None
    payload = row.snapshot_json or {}
    predictions = payload.get("predictions") or {}
    inventory = (
        (predictions.get("expert") or {}).get("inventory")
        or predictions.get("inventory")
    )
    if isinstance(inventory, dict) and inventory.get("available"):
        return inventory
    return None


def _fresh_inventory(db, project_id: int) -> dict[str, Any] | None:
    """Last-resort: re-run the predictions engine on the current frame.

    Only called when no snapshot exists; the daily-pulse cron normally
    produces one each night so this path is the on-demand bootstrap.
    """
    try:
        from backend import scheduler as sched
        df, _meta = sched._resolve_project_frame(db, project_id)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    try:
        from backend import predictions_engine as pe
        result = pe.run_prediction(df)
    except Exception:
        return None
    expert = (result or {}).get("expert") or {}
    inventory = expert.get("inventory")
    if isinstance(inventory, dict) and inventory.get("available"):
        return inventory
    return None


def _index_products(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Turn ``inventory.products`` into a name → row lookup."""
    out: dict[str, dict[str, Any]] = {}
    for prod in (inventory.get("products") or []):
        if not isinstance(prod, dict):
            continue
        name = str(prod.get("product") or "").strip()
        if name:
            out[name] = prod
    return out


def _stockout_index(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in (inventory.get("stockout_risk") or []):
        if not isinstance(r, dict):
            continue
        name = str(r.get("product") or "").strip()
        if name:
            out[name] = r
    return out


def _build_candidates(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn an inventory dict into a list of candidate recommendations.

    Each candidate is the dict that will be persisted as one row, minus
    the ``project_id`` / ``user_id`` / ``created_at`` fields the caller
    fills in. The list is intentionally not deduped here — the caller
    collapses by ``(type, product)`` so the most-recent rule wins.
    """
    candidates: list[dict[str, Any]] = []
    products = _index_products(inventory)
    stockouts = _stockout_index(inventory)
    horizon = int(inventory.get("stockout_horizon_days") or 14)

    # ---- 1. investigate (declining trend) ---------------------------------
    for d in (inventory.get("declining") or []):
        if not isinstance(d, dict):
            continue
        name = str(d.get("product") or "").strip()
        if not name:
            continue
        slope = float(d.get("slope") or 0.0)
        candidates.append({
            "type": "investigate",
            "product": name,
            "reason": (
                f"Sales of '{name}' are trending down "
                f"(slope {slope:+.4f} per day)."
            ),
            "suggested_action": (
                "Investigate root cause: pricing, competition, seasonality, "
                "stock issues, or upstream marketing."
            ),
            "expected_impact": "Reverse the decline before it compounds.",
            "priority": "high",
            "confidence": 0.7,
            "deadline": _deadline(days=14),
        })

    # ---- 2. reorder (stockout risk) ---------------------------------------
    for r in (inventory.get("stockout_risk") or []):
        if not isinstance(r, dict):
            continue
        name = str(r.get("product") or "").strip()
        if not name:
            continue
        days_to_zero = float(r.get("days_to_zero") or 0.0)
        urgent = days_to_zero <= _REORDER_URGENT_DAYS
        candidates.append({
            "type": "reorder",
            "product": name,
            "reason": (
                f"'{name}' will run out in ~{days_to_zero:.1f} days at the "
                f"current outflow ({float(r.get('avg_daily_outflow') or 0):.2f}"
                "/day)."
            ),
            "suggested_action": (
                f"Place a reorder now to cover at least the next "
                f"{horizon} days of demand."
            ),
            "expected_impact": "Avoid lost sales from a stockout.",
            "priority": "high" if urgent else "medium",
            "confidence": 0.85 if urgent else 0.7,
            "deadline": _deadline(days=max(1, int(days_to_zero))),
        })

    # ---- 3/4/5. discount / bundle / clearance from tiered suggestions ----
    for s in (inventory.get("discount_suggestions") or []):
        if not isinstance(s, dict):
            continue
        name = str(s.get("product") or "").strip()
        if not name:
            continue
        tier = str(s.get("tier") or "").lower()
        days_since = int(s.get("days_since_last_activity") or 0)
        pct = s.get("discount_pct")
        prod_meta = products.get(name) or {}
        avg_daily = float(prod_meta.get("avg_daily") or 0.0)

        if tier in ("light_discount", "deep_discount"):
            candidates.append({
                "type": "discount",
                "product": name,
                "reason": (
                    f"'{name}' has been idle for {days_since} day(s)."
                ),
                "suggested_action": (
                    f"Apply a {pct}% discount to revive demand."
                    if pct is not None else "Apply a discount to revive demand."
                ),
                "expected_impact": (
                    f"Pull aged stock through with a {pct}% price cut."
                    if pct is not None else "Pull aged stock through."
                ),
                "priority": "high" if tier == "deep_discount" else "medium",
                "confidence": 0.65 if tier == "deep_discount" else 0.55,
                "deadline": _deadline(days=14),
            })
        elif tier == "bundle_clearance":
            # Still moving (some daily outflow) → bundle. Stagnant
            # (zero outflow) → clearance. This split lets the user
            # see two different motions for two different problems.
            if avg_daily > 0:
                candidates.append({
                    "type": "bundle",
                    "product": name,
                    "reason": (
                        f"'{name}' is aging ({days_since}d idle) but still "
                        "has outflow."
                    ),
                    "suggested_action": (
                        f"Bundle '{name}' with a fast-moving SKU to keep it "
                        "in the basket."
                    ),
                    "expected_impact": "Lift aged stock without hard markdowns.",
                    "priority": "medium",
                    "confidence": 0.55,
                    "deadline": _deadline(days=21),
                })
            else:
                candidates.append({
                    "type": "clearance",
                    "product": name,
                    "reason": (
                        f"'{name}' has been completely stagnant for "
                        f"{days_since} day(s)."
                    ),
                    "suggested_action": (
                        f"Mark '{name}' for clearance — recover capital and "
                        "free up shelf/warehouse space."
                    ),
                    "expected_impact": "Recover working capital tied to dead stock.",
                    "priority": "high",
                    "confidence": 0.7,
                    "deadline": _deadline(days=30),
                })

    # ---- 6. promote (consistent strong sellers) --------------------------
    for prod in products.values():
        name = str(prod.get("product") or "").strip()
        if not name:
            continue
        slope = float(prod.get("slope") or 0.0)
        days_since = int(prod.get("days_since_last_activity") or 9999)
        history = int(prod.get("history_days") or 0)
        if (slope > 0
                and days_since <= _PROMOTE_RECENT_DAYS
                and history >= _PROMOTE_MIN_HISTORY
                and name not in stockouts):
            candidates.append({
                "type": "promote",
                "product": name,
                "reason": (
                    f"'{name}' is trending up (+{slope:.4f}/day) with recent "
                    "activity."
                ),
                "suggested_action": (
                    f"Feature '{name}' in marketing pushes — front-page slot, "
                    "email, paid social — while momentum is on its side."
                ),
                "expected_impact": "Compound the upswing while it's still warm.",
                "priority": "medium",
                "confidence": 0.6,
                "deadline": _deadline(days=14),
            })

    return candidates


def _deadline(days: int) -> datetime:
    return datetime.utcnow() + timedelta(days=max(1, int(days)))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def generate_for_project(
    db, project_id: int, *, today: date | None = None,
) -> list[models.Recommendation]:
    """Run all rules for ``project_id`` and persist new recommendations.

    The function is idempotent for the same calendar day: re-running it
    does not create duplicate ``(type, product, DATE(created_at))``
    rows. Returns the freshly persisted rows (not the historical ones).
    """
    today = today or datetime.utcnow().date()
    project = (
        db.query(models.Project)
          .filter(models.Project.id == project_id)
          .first()
    )
    if project is None:
        return []

    inventory = _project_inventory(db, project_id) or _fresh_inventory(db, project_id)
    if not inventory:
        return []

    candidates = _build_candidates(inventory)
    if not candidates:
        return []

    # In-memory dedupe per (type, product) — when two rules fire on the
    # same product (e.g. discount + bundle) we keep the higher-priority
    # one. Same priority → keep the first. This keeps the daily list
    # tight even before the unique index kicks in.
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for cand in candidates:
        key = (cand["type"], cand["product"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = cand
            continue
        if (_PRIORITY_ORDER.get(cand["priority"], 9)
                < _PRIORITY_ORDER.get(existing["priority"], 9)):
            by_key[key] = cand

    # Same-day rows already in the table: don't insert duplicates.
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)
    existing_today = {
        (r.type, r.product)
        for r in (
            db.query(models.Recommendation)
              .filter(models.Recommendation.project_id == project_id,
                      models.Recommendation.created_at >= start,
                      models.Recommendation.created_at < end)
              .all()
        )
    }

    inserted: list[models.Recommendation] = []
    for key, cand in by_key.items():
        if key in existing_today:
            continue
        row = models.Recommendation(
            project_id=project_id,
            user_id=int(project.user_id),
            type=cand["type"],
            product=cand["product"][:255],
            reason=cand["reason"],
            suggested_action=cand["suggested_action"],
            expected_impact=cand.get("expected_impact"),
            priority=cand.get("priority", "medium"),
            deadline=cand.get("deadline"),
            confidence=float(cand.get("confidence", 0.5)),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        try:
            db.commit()
        except Exception:
            # Lost a race against the unique index — fetch the existing
            # row instead of raising. ``commit`` is the only place the
            # constraint can fire so we reset cleanly.
            db.rollback()
            continue
        db.refresh(row)
        inserted.append(row)
    return inserted


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

router = APIRouter(tags=["recommendations"])


@router.get("/api/projects/{project_id}/recommendations")
async def list_recommendations(
    project_id: int,
    status: str = Query("open", regex="^(open|dismissed|applied|all)$"),
    user=Depends(get_current_user),
    db=Depends(get_db_session),
    mode: str = Depends(mode_dependency()),
):
    """List the project's recommendations, sorted by priority desc.

    ``status`` filter:

      * ``open`` (default) — neither dismissed nor applied.
      * ``dismissed`` — marked as dismissed.
      * ``applied`` — marked as applied.
      * ``all`` — everything.

    The response includes the resolved ``mode`` so a Guided client and
    an Expert client can render the same payload differently without
    needing a second round-trip.
    """
    project = models.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(404, "Project not found")

    # Bootstrap on first load: if there are no rows yet, try to derive
    # some so the panel never shows an empty state on a brand-new
    # project that already has data + a snapshot.
    existing = (
        db.query(models.Recommendation)
          .filter(models.Recommendation.project_id == project_id)
          .count()
    )
    if existing == 0:
        try:
            generate_for_project(db, project_id)
        except Exception:
            db.rollback()

    q = db.query(models.Recommendation).filter(
        models.Recommendation.project_id == project_id,
    )
    if status == "open":
        q = q.filter(models.Recommendation.dismissed.is_(False),
                     models.Recommendation.applied.is_(False))
    elif status == "dismissed":
        q = q.filter(models.Recommendation.dismissed.is_(True))
    elif status == "applied":
        q = q.filter(models.Recommendation.applied.is_(True))

    rows = q.order_by(models.Recommendation.created_at.desc()).all()
    # Sort by priority (high → low), then created_at desc. SQL CASE
    # would also work but the in-memory sort keeps the engine portable.
    rows.sort(key=lambda r: (
        _PRIORITY_ORDER.get(str(r.priority or "medium").lower(), 9),
        -(int((r.created_at or datetime.utcnow()).timestamp())),
    ))

    return {
        "mode": mode,
        "status": status,
        "recommendations": [_to_response(r).model_dump(mode="json") for r in rows],
    }


def _load_owned(db, project_id: int, rec_id: int, user_id: int) -> models.Recommendation:
    """Fetch a recommendation row, enforcing project + user ownership.

    Raises 404 when the project doesn't belong to the caller, the
    recommendation doesn't exist, or the recommendation belongs to a
    different project than the one in the URL — never a 403, so a
    forged id can't differentiate "not yours" from "doesn't exist".
    """
    project = models.get_project(db, project_id, user_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    row = (
        db.query(models.Recommendation)
          .filter(models.Recommendation.id == rec_id,
                  models.Recommendation.project_id == project_id)
          .first()
    )
    if row is None:
        raise HTTPException(404, "Recommendation not found")
    return row


@router.post("/api/projects/{project_id}/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(
    project_id: int,
    rec_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Mark a recommendation as dismissed.

    Idempotent — dismissing a row twice is fine and the second call
    returns the same payload. A row that has already been ``applied``
    can still be dismissed (so the user can clear their inbox after
    acting on it), but ``applied`` stays set.
    """
    row = _load_owned(db, project_id, rec_id, user.id)
    if not row.dismissed:
        row.dismissed = True
        row.dismissed_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return _to_response(row).model_dump(mode="json")


@router.post("/api/projects/{project_id}/recommendations/{rec_id}/apply")
async def apply_recommendation(
    project_id: int,
    rec_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Mark a recommendation as applied.

    There are **no external side-effects** — this just flips the flag
    and stamps ``applied_at`` so the user can keep a clean inbox. The
    actual action (e.g. placing a real reorder, configuring a discount
    in their store) is out of scope and lives in the integration the
    user already runs.
    """
    row = _load_owned(db, project_id, rec_id, user.id)
    if not row.applied:
        row.applied = True
        row.applied_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return _to_response(row).model_dump(mode="json")


__all__ = [
    "Recommendation",
    "generate_for_project",
    "router",
]
