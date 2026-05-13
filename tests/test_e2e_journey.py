"""Section 7: end-to-end user-journey smoke test.

Walks the full happy path a real user would take through AXIOM, using
the public HTTP surface end-to-end. The chat tool dispatcher is
exercised via the real ``POST /api/chat/stream`` endpoint with a
stubbed OpenAI client so no live LLM call leaves the process.

Documented 10-step journey:

   1. Register a new account.
   2. Create a project.
   3. Attach two related CSVs (customers + orders) plus a time-series
      dataset to the project (datasets are attached at upload time
      via the documented ``project_id`` form field).
   4. Refresh the project's data model.
   5. Inspect the data model and confirm the proposed customer_id
      relationship via PATCH /api/projects/<pid>/data-model/relationships/<rid>.
   6. Open a chat session inside the project.
   7. Seed the data-model artifact into the chat (so the report has
      a ``data_model`` artifact later).
   8. Drive a chat ``predict_column`` tool call through the real
      ``POST /api/chat/stream`` endpoint — this is the documented
      tool path the frontend uses, so we exercise it end-to-end.
   9. Verify both the prediction *and* the data-model artifacts are
      now visible on the session.
  10. Generate the final session report via
      ``POST /api/chats/<sid>/report.pdf`` and assert it includes both
      artifact kinds and that the resulting PDF is non-trivial.
"""
from __future__ import annotations

import json


def _is_json(response) -> bool:
    ctype = response.headers.get("content-type", "")
    if "application/json" not in ctype:
        return False
    try:
        json.loads(response.content.decode() or "null")
        return True
    except Exception:
        return False


