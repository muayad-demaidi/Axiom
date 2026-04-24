"""Streaming chat endpoint, wired to OpenAI + the existing assistant prompt.

We bypass `ai_assistant.chat_about_data` (non-streaming) and call the OpenAI
client directly with `stream=True`, but we reuse the same SYSTEM_PROMPT,
language detection, and dataset-context construction so the responses match
the legacy Streamlit assistant.
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


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatStreamRequest(BaseModel):
    messages: list[ChatMessage]
    dataset_id: int | None = None
    project_id: int | None = None


def _build_df_info(df: pd.DataFrame | None) -> dict:
    if df is None or df.empty:
        return {}
    return {
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "head": df.head(5).to_dict(orient="records"),
    }


@router.post("/stream")
async def stream(req: ChatStreamRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
    if not last_user:
        raise HTTPException(400, "No user message in conversation")

    df = None
    if req.dataset_id:
        record = models.get_dataset_record(db, req.dataset_id, user_id=user.id)
        if record and record.source_parquet:
            df = pd.read_parquet(io.BytesIO(record.source_parquet))

    df_info = _build_df_info(df)
    user_lang = ai_assistant.detect_language(last_user.content)

    system = ai_assistant.SYSTEM_PROMPT  # type: ignore[attr-defined]
    if user_lang == "ar":
        system += "\n\nThe user is writing in Arabic; respond in Arabic (Modern Standard or Levantine)."
    elif user_lang and user_lang != "en":
        system += f"\n\nThe user is writing in {user_lang}; respond in the same language."
    if df_info:
        system += "\n\nDataset summary (JSON):\n" + json.dumps(df_info, default=str)[:6000]

    msgs = [{"role": "system", "content": system}]
    for m in req.messages:
        if m.role in ("user", "assistant"):
            msgs.append({"role": m.role, "content": m.content})

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        async def fallback() -> AsyncIterator[bytes]:
            yield (
                "OpenAI key is not configured on the backend; chat is offline. "
                "Set OPENAI_API_KEY to enable streaming responses."
            ).encode()
        return StreamingResponse(fallback(), media_type="text/plain; charset=utf-8")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

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
                if req.dataset_id:
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
