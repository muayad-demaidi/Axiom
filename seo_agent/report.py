"""Weekly summary email via the existing Resend integration."""

from __future__ import annotations
import os
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import resend

from email_service import get_resend_credentials
from .config import load_config


def _normalise_base_url(value: str) -> Optional[str]:
    """Return ``https://host[/path]`` from a raw URL or bare hostname."""
    raw = (value or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "", "", ""))


def autodetect_app_url() -> Optional[str]:
    """Auto-detect the deployed Streamlit base URL from Replit env vars.

    Prefers ``REPLIT_DOMAINS`` (set in deployments and workspaces) and
    falls back to ``REPLIT_DEV_DOMAIN``. Returns ``None`` when neither
    is available.
    """
    domains = (os.environ.get("REPLIT_DOMAINS") or "").strip()
    if domains:
        first = domains.split(",")[0].strip()
        url = _normalise_base_url(first)
        if url:
            return url
    dev = (os.environ.get("REPLIT_DEV_DOMAIN") or "").strip()
    if dev:
        return _normalise_base_url(dev)
    return None


def resolve_public_app_url() -> Optional[str]:
    """Resolve the public base URL for the Streamlit app.

    Precedence: explicit ``SEO_AGENT_PUBLIC_APP_URL`` env var override →
    saved ``AgentConfig.public_app_url`` → auto-detected Replit
    deployment domain. Returns ``None`` if none can be determined.
    """
    env_override = _normalise_base_url(os.environ.get("SEO_AGENT_PUBLIC_APP_URL") or "")
    if env_override:
        return env_override
    try:
        cfg = load_config()
        cfg_url = _normalise_base_url(getattr(cfg, "public_app_url", "") or "")
        if cfg_url:
            return cfg_url
    except Exception:
        pass
    return autodetect_app_url()


def public_review_url() -> Optional[str]:
    """Build the token-gated public review URL for the Streamlit app.

    Combines :func:`resolve_public_app_url` with
    ``AgentConfig.admin_review_token``. Returns ``None`` if no base URL
    can be resolved or no token has been set.
    """
    base = resolve_public_app_url()
    cfg = load_config()
    token = (cfg.admin_review_token or "").strip()
    if not token:
        # Fall back to the first named operator token so emails still work
        # for setups that have moved entirely to per-operator tokens.
        for entry in (cfg.admin_review_tokens or []):
            t = (entry.get("token") or "").strip()
            if t:
                token = t
                break
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
        admin_hint = ("Or review them in the AXIOM admin panel "
                      "(Admin → SEO/GEO Agent → Review queue).")
    else:
        review_block = ""
        admin_hint = ("Review and approve drafts in the AXIOM admin panel "
                      "(Admin → SEO/GEO Agent → Review queue). Set an "
                      "<code>admin_review_token</code> in that tab to enable "
                      "the mobile review link.")

    return f"""
    <div style="font-family:'Inter',Arial,sans-serif;max-width:680px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:2rem;border-radius:12px;">
      <h1 style="color:#14b8a6;margin:0 0 0.25rem 0;">AXIOM — Weekly SEO/GEO Report</h1>
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


def render_new_drafts_alert_html(summary: Dict) -> str:
    count = summary.get("drafts_created", 0)
    drafts = summary.get("drafts", [])[:10]
    review_url = public_review_url()
    items = "".join(
        f'<li style="margin-bottom:6px;">'
        f'<span style="color:#14b8a6;">[{d.get("kind","?")}]</span> '
        f'<strong>{d.get("title","(untitled)")}</strong></li>'
        for d in drafts
    ) or "<li>(see admin panel for details)</li>"
    if review_url:
        cta = (
            f'<p style="margin:1rem 0 0 0;">'
            f'<a href="{review_url}" style="display:inline-block;padding:0.6rem 1.1rem;'
            f'background:#14b8a6;color:#0f172a;text-decoration:none;border-radius:6px;'
            f'font-weight:600;">Review {count} pending draft{"s" if count != 1 else ""} →</a>'
            f'</p>'
        )
    else:
        cta = ('<p style="margin:1rem 0 0 0;color:#94a3b8;">'
               'Open the admin panel → SEO/GEO Agent → Review queue to approve.</p>')
    return f"""
    <div style="font-family:'Inter',Arial,sans-serif;max-width:560px;margin:0 auto;
                background:#0f172a;color:#e2e8f0;padding:1.5rem;border-radius:12px;">
      <h2 style="color:#14b8a6;margin:0 0 0.25rem 0;">
        📱 {count} new draft{"s" if count != 1 else ""} ready to review
      </h2>
      <p style="color:#94a3b8;margin:0 0 1rem 0;">
        Run finished {summary.get('finished_at','')}
      </p>
      <ul style="color:#cbd5e1;line-height:1.6;padding-left:1.2rem;">{items}</ul>
      {cta}
    </div>
    """


def send_new_drafts_alert(to_email: str, summary: Dict) -> bool:
    """Send an instant alert when a run produces new drafts.

    Returns False (without raising) on any failure or when there is nothing
    to alert about, so the caller can stay best-effort.
    """
    count = int(summary.get("drafts_created", 0) or 0)
    if count <= 0:
        return False
    to_email = (to_email or "").strip()
    if not to_email:
        return False
    api_key, from_email = get_resend_credentials()
    if not api_key:
        print("[seo_agent] Resend API key unavailable; skipping new-drafts alert.")
        return False
    resend.api_key = api_key
    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"📱 {count} new DataVision draft{'s' if count != 1 else ''} ready to review",
            "html": render_new_drafts_alert_html(summary),
        })
        return True
    except Exception as e:
        print(f"[seo_agent] New-drafts alert failed: {e}")
        return False


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
            "subject": f"AXIOM — Weekly SEO/GEO Report "
                       f"({summary.get('drafts_created',0)} drafts, "
                       f"${summary.get('estimated_cost_usd',0):.2f})",
            "html": render_html(summary),
        })
        return True
    except Exception as e:
        print(f"[seo_agent] Report email failed: {e}")
        return False
