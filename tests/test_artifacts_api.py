"""Backend smoke tests for the conversational EDA endpoints.

Exercises the live FastAPI app via TestClient (no mocks):
  - registration / login
  - project + dataset upload
  - GET preview / profile / insights / suggestions
  - POST auto-profile (combined endpoint)
  - chat session + chat artifact pin/delete
  - GET /api/chats/{sid}/report (JSON synthesis + what-if payload)
  - POST /api/chats/{sid}/report.pdf (binary)
  - cross-user 404 isolation on every dataset/chat endpoint above
"""
from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app
import models


client = TestClient(app)


def _unique_email(tag: str) -> str:
    return f"smoke+{tag}+{int(time.time() * 1000)}@axiom.test"


def _register() -> dict:
    email = _unique_email("u")
    body = {
        "email": email,
        "username": email.split("@")[0],
        "password": "Pass1234!",
        "full_name": "Smoke User",
    }
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_csv() -> bytes:
    rng = np.random.default_rng(11)
    n = 80
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(10, 2, size=n).round(3),
            "feature_b": rng.normal(50, 10, size=n).round(3),
            "feature_c": rng.normal(0, 1, size=n).round(3),
        }
    )
    df["target"] = (
        2 * df["feature_a"] + 0.5 * df["feature_b"] - df["feature_c"]
        + rng.normal(0, 0.3, size=n)
    ).round(3)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _create_project(headers: dict[str, str], name: str) -> int:
    r = client.post("/api/projects", json={"name": name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _upload_dataset(headers: dict[str, str], project_id: int) -> int:
    files = {"file": ("smoke.csv", _make_csv(), "text/csv")}
    data = {"project_id": str(project_id), "dataset_name": "smoke"}
    r = client.post("/api/datasets/upload", files=files, data=data, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _new_chat(headers: dict[str, str], project_id: int) -> int:
    r = client.post(
        f"/api/projects/{project_id}/chats",
        json={"title": "smoke chat"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------


def test_dataset_endpoints_happy_path_and_cross_user_isolation():
    a = _register()
    b = _register()
    ah, bh = _auth(a["token"]), _auth(b["token"])

    pid = _create_project(ah, "smoke-a")
    did = _upload_dataset(ah, pid)

    # Owner can see all four GETs.
    for path in (
        f"/api/datasets/{did}/preview?rows=5",
        f"/api/datasets/{did}/profile",
        f"/api/datasets/{did}/insights",
        f"/api/datasets/{did}/suggestions",
    ):
        r = client.get(path, headers=ah)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text}"

    # Owner POST auto-profile combined endpoint returns the union.
    r = client.post(
        f"/api/datasets/{did}/auto-profile?rows=5", headers=ah
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == did
    assert body["rows"] == 80
    assert "preview" in body and len(body["preview"]) == 5
    assert "profile" in body and body["profile"]["rows"] == 80
    assert "insights" in body and isinstance(body["insights"], list)
    assert "suggestions" in body and len(body["suggestions"]) > 0
    # Default lang ("en") => suggestions are pure English (no Arabic chars).
    for q in body["suggestions"]:
        assert not any("\u0600" <= ch <= "\u06FF" for ch in q), f"EN suggestion leaked Arabic: {q}"

    # lang=ar returns Levantine Arabic suggestions (contains Arabic chars).
    r_ar = client.post(
        f"/api/datasets/{did}/auto-profile?rows=5&lang=ar", headers=ah
    )
    assert r_ar.status_code == 200, r_ar.text
    ar_body = r_ar.json()
    assert any(
        any("\u0600" <= ch <= "\u06FF" for ch in q)
        for q in ar_body["suggestions"]
    ), f"Arabic suggestions missing Arabic chars: {ar_body['suggestions']}"

    # Same contract on the dedicated /suggestions GET.
    r_sug_ar = client.get(
        f"/api/datasets/{did}/suggestions?lang=ar", headers=ah
    )
    assert r_sug_ar.status_code == 200
    assert any(
        any("\u0600" <= ch <= "\u06FF" for ch in q)
        for q in r_sug_ar.json()["suggestions"]
    )

    # Cross-user 404 on every dataset endpoint.
    for path, method in [
        (f"/api/datasets/{did}/preview", "get"),
        (f"/api/datasets/{did}/profile", "get"),
        (f"/api/datasets/{did}/insights", "get"),
        (f"/api/datasets/{did}/suggestions", "get"),
        (f"/api/datasets/{did}/auto-profile", "post"),
    ]:
        r = client.request(method, path, headers=bh)
        assert r.status_code == 404, f"{method} {path} leaked to other user: {r.status_code}"


def test_chat_artifact_pin_delete_and_report_pdf_isolation():
    a = _register()
    b = _register()
    ah, bh = _auth(a["token"]), _auth(b["token"])

    pid = _create_project(ah, "smoke-report")
    did = _upload_dataset(ah, pid)
    sid = _new_chat(ah, pid)

    # Drop a synthesis-eligible artifact in directly via the model helper
    # so we don't have to wait for the LLM tool stream.
    db = models.SessionLocal()
    try:
        models.save_chat_artifact(
            db,
            session_id=sid,
            user_id=a["user"]["id"],
            project_id=pid,
            dataset_id=did,
            kind="profile",
            title="Profile",
            params={},
            result={"rows": 80, "cols": 4, "columns": []},
            pinned=True,
        )
        chart = models.save_chat_artifact(
            db,
            session_id=sid,
            user_id=a["user"]["id"],
            project_id=pid,
            dataset_id=did,
            kind="chart",
            title="Bar of a vs b",
            params={"chart_type": "bar"},
            result={"chart_type": "bar", "x": ["a", "b"], "y": [1, 2]},
            pinned=False,  # default False per the new pinning policy
        )
    finally:
        db.close()

    # Owner can flip the pin.
    r = client.patch(
        f"/api/artifacts/{chart.id}/pin",
        json={"pinned": True},
        headers=ah,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pinned"] is True

    # Other user cannot — should 404.
    r = client.patch(
        f"/api/artifacts/{chart.id}/pin",
        json={"pinned": False},
        headers=bh,
    )
    assert r.status_code == 404

    # Report JSON returns synthesis + what_if keys (what_if may be empty
    # without prediction artifacts; the field must still exist).
    r = client.get(
        f"/api/chats/{sid}/report?pinned_only=true", headers=ah
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "synthesis" in body
    assert "what_if" in body
    # The pinned chart should be visible.
    assert any(c.get("id") == chart.id for c in body.get("artifacts", {}).get("chart", []))

    # PDF endpoint returns a non-empty PDF for the owner.
    r = client.post(
        f"/api/chats/{sid}/report.pdf?pinned_only=true", headers=ah
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert len(r.content) > 1000

    # Cross-user 404 on report endpoints.
    for method, path in [
        ("get", f"/api/chats/{sid}/report"),
        ("post", f"/api/chats/{sid}/report.pdf"),
    ]:
        r = client.request(method, path, headers=bh)
        assert r.status_code == 404, f"{method} {path} leaked: {r.status_code}"

    # Owner can delete the chart artifact; second user cannot.
    r = client.delete(f"/api/artifacts/{chart.id}", headers=bh)
    assert r.status_code == 404
    r = client.delete(f"/api/artifacts/{chart.id}", headers=ah)
    assert r.status_code == 200


def test_seed_profile_endpoint_pins_profile_artifact():
    """`POST /api/chats/{sid}/seed-profile` must run `_run_profile`
    deterministically (no LLM) and persist the profile artifact in the
    target session so the workspace can show it the moment a CSV lands.
    Verifies cross-user isolation as well."""
    a = _register()
    b = _register()
    ah, bh = _auth(a["token"]), _auth(b["token"])
    pid = _create_project(ah, "seed proj")
    did = _upload_dataset(ah, pid)
    sid = _new_chat(ah, pid)

    r = client.post(
        f"/api/chats/{sid}/seed-profile?dataset_id={did}", headers=ah
    )
    assert r.status_code == 200, r.text
    body = r.json()
    arts = body["artifacts"]
    assert any(a_["kind"] == "profile" for a_ in arts), arts
    profile = next(a_ for a_ in arts if a_["kind"] == "profile")
    assert profile["pinned"] is True  # profile auto-pins per spec
    assert profile["dataset_id"] == did

    # The artifact must show up on the session's artifact list.
    r = client.get(f"/api/chats/{sid}/artifacts", headers=ah)
    assert r.status_code == 200
    listing = r.json()
    assert any(x["id"] == profile["id"] for x in listing)

    # Cross-user 404: user B cannot seed against A's session/dataset.
    r = client.post(
        f"/api/chats/{sid}/seed-profile?dataset_id={did}", headers=bh
    )
    assert r.status_code == 404


def test_chat_tool_handlers_dispatched_directly():
    """Exercise the four tool handlers via `_TOOL_HANDLERS` exactly the
    way the streaming chat dispatcher does (no LLM, no HTTP). This is
    the single source of truth that profile auto-pins while chart /
    prediction / cluster default to unpinned, that the artifacts land
    in the correct session, and that the dispatcher-friendly
    `(summary, [view])` tuple is returned."""
    from backend import chat as chat_mod
    from models import SessionLocal

    a = _register()
    ah = _auth(a["token"])
    pid = _create_project(ah, "tools proj")
    did = _upload_dataset(ah, pid)
    sid = _new_chat(ah, pid)
    user_id = a["user"]["id"]
    ctx = {"user_id": user_id, "project_id": pid, "session_id": sid}

    db = SessionLocal()
    try:
        # 1. profile_dataset → emits one PROFILE (pinned) artifact at minimum.
        handler = chat_mod._TOOL_HANDLERS["profile_dataset"]
        summary, views = handler(db, {"dataset_id": did}, ctx)
        assert isinstance(summary, dict) and isinstance(views, list)
        profile_views = [v for v in views if v["kind"] == "profile"]
        assert profile_views, views
        assert profile_views[0]["pinned"] is True

        # 2. make_chart → bar chart of feature_a, must NOT auto-pin.
        handler = chat_mod._TOOL_HANDLERS["make_chart"]
        summary, views = handler(
            db,
            {"dataset_id": did, "chart": "histogram", "x": "feature_a"},
            ctx,
        )
        assert views and views[0]["kind"] == "chart"
        assert views[0]["pinned"] is False, "charts must default to unpinned"

        # 3. predict_column → linear regression of target, NOT auto-pin.
        handler = chat_mod._TOOL_HANDLERS["predict_column"]
        summary, views = handler(
            db, {"dataset_id": did, "target": "target"}, ctx
        )
        assert views and views[0]["kind"] == "prediction"
        assert views[0]["pinned"] is False
        result = views[0]["result"]
        # The handler emits a metrics block and feature importances
        # (the importances feed the InteractiveTable in the report).
        assert "metrics" in result
        assert "r2" in result["metrics"] and "mae" in result["metrics"]
        assert "feature_importance" in result
        assert "baseline_prediction" in result  # what-if needs this

        # 4. cluster_dataset → k=3 KMeans, NOT auto-pin.
        handler = chat_mod._TOOL_HANDLERS["cluster_dataset"]
        summary, views = handler(db, {"dataset_id": did, "k": 3}, ctx)
        assert views and views[0]["kind"] == "cluster"
        assert views[0]["pinned"] is False
        assert int(views[0]["result"]["k"]) == 3

        # End-to-end: the four artifacts must all be readable through the
        # session's HTTP listing and only the profile is pinned.
        r = client.get(f"/api/chats/{sid}/artifacts", headers=ah)
        assert r.status_code == 200
        items = r.json()
        kinds = {x["kind"] for x in items}
        assert {"profile", "chart", "prediction", "cluster"}.issubset(kinds)
        pinned_kinds = {x["kind"] for x in items if x["pinned"]}
        assert "profile" in pinned_kinds
        assert "chart" not in pinned_kinds
        assert "prediction" not in pinned_kinds
        assert "cluster" not in pinned_kinds
    finally:
        db.close()