def _read_ndjson(resp) -> list[dict]:
    """Decode an x-ndjson StreamingResponse body into events."""
    out: list[dict] = []
    for line in (resp.text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def test_full_user_journey(client, register, customers_csv, orders_csv,
                            timeseries_sales_csv, driver_regression_csv,
                            stub_openai):
    journey: list[str] = []

    # ── Step 1: register ────────────────────────────────────────────
    user = register("e2e")
    headers = user["headers"]
    journey.append("1: register")

    # ── Step 2: create project ──────────────────────────────────────
    r = client.post("/api/projects", json={"name": "E2E Journey"},
                    headers=headers)
    assert r.status_code == 200 and _is_json(r), r.text
    project_id = r.json()["id"]
    journey.append(f"2: project={project_id}")

    # ── Step 3: attach datasets to the project (upload with the
    #            documented ``project_id`` form field) ──────────────
    def _attach(name: str, blob: bytes) -> int:
        files = {"file": (f"{name}.csv", blob, "text/csv")}
        r = client.post(
            "/api/datasets/upload",
            files=files,
            data={"dataset_name": name, "project_id": str(project_id)},
            headers=headers,
        )
        assert r.status_code == 200, f"attach {name}: {r.text}"
        body = r.json()
        # ``project_id`` is not always echoed back on upload — some
        # responses (and chat /quick paths) omit it. Verify the attach
        # landed by re-reading the dataset detail endpoint instead.
        ds_id = int(body["id"])
        rr = client.get(f"/api/datasets/{ds_id}", headers=headers)
        assert rr.status_code == 200, rr.text
        bound_pid = int((rr.json() or {}).get("project_id") or 0)
        assert bound_pid == project_id, (
            f"dataset {ds_id} not attached to project {project_id}: "
            f"detail.project_id={bound_pid}"
        )
        return ds_id

    customers_id = _attach("customers", customers_csv)
    orders_id = _attach("orders", orders_csv)
    sales_id = _attach("sales_ts", timeseries_sales_csv)
    drivers_id = _attach("drivers", driver_regression_csv)
    journey.append(
        f"3: datasets attached="
        f"{[customers_id, orders_id, sales_id, drivers_id]}"
    )

    # And verify the project listing shows all three attached.
    r = client.get("/api/datasets", headers=headers, params={"project_id": project_id})
    assert r.status_code == 200 and _is_json(r), r.text
    body = r.json()
    listed = body["datasets"] if isinstance(body, dict) else body
    listed_ids = {int(d["id"]) for d in listed}
    assert {customers_id, orders_id, sales_id, drivers_id}.issubset(
        listed_ids
    ), listed_ids

    # ── Step 4: refresh data model ──────────────────────────────────
    r = client.post(
        f"/api/projects/{project_id}/data-model/refresh",
        json={},
        headers=headers,
    )
    assert r.status_code == 200 and _is_json(r), r.text
    journey.append("4: data-model refreshed")

    # ── Step 5: inspect + confirm a relationship ────────────────────
    r = client.get(f"/api/projects/{project_id}/data-model", headers=headers)
    assert r.status_code == 200 and _is_json(r), r.text
    data_model = r.json()
    relationships = (
        data_model.get("relationships")
        or data_model.get("model", {}).get("relationships")
        or []
    )
    assert relationships, f"no relationships proposed: {data_model}"
    proposed = [
        rel for rel in relationships
        if (rel.get("status") in (None, "proposed", "suggested"))
    ] or relationships
    target = proposed[0]
    rid = target.get("id")
    assert rid is not None, f"relationship missing id: {target}"
    r = client.patch(
        f"/api/projects/{project_id}/data-model/relationships/{rid}",
        json={"status": "confirmed"},
        headers=headers,
    )
    assert r.status_code == 200 and _is_json(r), r.text
    confirmed_bundle = r.json()
    assert any(
        rel.get("id") == rid and rel.get("status") == "confirmed"
        for rel in confirmed_bundle.get("relationships", [])
    ), confirmed_bundle
    journey.append(f"5: relationship {rid} → confirmed")

    # ── Step 6: open a chat session ─────────────────────────────────
    r = client.post(
        f"/api/projects/{project_id}/chats",
        json={"title": "E2E chat"},
        headers=headers,
    )
    assert r.status_code == 200 and _is_json(r), r.text
    session_id = r.json()["id"]
    journey.append(f"6: chat={session_id}")

    # ── Step 7: seed data-model artifact ────────────────────────────
    # This is what gives the final report a ``data_model`` artifact
    # to render alongside the prediction.
    r = client.post(
        f"/api/chats/{session_id}/seed-data-model",
        headers=headers,
    )
    assert r.status_code == 200 and _is_json(r), r.text
    seed_payload = r.json()
    assert isinstance(seed_payload.get("artifacts"), list)
    assert len(seed_payload["artifacts"]) >= 1, seed_payload
    journey.append("7: data-model artifact seeded")

    # ── Step 8: drive the documented cross-table ``query_model`` tool
    #            through POST /api/chat/stream. This is the multi-table
    #            join path the chat uses to answer "sum of order
    #            amounts by customer country" — exactly the case the
    #            semantic model + relationship inference are built for.
    stub_openai.script([
        {
            "text": "Joining customers + orders to sum amount by country.",
            "tool_calls": [
                {
                    "id": "call_query_e2e",
                    "name": "query_model",
                    "arguments": {
                        "tables": ["orders", "customers"],
                        "metrics": [
                            {"table": "orders", "column": "amount",
                             "agg": "sum", "alias": "total_amount"},
                        ],
                        "group_by": [
                            {"table": "customers", "column": "country"},
                        ],
                    },
                },
            ],
        },
        "Here are the totals by country.",
    ])
    chat_body = {
        "session_id": session_id,
        "project_id": project_id,
        "messages": [
            {"role": "user",
             "content": "Sum order amount by customer country."},
        ],
    }
    r = client.post("/api/chat/stream", json=chat_body, headers=headers)
    assert r.status_code == 200, r.text
    events = _read_ndjson(r)
    finished = [e for e in events if e.get("type") == "tool_finished"]
    assert finished, events
    qm_evt = next(
        (e for e in finished if (e.get("tool") or "") == "query_model"),
        finished[0],
    )
    assert qm_evt.get("ok") is True, f"query_model failed: {qm_evt}"
    # The chat event uses ``summary`` (not ``result``) to carry the
    # tool's structured output — that's what the React ChatPanel reads.
    # The summary documented contract is:
    #   {row_count, columns, warnings, refusals, join_path,
    #    uses_inferred_join, inferred_joins, preview, sql_like}
    qm_summary = qm_evt.get("summary") or {}
    qm_refusals = qm_summary.get("refusals") or []
    qm_row_count = int(qm_summary.get("row_count") or 0)
    qm_preview = qm_summary.get("preview") or []
    qm_join_path = qm_summary.get("join_path") or []
    assert not qm_refusals, (
        f"cross-table query_model returned refusals on a clean two-"
        f"table join: {qm_refusals}"
    )
    assert qm_row_count > 0, (
        f"cross-table query_model returned zero rows; summary={qm_summary}"
    )
    assert qm_preview, (
        f"cross-table query_model returned no preview rows; "
        f"summary={qm_summary}"
    )
    # The grouping column must appear on every preview row.
    assert all("country" in row for row in qm_preview), qm_preview
    # And the join must have actually traversed both tables.
    assert qm_join_path, (
        f"cross-table query_model returned no join_path; "
        f"summary={qm_summary}"
    )
    journey.append(
        f"8: chat query_model joined customers↔orders → "
        f"{qm_row_count} rows via {len(qm_join_path)} relationship(s)"
    )

    # ── Step 9: drive the documented chat predict_column tool through
    #            POST /api/chat/stream — same code path the React
    #            ChatPanel uses. The drivers dataset has multiple
    #            numeric columns so the multi-feature regression tool
    #            can fit cleanly.
    stub_openai.script([
        {
            "text": "Sure — I'll model sales from marketing_spend and units.",
            "tool_calls": [
                {"id": "call_predict_e2e", "name": "predict_column",
                 "arguments": {"dataset_id": drivers_id,
                                "target": "sales"}},
            ],
        },
        "All done — your prediction is ready.",
    ])
    chat_body = {
        "session_id": session_id,
        "project_id": project_id,
        "messages": [
            {"role": "user", "content": "Predict sales from the drivers dataset."},
        ],
    }
    r = client.post("/api/chat/stream", json=chat_body, headers=headers)
    assert r.status_code == 200, r.text
    events = _read_ndjson(r)
    types = [e.get("type") for e in events]
    assert "tool_started" in types, types
    finished = [e for e in events if e.get("type") == "tool_finished"]
    assert finished, events
    # The dispatcher must have run predict_column without error and
    # attached at least one artifact in the tool_finished event.
    assert finished[0].get("ok") is True, finished
    assert finished[0].get("artifacts"), finished

    # Verify that BOTH the prediction and the data-model artifacts are
    # now visible on the session — the report endpoint relies on this.
    r = client.get(f"/api/chats/{session_id}/artifacts", headers=headers)
    assert r.status_code == 200 and _is_json(r), r.text
    artifact_payload = r.json()
    artifacts = (
        artifact_payload.get("artifacts")
        if isinstance(artifact_payload, dict)
        else artifact_payload
    )
    kinds = {(a.get("kind") or "").lower() for a in artifacts}
    assert any(k in kinds for k in ("prediction", "predict_column")), kinds
    assert any("data_model" in k for k in kinds), kinds
    journey.append(
        f"9: chat predict_column executed; artifact kinds={sorted(kinds)}"
    )

    # ── Step 10: final session report (JSON view + PDF download) ───
    r = client.get(
        f"/api/chats/{session_id}/report",
        headers=headers,
        params={"pinned_only": "false"},
    )
    assert r.status_code == 200 and _is_json(r), r.text
    report = r.json()
    by_kind = report.get("artifacts") or {}
    # The report MUST surface both a prediction artifact and a
    # data-model artifact — that's the whole point of the report
    # bundling chat artifacts together for the final hand-off.
    pred_arts = by_kind.get("prediction") or []
    dm_arts = (
        by_kind.get("data_model")
        or by_kind.get("data-model")
        or []
    )
    assert pred_arts, f"report missing prediction artifact: {list(by_kind)}"
    assert dm_arts, f"report missing data-model artifact: {list(by_kind)}"

    r = client.post(
        f"/api/chats/{session_id}/report.pdf",
        headers=headers,
        params={"pinned_only": "false"},
    )
    assert r.status_code == 200, r.text
    assert (
        r.headers.get("content-type", "").startswith("application/pdf")
        or r.content[:4] == b"%PDF"
    ), "report endpoint did not return a PDF"
    assert len(r.content) > 1024, (
        f"PDF report body suspiciously small: {len(r.content)} bytes"
    )
    journey.append("10: session report.pdf generated")

    # Final smoke sanity — every documented step should have a marker.
    assert len(journey) == 10, f"journey markers: {journey}"
