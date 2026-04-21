"""Trend-research sources. Free / public APIs only.

Each function returns a list of normalized dicts:
    {topic, source, signal_score, sample_urls, snippet}

Failures are swallowed and reported via the returned ``errors`` channel; we
never block a weekly run because Reddit happened to 503.
"""

from __future__ import annotations
import re
import time
from typing import List, Dict, Tuple

import requests

USER_AGENT = "DataVisionProSEOBot/1.0 (+https://datavisionpro.app)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
TIMEOUT = 15

REDDIT_SUBS = ["dataisbeautiful", "datascience", "analytics", "dataengineering"]
SO_TAGS = ["pandas", "data-cleaning", "data-visualization"]


def _safe_get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r
    except Exception:
        return None
    return None


def fetch_reddit(limit_per_sub: int = 25) -> Tuple[List[Dict], List[str]]:
    out, errors = [], []
    for sub in REDDIT_SUBS:
        r = _safe_get(f"https://www.reddit.com/r/{sub}/top.json?t=week&limit={limit_per_sub}")
        if r is None:
            errors.append(f"reddit:{sub} fetch failed")
            continue
        try:
            posts = r.json().get("data", {}).get("children", [])
        except Exception:
            errors.append(f"reddit:{sub} parse failed")
            continue
        for p in posts:
            d = p.get("data", {})
            title = (d.get("title") or "").strip()
            if not title:
                continue
            score = int(d.get("score") or 0)
            comments = int(d.get("num_comments") or 0)
            out.append({
                "topic": title,
                "source": f"reddit/r/{sub}",
                "signal_score": score + comments * 2,
                "sample_urls": [f"https://reddit.com{d.get('permalink','')}"],
                "snippet": (d.get("selftext") or "")[:400],
            })
        time.sleep(0.3)
    return out, errors


def fetch_hackernews(limit: int = 50) -> Tuple[List[Dict], List[str]]:
    out, errors = [], []
    query_terms = ["data analysis", "data cleaning", "pandas", "csv", "etl",
                   "data visualization", "machine learning csv"]
    for q in query_terms:
        url = f"https://hn.algolia.com/api/v1/search?query={requests.utils.quote(q)}&tags=story&numericFilters=created_at_i>{int(time.time())-7*86400}&hitsPerPage={limit//len(query_terms)+1}"
        r = _safe_get(url)
        if r is None:
            errors.append(f"hn:{q} fetch failed")
            continue
        try:
            hits = r.json().get("hits", [])
        except Exception:
            errors.append(f"hn:{q} parse failed")
            continue
        for h in hits:
            title = (h.get("title") or "").strip()
            if not title:
                continue
            out.append({
                "topic": title,
                "source": "hackernews",
                "signal_score": int(h.get("points") or 0) + int(h.get("num_comments") or 0),
                "sample_urls": [h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"],
                "snippet": (h.get("story_text") or "")[:400],
            })
    return out, errors


def fetch_stackoverflow(pages: int = 1) -> Tuple[List[Dict], List[str]]:
    out, errors = [], []
    for tag in SO_TAGS:
        url = (f"https://api.stackexchange.com/2.3/questions?order=desc&sort=week"
               f"&tagged={tag}&site=stackoverflow&pagesize=30&page={pages}")
        r = _safe_get(url)
        if r is None:
            errors.append(f"so:{tag} fetch failed")
            continue
        try:
            items = r.json().get("items", [])
        except Exception:
            errors.append(f"so:{tag} parse failed")
            continue
        for q in items:
            title = (q.get("title") or "").strip()
            if not title:
                continue
            out.append({
                "topic": _decode(title),
                "source": f"stackoverflow/{tag}",
                "signal_score": int(q.get("score") or 0) * 5 + int(q.get("view_count") or 0) // 100,
                "sample_urls": [q.get("link", "")],
                "snippet": "",
            })
    return out, errors


def fetch_google_trends() -> Tuple[List[Dict], List[str]]:
    """Optional. Requires the ``pytrends`` package; off by default."""
    try:
        from pytrends.request import TrendReq  # type: ignore
    except Exception:
        return [], ["pytrends not installed; google_trends source skipped"]
    out: List[Dict] = []
    errors: List[str] = []
    try:
        py = TrendReq(hl="en-US", tz=0)
        kw_seed = ["data cleaning", "pandas", "data analysis", "outlier detection",
                   "k-means clustering", "data drift", "csv cleaning"]
        py.build_payload(kw_seed, timeframe="now 7-d")
        related = py.related_queries()
        for kw, blocks in (related or {}).items():
            top = (blocks or {}).get("top")
            if top is None:
                continue
            for _, row in top.head(10).iterrows():
                out.append({
                    "topic": str(row["query"]),
                    "source": "google_trends",
                    "signal_score": int(row.get("value") or 0),
                    "sample_urls": [f"https://www.google.com/search?q={requests.utils.quote(str(row['query']))}"],
                    "snippet": f"Related to seed: {kw}",
                })
    except Exception as e:
        errors.append(f"pytrends error: {e}")
    return out, errors


def _decode(s: str) -> str:
    return (s.replace("&#39;", "'").replace("&quot;", '"')
             .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def gather_all(sources_enabled: Dict[str, bool]) -> Tuple[List[Dict], List[str]]:
    """Run every enabled source and concatenate results + errors."""
    all_items: List[Dict] = []
    all_errors: List[str] = []
    if sources_enabled.get("reddit"):
        i, e = fetch_reddit();          all_items += i; all_errors += e
    if sources_enabled.get("hackernews"):
        i, e = fetch_hackernews();      all_items += i; all_errors += e
    if sources_enabled.get("stackoverflow"):
        i, e = fetch_stackoverflow();   all_items += i; all_errors += e
    if sources_enabled.get("google_trends"):
        i, e = fetch_google_trends();   all_items += i; all_errors += e
    return all_items, all_errors
