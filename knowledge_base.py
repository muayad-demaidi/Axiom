"""Project knowledge-base ingestion helpers.

Three source kinds are supported as project background context for the
AI assistant:

* ``text`` — uploaded ``.txt`` / ``.md`` file. Read as UTF-8 with a
  latin-1 fallback so we never fail on a stray byte.
* ``pdf``  — uploaded ``.pdf`` file. Plain text extraction via
  ``pypdf`` (no OCR; image-only PDFs surface a clear error).
* ``url``  — public web page. Fetched once with a short timeout, parsed
  with BeautifulSoup, scripts/styles stripped, whitespace collapsed.

Each entry point returns ``(text, label)`` on success or raises
``KnowledgeBaseError`` with a human-readable message the UI can display
verbatim.

Storage caps are enforced by ``models.set_project_knowledge_base``; the
helpers here only enforce the per-source download/read ceiling so a
hostile URL or huge PDF can't exhaust memory before truncation.
"""
from __future__ import annotations

import io
import re
from typing import Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


class KnowledgeBaseError(Exception):
    """User-facing error raised by the extraction helpers."""


# Hard ceilings — content beyond these bounds is dropped with a clear
# message rather than silently truncated mid-sentence. The DB layer also
# truncates to ``KB_MAX_CHARS`` as a defence in depth.
MAX_FETCH_BYTES = 8 * 1024 * 1024     # 8 MB on URL responses
MAX_PDF_BYTES   = 20 * 1024 * 1024    # 20 MB on PDF uploads
MAX_TEXT_BYTES  = 5 * 1024 * 1024     # 5 MB on plain-text uploads
HTTP_TIMEOUT    = 12                  # seconds


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of blank lines and trim trailing spaces line by line."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if ln.strip():
            out.append(ln)
            blank = 0
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


def extract_text(raw_bytes: bytes, filename: str = "text-upload") -> Tuple[str, str]:
    """Read a raw byte stream for a .txt / .md file."""
    if len(raw_bytes) > MAX_TEXT_BYTES:
        raise KnowledgeBaseError(
            f"Text file is too large ({len(raw_bytes) // 1024} KB). "
            f"Limit is {MAX_TEXT_BYTES // (1024 * 1024)} MB.")
    if not raw_bytes:
        raise KnowledgeBaseError("The provided text content is empty.")
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise KnowledgeBaseError("Could not decode the text content as UTF-8 or Latin-1.")
    text = _normalize_whitespace(text)
    if not text:
        raise KnowledgeBaseError("The text content contains no readable text.")
    return text, filename


def extract_pdf(raw_bytes: bytes, filename: str = "pdf-upload") -> Tuple[str, str]:
    """Pull plain text out of a raw PDF byte stream using pypdf.

    Image-only PDFs (scans without an embedded text layer) yield no text
    and raise ``KnowledgeBaseError`` — OCR is explicitly out of scope for
    AXIOM's current engine.
    """
    if len(raw_bytes) > MAX_PDF_BYTES:
        raise KnowledgeBaseError(
            f"PDF is too large ({len(raw_bytes) // (1024 * 1024)} MB). "
            f"Limit is {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    if not raw_bytes:
        raise KnowledgeBaseError("The provided PDF content is empty.")
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
    except Exception as e:
        raise KnowledgeBaseError(f"Could not read PDF: {e}") from e
    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)
    text = _normalize_whitespace("\n\n".join(parts))
    if not text:
        raise KnowledgeBaseError(
            "No readable text found in this PDF. "
            "Image-only or scanned PDFs aren't supported (no OCR).")
    return text, filename


def extract_url(url: str) -> Tuple[str, str]:
    """Fetch a single public URL and return its readable text."""
    url = (url or "").strip()
    if not url:
        raise KnowledgeBaseError("Please paste a URL first.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise KnowledgeBaseError("That doesn't look like a valid URL.")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AXIOM-KnowledgeBase/1.0; "
            "+https://axiom.ai)"),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT,
                            allow_redirects=True, stream=True)
    except requests.exceptions.Timeout as e:
        raise KnowledgeBaseError(f"Timed out fetching {url}.") from e
    except requests.exceptions.RequestException as e:
        raise KnowledgeBaseError(f"Could not fetch URL: {e}") from e
    if resp.status_code >= 400:
        raise KnowledgeBaseError(
            f"URL returned HTTP {resp.status_code}. Make sure the page is public.")
    # Read with a hard byte ceiling so a huge response can't OOM us.
    try:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_FETCH_BYTES:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if not raw:
        raise KnowledgeBaseError("The URL returned an empty response.")
    ctype = (resp.headers.get("Content-Type") or "").lower()
    encoding = resp.encoding or "utf-8"
    try:
        body = raw.decode(encoding, errors="replace")
    except Exception:
        body = raw.decode("utf-8", errors="replace")
    if "html" in ctype or "<html" in body[:2048].lower():
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()
        # ``get_text`` with a separator preserves natural sentence breaks
        # so the AI sees readable paragraphs rather than one wall of text.
        text = soup.get_text(separator="\n", strip=True)
    else:
        text = body
    text = _normalize_whitespace(text)
    if not text:
        raise KnowledgeBaseError(
            "Could not extract any readable text from that page.")
    label = url
    return text, label


def build_context_block(bundle: dict, char_budget: int = 12000) -> str:
    """Render a knowledge-base bundle as a system-prompt fragment.

    Truncates the bundle to ``char_budget`` characters total, splitting
    the budget between the KB body (most of it) and the most recent
    learned notes (a smaller tail). Returns an empty string if the
    bundle has nothing useful in it.
    """
    if not bundle or (not bundle.get("kb") and not bundle.get("notes")):
        return ""
    parts: list[str] = []
    kb = bundle.get("kb") or {}
    if kb and (kb.get("text") or "").strip():
        body = kb["text"].strip()
        kb_budget = max(1000, char_budget - 2500)  # leave room for notes
        if len(body) > kb_budget:
            body = body[:kb_budget].rstrip() + "\n…[truncated]"
        kind = (kb.get("kind") or "").upper()
        label = kb.get("label") or ""
        parts.append(
            f"PROJECT KNOWLEDGE BASE [{kind} · {label}]\n"
            f"Treat the following as authoritative project background.\n"
            f"---\n{body}\n---")
    notes = bundle.get("notes") or []
    if notes:
        # Newest first in the bundle; show oldest→newest so the model
        # reads them as a chronological log.
        rendered: list[str] = []
        used = 0
        cap = 2500 if parts else char_budget
        for n in reversed(notes):
            line = f"[{(n.get('kind') or '').upper()}] {n.get('content') or ''}".strip()
            if not line:
                continue
            if used + len(line) > cap:
                break
            rendered.append(line)
            used += len(line) + 2
        if rendered:
            parts.append(
                "PROJECT LEARNED NOTES (auto-collected from prior AI exchanges):\n"
                + "\n• ".join([""] + rendered).lstrip())
    return "\n\n".join(parts).strip()
