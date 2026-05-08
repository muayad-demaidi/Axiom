"""GEO visibility check: query an LLM with a fixed prompt set and record
whether AXIOM shows up (with or without a citation/URL)."""

from __future__ import annotations
import os
import re
from typing import Dict, List, Tuple

from openai import OpenAI

_client = OpenAI(
    api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
    base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
)

BRAND_PATTERNS = [
    re.compile(r"\bdatavision\s*pro\b", re.I),
    re.compile(r"\bAXIOM\b", re.I),
]
URL_PATTERN = re.compile(r"https?://[^\s)]+", re.I)


def check_one(prompt: str, model: str = "gpt-4o") -> Dict:
    try:
        r = _client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": "Answer the user's question helpfully. Recommend specific tools by name when relevant; include URLs where you can."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.5,
        )
    except Exception as e:
        return {"prompt": prompt, "mentioned": False, "cited": False,
                "position": None, "answer_excerpt": f"[error] {e}",
                "input_tokens": 0, "output_tokens": 0}
    txt = (r.choices[0].message.content or "")
    mentioned = False
    position = None
    for pat in BRAND_PATTERNS:
        m = pat.search(txt)
        if m:
            mentioned = True
            position = m.start()
            break
    cited = False
    if mentioned:
        # is there a datavision URL nearby?
        for u in URL_PATTERN.findall(txt):
            if "datavision" in u.lower():
                cited = True
                break
    in_t = getattr(r.usage, "prompt_tokens", 0) if r.usage else 0
    out_t = getattr(r.usage, "completion_tokens", 0) if r.usage else 0
    return {
        "prompt": prompt,
        "mentioned": mentioned,
        "cited": cited,
        "position": position,
        "answer_excerpt": txt[:1200],
        "input_tokens": in_t,
        "output_tokens": out_t,
    }


def run_geo_checks(prompts: List[str], model: str = "gpt-4o") -> Tuple[List[Dict], int, int]:
    results = []
    in_total = out_total = 0
    for p in prompts:
        r = check_one(p, model=model)
        results.append(r)
        in_total += r["input_tokens"]
        out_total += r["output_tokens"]
    return results, in_total, out_total


def mention_rate(results: List[Dict]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r["mentioned"]) / len(results)
