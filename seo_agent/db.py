"""Lightweight tables for the SEO/GEO agent.

Reuses the SQLAlchemy engine configured by ``models.py`` so we share the
same PostgreSQL connection pool. Tables are created on demand via
``init_agent_db()`` and never touch the existing data/ML schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Float, JSON, Boolean,
)
from sqlalchemy.ext.declarative import declarative_base

from models import engine, SessionLocal

AgentBase = declarative_base()


class AgentRun(AgentBase):
    """One full weekly-cycle run. Audit trail for cost / output / errors."""
    __tablename__ = "seo_agent_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="running")  # running|ok|partial|error
    topics_discovered = Column(Integer, default=0)
    topics_selected = Column(Integer, default=0)
    drafts_created = Column(Integer, default=0)
    drafts_refreshed = Column(Integer, default=0)
    drafts_dropped = Column(Integer, default=0)
    openai_input_tokens = Column(Integer, default=0)
    openai_output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    config_snapshot = Column(JSON, nullable=True)
    summary = Column(JSON, nullable=True)  # {"trending_keywords": [...], ...}
    errors = Column(Text, nullable=True)


class AgentDraft(AgentBase):
    """A single generated/refreshed page awaiting human review."""
    __tablename__ = "seo_agent_drafts"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    kind = Column(String(32), nullable=False)  # glossary|guide|compare
    slug = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    target_query = Column(String(500), nullable=True)
    is_refresh = Column(Boolean, default=False)
    info_gain = Column(Text, nullable=True)  # what's new vs the SERP
    file_path = Column(String(500), nullable=False)  # JSON path in _review/
    status = Column(String(32), default="pending")  # pending|approved|rejected|edited
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    review_notes = Column(Text, nullable=True)


class AgentBuildJob(AgentBase):
    """A queued rebuild + redeploy of the marketing site.

    Created when a draft is approved (or nightly batch fires). A background
    worker picks it up, runs ``npm run build`` and optionally hits a deploy
    webhook. Failures are retried with exponential backoff up to
    ``max_attempts`` so an approval is never silently lost.
    """
    __tablename__ = "seo_agent_build_jobs"

    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, nullable=True, index=True)
    reason = Column(String(255), nullable=True)  # e.g. "approve:42", "manual", "nightly"
    status = Column(String(32), default="queued", index=True)
    # queued | running | success | failed | skipped
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    queued_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    build_ok = Column(Boolean, nullable=True)
    deploy_ok = Column(Boolean, nullable=True)
    deploy_target = Column(String(255), nullable=True)  # webhook URL or "build-only"
    log_tail = Column(Text, nullable=True)  # last ~4 KB of build/deploy output
    error = Column(Text, nullable=True)


class GeoCheckResult(AgentBase):
    """Per-prompt result of the GEO visibility check."""
    __tablename__ = "seo_agent_geo_checks"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, nullable=True, index=True)
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    prompt = Column(Text, nullable=False)
    mentioned = Column(Boolean, default=False)
    cited = Column(Boolean, default=False)  # link/url present
    position = Column(Integer, nullable=True)  # 1-based char-offset rank
    answer_excerpt = Column(Text, nullable=True)


class PageMetric(AgentBase):
    """Per-URL organic-traffic snapshot pulled from a free analytics source.

    One row per (slug, period_start, source). The agent appends new rows on
    every weekly pull rather than upserting, so we keep a time series we can
    reason about (e.g. "zero traffic for >60 days").
    """
    __tablename__ = "seo_agent_page_metrics"

    id = Column(Integer, primary_key=True, index=True)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)
    period_start = Column(DateTime, index=True, nullable=True)
    period_end = Column(DateTime, index=True, nullable=True)
    source = Column(String(32), default="gsc_csv")  # gsc_csv|plausible|cloudflare
    url = Column(String(1000), nullable=True)
    slug = Column(String(255), index=True, nullable=False)
    kind = Column(String(32), nullable=True)  # glossary|guides|compare|other
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    ctr = Column(Float, default=0.0)
    avg_position = Column(Float, nullable=True)


def init_agent_db():
    """Create the agent tables if they do not yet exist."""
    AgentBase.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()
