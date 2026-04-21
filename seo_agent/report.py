"""Weekly summary email via the existing Resend integration."""

from __future__ import annotations
from typing import Dict, List

import resend

from email_service import get_resend_credentials


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

      <h3 style="color:#14b8a6;">Refreshed pages</h3>
      <ul style="color:#cbd5e1;line-height:1.6;">{refreshed_html}</ul>

      <h3 style="color:#14b8a6;">Errors / warnings</h3>
      <ul style="color:#cbd5e1;line-height:1.6;">{errors_html}</ul>

      <p style="margin-top:1.5rem;color:#94a3b8;font-size:0.9rem;">
        Review and approve drafts in the DataVision Pro admin panel
        (Admin → SEO/GEO Agent → Review queue).
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
