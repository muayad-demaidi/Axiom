"""File-based review queue + approval / publish pipeline.

Drafts are JSON files under ``marketing-site/_review/drafts/``. On approval,
we write the entry as a Markdown file with YAML frontmatter under
``marketing-site/src/content/<kind>/<slug>.md`` (the canonical CMS-friendly
format), then trigger an Astro rebuild so the new page reaches production.
"""

from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import REVIEW_DIR
from .content_io import KIND_DIRS, entry_path, write_entry
from .db import get_session, AgentDraft

REVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    return re.sub(r"[\s_]+", "-", s)[:80]


def write_draft(run_id: int, kind: str, payload: Dict, target_query: str,
                info_gain: str, is_refresh: bool = False) -> AgentDraft:
    """Persist draft JSON + DB row. Returns the AgentDraft."""
    slug = payload.get("slug") or _slugify(payload.get("title") or payload.get("term") or "draft")
    payload["slug"] = slug
    fname = f"{kind}__{slug}__{int(datetime.utcnow().timestamp())}.json"
    fpath = REVIEW_DIR / fname
    body = {
        "kind": kind,
        "is_refresh": is_refresh,
        "target_query": target_query,
        "info_gain": info_gain,
        "created_at": datetime.utcnow().isoformat(),
        "payload": payload,
    }
    fpath.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    sess = get_session()
    try:
        title = payload.get("title") or payload.get("term") or payload.get("competitor") or slug
        d = AgentDraft(
            run_id=run_id, kind=kind, slug=slug, title=title,
            target_query=target_query, is_refresh=is_refresh,
            info_gain=info_gain, file_path=str(fpath), status="pending",
        )
        sess.add(d)
        sess.commit()
        sess.refresh(d)
        return d
    finally:
        sess.close()


def list_drafts(status: Optional[str] = "pending") -> List[AgentDraft]:
    sess = get_session()
    try:
        q = sess.query(AgentDraft)
        if status:
            q = q.filter(AgentDraft.status == status)
        return q.order_by(AgentDraft.created_at.desc()).all()
    finally:
        sess.close()


def get_draft_payload(draft_id: int) -> Optional[Dict]:
    sess = get_session()
    try:
        d = sess.query(AgentDraft).filter(AgentDraft.id == draft_id).first()
        if not d:
            return None
        p = Path(d.file_path)
        if not p.exists():
            return None
        return json.loads(p.read_text())
    finally:
        sess.close()


def reject_draft(draft_id: int, reviewer: str, notes: str = "") -> bool:
    sess = get_session()
    try:
        d = sess.query(AgentDraft).filter(AgentDraft.id == draft_id).first()
        if not d:
            return False
        d.status = "rejected"
        d.reviewed_at = datetime.utcnow()
        d.reviewed_by = reviewer
        d.review_notes = notes
        sess.commit()
        rej_dir = REVIEW_DIR.parent / "rejected"
        rej_dir.mkdir(parents=True, exist_ok=True)
        try:
            Path(d.file_path).rename(rej_dir / Path(d.file_path).name)
        except Exception:
            pass
        return True
    finally:
        sess.close()


import bleach

# Strict allowlist for HTML embedded inside markdown body sections. Anything
# outside this list (script, iframe, on* handlers, javascript: URIs, style
# attributes, etc.) is stripped by bleach before the file is written.
_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "u", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "h2", "h3", "h4", "table", "thead", "tbody",
    "tr", "th", "td", "span", "small",
}
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "th": ["scope"], "td": ["colspan", "rowspan"],
    "span": [], "code": [],
}
_ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


def _sanitize_html(s: str) -> str:
    """Allow-list-based sanitizer (bleach). Strips scripts, event handlers,
    javascript: hrefs, style attributes, and any tag outside _ALLOWED_TAGS."""
    return bleach.clean(
        s,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def _sanitize_payload(payload: Dict) -> Dict:
    """Recursively sanitize any string value that contains HTML markup."""
    def walk(v):
        if isinstance(v, str):
            return _sanitize_html(v) if "<" in v else v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return walk(payload)


def approve_draft(draft_id: int, reviewer: str, notes: str = "",
                  edited_payload: Optional[Dict] = None) -> Dict:
    """Write the draft to its Markdown file, then trigger a rebuild."""
    sess = get_session()
    try:
        d = sess.query(AgentDraft).filter(AgentDraft.id == draft_id).first()
        if not d:
            return {"ok": False, "error": "draft not found"}
        body = get_draft_payload(draft_id)
        if not body:
            return {"ok": False, "error": "draft file missing"}
        payload = edited_payload or body["payload"]
        kind = d.kind
        if kind not in KIND_DIRS:
            return {"ok": False, "error": f"unknown kind {kind}"}

        target = entry_path(kind, d.slug)
        if not d.is_refresh and target.exists():
            return {"ok": False, "error": f"slug {d.slug} already exists in {kind}"}

        payload = dict(payload)
        payload["slug"] = d.slug  # filename is the canonical slug
        payload = _sanitize_payload(payload)
        written = write_entry(kind, payload)

        d.status = "approved"
        d.reviewed_at = datetime.utcnow()
        d.reviewed_by = reviewer
        d.review_notes = notes
        sess.commit()

        appr_dir = REVIEW_DIR.parent / "approved"
        appr_dir.mkdir(parents=True, exist_ok=True)
        try:
            Path(d.file_path).rename(appr_dir / Path(d.file_path).name)
        except Exception:
            pass

        build_ok = trigger_sitemap_regen()

        return {"ok": True, "kind": kind, "slug": d.slug, "file": str(written),
                "build_triggered": build_ok}
    finally:
        sess.close()


def trigger_sitemap_regen() -> bool:
    """Rebuild the marketing site so the new entry reaches production.

    Default command is ``npm run build`` inside ``marketing-site/``; the
    Astro build emits the sitemap as part of the build. Override via the
    ``SEO_AGENT_BUILD_CMD`` env var (set to an empty string to skip).
    """
    import os as _os
    from .config import CONTENT_DIR
    cmd = _os.environ.get("SEO_AGENT_BUILD_CMD", "npm run build")
    if not cmd.strip():
        return True
    site_dir = CONTENT_DIR.parent.parent  # marketing-site/
    try:
        subprocess.run(cmd, shell=True, check=True, cwd=str(site_dir), timeout=600)
        return True
    except Exception:
        return False
