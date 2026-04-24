"""Configuration knobs for the SEO/GEO agent.

Persisted as a JSON file at ``seo_agent/agent_config.json`` so the admin
panel can read/write it without a deploy. Falls back to sensible defaults
on first run.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any

CONFIG_PATH = Path(__file__).parent / "agent_config.json"
REVIEW_DIR = Path(__file__).resolve().parent.parent / "frontend" / "_review" / "drafts"
CONTENT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "content"

# Per-1M-token pricing for gpt-4o (USD) — used for the soft cost cap.
PRICE_PER_M_INPUT = 2.50
PRICE_PER_M_OUTPUT = 10.00


@dataclass
class AgentConfig:
    schedule_cron: str = "0 8 * * 1"        # Mondays 08:00 UTC
    max_new_pages_per_week: int = 5
    max_refresh_pages_per_week: int = 3
    openai_model: str = "gpt-4o"
    weekly_budget_usd: float = 7.0
    auto_publish: bool = False              # human-approval required by default
    sources_enabled: Dict[str, bool] = field(default_factory=lambda: {
        "reddit": True,
        "hackernews": True,
        "stackoverflow": True,
        "google_trends": False,             # requires pytrends; off by default
    })
    geo_prompts: List[str] = field(default_factory=lambda: [
        "What's the best tool for cleaning messy CSV files?",
        "Recommend an AI-powered data analysis platform for non-engineers.",
        "How do I detect outliers in a sales dataset without writing code?",
        "What's a good alternative to Tableau for ad-hoc analysis of CSV files?",
        "Which platform helps me build a 3-month sales forecast from a spreadsheet?",
        "Best app to auto-clean a CSV and run statistics on it?",
        "I have a messy Excel file; what tool can clean and visualise it for me?",
        "Recommend a beginner-friendly data analytics tool with AI chat.",
        "What's the easiest way to do K-Means clustering on a CSV?",
        "Which tool can detect data drift between two monthly datasets?",
        "Best low-code platform for descriptive statistics on uploaded files?",
        "I need to compare two months of sales data — what tool should I use?",
        "Tool that lets non-technical users build predictive models from CSV?",
        "Where can I get AI-generated insights about a pandas DataFrame?",
        "Cheapest AI tool to clean and analyse a 100k-row CSV?",
    ])
    admin_review_token: str = ""            # legacy single-token (anonymous)
    # Named tokens so each operator can have their own review link and we
    # can attribute approvals to a real person. Each entry is
    # ``{"name": "alice", "token": "abc..."}``.
    admin_review_tokens: List[Dict[str, str]] = field(default_factory=list)
    public_app_url: str = ""                # base URL used to build the mobile review link
    refresh_after_days: int = 90
    report_email_to: str = "muayad.demaidi.work@gmail.com"
    notify_on_new_drafts: bool = False      # opt-in instant alert when drafts land
    notify_email_to: str = ""               # routes the alert (falls back to report_email_to)
    site_existing_slugs: Dict[str, List[str]] = field(default_factory=dict)

    # --- Organic-traffic analytics (Task #35) ---
    # Pulls per-URL impressions/clicks/CTR from a free source so the selector
    # can learn which categories actually earn traffic.
    analytics_source: str = "none"          # none|plausible|gsc_csv
    analytics_site_url: str = ""            # plausible site_id or canonical site URL
    analytics_lookback_days: int = 7        # window for the weekly pull
    topic_dead_lookback_days: int = 60      # zero-traffic window that triggers down-weight
    topic_dead_score_factor: float = 0.4    # multiplier on signal_score for dead-category overlap
    topic_winner_score_factor: float = 1.6  # multiplier for winning-category overlap

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_config() -> AgentConfig:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            cfg = AgentConfig()
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            return cfg
        except Exception:
            pass
    cfg = AgentConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: AgentConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg.to_dict(), indent=2))


def env_override(cfg: AgentConfig) -> AgentConfig:
    """Allow env vars to override config (handy in scheduled deployments)."""
    if os.environ.get("SEO_AGENT_MODEL"):
        cfg.openai_model = os.environ["SEO_AGENT_MODEL"]
    if os.environ.get("SEO_AGENT_BUDGET_USD"):
        try:
            cfg.weekly_budget_usd = float(os.environ["SEO_AGENT_BUDGET_USD"])
        except Exception:
            pass
    if os.environ.get("SEO_AGENT_AUTO_PUBLISH"):
        cfg.auto_publish = os.environ["SEO_AGENT_AUTO_PUBLISH"].lower() in ("1", "true", "yes")
    return cfg
