"""File-based review queue + approval / publish pipeline.

Drafts are JSON files under marketing-site/_review/drafts/. On approval,
we inject the entry into the appropriate marketing-site/src/content/*.ts
file as a JS object literal, then trigger a sitemap regeneration on the
next Astro build.
"""

from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from .config import REVIEW_DIR, CONTENT_DIR
from .db import get_session, AgentDraft

REVIEW_DIR.mkdir(parents=True, exist_ok=True)

KIND_TO_FILE = {
    "glossary": "glossary.ts",
    "guides": "guides.ts",
    "compare": "compare.ts",
}
KIND_TO_CONST = {
    "glossary": "GLOSSARY",
    "guides": "GUIDES",
    "compare": "COMPARE",
}


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
        # Move file to rejected/ subfolder for audit
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

# Strict allowlist for content that will be rendered with `set:html` on the
# marketing site. Anything outside this list (script, iframe, on* handlers,
# javascript: URIs, style attributes, etc.) is stripped by bleach.
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


def _to_js_literal(v) -> str:
    """Render a Python value as a JS literal (compatible with the TS files).
    HTML strings are sanitized to drop scripts / event handlers."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = _sanitize_html(v) if "<" in v else v
        return json.dumps(s, ensure_ascii=False)
    if isinstance(v, list):
        items = [_to_js_literal(x) for x in v]
        return "[" + ", ".join(items) + "]"
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            # bare identifier keys if safe, else quoted
            key = k if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k) else json.dumps(k)
            parts.append(f"{key}: {_to_js_literal(val)}")
        return "{ " + ", ".join(parts) + " }"
    return json.dumps(str(v))


def _inject_into_array(file_text: str, const_name: str, js_literal: str) -> str:
    """Insert a new JS object literal as the last element of `export const NAME: T[] = [...]`."""
    pattern = re.compile(
        r"(export\s+const\s+" + re.escape(const_name) + r"[^=]*=\s*\[)([\s\S]*?)(\];)",
    )
    m = pattern.search(file_text)
    if not m:
        raise RuntimeError(f"Could not locate `export const {const_name}` array")
    head, body, tail = m.group(1), m.group(2), m.group(3)
    body_stripped = body.rstrip()
    sep = "," if body_stripped and not body_stripped.endswith(",") else ""
    new_body = body_stripped + sep + "\n  " + js_literal + ",\n"
    return file_text[:m.start()] + head + new_body + tail + file_text[m.end():]


def _replace_in_array(file_text: str, slug: str, js_literal: str) -> Optional[str]:
    """Find an entry with the given slug and replace its block with js_literal."""
    # Reuse the entry parser from refresh
    from .refresh import _parse_entries
    for start, end, s in _parse_entries(file_text):
        if s == slug:
            return file_text[:start] + js_literal + file_text[end:]
    return None


def approve_draft(draft_id: int, reviewer: str, notes: str = "",
                  edited_payload: Optional[Dict] = None) -> Dict:
    """Move the draft into the live content TS file. Returns a result dict."""
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
        fname = KIND_TO_FILE.get(kind)
        const = KIND_TO_CONST.get(kind)
        if not fname or not const:
            return {"ok": False, "error": f"unknown kind {kind}"}
        target = CONTENT_DIR / fname
        if not target.exists():
            return {"ok": False, "error": f"content file missing: {target}"}
        text = target.read_text()
        js = _to_js_literal(payload)

        if d.is_refresh:
            new_text = _replace_in_array(text, d.slug, js)
            if new_text is None:
                return {"ok": False, "error": f"slug {d.slug} not found for refresh"}
        else:
            # Avoid duplicate slug
            if re.search(r'slug:\s*"' + re.escape(d.slug) + r'"', text):
                return {"ok": False, "error": f"slug {d.slug} already exists in {fname}"}
            new_text = _inject_into_array(text, const, js)

        # Write atomically
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(new_text)
        tmp.replace(target)

        d.status = "approved"
        d.reviewed_at = datetime.utcnow()
        d.reviewed_by = reviewer
        d.review_notes = notes
        sess.commit()

        # Move JSON to approved/ for audit
        appr_dir = REVIEW_DIR.parent / "approved"
        appr_dir.mkdir(parents=True, exist_ok=True)
        try:
            Path(d.file_path).rename(appr_dir / Path(d.file_path).name)
        except Exception:
            pass

        # Kick the static-site rebuild so the new page reaches production.
        # Sitemap regeneration happens as part of the Astro build.
        build_ok = trigger_sitemap_regen()

        return {"ok": True, "kind": kind, "slug": d.slug, "file": str(target),
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
    cmd = _os.environ.get("SEO_AGENT_BUILD_CMD", "npm run build")
    if not cmd.strip():
        return True
    site_dir = CONTENT_DIR.parent.parent  # marketing-site/
    try:
        subprocess.run(cmd, shell=True, check=True, cwd=str(site_dir), timeout=600)
        return True
    except Exception:
        return False
