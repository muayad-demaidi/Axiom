"""Streaming chat endpoint — project-aware, session-anchored.

Each turn:
  * resolves the chat session (and therefore the owning project)
  * loads **all** datasets attached to that project so the model can
    cross-reference them, not just the one the user "selected"
  * builds a structured methodology system prompt + per-dataset summary
  * streams the OpenAI completion back to the browser
  * persists the user/assistant turn under the session
  * auto-titles a brand-new session from the first user message
"""
from __future__ import annotations

import io
import json
import os
from typing import AsyncIterator

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import models  # type: ignore
import ai_assistant  # type: ignore

from .auth import get_current_user, get_db_session

router = APIRouter(prefix="/api/chat", tags=["chat"])


# Methodology block — appended to the assistant's existing SYSTEM_PROMPT
# so every reply walks the user through a transparent analysis path.
METHODOLOGY_PROMPT = """
You are AXIOM's project-aware data analyst. Inside an open project you
can see **all** datasets the user uploaded — treat them as one connected
workspace. When the user asks a question, follow this methodology and
make the steps visible in your reply (concise, no fluff):

1. Understand — restate the question in one line.
2. Identify data — name which dataset(s) and column(s) you'll use, and
   how they relate (shared keys, time alignment, etc).
3. Plan — list the analytical steps you'll take (clean? aggregate?
   compare? model?). Keep it short, 2–5 bullets.
4. Result — give the answer or finding. If you would compute a number,
   describe the formula clearly with the columns involved.
5. Caveats — call out missing data, sample-size issues, assumptions.

Style rules:
  * Always answer in the same language as the user's last message.
  * Refer to datasets by their `dataset_name` exactly as listed below.
  * If a question can't be answered from the data the project contains,
    say so explicitly and suggest what the user could upload.
  * Never invent column values you can't see — only reason from the
    column names, dtypes, and sample rows in context.
"""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    # `messages` is the working transcript from the browser. We use the
    # last user message; older turns are reloaded from the DB so context
    # survives page reloads.
    messages: list[ChatMessage]
    session_id: int | None = None
    # Legacy fields kept so older clients keep working during rollout.
    dataset_id: int | None = None
    project_id: int | None = None


