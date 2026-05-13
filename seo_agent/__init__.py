"""Weekly SEO/GEO automation agent for the AXIOM marketing site.

This package is purely additive. It never touches the Streamlit data/ML
modules. It researches trending data topics, drafts new GEO-optimised pages
into a review queue, refreshes stale pages, runs a brand-visibility check
against an LLM, and emails a weekly report.

Entry points:
    seo_agent.runner.run_weekly_cycle()  - full cycle (used by the cron job)
    seo_agent.review.list_drafts()       - read the review queue
    seo_agent.review.approve_draft(id)   - publish a draft
"""

from .config import AgentConfig, load_config
from .db import init_agent_db, AgentRun, AgentDraft, GeoCheckResult, AgentBuildJob

__all__ = [
    "AgentConfig", "load_config", "init_agent_db",
    "AgentRun", "AgentDraft", "GeoCheckResult", "AgentBuildJob",
]
