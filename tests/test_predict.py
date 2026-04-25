"""Tests for backend.chat._run_predict — Task #166.

Covers the small-sample branch: when a user asks for a prediction on a
dataset with fewer than ``PREDICT_MIN_ROWS`` usable rows, the tool now
returns a friendly bilingual (EN + Levantine Arabic) notice instead of
raising a ValueError that the chat would render as a red
"Fit prediction model failed: ..." stack-trace box.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backend import chat as chat_module
from backend.chat import (
    PREDICT_MIN_ROWS,
    _run_predict,
    _small_sample_predict_notice,
)


def _tiny_df(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "revenue": [10.0 + i for i in range(n)],
            "units": [1 + i for i in range(n)],
            "marketing_spend": [2 + i for i in range(n)],
        }
    )


def _stub_record():
    return SimpleNamespace(id=1, dataset_name="tiny.csv", filename="tiny.csv")


def test_small_sample_notice_helper_is_bilingual():
    notice = _small_sample_predict_notice(rows_available=4, target="revenue")
    assert notice["kind"] == "small_sample_notice"
    assert notice["rows_available"] == 4
    assert notice["rows_required"] == PREDICT_MIN_ROWS
    assert notice["target"] == "revenue"
    # English copy mentions the actual numbers and the target.
    assert "4" in notice["message_en"]
    assert str(PREDICT_MIN_ROWS) in notice["message_en"]
    assert "revenue" in notice["message_en"]
    # Arabic copy is present and contains Arabic script characters.
    assert any("\u0600" <= ch <= "\u06ff" for ch in notice["message_ar"])
    # Suggests calmer alternative tools rather than failing outright.
    assert "profile_dataset" in notice["suggested_tools"]
    assert "make_chart" in notice["suggested_tools"]


def test_run_predict_returns_notice_for_tiny_dataset(monkeypatch):
    rec = _stub_record()
    df = _tiny_df(n=4)  # 4 < PREDICT_MIN_ROWS (10)

    def _fake_load_df(db, dataset_id, user_id, project_id=None):
        return rec, df

    saved = []

    def _fail_save(*args, **kwargs):  # pragma: no cover - must not be called
        saved.append(kwargs)
        raise AssertionError("save_chat_artifact must not be called for tiny data")

    monkeypatch.setattr(chat_module, "_load_df", _fake_load_df)
    monkeypatch.setattr(chat_module.models, "save_chat_artifact", _fail_save)

    summary, artifacts = _run_predict(
        db=None,
        args={"dataset_id": 1, "target": "revenue"},
        ctx={"user_id": 1, "project_id": 1, "session_id": 1},
    )
    assert artifacts == []
    assert summary["ok"] is True
    assert summary["skipped"] == "small_sample"
    assert summary["kind"] == "small_sample_notice"
    assert summary["target"] == "revenue"
    assert summary["rows_available"] == 4
    assert summary["rows_required"] == PREDICT_MIN_ROWS
    notice = summary["notice"]
    assert notice["kind"] == "small_sample_notice"
    assert notice["message_en"] and notice["message_ar"]
    assert saved == []  # confirm the persistence path was skipped


def test_run_predict_still_raises_for_non_numeric_target(monkeypatch):
    rec = _stub_record()
    df = pd.DataFrame({"label": ["a", "b", "c"], "x": [1, 2, 3]})

    monkeypatch.setattr(
        chat_module, "_load_df", lambda *a, **k: (rec, df)
    )
    with pytest.raises(ValueError, match="not numeric"):
        _run_predict(
            db=None,
            args={"dataset_id": 1, "target": "label"},
            ctx={"user_id": 1, "project_id": 1, "session_id": 1},
        )
