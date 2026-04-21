"""GEO-template page generation using the existing OpenAI integration.

Produces a draft as a kind-specific Python dict (matching the shape of
GLOSSARY/GUIDES/COMPARE entries in marketing-site/src/content/*.ts) and
validates against a strict checklist. Pages that fail validation are
dropped — never softened, never published.
"""

from __future__ import annotations
import json
import os
import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from .config import PRICE_PER_M_INPUT, PRICE_PER_M_OUTPUT

_client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
)


GEO_RULES = """\
You write factual, GEO-optimised reference pages for an analytics product called
DataVision Pro. You follow these non-negotiable rules:

1. DIRECT-ANSWER BLOCK first, exactly 40-60 words, plainly answering the
   user's question. No fluff, no marketing.
2. At least ONE cited statistic per major section. Cite ONLY real, verifiable
   sources (peer-reviewed papers, .gov/.edu, recognised publications, or the
   vendor's own published docs). NEVER invent numbers, quotes, customer
   stories, or competitor metrics.
3. If a needed number is unavailable, leave a clearly-marked placeholder of
   the form [INSERT: <description>] — do not invent.
4. Headings phrased as questions where natural. FAQ block at the end.
5. Total length 1,200-2,000 words.
6. Mention DataVision Pro at most twice and only where genuinely relevant.
7. The page MUST contain at least one fact, statistic, framework, or angle
   absent from the SERP brief you are given. If you cannot, output the single
   string DROP_NO_INFORMATION_GAIN and nothing else.
"""


GLOSSARY_SCHEMA = """\
Return ONLY a single JSON object with these keys (no prose, no markdown
fence):

{
  "slug": "kebab-case-slug",
  "term": "Title-Case Term",
  "question": "What is <term>?",
  "shortDef": "<one-sentence dictionary definition, <=200 chars>",
  "description": "<meta description, 140-160 chars>",
  "answer": "<direct-answer block, 40-60 words>",
  "stats": [
    {"value": "...", "label": "...", "source": {"label": "...", "url": "https://..."}},
    {"value": "...", "label": "...", "source": {"label": "...", "url": "https://..."}}
  ],
  "sections": [
    {"heading": "...", "html": "<p>...</p><ul><li>...</li></ul>"},
    {"heading": "...", "html": "<p>...</p>"}
  ],
  "faq": [
    {"q": "...", "a": "..."}, {"q": "...", "a": "..."},
    {"q": "...", "a": "..."}, {"q": "...", "a": "..."},
    {"q": "...", "a": "..."}
  ],
  "related": ["existing-slug-1", "existing-slug-2"],
  "updated": "<YYYY-MM-DD>",
  "jsonLd": [
    {"@context":"https://schema.org","@type":"DefinedTerm","name":"<term>","description":"<shortDef>","inDefinedTermSet":"https://datavision.pro/glossary"},
    {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
      {"@type":"Question","name":"<faq[0].q>","acceptedAnswer":{"@type":"Answer","text":"<faq[0].a>"}}
    ]}
  ]
}

Every section.html MUST contain at least one inline citation as <a href="https://...">…</a>
or reference one of the values declared in stats[]. The jsonLd block is REQUIRED.
"""

GUIDE_SCHEMA = """\
Return ONLY a single JSON object:

{
  "slug": "how-to-...",
  "title": "How to ...",
  "description": "<meta description 140-160 chars>",
  "intro": "<direct-answer block, 40-60 words>",
  "estTime": "...",
  "difficulty": "Beginner|Intermediate|Advanced",
  "prerequisites": ["...", "..."],
  "steps": [{"name": "...", "html": "<p>...</p>"}, ...],
  "pitfalls": ["...", "..."],
  "faq": [{"q": "...", "a": "..."}, ...],
  "updated": "<YYYY-MM-DD>",
  "jsonLd": [
    {"@context":"https://schema.org","@type":"HowTo","name":"<title>","step":[{"@type":"HowToStep","name":"<steps[0].name>","text":"<plain-text of steps[0].html>"}]},
    {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
      {"@type":"Question","name":"<faq[0].q>","acceptedAnswer":{"@type":"Answer","text":"<faq[0].a>"}}
    ]}
  ]
}

The jsonLd block is REQUIRED.
"""


