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


# ---------------------------------------------------------------------------
# Task #254 — fan-out guard for unexpectedly huge N:N joins
# ---------------------------------------------------------------------------

def _fanout_pair(client, project, upload_dataset, headers_user_pid=None):
    """Build a left/right pair that fans out to a much larger result.
    Each side has 100 rows but every row shares the same value on the
    join key (``country = 'US'``), so an inner join on ``country``
    produces 100×100 = 10,000 rows — well over both the 5× ratio guard
    and the 1,000-row floor used in ``_is_large_join``."""
    if headers_user_pid is None:
        u, pid = project("join-fanout")
    else:
        u, pid = headers_user_pid
    left_csv = pd.DataFrame({
        "id": list(range(100)),
        "country": ["US"] * 100,
        "amount": list(range(100)),
    }).to_csv(index=False).encode()
    right_csv = pd.DataFrame({
        "ref_id": list(range(100)),
        "country": ["US"] * 100,
        "tax": [0.1 * i for i in range(100)],
    }).to_csv(index=False).encode()
    left = upload_dataset(u["headers"], pid, "wide_left", left_csv)
    right = upload_dataset(u["headers"], pid, "wide_right", right_csv)
    return u, pid, left, right


def test_join_preview_surfaces_cardinality_and_large_join_flag(
    client, project, upload_dataset,
):
    """Preview always succeeds, but the summary now includes the
    ``cardinality`` (N:N here, since both sides have duplicate
    countries) and a ``large_join`` boolean the UI keys off of."""
    u, _pid, left, right = _fanout_pair(client, project, upload_dataset)
    r = _post_join(client, u["headers"], {
        "left_dataset_id": left,
        "right_dataset_id": right,
        "join_key": "country",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["cardinality"] == "N:N"
    assert s["large_join"] is True
    # Sanity: the projection really is 100 × 100.
    assert s["result_rows"] == 10_000


def test_join_save_refused_on_unexpected_fanout_without_confirm(
    client, project, upload_dataset,
):
    """Without ``confirm_large_join: true`` the persist call must fail
    fast with a 400 — this is the actual footgun the task is
    preventing (a non-key join silently writing a multi-MB parquet
    blob into the database)."""
    u, _pid, left, right = _fanout_pair(client, project, upload_dataset)
    r = _post_join(client, u["headers"], {
        "left_dataset_id": left,
        "right_dataset_id": right,
        "join_key": "country",
        "join_type": "inner",
        "preview_only": False,
        "result_name": "should_not_persist",
    })
    assert r.status_code == 400, r.text
    assert "confirm_large_join" in r.text


def test_join_save_succeeds_with_confirm_large_join(
    client, project, upload_dataset,
):
    """When the caller acknowledges the fan-out, the save goes through
    and the resulting dataset is persisted exactly like any other
    join result."""
    u, pid, left, right = _fanout_pair(client, project, upload_dataset)
    r = _post_join(client, u["headers"], {
        "left_dataset_id": left,
        "right_dataset_id": right,
        "join_key": "country",
        "join_type": "inner",
        "preview_only": False,
        "result_name": "fanout_confirmed",
        "confirm_large_join": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview_only"] is False
    assert body["dataset_name"] == "fanout_confirmed"
    assert body["rows"] == 10_000
    assert body["summary"]["cardinality"] == "N:N"
    assert body["summary"]["large_join"] is True
    assert body["project_id"] == pid


def test_join_small_one_to_one_does_not_trigger_large_join(client, joined_pair):
    """A normal 1:N join on a real key (orders.customer_id ↔
    customers.customer_id, 50 rows) must NOT be flagged — the row
    floor in ``_is_large_join`` exists precisely to keep small
    everyday joins quiet."""
    u, _pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "inner",
        "preview_only": True,
    })
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["large_join"] is False
    # orders.customer_id has duplicates, customers.customer_id is unique → N:1.
    assert s["cardinality"] == "N:1"


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


# ---------------------------------------------------------------------------
# Task #252 — POST /api/datasets/join/suggest
# ---------------------------------------------------------------------------

def test_join_suggest_ranks_real_value_overlap_above_name_match(
    client, project, upload_dataset,
):
    """A column whose name matches but whose values don't must NOT
    out-rank a column whose values genuinely overlap. This is the
    headline behaviour the task adds: pre-Task #252 the picker would
    have grabbed ``id`` because the name matched on both sides; post-
    Task #252 it has to pick ``customer_id`` because the values overlap.
    """
    u, pid = project("join-suggest-overlap")
    left = pd.DataFrame({
        "id": [9001, 9002, 9003, 9004, 9005],
        "customer_id": [1, 2, 3, 4, 5],
        "amount": [10, 20, 30, 40, 50],
    }).to_csv(index=False).encode()
    right = pd.DataFrame({
        # Same name "id" but completely disjoint values from left.id.
        "id": [50_001, 50_002, 50_003, 50_004, 50_005],
        "customer_id": [1, 2, 3, 4, 5],
        "name": ["Ada", "Linus", "Grace", "Hopper", "Turing"],
    }).to_csv(index=False).encode()
    da = upload_dataset(u["headers"], pid, "left_t", left)
    dr = upload_dataset(u["headers"], pid, "right_t", right)
    r = client.post(
        "/api/datasets/join/suggest",
        json={"left_dataset_id": da, "right_dataset_id": dr},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["left_dataset_id"] == da
    assert body["right_dataset_id"] == dr
    suggestions = body["suggestions"]
    assert len(suggestions) >= 1
    top = suggestions[0]
    assert top["left_column"] == "customer_id"
    assert top["right_column"] == "customer_id"
    # Real-value overlap is the dominant signal — the top hit should
    # have a perfect Jaccard since both sides cover {1..5}.
    assert top["overlap_score"] == 1.0
    # And it should beat the same-named "id" column-pair, which has
    # zero overlap. The "id" pair may still surface because
    # name+dtype clear the threshold, but it must rank below.
    id_pair = next(
        (s for s in suggestions
         if s["left_column"] == "id" and s["right_column"] == "id"),
        None,
    )
    if id_pair is not None:
        assert id_pair["overlap_score"] == 0.0
        assert top["confidence"] > id_pair["confidence"]


def test_join_suggest_returns_empty_for_unrelated_datasets(
    client, project, upload_dataset,
):
    """Two datasets with no name match AND no value overlap should
    return an empty list — the frontend then falls back to the manual
    column picker."""
    u, pid = project("join-suggest-empty")
    a = pd.DataFrame({
        "alpha": ["foo", "bar", "baz"],
        "beta": [1, 2, 3],
    }).to_csv(index=False).encode()
    b = pd.DataFrame({
        "gamma": ["qux", "quux", "quuux"],
        "delta": [100.5, 200.5, 300.5],
    }).to_csv(index=False).encode()
    da = upload_dataset(u["headers"], pid, "alpha_t", a)
    dr = upload_dataset(u["headers"], pid, "gamma_t", b)
    r = client.post(
        "/api/datasets/join/suggest",
        json={"left_dataset_id": da, "right_dataset_id": dr},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json()["suggestions"] == []


def test_join_suggest_cross_user_isolation_returns_404(
    client, register, project, upload_dataset, customers_csv, orders_csv,
):
    a, pid_a = project("ua-suggest", user=register("alice2"))
    cust = upload_dataset(a["headers"], pid_a, "customers", customers_csv)
    ords = upload_dataset(a["headers"], pid_a, "orders", orders_csv)
    b, _pid_b = project("ub-suggest", user=register("bob2"))
    r = client.post(
        "/api/datasets/join/suggest",
        json={"left_dataset_id": ords, "right_dataset_id": cust},
        headers=b["headers"],
    )
    assert r.status_code == 404, r.text


def test_join_suggest_finds_differently_named_fk_pair(
    client, project, upload_dataset,
):
    """The classic FK case: ``customer_id`` on one side, ``id`` on
    the other, with overlapping values. The endpoint must surface the
    pair so the frontend can pre-fill the expert overrides."""
    u, pid = project("join-suggest-fk")
    customers = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "name": ["a", "b", "c", "d", "e"],
    }).to_csv(index=False).encode()
    orders = pd.DataFrame({
        "order_id": [10, 11, 12, 13],
        "customer_id": [1, 1, 3, 5],
        "amount": [10, 20, 30, 40],
    }).to_csv(index=False).encode()
    dc = upload_dataset(u["headers"], pid, "customers_x", customers)
    do = upload_dataset(u["headers"], pid, "orders_x", orders)
    r = client.post(
        "/api/datasets/join/suggest",
        json={"left_dataset_id": do, "right_dataset_id": dc},
        headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    suggestions = r.json()["suggestions"]
    assert len(suggestions) >= 1
    # The (customer_id, id) pair should be among the suggestions with
    # non-zero overlap.
    fk_pair = next(
        (s for s in suggestions
         if s["left_column"] == "customer_id" and s["right_column"] == "id"),
        None,
    )
    assert fk_pair is not None, suggestions
    assert fk_pair["overlap_score"] > 0


# ---------------------------------------------------------------------------
# Task #253 — join provenance + DELETE /api/datasets/{id} (Undo)
# ---------------------------------------------------------------------------

def test_join_save_records_provenance_on_parse_meta(client, joined_pair):
    """Saved joins must stamp ``join_provenance`` (left + right ids,
    keys, type, frozen names) on the new dataset's ``parse_meta`` so
    the Files page can render the badge and the Join page can offer
    one-click Undo without an extra round-trip."""
    u, _pid, cust, ords = joined_pair
    r = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "left",
        "preview_only": False,
        "result_name": "orders_left_customers",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    new_id = body["dataset_id"]
    # Save response surfaces the provenance inline.
    prov = body["join_provenance"]
    assert prov["left_dataset_id"] == ords
    assert prov["right_dataset_id"] == cust
    assert prov["left_key"] == "customer_id"
    assert prov["right_key"] == "customer_id"
    assert prov["join_type"] == "left"
    assert prov["left_dataset_name"] == "orders"
    assert prov["right_dataset_name"] == "customers"
    # GET single + list both echo the same provenance back.
    fetched = client.get(
        f"/api/datasets/{new_id}", headers=u["headers"],
    ).json()
    assert fetched["join_provenance"]["join_type"] == "left"
    assert fetched["join_provenance"]["left_dataset_id"] == ords
    rows = client.get("/api/datasets", headers=u["headers"]).json()
    derived = next(d for d in rows if d["id"] == new_id)
    assert derived["join_provenance"]["right_dataset_name"] == "customers"
    # Vanilla uploads still get a null provenance, not an empty dict.
    parent = next(d for d in rows if d["id"] == cust)
    assert parent["join_provenance"] is None


def test_join_undo_deletes_saved_dataset(client, joined_pair):
    u, _pid, cust, ords = joined_pair
    save = _post_join(client, u["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "join_type": "inner",
        "preview_only": False,
        "result_name": "to_be_undone",
    }).json()
    new_id = save["dataset_id"]
    r = client.delete(
        f"/api/datasets/{new_id}", headers=u["headers"],
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": True, "dataset_id": new_id}
    # Subsequent GET should now 404 — the dataset is gone, parents stay.
    assert client.get(
        f"/api/datasets/{new_id}", headers=u["headers"],
    ).status_code == 404
    rows = client.get("/api/datasets", headers=u["headers"]).json()
    ids = {d["id"] for d in rows}
    assert new_id not in ids
    assert cust in ids and ords in ids


def test_join_undo_cross_user_isolation(
    client, register, project, upload_dataset, customers_csv, orders_csv,
):
    """User B must not be able to delete user A's saved join."""
    a, pid_a = project("ua-undo", user=register("alice2"))
    cust = upload_dataset(a["headers"], pid_a, "customers", customers_csv)
    ords = upload_dataset(a["headers"], pid_a, "orders", orders_csv)
    save = _post_join(client, a["headers"], {
        "left_dataset_id": ords,
        "right_dataset_id": cust,
        "join_key": "customer_id",
        "preview_only": False,
    }).json()
    new_id = save["dataset_id"]
    b, _pid_b = project("ub-undo", user=register("bob2"))
    r = client.delete(
        f"/api/datasets/{new_id}", headers=b["headers"],
    )
    assert r.status_code == 404, r.text
    # Owner can still see + delete it themselves.
    assert client.get(
        f"/api/datasets/{new_id}", headers=a["headers"],
    ).status_code == 200


def test_join_chat_tool_save_records_provenance(
    client, register, project, upload_dataset, chat_session,
    customers_csv, orders_csv, stub_openai,
):
    """The chat-tool save branch must stamp the same provenance the
    HTTP save branch does, so chat-driven joins are also undoable."""
    from backend import chat as chat_mod
    from backend.auth import get_db_session
    u, pid = project("chat-join-prov")
    cust = upload_dataset(u["headers"], pid, "customers", customers_csv)
    ords = upload_dataset(u["headers"], pid, "orders", orders_csv)
    sid = chat_session(u["headers"], pid)
    ctx = {"user_id": u["user"]["id"], "project_id": pid, "session_id": sid}
    db = next(get_db_session())
    try:
        summary, _ = chat_mod._run_join_datasets(
            db,
            {
                "left_dataset_id": ords,
                "right_dataset_id": cust,
                "join_key": "customer_id",
                "join_type": "inner",
                "preview_only": False,
                "result_name": "chat_undoable",
            },
            ctx,
        )
    finally:
        db.close()
    new_id = summary["dataset_id"]
    fetched = client.get(
        f"/api/datasets/{new_id}", headers=u["headers"],
    ).json()
    prov = fetched["join_provenance"]
    assert prov is not None
    assert prov["left_dataset_id"] == ords
    assert prov["right_dataset_id"] == cust
    assert prov["join_type"] == "inner"


def test_delete_unknown_dataset_returns_404(client, register):
    u = register("solo-deleter")
    r = client.delete("/api/datasets/9999999", headers=u["headers"])
    assert r.status_code == 404


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
