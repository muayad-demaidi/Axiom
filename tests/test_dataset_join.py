"""Task #247 — POST /api/datasets/join + join_datasets chat tool.

Covers each join_type (inner / left / right / outer), preview vs save,
suffix collisions when the two sides share non-key columns, the
missing-key 400, cross-user isolation, and the chat-tool dispatcher
path. The HTTP suite reuses the existing `customers_csv` /
`orders_csv` fixtures (customer_id is the common key, with one
customer absent from the orders side so left/outer joins surface
nulls).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# HTTP-level coverage
# ---------------------------------------------------------------------------

@pytest.fixture
def joined_pair(client, project, upload_dataset, customers_csv, orders_csv):
    """Upload customers + orders into the same project and return the ids."""
    u, pid = project("join-suite")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    ords = upload_dataset(u["headers"], pid, "orders", orders_csv)
    return u, pid, cust, ords


def _post_join(client, headers, body):
    r = client.post("/api/datasets/join", json=body, headers=headers)
    return r


def test_join_inner_preview_returns_only_matching_rows(client, joined_pair):
    u, _pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["preview_only"] is True
    s = data["summary"]
    # Orders fixture has 50 rows on customer ids 1..10 — all customers
    # match because the customers fixture covers ids 1..10.
    assert s["join_type"] == "inner"
    assert s["left_rows"] == 50
    assert s["right_rows"] == 10
    assert s["result_rows"] == 50          # every order has a customer
    assert s["left_key"] == "customer_id"
    assert s["right_key"] == "customer_id"
    assert s["collisions"] == []           # no shared non-key columns
    # Preview is capped at 20 rows even though the full result has 50.
    assert len(data["preview_rows"]) == 20
    cols = {c["name"] for c in data["columns"]}
    assert {"order_id", "amount", "customer_id", "name", "country"} <= cols


def test_join_left_keeps_left_rows_when_right_is_missing(
    client, project, upload_dataset, customers_csv,
):
    """LEFT JOIN must preserve every left-side row even when the right
    side has no match. We use a tiny tailored second dataset (only one
    customer_id, 5) so most of the rows on the left have no match."""
    u, pid = project("join-left")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    # Custom orders frame — only one matching customer.
    tiny_orders = pd.DataFrame({
        "order_id": [9001, 9002],
        "customer_id": [5, 999],
        "amount": [12.0, 34.0],
    }).to_csv(index=False).encode()
    ords = upload_dataset(u["headers"], pid, "tiny_orders", tiny_orders)

    r = _post_join(client, u["headers"], {
        "left_dataset_id": cust,
        "right_dataset_id": ords,
        "join_key": "customer_id",
        "join_type": "left",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["join_type"] == "left"
    assert s["left_rows"] == 10
    assert s["right_rows"] == 2
    # Every left row preserved — customer 5 picks up the matching order
    # so we get one extra row from the join (10 + 1 dup of customer 5).
    # pandas semantics: LEFT JOIN with a 1:N right side fans out, but
    # here right has at most one match per left row, so it stays at 10.
    assert s["result_rows"] == 10
    # Nine of the 10 left rows had no match → order_id is null nine times.
    assert s["null_counts"]["order_id"] == 9


def test_join_right_mirrors_left(client, project, upload_dataset, customers_csv):
    u, pid = project("join-right")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    tiny_orders = pd.DataFrame({
        "order_id": [9001, 9002, 9003],
        "customer_id": [5, 999, 1000],
        "amount": [12.0, 34.0, 56.0],
    }).to_csv(index=False).encode()
    ords = upload_dataset(u["headers"], pid, "tiny_orders", tiny_orders)

    r = _post_join(client, u["headers"], {
        "left_dataset_id": cust,
        "right_dataset_id": ords,
        "join_key": "customer_id",
        "join_type": "right",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["join_type"] == "right"
    # RIGHT JOIN keeps all 3 right rows.
    assert s["result_rows"] == 3


def test_join_outer_keeps_unmatched_from_both_sides(
    client, project, upload_dataset, customers_csv,
):
    u, pid = project("join-outer")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    tiny_orders = pd.DataFrame({
        "order_id": [9001, 9002],
        "customer_id": [5, 999],   # 999 doesn't exist on the customers side
        "amount": [12.0, 34.0],
    }).to_csv(index=False).encode()
    ords = upload_dataset(u["headers"], pid, "tiny_orders", tiny_orders)

    r = _post_join(client, u["headers"], {
        "left_dataset_id": cust,
        "right_dataset_id": ords,
        "join_key": "customer_id",
        "join_type": "outer",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["join_type"] == "outer"
    # 10 customers + 1 order that doesn't match any of them = 11.
    assert s["result_rows"] == 11


def test_join_save_persists_new_dataset_under_left_project(client, joined_pair):
    u, pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "inner",
        "preview_only": False,
        "result_name": "orders_with_customers",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_only"] is False
    new_id = body["dataset_id"]
    assert body["project_id"] == pid
    assert body["dataset_name"] == "orders_with_customers"
    # The new dataset is fetchable as a regular dataset.
    r2 = client.get(f"/api/datasets/{new_id}", headers=u["headers"])
    assert r2.status_code == 200
    fetched = r2.json()
    assert fetched["project_id"] == pid
    assert fetched["rows"] == 50


def test_join_suffix_collisions_get_left_right_suffix(
    client, project, upload_dataset,
):
    """When the two sides share non-key columns, pandas.merge with
    suffixes=('_left','_right') renames them. The endpoint must surface
    the colliding names so the UI can warn."""
    u, pid = project("join-suffix")
    a = pd.DataFrame({
        "id": [1, 2, 3],
        "amount": [10, 20, 30],
        "label": ["a", "b", "c"],
    }).to_csv(index=False).encode()
    b = pd.DataFrame({
        "id": [1, 2, 3],
        "amount": [99, 88, 77],
        "label": ["x", "y", "z"],
    }).to_csv(index=False).encode()
    da = upload_dataset(u["headers"], pid, "frame_a", a)
    db = upload_dataset(u["headers"], pid, "frame_b", b)
    r = _post_join(client, u["headers"], {
        "left_dataset_id": da,
        "right_dataset_id": db,
        "join_key": "id",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert sorted(data["summary"]["collisions"]) == ["amount", "label"]
    cols = {c["name"] for c in data["columns"]}
    assert {"amount_left", "amount_right", "label_left", "label_right"} <= cols


def test_join_missing_key_returns_400(client, joined_pair):
    u, _pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "definitely_not_a_column",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 400, r.text
    assert "definitely_not_a_column" in r.text


def test_join_invalid_join_type_returns_400(client, joined_pair):
    u, _pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "diagonal",
    })
    assert r.status_code == 400


def test_join_cross_user_isolation_returns_404(
    client, register, project, upload_dataset, customers_csv, orders_csv,
):
    """User A uploads two datasets; user B must not be able to join them
    even when they pass the right ids."""
    a, pid_a = project("ua", user=register("alice"))
    cust = upload_dataset(a["headers"], pid_a, "customers", customers_csv)
    ords = upload_dataset(a["headers"], pid_a, "orders", orders_csv)
    b, _pid_b = project("ub", user=register("bob"))
    r = _post_join(client, b["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
    })
    assert r.status_code == 404, r.text


def test_join_separate_left_and_right_keys(
    client, project, upload_dataset,
):
    """A foreign-key style join where the columns are spelled differently
    on each side (customer.id ↔ order.customer_id)."""
    u, pid = project("join-separate-keys")
    a = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Ada", "Linus", "Grace"],
    }).to_csv(index=False).encode()
    b = pd.DataFrame({
        "order_id": [10, 11, 12, 13],
        "customer_id": [1, 1, 2, 99],
        "amount": [10, 20, 30, 40],
    }).to_csv(index=False).encode()
    da = upload_dataset(u["headers"], pid, "customers_x", a)
    db = upload_dataset(u["headers"], pid, "orders_x", b)
    r = _post_join(client, u["headers"], {
        "left_dataset_id": db,
        "right_dataset_id": da,
        "join_key": "ignored",       # overridden below
        "left_key": "customer_id",
        "right_key": "id",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["left_key"] == "customer_id"
    assert s["right_key"] == "id"
    assert s["result_rows"] == 3   # order with customer 99 is dropped


# ---------------------------------------------------------------------------
# Chat-tool dispatcher coverage
# ---------------------------------------------------------------------------

def test_join_datasets_chat_tool_preview(
    client, register, project, upload_dataset, chat_session,
    customers_csv, orders_csv, stub_openai,
):
    """The chat-tool wrapper runs the same logic as the HTTP endpoint
    but persists nothing when preview_only is True. Mirrors how the
    other tool tests in test_api_endpoints.py exercise the dispatcher
    directly."""
    from backend import chat as chat_mod
    from backend.auth import get_db_session
    u, pid = project("chat-join")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    ords = upload_dataset(u["headers"], pid, "orders", orders_csv)
    sid = chat_session(u["headers"], pid)
    ctx = {"user_id": u["user"]["id"], "project_id": pid, "session_id": sid}
    db = next(get_db_session())
    try:
        summary, artifacts = chat_mod._run_join_datasets(
            db,
            {
                "left_dataset_id": ords,
                "right_dataset_id": cust,
                "join_key": "customer_id",
                "join_type": "inner",
                "preview_only": True,
            },
            ctx,
        )
    finally:
        db.close()
    assert isinstance(summary, dict)
    assert summary["join_type"] == "inner"
    assert summary["result_rows"] == 50
    # Preview returns rows in the summary, no artifact persisted.
    assert artifacts == []
    assert "preview_rows" in summary
    assert len(summary["preview_rows"]) == 20


def test_join_datasets_chat_tool_save_persists_artifact(
    client, register, project, upload_dataset, chat_session,
    customers_csv, orders_csv, stub_openai,
):
    from backend import chat as chat_mod
    from backend.auth import get_db_session
    u, pid = project("chat-join-save")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    ords = upload_dataset(u["headers"], pid, "orders", orders_csv)
    sid = chat_session(u["headers"], pid)
    ctx = {"user_id": u["user"]["id"], "project_id": pid, "session_id": sid}
    db = next(get_db_session())
    try:
        summary, artifacts = chat_mod._run_join_datasets(
            db,
            {
                "left_dataset_id": ords,
                "right_dataset_id": cust,
                "join_key": "customer_id",
                "join_type": "left",
                "preview_only": False,
                "result_name": "orders_join_customers",
            },
            ctx,
        )
    finally:
        db.close()
    assert summary["dataset_id"]
    assert summary["dataset_name"] == "orders_join_customers"
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art["kind"] == "dataset_join"
    assert art["dataset_id"] == summary["dataset_id"]
    # The persisted dataset is visible via the regular datasets list.
    rows = client.get("/api/datasets", headers=u["headers"]).json()
    assert any(r["id"] == summary["dataset_id"] for r in rows)


def test_join_datasets_registered_in_tool_handlers_and_schema():
    """Smoke check: the chat tool name shows up in both the OpenAI
    schema and the dispatcher map. Catches the case where someone adds
    the handler but forgets to wire it up (or vice versa)."""
    from backend import chat as chat_mod
    assert "join_datasets" in chat_mod._TOOL_HANDLERS
    schema_names = {
        s["function"]["name"] for s in chat_mod.TOOL_SCHEMA
    }
    assert "join_datasets" in schema_names
    # Round-trip the schema entry through json so we know it's
    # serialisable (the OpenAI client demands JSON-clean dicts).
    entry = next(
        s for s in chat_mod.TOOL_SCHEMA
        if s["function"]["name"] == "join_datasets"
    )
    json.dumps(entry)
