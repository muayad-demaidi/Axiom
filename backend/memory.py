"""User long-term memory routes.

Exposes the per-user business profile, reporting preferences, and durable
learned facts that the AI assistant uses to reason in the user's real
business terms. This is the production replacement for the legacy
Streamlit ``context/business_memory.py`` (which stored context in
replit.db and cannot run on the FastAPI/Postgres backend).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import models  # type: ignore

from .auth import get_current_user, get_db_session

router = APIRouter(prefix="/api/memory", tags=["memory"])


class MemoryUpdate(BaseModel):
    # Both are free-form maps merged into the stored JSON. Common profile
    # keys: industry, currency, fiscal_year_start, role, company_size,
    # kpis. Common preference keys: report_style, detail_level, language,
    # chart_style.
    profile: dict | None = None
    preferences: dict | None = None


class FactCreate(BaseModel):
    fact: str = Field(min_length=2, max_length=500)
    source: str = Field(default="manual", max_length=16)


def _facts_view(rows) -> list[dict]:
    return [
        {"id": r.id, "fact": r.fact, "source": r.source,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


@router.get("")
async def get_memory(user=Depends(get_current_user), db=Depends(get_db_session)):
    """Return the user's profile, preferences, and recent learned facts."""
    mem = models.get_user_memory(db, user.id)
    facts = models.list_user_facts(db, user.id, limit=30)
    return {
        "profile": mem["profile"],
        "preferences": mem["preferences"],
        "facts": _facts_view(facts),
    }


@router.patch("")
async def update_memory(
    req: MemoryUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Merge-update the user's business profile and/or preferences."""
    if req.profile is None and req.preferences is None:
        raise HTTPException(400, "Provide profile and/or preferences to update")
    row = models.upsert_user_memory(
        db, user.id, profile=req.profile, preferences=req.preferences
    )
    if row is None:
        raise HTTPException(500, "Could not save memory")
    return {"profile": dict(row.profile or {}), "preferences": dict(row.preferences or {})}


@router.post("/facts")
async def add_fact(
    req: FactCreate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Teach the assistant a durable fact about the user (deduplicated)."""
    row = models.append_user_fact(db, user.id, req.fact, source=req.source)
    if row is None:
        raise HTTPException(500, "Could not save fact")
    return {"id": row.id, "fact": row.fact, "source": row.source}


@router.delete("/facts/{fact_id}")
async def delete_fact(
    fact_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Forget a single learned fact (scoped to the owning user)."""
    n = (
        db.query(models.UserLearnedFact)
        .filter(models.UserLearnedFact.id == fact_id,
                models.UserLearnedFact.user_id == user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    if not n:
        raise HTTPException(404, "Fact not found")
    return {"ok": True, "deleted": int(n)}
