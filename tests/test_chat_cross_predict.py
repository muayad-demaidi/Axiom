"""Tests for the chat ``cross_predict_column`` tool (Task #259).

The HTTP cross-predict endpoint is already covered by
``tests/test_cross_predict.py``. These tests focus on the chat-tool
wrapper:

  * the dispatcher invokes ``_run_cross_predict`` for the registered
    tool name and persists a ``cross_prediction`` chat artifact;
  * the artifact payload preserves the join_plan + dual guided/expert
    block;
  * the summary returned to the model contains a plain-language
    join_plan_text the assistant is instructed to quote;
  * the schema entry is registered alongside the other tools so the
    OpenAI client can call it.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

import models  # type: ignore
from backend import chat as chat_mod
from backend.chat import (
    TOOL_SCHEMA,
    _TOOL_HANDLERS,
    _format_join_plan_text,
    _run_cross_predict,
)


# ---------------------------------------------------------------------------
# Sample frames — two datasets with a shared customer_id key
# ---------------------------------------------------------------------------

@pytest.fixture
def cp_orders_csv() -> bytes:
    rng = np.random.default_rng(42)
    n = 40
    df = pd.DataFrame({
        "order_id": list(range(2001, 2001 + n)),
        "customer_id": rng.integers(1, 9, size=n),
        "spend": rng.uniform(20, 200, size=n).round(2),
        "sales": rng.uniform(50, 500, size=n).round(2),
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def cp_customers_csv() -> bytes:
    df = pd.DataFrame({
        "customer_id": list(range(1, 9)),
        "tenure_months": [3, 12, 27, 5, 18, 9, 41, 7],
        "segment_score": [0.2, 0.7, 0.9, 0.3, 0.5, 0.4, 0.95, 0.35],
    })
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


# ---------------------------------------------------------------------------
# Schema / dispatcher registration
# ---------------------------------------------------------------------------

def test_cross_predict_tool_is_registered_in_dispatcher_and_schema():
    assert "cross_predict_column" in _TOOL_HANDLERS
    assert _TOOL_HANDLERS["cross_predict_column"] is _run_cross_predict
    schema_names = {t["function"]["name"] for t in TOOL_SCHEMA
                    if t.get("type") == "function"}
    assert "cross_predict_column" in schema_names
    spec = next(t["function"] for t in TOOL_SCHEMA
                if t.get("type") == "function"
                and t["function"]["name"] == "cross_predict_column")
    params = spec["parameters"]["properties"]
    assert "target_dataset_id" in params
    assert "target_column" in params
    assert set(spec["parameters"]["required"]) == {
        "target_dataset_id", "target_column"
    }


# ---------------------------------------------------------------------------
# Plain-language join_plan formatter
# ---------------------------------------------------------------------------

def test_format_join_plan_text_no_steps_explains_target_only():
    text = _format_join_plan_text([], "orders")
    assert "no joins" in text
    assert "orders" in text


def test_format_join_plan_text_includes_keys_and_row_counts():
    steps = [
        {"dataset_name": "customers", "left_column": "customer_id",
         "right_column": "customer_id", "rows_before": 40, "rows_after": 40},
        {"dataset_name": "regions", "left_column": "region_code",
         "right_column": "code", "rows_before": 40, "rows_after": 40},
    ]
    text = _format_join_plan_text(steps, "orders")
    assert "starting from orders" in text
    assert "customers" in text
    assert "customer_id" in text
    assert "then joined regions" in text
    assert "region_code" in text and "code" in text
    assert "40 → 40" in text


# ---------------------------------------------------------------------------
# End-to-end through the FastAPI test client (real DB session, real auth,
# real cross-predict logic) — mirrors test_artifacts_api.py for parity with
# how predict_column is exercised.
# ---------------------------------------------------------------------------

def test_cross_predict_tool_persists_artifact_with_join_plan(
    client, project, upload_dataset, chat_session,
    cp_customers_csv, cp_orders_csv,
):
    """Drives ``_run_cross_predict`` exactly the way the chat
    dispatcher does and checks that a ``cross_prediction`` artifact
    lands with both the dual {guided, expert} payload and the
    join_plan describing the auto-join."""
    from models import SessionLocal

    u, pid = project("chat-cp")
    upload_dataset(u["headers"], pid, "customers", cp_customers_csv)
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    sid = chat_session(u["headers"], pid, "chat-cp-session")

    ctx = {
        "user_id": u["user"]["id"],
        "project_id": pid,
        "session_id": sid,
        "mode": "guided",
    }
    db = SessionLocal()
    try:
        summary, views = _run_cross_predict(
            db,
            {"target_dataset_id": orders_id, "target_column": "sales"},
            ctx,
        )
    finally:
        db.close()

    # The summary the assistant sees describes the join_plan in plain
    # language so the methodology prompt can quote it verbatim.
    assert summary["target_dataset"] == "orders"
    assert summary["target_column"] == "sales"
    assert summary["merged_cols"] >= 6  # picked up dimension features
    assert summary["skipped"] is False
    assert "customers" in summary["join_plan_text"]
    assert "customer_id" in summary["join_plan_text"]
    assert summary["joins"], summary
    step = summary["joins"][0]
    assert step["dataset_name"] == "customers"
    assert step["left_column"] and step["right_column"]
    # Either guided or expert metrics should be present (the engine
    # populates both — we don't assert on the value beyond presence).
    assert summary["guided_summary"] is not None
    assert summary["model_used"]

    # Artifact persistence parity with predict_column.
    assert len(views) == 1
    art = views[0]
    assert art["kind"] == "cross_prediction"
    assert art["pinned"] is True
    assert art["dataset_id"] == orders_id
    assert art["params"]["target_dataset_id"] == orders_id
    assert art["params"]["target_column"] == "sales"
    payload = art["result"]
    assert payload["flow"] == "cross_predict"
    assert "guided" in payload and "expert" in payload
    plan = payload["join_plan"]
    assert plan["target_dataset_id"] == orders_id
    assert plan["target_dataset_name"] == "orders"
    assert plan["skipped"] is False
    assert plan["merged_cols"] >= 6
    assert isinstance(plan["joins"], list) and plan["joins"]


def test_cross_predict_tool_falls_back_to_target_alone_when_no_relationships(
    client, project, upload_dataset, chat_session, cp_orders_csv,
):
    """A single-dataset project still produces a prediction on the
    target alone with skipped=True and a warning surfaced in the
    summary."""
    from models import SessionLocal

    u, pid = project("chat-cp-solo")
    orders_id = upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    sid = chat_session(u["headers"], pid, "chat-cp-solo-session")

    ctx = {"user_id": u["user"]["id"], "project_id": pid,
           "session_id": sid, "mode": "guided"}
    db = SessionLocal()
    try:
        summary, views = _run_cross_predict(
            db,
            {"target_dataset_id": orders_id, "target_column": "sales"},
            ctx,
        )
    finally:
        db.close()
    assert summary["skipped"] is True
    assert summary["joins"] == []
    assert any("alone" in w for w in summary["warnings"])
    assert "no joins" in summary["join_plan_text"]
    assert views and views[0]["kind"] == "cross_prediction"
    assert views[0]["result"]["join_plan"]["skipped"] is True


def test_cross_predict_tool_rejects_target_outside_project(
    client, project, upload_dataset, chat_session, cp_orders_csv,
):
    """The tool must refuse a target dataset that doesn't belong to
    the active project — mirrors the HTTP endpoint's 422."""
    from models import SessionLocal

    u, pid = project("chat-cp-strict")
    upload_dataset(u["headers"], pid, "orders", cp_orders_csv)
    sid = chat_session(u["headers"], pid, "chat-cp-strict-session")

    ctx = {"user_id": u["user"]["id"], "project_id": pid,
           "session_id": sid, "mode": "guided"}
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="does not belong"):
            _run_cross_predict(
                db,
                {"target_dataset_id": 999_999, "target_column": "sales"},
                ctx,
            )
    finally:
        db.close()


def test_cross_predict_tool_requires_project_context():
    with pytest.raises(ValueError, match="project context"):
        _run_cross_predict(
            db=None,
            args={"target_dataset_id": 1, "target_column": "sales"},
            ctx={"user_id": 1, "project_id": None, "session_id": 1},
        )
