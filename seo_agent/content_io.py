"""Read/write marketing-site content as Markdown + YAML frontmatter.

The marketing site stores each glossary term, compare page, and guide as a
single ``.md`` file under ``marketing-site/src/content/<kind>/<slug>.md``. The
SEO agent works internally with the legacy dict shape (``sections`` /
``steps`` arrays of ``{heading|name, html}``) so this module is the single
adapter between the two representations.

Read:  ``read_entry(kind, slug)``  →  dict matching the legacy schema
Write: ``write_entry(kind, payload)``  →  ``Path`` of the .md file written
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .config import CONTENT_DIR

KIND_DIRS = {"glossary": "glossary", "compare": "compare", "guides": "guides"}
# kinds that store ordered sub-content in the markdown body
BODY_KEY = {"glossary": "sections", "guides": "steps"}
HEADING_KEY = {"glossary": "heading", "guides": "name"}

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def entry_dir(kind: str) -> Path:
    return CONTENT_DIR / KIND_DIRS[kind]


def entry_path(kind: str, slug: str) -> Path:
    return entry_dir(kind) / f"{slug}.md"


def list_slugs(kind: str) -> List[str]:
    d = entry_dir(kind)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.md"))


def _split_md(text: str):
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).lstrip("\n")
    return fm, body


def _parse_body_sections(body: str, heading_key: str) -> List[Dict]:
    """Split body on top-level ``## `` headings; each becomes one section."""
    chunks = re.split(r"(?m)^##\s+", body)
    out: List[Dict] = []
    for chunk in chunks[1:]:  # first chunk is whatever precedes the first ##
        nl = chunk.find("\n")
        if nl == -1:
            heading, html = chunk.strip(), ""
        else:
            heading = chunk[:nl].strip()
            html = chunk[nl + 1:].strip()
        out.append({heading_key: heading, "html": html})
    return out


def read_entry(kind: str, slug: str) -> Optional[Dict]:
    p = entry_path(kind, slug)
    if not p.exists():
        return None
    fm, body = _split_md(p.read_text())
    fm["slug"] = slug
    if kind in BODY_KEY:
        fm[BODY_KEY[kind]] = _parse_body_sections(body, HEADING_KEY[kind])
    return fm


def _yaml_dump(fm: Dict) -> str:
    return yaml.dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=10000,
    )


def write_entry(kind: str, payload: Dict) -> Path:
    """Serialize a payload dict to ``<kind>/<slug>.md``.

    The slug is taken from ``payload["slug"]`` and used as the filename; it
    is removed from the written frontmatter (the filename is the canonical
    source of the slug). Any ``jsonLd`` field is dropped because the page
    template generates JSON-LD at render time from the structured fields.
    """
    payload = dict(payload)
    slug = payload.pop("slug", None)
    if not slug:
        raise ValueError("payload must include 'slug'")
    payload.pop("jsonLd", None)

    body_text = ""
    if kind in BODY_KEY:
        hk = HEADING_KEY[kind]
        sections = payload.pop(BODY_KEY[kind], []) or []
        body_parts = []
        for s in sections:
            heading = (s.get(hk) or "").strip()
            html = (s.get("html") or "").strip()
            body_parts.append(f"## {heading}\n\n{html}")
        body_text = "\n\n".join(body_parts)

    fm_text = _yaml_dump(payload)
    out = f"---\n{fm_text}---\n\n{body_text}".rstrip() + "\n"
    p = entry_path(kind, slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out)
    return p
