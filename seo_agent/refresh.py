"""Refresh existing pages whose 'updated' marker is older than N days."""

from __future__ import annotations
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from openai import OpenAI
import os

from .content_io import list_slugs, read_entry, entry_path

_client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
)

REFRESH_RULES = """\
You are refreshing an existing reference page. Update only what is genuinely
out of date: numeric statistics, dated language ("as of 2024"), and dead
links. Preserve the page's voice and structure. NEVER fabricate numbers; if
a fresh number is unavailable, leave [INSERT: <description>]. Cite real
sources. Output ONLY a JSON object with the same shape as the input, with
fields you changed updated and an updated 'updated' date of today.
"""


def stale_pages(refresh_after_days: int) -> List[Dict]:
    """List pages whose 'updated' is older than the cutoff.

    We only refresh kinds we can re-validate against the GEO checklist.
    Compare pages are hand-curated and have a different shape, so they are
    excluded from the auto-refresh loop.
    """
    cutoff = date.today() - timedelta(days=refresh_after_days)
    out: List[Dict] = []
    for kind in ("glossary", "guides"):
        for slug in list_slugs(kind):
            entry = read_entry(kind, slug)
            if not entry or "updated" not in entry:
                continue
            try:
                upd = datetime.strptime(str(entry["updated"]), "%Y-%m-%d").date()
            except Exception:
                continue
            if upd < cutoff:
                # Feed the LLM a JSON-serialised view of the entry; the
                # response is parsed back as JSON below.
                block = json.dumps(entry, indent=2, ensure_ascii=False, default=str)
                out.append({
                    "kind": kind,
                    "slug": slug,
                    "file": str(entry_path(kind, slug)),
                    "block": block,
                    "updated": str(entry["updated"]),
                    "entry": entry,
                })
    out.sort(key=lambda x: x["updated"])
    return out


def refresh_one(model: str, page: Dict) -> Tuple[Optional[Dict], int, int, str]:
    """Ask LLM to refresh a single page block. Returns dict with updated stats."""
    user = (f"Existing page (kind={page['kind']}, slug={page['slug']}, last updated "
            f"{page['updated']}):\n\n{page['block']}\n\n"
            f"Today's date: {date.today().isoformat()}\n\n"
            f"Return only the refreshed JSON object.")
    try:
        resp = _client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": REFRESH_RULES},
                      {"role": "user", "content": user}],
            max_tokens=4500,
            temperature=0.3,
        )
    except Exception as e:
        return None, 0, 0, f"openai error: {e}"
    txt = (resp.choices[0].message.content or "").strip()
    in_t = getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0
    out_t = getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt)
    m = re.search(r"\{.*\}", txt, flags=re.S)
    if not m:
        return None, in_t, out_t, "no json in response"
    try:
        data = json.loads(m.group(0))
    except Exception as e:
        return None, in_t, out_t, f"json parse: {e}"
    data["updated"] = date.today().isoformat()
    # Re-validate refreshed pages with the same checklist as new pages so a
    # refresh can never silently degrade a page below the GEO standard.
    from .generator import validate_glossary, validate_guide
    # Refreshing pre-existing pages: jsonLd was not previously required, so
    # accept refreshed payloads without it (the rest of the GEO checklist
    # still applies in full).
    if page["kind"] == "guides":
        ok, errs = validate_guide(data, require_jsonld=False)
    else:
        ok, errs = validate_glossary(data, require_jsonld=False)
    if not ok:
        return None, in_t, out_t, "refresh-validation: " + "; ".join(errs)
    return data, in_t, out_t, ""
