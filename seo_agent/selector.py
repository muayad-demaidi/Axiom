"""Topic deduplication, scoring, and filtering against existing site coverage."""

from __future__ import annotations
import re
from collections import defaultdict
from typing import Dict, List, Set

from .content_io import KIND_DIRS, list_slugs, read_entry

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "i", "my", "me", "you", "your", "we", "our", "it", "its", "they",
    "how", "what", "why", "when", "where", "do", "does", "did", "can",
    "best", "good", "new", "use", "using", "vs", "from", "by", "at",
}


def _tokens(s: str) -> Set[str]:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    return {t for t in s.split() if t and t not in STOPWORDS and len(t) > 2}


def _signature(s: str) -> str:
    toks = sorted(_tokens(s))
    return " ".join(toks[:6])


def existing_slugs() -> Dict[str, List[str]]:
    """Read marketing-site content and extract slugs/titles per kind.

    Each entry is now its own ``.md`` file under
    ``marketing-site/src/content/<kind>/<slug>.md``; the filename is the
    slug and the title/term/competitor lives in the YAML frontmatter.
    """
    out: Dict[str, List[str]] = {k: [] for k in KIND_DIRS}
    for kind in KIND_DIRS:
        slugs = list_slugs(kind)
        titles: List[str] = []
        for s in slugs:
            entry = read_entry(kind, s) or {}
            title = entry.get("term") or entry.get("title") or entry.get("competitor")
            if title:
                titles.append(str(title).lower())
        out[kind] = list({*slugs, *titles})
    return out


def filter_already_covered(items: List[Dict], existing: Dict[str, List[str]]) -> List[Dict]:
    """Drop items whose topic obviously overlaps an existing page."""
    covered_tokens: Set[str] = set()
    for slugs in existing.values():
        for s in slugs:
            covered_tokens |= _tokens(s.replace("-", " "))
    kept = []
    for it in items:
        toks = _tokens(it["topic"])
        if not toks:
            continue
        overlap = len(toks & covered_tokens) / max(len(toks), 1)
        if overlap >= 0.85:
            continue
        kept.append(it)
    return kept


def deduplicate(items: List[Dict]) -> List[Dict]:
    """Merge near-duplicate topics across sources; bump score on overlap."""
    buckets: Dict[str, List[Dict]] = defaultdict(list)
    for it in items:
        buckets[_signature(it["topic"])].append(it)
    merged = []
    for sig, group in buckets.items():
        if not sig:
            continue
        group.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
        head = dict(group[0])
        head["sources"] = sorted({g["source"] for g in group})
        head["signal_score"] = sum(g.get("signal_score", 0) for g in group) + 25 * (len(group) - 1)
        head["sample_urls"] = list({u for g in group for u in g.get("sample_urls", []) if u})[:5]
        merged.append(head)
    merged.sort(key=lambda x: x["signal_score"], reverse=True)
    return merged


def select_topics(raw_items: List[Dict], top_n: int = 10) -> List[Dict]:
    existing = existing_slugs()
    deduped = deduplicate(raw_items)
    filtered = filter_already_covered(deduped, existing)
    return filtered[:top_n]
