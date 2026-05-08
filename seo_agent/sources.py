"""Trend-research sources. Free / public APIs only.

Each function returns a list of normalized dicts:
    {topic, source, signal_score, sample_urls, snippet}

Failures are swallowed and reported via the returned ``errors`` channel; we
never block a weekly run because Reddit happened to 503.
"""

from __future__ import annotations
import csv
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple
from urllib.parse import urlparse

import requests

USER_AGENT = "AXIOMSEOBot/1.0 (+https://AXIOM.app)"
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


# --- Organic-traffic analytics (Task #35) -----------------------------------
#
# Free signals only. We support two no-cost sources:
#
#   plausible : Plausible Analytics breakdown API (needs PLAUSIBLE_API_KEY env
#               var). Returns clicks (visitors) only — impressions/position are
#               left null because Plausible doesn't expose them.
#   gsc_csv   : Google Search Console "Pages" CSV exported from the
#               Performance report and dropped at GSC_CSV_IMPORT_PATH (default
#               ``data/gsc_pages.csv``). Returns clicks, impressions, CTR,
#               and average position.
#
# Each row returned by ``fetch_analytics`` is normalized to:
#   {url, slug, kind, source, period_start, period_end,
#    impressions, clicks, ctr, avg_position}


def _slug_kind_from_url(url: str) -> Tuple[str, str]:
    """Map a marketing-site URL to ``(slug, kind)``.

    Path conventions: ``/glossary/<slug>``, ``/guides/<slug>``,
    ``/compare/<slug>``. Anything else is bucketed as ``other`` with the
    last path segment as the slug.
    """
    try:
        path = urlparse(url).path
    except Exception:
        path = url
    path = (path or "/").strip("/")
    if not path:
        return ("__home__", "other")
    parts = path.split("/")
    if parts[0] in ("glossary", "guides", "compare") and len(parts) >= 2:
        return (parts[1], parts[0])
    return (parts[-1], "other")


def fetch_plausible(site_id: str, lookback_days: int = 7) -> Tuple[List[Dict], List[str]]:
    """Pull the per-page visitor breakdown from Plausible.

    Requires ``PLAUSIBLE_API_KEY`` in the environment. ``site_id`` is the
    bare hostname registered with Plausible (e.g. ``AXIOM.app``).
    """
    out: List[Dict] = []
    errors: List[str] = []
    token = os.environ.get("PLAUSIBLE_API_KEY")
    if not token:
        return out, ["plausible: PLAUSIBLE_API_KEY env var not set"]
    if not site_id:
        return out, ["plausible: analytics_site_url not configured"]
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=lookback_days)
    url = (
        "https://plausible.io/api/v1/stats/breakdown"
        f"?site_id={requests.utils.quote(site_id)}"
        f"&period={lookback_days}d"
        "&property=event:page&metrics=visitors,pageviews&limit=500"
    )
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return out, [f"plausible HTTP {r.status_code}: {r.text[:200]}"]
        results = r.json().get("results", []) or []
    except Exception as e:
        return out, [f"plausible fetch failed: {e}"]
    base = site_id if site_id.startswith("http") else f"https://{site_id}"
    for row in results:
        page_path = row.get("page") or "/"
        page_url = base.rstrip("/") + page_path
        slug, kind = _slug_kind_from_url(page_url)
        out.append({
            "url": page_url,
            "slug": slug,
            "kind": kind,
            "source": "plausible",
            "period_start": period_start,
            "period_end": period_end,
            "impressions": 0,                # not exposed
            "clicks": int(row.get("visitors") or 0),
            "ctr": 0.0,
            "avg_position": None,
        })
    return out, errors


def fetch_gsc_csv(csv_path: str | None = None,
                  lookback_days: int = 7,
                  site_url: str = "") -> Tuple[List[Dict], List[str]]:
    """Read a Google Search Console "Pages" CSV export.

    The operator drops the latest export at ``GSC_CSV_IMPORT_PATH`` (default
    ``data/gsc_pages.csv``). Expected columns (case-insensitive):
    ``Top pages``/``Page``, ``Clicks``, ``Impressions``, ``CTR``, ``Position``.

    If ``site_url`` is provided (e.g. ``AXIOM.app`` or
    ``https://AXIOM.app``), only rows whose page URL matches that
    host are kept. This lets the same fetcher coexist with multi-property
    GSC exports.
    """
    out: List[Dict] = []
    errors: List[str] = []
    path_str = csv_path or os.environ.get("GSC_CSV_IMPORT_PATH", "data/gsc_pages.csv")
    path = Path(path_str)
    if not path.exists():
        return out, [f"gsc_csv: file not found at {path}"]
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=lookback_days)
    host_filter = ""
    if site_url:
        try:
            host_filter = (urlparse(site_url).netloc or site_url).strip("/").lower()
        except Exception:
            host_filter = site_url.strip("/").lower()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in raw.items()}
                page_url = row.get("page") or row.get("top pages") or row.get("url") or ""
                if not page_url:
                    continue
                if host_filter:
                    try:
                        row_host = (urlparse(page_url).netloc or "").lower()
                    except Exception:
                        row_host = ""
                    if host_filter not in row_host and host_filter not in page_url.lower():
                        continue
                slug, kind = _slug_kind_from_url(page_url)
                ctr_raw = row.get("ctr") or "0"
                ctr = float(ctr_raw.rstrip("%")) / (100 if "%" in ctr_raw else 1) if ctr_raw else 0.0
                try:
                    pos = float(row.get("position") or row.get("average position") or 0) or None
                except Exception:
                    pos = None
                try:
                    clicks = int(float(row.get("clicks") or 0))
                except Exception:
                    clicks = 0
                try:
                    impr = int(float(row.get("impressions") or 0))
                except Exception:
                    impr = 0
                out.append({
                    "url": page_url,
                    "slug": slug,
                    "kind": kind,
                    "source": "gsc_csv",
                    "period_start": period_start,
                    "period_end": period_end,
                    "impressions": impr,
                    "clicks": clicks,
                    "ctr": ctr,
                    "avg_position": pos,
                })
    except Exception as e:
        errors.append(f"gsc_csv parse failed: {e}")
    return out, errors


def fetch_analytics(source: str, site_url: str = "",
                    lookback_days: int = 7) -> Tuple[List[Dict], List[str]]:
    """Dispatch to the configured free analytics source."""
    if source == "plausible":
        return fetch_plausible(site_url, lookback_days=lookback_days)
    if source == "gsc_csv":
        return fetch_gsc_csv(lookback_days=lookback_days, site_url=site_url)
    if source in ("", "none", None):
        return [], []
    return [], [f"analytics source '{source}' not supported"]


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
