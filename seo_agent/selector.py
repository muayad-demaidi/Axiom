"""Topic deduplication, scoring, and filtering against existing site coverage."""

from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

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


def _traffic_token_buckets(lookback_days: int = 60) -> Tuple[Set[str], Set[str], Dict]:
    """Inspect recorded ``PageMetric`` rows and bucket slug-tokens by performance.

    Returns ``(dead_tokens, winner_tokens, debug)`` where:
      * ``dead_tokens``  — tokens of slugs with **zero** clicks AND zero
        impressions over the lookback window. Topics that overlap heavily
        with these tokens get down-weighted in the selector.
      * ``winner_tokens`` — tokens of slugs in the top-quartile by clicks
        within the same window. Topics that overlap with these get a boost.
      * ``debug`` — small dict useful for the admin panel and the report.

    All DB access is best-effort; failures return empty sets so the agent
    never falls over because analytics is misconfigured.
    """
    dead: Set[str] = set()
    winners: Set[str] = set()
    debug = {"slugs_with_metrics": 0, "dead_slugs": [], "winner_slugs": [],
             "lookback_days": lookback_days}
    try:
        from .db import get_session, PageMetric
    except Exception:
        return dead, winners, debug
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    sess = get_session()
    try:
        rows = (sess.query(PageMetric)
                .filter(PageMetric.fetched_at >= cutoff)
                .all())
    except Exception:
        rows = []
    finally:
        sess.close()
    if not rows:
        return dead, winners, debug
    agg: Dict[str, Dict[str, int]] = defaultdict(lambda: {"clicks": 0, "impressions": 0})
    for r in rows:
        agg[r.slug]["clicks"] += int(r.clicks or 0)
        agg[r.slug]["impressions"] += int(r.impressions or 0)
    debug["slugs_with_metrics"] = len(agg)
    # Dead set: slug saw zero traffic at all in the window.
    dead_slugs = [s for s, m in agg.items()
                  if m["clicks"] == 0 and m["impressions"] == 0]
    # Winners: top quartile by clicks among slugs that have some clicks.
    clicked = sorted(((s, m["clicks"]) for s, m in agg.items() if m["clicks"] > 0),
                     key=lambda x: x[1], reverse=True)
    cutoff_n = max(1, len(clicked) // 4) if clicked else 0
    winner_slugs = [s for s, _ in clicked[:cutoff_n]]
    debug["dead_slugs"] = dead_slugs[:50]
    debug["winner_slugs"] = winner_slugs[:50]
    for s in dead_slugs:
        dead |= _tokens(s.replace("-", " "))
    for s in winner_slugs:
        winners |= _tokens(s.replace("-", " "))
    # A token shared by both buckets is ambiguous — drop it.
    overlap = dead & winners
    dead -= overlap
    winners -= overlap
    return dead, winners, debug


def apply_traffic_signal(items: List[Dict],
                         lookback_days: int = 60,
                         dead_factor: float = 0.4,
                         winner_factor: float = 1.6) -> List[Dict]:
    """Re-score topics using observed organic-traffic performance.

    Topics adjacent to slugs with no traffic for >``lookback_days`` are
    down-weighted; topics adjacent to high-performing slugs are boosted.
    Items keep their original ``signal_score`` under ``signal_score_raw``
    for transparency, and we annotate which bucket triggered the change.
    """
    dead, winners, _debug = _traffic_token_buckets(lookback_days)
    if not dead and not winners:
        return items
    out: List[Dict] = []
    for it in items:
        toks = _tokens(it.get("topic", ""))
        if not toks:
            out.append(it)
            continue
        new = dict(it)
        new["signal_score_raw"] = it.get("signal_score", 0)
        traffic_tag = None
        if dead:
            d_overlap = len(toks & dead) / len(toks)
            if d_overlap >= 0.5:
                new["signal_score"] = int(round(new["signal_score"] * dead_factor))
                traffic_tag = f"down (dead-overlap={d_overlap:.0%})"
        if winners and traffic_tag is None:
            w_overlap = len(toks & winners) / len(toks)
            if w_overlap >= 0.4:
                new["signal_score"] = int(round(new["signal_score"] * winner_factor))
                traffic_tag = f"up (winner-overlap={w_overlap:.0%})"
        if traffic_tag:
            new["traffic_signal"] = traffic_tag
        out.append(new)
    out.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
    return out


def select_topics(raw_items: List[Dict], top_n: int = 10,
                  traffic_lookback_days: int = 60,
                  dead_factor: float = 0.4,
                  winner_factor: float = 1.6) -> List[Dict]:
    existing = existing_slugs()
    deduped = deduplicate(raw_items)
    filtered = filter_already_covered(deduped, existing)
    rescored = apply_traffic_signal(filtered,
                                    lookback_days=traffic_lookback_days,
                                    dead_factor=dead_factor,
                                    winner_factor=winner_factor)
    return rescored[:top_n]