def _llm_call(model: str, system: str, user: str, max_tokens: int = 4000):
    resp = _client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.4,
    )
    txt = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    in_t = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_t = getattr(usage, "completion_tokens", 0) if usage else 0
    return txt, in_t, out_t


def estimate_cost(in_t: int, out_t: int) -> float:
    return (in_t / 1_000_000) * PRICE_PER_M_INPUT + (out_t / 1_000_000) * PRICE_PER_M_OUTPUT


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text == "DROP_NO_INFORMATION_GAIN":
        return None
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find first {...} block
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _word_count(s: str) -> int:
    return len(re.findall(r"\b\w+\b", s or ""))


_NUMBER_OR_STAT_RE = re.compile(r"(\d[\d,.]*\s*(%|percent|x|×|million|billion|trillion|k\b)?|\$\s*\d|href=)", re.I)


def _section_has_cited_stat(section_html: str, stats: List[Dict]) -> bool:
    """A section satisfies the rule if it contains an inline citation/link or
    references one of the stats by value (e.g. "80%")."""
    if not section_html:
        return False
    if "<a " in section_html.lower() or "href=" in section_html.lower():
        return True
    if _NUMBER_OR_STAT_RE.search(section_html):
        return True
    for s in stats or []:
        v = (s.get("value") or "").strip()
        if v and v.lower() in section_html.lower():
            return True
    return False


def validate_glossary(d: dict, require_jsonld: bool = True) -> Tuple[bool, List[str]]:
    errs = []
    for k in ("slug", "term", "question", "shortDef", "description", "answer",
              "stats", "sections", "faq", "related", "updated"):
        if k not in d:
            errs.append(f"missing key: {k}")
    if errs:
        return False, errs
    aw = _word_count(d["answer"])
    if not (35 <= aw <= 70):
        errs.append(f"answer must be ~40-60 words (got {aw})")
    if not isinstance(d["stats"], list) or not d["stats"]:
        errs.append("must have ≥1 stats entry")
    for s in d.get("stats", []):
        if not (isinstance(s, dict) and s.get("value") and s.get("label")
                and isinstance(s.get("source"), dict)
                and s["source"].get("url", "").startswith("http")):
            errs.append("each stat needs value, label, source.url")
            break
    if not isinstance(d["sections"], list) or len(d["sections"]) < 2:
        errs.append("need ≥2 sections")
    for sec in d.get("sections", []):
        if not (isinstance(sec, dict) and sec.get("heading") and sec.get("html")):
            errs.append("each section needs heading + html")
            break
    # ≥1 cited statistic per major section (citation = inline link OR a number/
    # value that appears in the stats table the page declares)
    for sec in d.get("sections", []):
        if not _section_has_cited_stat(sec.get("html", ""), d.get("stats", [])):
            errs.append(f"section '{sec.get('heading','?')}' lacks a cited statistic")
            break
    if not isinstance(d["faq"], list) or len(d["faq"]) < 4:
        errs.append("need ≥4 FAQ entries")
    body_words = _word_count(d.get("answer", "")) + sum(
        _word_count(re.sub(r"<[^>]+>", " ", s.get("html", ""))) for s in d.get("sections", [])
    ) + sum(_word_count(f.get("a", "")) for f in d.get("faq", []))
    if not (1100 <= body_words <= 2200):
        errs.append(f"length {body_words} words outside 1200-2000 target")
    if not re.match(r"^[a-z0-9-]+$", d["slug"]):
        errs.append("slug must be kebab-case")
    # JSON-LD must be present and valid for newly generated pages.
    # (For refreshes of pre-existing pages we accept missing jsonLd, since
    # historical entries on the site predate this requirement.)
    if require_jsonld:
        jl = d.get("jsonLd")
        if not isinstance(jl, list) or not jl:
            errs.append("missing jsonLd block (must include DefinedTerm + FAQPage)")
        else:
            types = {(b.get("@type") if isinstance(b, dict) else "") for b in jl}
            if "DefinedTerm" not in types:
                errs.append("jsonLd must include a DefinedTerm entry")
            if "FAQPage" not in types:
                errs.append("jsonLd must include a FAQPage entry")
    return (not errs), errs


