"""SERP + AI-engine analysis.

Tries Google Search first (no API key — scrapes the public results page),
then falls back to DuckDuckGo HTML if Google returns nothing usable.
Optionally attempts to fetch a Perplexity answer for the same query so
the page generator can compete on the LLM-cited surface as well.

We only extract title + URL + snippet; we do not crawl full bodies.
"""

from __future__ import annotations
import os
import re
import time
from html import unescape
from typing import Dict, List, Optional

import requests

GOOGLE_URL = "https://www.google.com/search"
DDG_URL = "https://html.duckduckgo.com/html/"
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


def _strip(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def _fetch_google(query: str, n: int = 3) -> List[Dict]:
    try:
        r = requests.get(GOOGLE_URL, params={"q": query, "hl": "en", "num": str(n + 2)},
                         headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    html = r.text
    out: List[Dict] = []
    # Google's classic result block — anchor with /url? wrapper or direct https
    # then a sibling div containing the snippet.
    for m in re.finditer(
        r'<a[^>]+href="(/url\?q=)?(https?://[^&"]+)[^"]*"[^>]*><h3[^>]*>(.*?)</h3>',
        html, flags=re.S,
    ):
        url = m.group(2)
        title = _strip(m.group(3))
        # Skip Google's own properties and ad/aggregator junk
        if "google.com" in url or "youtube.com/results" in url or not title:
            continue
        # Snippet — closest VwiC3b/IsZvec block after this anchor
        tail = html[m.end(): m.end() + 1500]
        sm = re.search(r'<div[^>]+class="[^"]*(?:VwiC3b|IsZvec|MUxGbd)[^"]*"[^>]*>(.*?)</div>',
                       tail, flags=re.S)
        snippet = _strip(sm.group(1)) if sm else ""
        out.append({"url": url, "title": title[:200], "snippet": snippet[:500],
                    "source": "google"})
        if len(out) >= n:
            break
    time.sleep(0.5)
    return out


def _fetch_duckduckgo(query: str, n: int = 3) -> List[Dict]:
    try:
        r = requests.post(DDG_URL, data={"q": query}, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    html = r.text
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, flags=re.S,
    )
    out = []
    for url, title, snippet in blocks[:n]:
        out.append({"url": url, "title": _strip(title)[:200],
                    "snippet": _strip(snippet)[:500], "source": "duckduckgo"})
    time.sleep(0.5)
    return out


def fetch_top_results(query: str, n: int = 3) -> List[Dict]:
    """Best-effort top-3 from Google; fall back to DuckDuckGo on miss."""
    results = _fetch_google(query, n=n)
    if not results:
        results = _fetch_duckduckgo(query, n=n)
    return results


def fetch_perplexity_answer(query: str) -> Optional[Dict]:
    """If a PERPLEXITY_API_KEY is configured, fetch one online answer with
    citations. Returns ``None`` silently if not configured or on error."""
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            PERPLEXITY_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 600,
            },
            timeout=25,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        msg = (data.get("choices") or [{}])[0].get("message", {})
        return {
            "engine": "perplexity",
            "answer": (msg.get("content") or "")[:1500],
            "citations": (data.get("citations") or [])[:8],
        }
    except Exception:
        return None


def information_gap_brief(query: str, top_results: List[Dict],
                          ai_answer: Optional[Dict] = None) -> str:
    """Summarize what's already on the SERP + AI engines to brief the generator."""
    lines: List[str] = []
    if top_results:
        src = top_results[0].get("source", "search")
        lines.append(f"Top-3 {src} results for: {query!r}\n")
        for i, r in enumerate(top_results, 1):
            lines.append(f"{i}. {r['title']} — {r['url']}\n   Snippet: {r['snippet']}\n")
    else:
        lines.append("No top results were retrievable for this query.\n")
    if ai_answer:
        lines.append(f"\nCurrent {ai_answer['engine']} answer (truncated):\n")
        lines.append(ai_answer["answer"])
        if ai_answer.get("citations"):
            lines.append("\nCited URLs: " + ", ".join(ai_answer["citations"]))
    lines.append(
        "\nYour information-gain mandate: the new page MUST contain at least one "
        "fact, statistic, framework, or angle absent from the above. If you cannot "
        "produce one with real cited sources, output the literal string "
        "DROP_NO_INFORMATION_GAIN and nothing else."
    )
    return "\n".join(lines)
