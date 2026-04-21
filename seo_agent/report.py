"""Weekly summary email via the existing Resend integration."""

from __future__ import annotations
import os
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import resend

from email_service import get_resend_credentials
from .config import load_config


def public_review_url() -> Optional[str]:
    """Build the token-gated public review URL for the Streamlit app.

    Requires both the ``SEO_AGENT_PUBLIC_APP_URL`` env var (e.g. the
    deployed app's base URL) and ``AgentConfig.admin_review_token`` to
    be set. Returns ``None`` if either is missing so callers can render
    a graceful fallback in the email.
    """
    base = (os.environ.get("SEO_AGENT_PUBLIC_APP_URL") or "").strip()
    cfg = load_config()
    token = (cfg.admin_review_token or "").strip()
    if not base or not token:
        return None
    parts = urlsplit(base)
    if not parts.scheme or not parts.netloc:
        return None
    query = urlencode({"review_token": token})
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, ""))


def _row(label: str, value) -> str:
    return (f'<tr><td style="padding:6px 14px;color:#94a3b8;">{label}</td>'
            f'<td style="padding:6px 14px;color:#e2e8f0;"><strong>{value}</strong></td></tr>')


def render_html(summary: Dict) -> str:
    drafts_html = ""
    for d in summary.get("drafts", [])[:25]:
        drafts_html += (
            f'<li style="margin-bottom:6px;">'
            f'<span style="color:#14b8a6;">[{d.get("kind","?")}]</span> '
            f'<strong>{d.get("title","(untitled)")}</strong> — '
            f'<em style="color:#94a3b8;">{d.get("status","pending")}</em></li>'
        )
    refreshed_html = "".join(
        f'<li>{r.get("kind","?")} / {r.get("slug","?")}</li>'
        for r in summary.get("refreshed", [])
    ) or "<li>None</li>"
    keywords_html = ", ".join(summary.get("trending_keywords", [])[:10]) or "—"
    errors = summary.get("errors") or []
    errors_html = "".join(f"<li>{e}</li>" for e in errors[:20]) or "<li>None</li>"
    geo_rate = summary.get("geo_mention_rate")
    geo_rate_str = f"{geo_rate*100:.1f}%" if geo_rate is not None else "—"

    review_url = public_review_url()
    if review_url:
        review_block = f"""
      <div style="margin:1.25rem 0;padding:1rem 1.25rem;background:rgba(20,184,166,0.10);
                  border:1px solid rgba(20,184,166,0.35);border-radius:8px;">
        <p style="margin:0 0 0.6rem 0;color:#e2e8f0;">
          📱 <strong>Approve drafts on the go</strong> — open the secure link
          below on your phone (no admin login required):
        </p>
        <p style="margin:0;">
          <a href="{review_url}" style="display:inline-block;padding:0.6rem 1.1rem;
             background:#14b8a6;color:#0f172a;text-decoration:none;border-radius:6px;
             font-weight:600;">Review pending drafts →</a>
        </p>
      </div>
        """
        admin_hint = ("Or review them in the DataVision Pro admin panel "
                      "(Admin → SEO/GEO Agent → Review queue).")
    else:
        review_block = ""
        admin_hint = ("Review and approve drafts in the DataVision Pro admin panel "
                      "(Admin → SEO/GEO Agent → Review queue). Set "
                      "<code>SEO_AGENT_PUBLIC_APP_URL</code> and an "
                      "<code>admin_review_token</code> to enable the mobile review link.")

    return f"""
    <div style="font-family:'Inter',Arial,sans-serif;max-width:680px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px;">
      <h1 style="color:#14b8a6;margin:0 0 0.25rem 0;">DataVision Pro — Weekly SEO/GEO Report</h1>
      <p style="color:#94a3b8;margin:0 0 1.5rem 0;">Run finished {summary.get('finished_at','')}</p>

      <table style="width:100%;border-collapse:collapse;background:rgba(20,184,166,0.06);
                    border:1px solid rgba(20,184,166,0.2);border-radius:8px;margin-bottom:1.5rem;">
        {_row("Topics discovered", summary.get("topics_discovered", 0))}
        {_row("Topics selected", summary.get("topics_selected", 0))}
        {_row("Drafts created", summary.get("drafts_created", 0))}
        {_row("Drafts dropped", summary.get("drafts_dropped", 0))}
        {_row("Pages refreshed", summary.get("drafts_refreshed", 0))}
        {_row("OpenAI input tokens", f'{summary.get("openai_input_tokens",0):,}')}
        {_row("OpenAI output tokens", f'{summary.get("openai_output_tokens",0):,}')}
        {_row("Estimated cost", f'${summary.get("estimated_cost_usd",0):.3f}')}
        {_row("GEO mention rate", geo_rate_str)}
      </table>

      <h3 style="color:#14b8a6;">Top trending keywords this week</h3>
      <p style="color:#cbd5e1;">{keywords_html}</p>

      <h3 style="color:#14b8a6;">Drafts (review queue)</h3>
      <ul style="color:#cbd5e1;line-height:1.6;">{drafts_html or "<li>No new drafts.</li>"}</ul>
      {review_block}

      <h3 style="color:#14b8a6;">Refreshed pages</h3>
      <ul style="color:#cbd5e1;line-height:1.6;">{refreshed_html}</ul>

      <h3 style="color:#14b8a6;">Errors / warnings</h3>
      <ul style="color:#cbd5e1;line-height:1.6;">{errors_html}</ul>

      <p style="margin-top:1.5rem;color:#94a3b8;font-size:0.9rem;">
        {admin_hint}
      </p>
    </div>
    """


def send_weekly_report(to_email: str, summary: Dict) -> bool:
    api_key, from_email = get_resend_credentials()
    if not api_key:
        print("[seo_agent] Resend API key unavailable; skipping report email.")
        return False
    resend.api_key = api_key
    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"DataVision Pro — Weekly SEO/GEO Report "
                       f"({summary.get('drafts_created',0)} drafts, "
                       f"${summary.get('estimated_cost_usd',0):.2f})",
            "html": render_html(summary),
        })
        return True
    except Exception as e:
        print(f"[seo_agent] Report email failed: {e}")
        return False