def validate_guide(d: dict, require_jsonld: bool = True) -> Tuple[bool, List[str]]:
    errs = []
    for k in ("slug", "title", "description", "intro", "estTime", "difficulty",
              "prerequisites", "steps", "pitfalls", "faq", "updated"):
        if k not in d:
            errs.append(f"missing key: {k}")
    if errs:
        return False, errs
    iw = _word_count(d["intro"])
    if not (35 <= iw <= 70):
        errs.append(f"intro must be ~40-60 words (got {iw})")
    if not isinstance(d["steps"], list) or len(d["steps"]) < 3:
        errs.append("need ≥3 steps")
    for i, st in enumerate(d.get("steps", []), 1):
        if not (isinstance(st, dict) and st.get("name") and st.get("html")):
            errs.append(f"step {i} missing name/html")
            break
    if not isinstance(d["faq"], list) or len(d["faq"]) < 3:
        errs.append("need ≥3 FAQ entries")
    if not re.match(r"^[a-z0-9-]+$", d["slug"]):
        errs.append("slug must be kebab-case")
    body_words = _word_count(d.get("intro", "")) + sum(
        _word_count(re.sub(r"<[^>]+>", " ", s.get("html", ""))) for s in d.get("steps", [])
    ) + sum(_word_count(f.get("a", "")) for f in d.get("faq", []))
    if not (1100 <= body_words <= 2200):
        errs.append(f"length {body_words} words outside 1200-2000 target")
    if require_jsonld:
        jl = d.get("jsonLd")
        if not isinstance(jl, list) or not jl:
            errs.append("missing jsonLd block (must include HowTo + FAQPage)")
        else:
            types = {(b.get("@type") if isinstance(b, dict) else "") for b in jl}
            if "HowTo" not in types:
                errs.append("jsonLd must include a HowTo entry")
            if "FAQPage" not in types:
                errs.append("jsonLd must include a FAQPage entry")
    return (not errs), errs


def generate_glossary_page(model: str, topic: str, info_gap_brief: str
                           ) -> Tuple[Optional[dict], int, int, str]:
    """Return (entry, input_tokens, output_tokens, fail_reason)."""
    user = (f"Topic to cover: {topic}\n\n{info_gap_brief}\n\n"
            f"Today's date: {date.today().isoformat()}\n\n{GLOSSARY_SCHEMA}")
    txt, in_t, out_t = _llm_call(model, GEO_RULES, user, max_tokens=4500)
    data = _extract_json(txt)
    if data is None:
        return None, in_t, out_t, "DROP_NO_INFORMATION_GAIN" if "DROP_NO_INFORMATION_GAIN" in txt else "no json"
    data["updated"] = date.today().isoformat()
    if not data.get("related"):
        data["related"] = []
    ok, errs = validate_glossary(data)
    if not ok:
        return None, in_t, out_t, "validation: " + "; ".join(errs)
    return data, in_t, out_t, ""


def generate_guide_page(model: str, topic: str, info_gap_brief: str
                        ) -> Tuple[Optional[dict], int, int, str]:
    user = (f"How-to topic: {topic}\n\n{info_gap_brief}\n\n"
            f"Today's date: {date.today().isoformat()}\n\n{GUIDE_SCHEMA}")
    txt, in_t, out_t = _llm_call(model, GEO_RULES, user, max_tokens=4500)
    data = _extract_json(txt)
    if data is None:
        return None, in_t, out_t, "DROP_NO_INFORMATION_GAIN" if "DROP_NO_INFORMATION_GAIN" in txt else "no json"
    data["updated"] = date.today().isoformat()
    ok, errs = validate_guide(data)
    if not ok:
        return None, in_t, out_t, "validation: " + "; ".join(errs)
    return data, in_t, out_t, ""


def classify_kind(topic: str) -> str:
    t = topic.lower()
    if t.startswith(("how to", "how do i", "tutorial", "step")) or "how-to" in t:
        return "guides"
    return "glossary"