def _df_block(name: str, df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"name": name, "rows": 0, "cols": 0, "columns": [], "head": []}
    return {
        "name": name,
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "columns": [
            {"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns
        ],
        "head": df.head(5).to_dict(orient="records"),
    }


def _load_project_datasets(db, project_id: int, user_id: int) -> list[dict]:
    """Return a compact summary of every dataset attached to the project."""
    rows = (
        db.query(models.DatasetRecord)
        .filter(
            models.DatasetRecord.project_id == project_id,
            models.DatasetRecord.user_id == user_id,
        )
        .order_by(models.DatasetRecord.id.asc())
        .all()
    )
    out: list[dict] = []
    for r in rows:
        df = None
        try:
            if r.source_parquet:
                df = pd.read_parquet(io.BytesIO(r.source_parquet))
        except Exception:
            df = None
        block = _df_block(r.dataset_name or r.filename or f"dataset_{r.id}", df)
        block["id"] = r.id
        out.append(block)
    return out


def _load_relationships(db, dataset_ids: list[int]) -> list[dict]:
    if not dataset_ids:
        return []
    rels = (
        db.query(models.DatasetRelationship)
        .filter(
            models.DatasetRelationship.left_dataset_id.in_(dataset_ids)
            | models.DatasetRelationship.right_dataset_id.in_(dataset_ids)
        )
        .all()
    )
    return [
        {
            "left_dataset_id": r.left_dataset_id,
            "left_column": r.left_column,
            "right_dataset_id": r.right_dataset_id,
            "right_column": r.right_column,
            "cardinality": r.cardinality,
            "join_type": r.join_type,
        }
        for r in rels
    ]


def _project_knowledge(db, project_id: int, user_id: int) -> str | None:
    """KB text scoped to the requesting user — defence-in-depth alongside
    the project ownership check the caller already performs."""
    kb = (
        db.query(models.ProjectKnowledgeBase)
        .join(models.Project, models.Project.id == models.ProjectKnowledgeBase.project_id)
        .filter(
            models.ProjectKnowledgeBase.project_id == project_id,
            models.Project.user_id == user_id,
        )
        .first()
    )
    if kb and kb.content_text:
        return kb.content_text[:6000]
    return None


def _recent_learned_notes(db, project_id: int, user_id: int, limit: int = 6) -> list[str]:
    """Recent notes scoped to the requesting user."""
    notes = (
        db.query(models.ProjectLearnedNote)
        .join(models.Project, models.Project.id == models.ProjectLearnedNote.project_id)
        .filter(
            models.ProjectLearnedNote.project_id == project_id,
            models.Project.user_id == user_id,
        )
        .order_by(models.ProjectLearnedNote.created_at.desc())
        .limit(limit)
        .all()
    )
    return [n.content[:600] for n in notes]


def _auto_title(text: str) -> str:
    """Cheap auto-title from the first user message."""
    snippet = " ".join((text or "").split())
    if not snippet:
        return "New chat"
    return snippet[:60] + ("…" if len(snippet) > 60 else "")


@router.post("/stream")
async def stream(
    req: ChatStreamRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if not last_user:
        raise HTTPException(400, "No user message in conversation")

    # Resolve session → project (preferred path).
    session = None
    project_id: int | None = None
    if req.session_id:
        session = models.get_chat_session(db, req.session_id, user.id)
        if not session:
            raise HTTPException(404, "Chat session not found")
        project_id = session.project_id
    elif req.project_id:
        # Legacy path: must validate ownership before trusting the id.
        proj = models.get_project(db, req.project_id, user.id)
        if not proj:
            raise HTTPException(404, "Project not found")
        project_id = req.project_id

    # Build the data context.
    datasets_ctx: list[dict] = []
    if project_id:
        datasets_ctx = _load_project_datasets(db, project_id, user.id)
    elif req.dataset_id:
        # Legacy single-dataset path (kept for old /app/chat callers).
        record = models.get_dataset_record(db, req.dataset_id, user_id=user.id)
        if record and record.source_parquet:
            df = pd.read_parquet(io.BytesIO(record.source_parquet))
            block = _df_block(record.dataset_name or record.filename or "dataset", df)
            block["id"] = record.id
            datasets_ctx = [block]

    relationships = _load_relationships(db, [d.get("id") for d in datasets_ctx if d.get("id")])
    kb_text = _project_knowledge(db, project_id, user.id) if project_id else None
    learned = _recent_learned_notes(db, project_id, user.id) if project_id else []

    # Build system prompt.
    user_lang = ai_assistant.detect_language(last_user.content)
    system_parts = [ai_assistant.SYSTEM_PROMPT, METHODOLOGY_PROMPT]
    if user_lang == "ar":
        system_parts.append(
            "The user is writing in Arabic; reply in clear Levantine Arabic."
        )
    elif user_lang and user_lang != "en":
        system_parts.append(
            f"The user is writing in {user_lang}; reply in the same language."
        )

    if datasets_ctx:
        ds_summary = {
            "project_id": project_id,
            "dataset_count": len(datasets_ctx),
            "datasets": datasets_ctx,
            "relationships": relationships,
        }
        system_parts.append(
            "Project data context (JSON):\n" + json.dumps(ds_summary, default=str)[:9000]
        )
    else:
        system_parts.append(
            "This project currently has no uploaded datasets. Ask the user "
            "to upload data before attempting numeric analysis."
        )

    if kb_text:
        system_parts.append(
            "Project knowledge base (user-attached reference text):\n"
            + kb_text
        )
    if learned:
        system_parts.append(
            "Recent project notes (most recent first):\n- "
            + "\n- ".join(learned)
        )

    system = "\n\n".join(system_parts)

    # Build the message list. If we have a session, replay its history
    # from the DB so reloads don't lose context; otherwise trust the
    # client-supplied transcript.
    msgs: list[dict] = [{"role": "system", "content": system}]
    if session is not None:
        history = models.get_session_messages(db, session.id)
        for h in history:
            if h.user_message:
                msgs.append({"role": "user", "content": h.user_message})
            if h.ai_response:
                msgs.append({"role": "assistant", "content": h.ai_response})
        msgs.append({"role": "user", "content": last_user.content})
    else:
        for m in req.messages:
            if m.role in ("user", "assistant"):
                msgs.append({"role": m.role, "content": m.content})

    api_key = (
        os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    base_url = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
    if not api_key:
        async def fallback() -> AsyncIterator[bytes]:
            yield (
                "OpenAI key is not configured on the backend; chat is offline."
            ).encode()
        return StreamingResponse(fallback(), media_type="text/plain; charset=utf-8")

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    # Decide whether this turn should auto-title the session.
    will_auto_title = False
    if session is not None and (session.title or "").strip().lower() in ("", "new chat"):
        prior = models.get_session_messages(db, session.id, limit=1)
        if not prior:
            will_auto_title = True

    def producer():
        try:
            stream_resp = client.chat.completions.create(
                model="gpt-4o",
                messages=msgs,
                temperature=0.4,
                stream=True,
            )
            collected: list[str] = []
            for chunk in stream_resp:
                delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                if delta:
                    collected.append(delta)
                    yield delta.encode()
            full = "".join(collected)
            try:
                if session is not None:
                    models.save_chat_message(
                        db,
                        session_id=session.id,
                        user_message=last_user.content,
                        ai_response=full,
                    )
                    if will_auto_title:
                        models.rename_chat_session(
                            db, session.id, user.id, _auto_title(last_user.content)
                        )
                    if project_id:
                        try:
                            note = models.ProjectLearnedNote(
                                project_id=project_id,
                                kind="chat",
                                content=f"Q: {last_user.content[:300]}\nA: {full[:600]}",
                            )
                            db.add(note)
                            db.commit()
                        except Exception:
                            db.rollback()
                elif req.dataset_id:
                    models.save_chat_message(
                        db,
                        dataset_id=req.dataset_id,
                        user_message=last_user.content,
                        ai_response=full,
                    )
            except Exception:
                pass
        except Exception as e:
            yield f"\n\n[chat error: {e}]".encode()

    return StreamingResponse(producer(), media_type="text/plain; charset=utf-8")
