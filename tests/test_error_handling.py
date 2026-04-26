"""Section 5: error-handling guarantees.

Every API endpoint must return JSON (never plain text or HTML) for
all of: 400 (bad request), 401 (unauthenticated), 404 (not found),
422 (pydantic validation), and 500 (uncaught error). FastAPI's
default error envelope is ``{"detail": "..."}``; the project is
documented to wrap server errors in ``{"error": "...", "detail":
"..."}``. We exercise both shapes and surface a clear failure when
the documented envelope is missing.
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


# ---------------------------------------------------------------------------
# 401 — Unauthenticated requests on protected routes
# ---------------------------------------------------------------------------

def test_401_returns_json_on_protected_routes(client):
    """backend/auth.py:get_current_user always raises HTTPException(401)
    for both missing and invalid bearer credentials, so we assert the
    exact 401 status — no permissive 401/403 fallback."""
    for path in ("/api/projects", "/api/datasets", "/api/auth/me",
                 "/api/chats/recent"):
        r = client.get(path)
        assert r.status_code == 401, f"{path} → {r.status_code}"
        assert _is_json(r), f"{path} returned non-JSON 401 body"
        body = r.json()
        assert "detail" in body or "error" in body


def test_401_returns_json_for_invalid_jwt(client):
    """A *malformed* / *forged* bearer token must produce the same JSON
    401 envelope — backend/auth.py:69 raises 401 with detail
    "Invalid token: ...". No 403 fallback is acceptable here."""
    headers = {"Authorization": "Bearer this-is-not-a-real-jwt.deadbeef.xx"}
    for path in ("/api/projects", "/api/datasets", "/api/auth/me"):
        r = client.get(path, headers=headers)
        assert r.status_code == 401, f"{path} → {r.status_code}"
        assert _is_json(r), (
            f"{path} returned non-JSON body for invalid JWT: "
            f"content-type={r.headers.get('content-type')}"
        )
        body = r.json()
        assert "detail" in body or "error" in body


# ---------------------------------------------------------------------------
# 422 — Pydantic validation failures
# ---------------------------------------------------------------------------

def test_422_returns_json_envelope_on_invalid_register(client):
    r = client.post("/api/auth/register", json={"email": "not-an-email"})
    assert r.status_code == 422
    assert _is_json(r)
    body = r.json()
    assert "detail" in body or "error" in body


def test_422_returns_json_envelope_on_invalid_predict(client, register):
    u = register("err422")
    r = client.post(
        "/api/predict",
        json={"dataset_id": "not-an-int"},  # bad type
        headers=u["headers"],
    )
    assert r.status_code == 422
    assert _is_json(r)


# ---------------------------------------------------------------------------
# 404 — Resource not found
# ---------------------------------------------------------------------------

def test_404_returns_json_for_missing_dataset(client, register):
    u = register("err404")
    r = client.get("/api/datasets/9999999", headers=u["headers"])
    assert r.status_code == 404
    assert _is_json(r)
    body = r.json()
    assert "detail" in body or "error" in body


def test_404_returns_json_for_predict_on_missing_dataset(client, register):
    """Predicting against a dataset id the user does not own / does
    not exist must produce a JSON 404 (not a 500 stack trace).
    """
    u = register("err404pd")
    r = client.post(
        "/api/predict",
        json={"dataset_id": 9999999, "column": "anything"},
        headers=u["headers"],
    )
    # backend/analysis.py:33 raises HTTPException(404, "Dataset not
    # found") via the shared _require_dataset helper, so we assert the
    # exact 404 status — anything else (including a 400 fallback) would
    # mask a regression in the documented error surface.
    assert r.status_code == 404, (
        f"unexpected status for missing-dataset predict: {r.status_code}"
    )
    assert _is_json(r), (
        f"predict on missing dataset returned non-JSON body: "
        f"content-type={r.headers.get('content-type')}"
    )
    body = r.json()
    assert "detail" in body or "error" in body


def test_404_returns_json_for_missing_project(client, register):
    u = register("err404p")
    r = client.delete("/api/projects/9999999", headers=u["headers"])
    assert r.status_code == 404
    assert _is_json(r)


def test_404_returns_json_for_missing_chat(client, register):
    u = register("err404c")
    r = client.get("/api/chats/9999999/messages", headers=u["headers"])
    assert r.status_code == 404
    assert _is_json(r)


# ---------------------------------------------------------------------------
# 400 — Bad request (validated by application code, not pydantic)
# ---------------------------------------------------------------------------

def test_400_returns_json_for_predict_on_missing_column(
    client, project, upload_dataset, customers_csv,
):
    u, pid = project("err400")
    dsid = upload_dataset(u["headers"], pid, "customers", customers_csv)
    r = client.post(
        "/api/predict",
        json={"dataset_id": dsid, "column": "ghost-column"},
        headers=u["headers"],
    )
    assert r.status_code == 400
    assert _is_json(r)


def test_400_returns_json_for_unknown_model_method(
    client, project, upload_dataset, driver_regression_csv,
):
    u, pid = project("err400m")
    dsid = upload_dataset(u["headers"], pid, "drivers", driver_regression_csv)
    r = client.post(
        "/api/model",
        json={"dataset_id": dsid, "method": "no-such-method"},
        headers=u["headers"],
    )
    assert r.status_code == 400
    assert _is_json(r)


def test_400_returns_json_for_empty_csv_upload(client, register):
    """backend/datasets.py:62 raises HTTPException(400, "Empty upload")
    on a zero-byte body — assert exactly 400, not a permissive
    400-or-422 fallback."""
    u = register("err400u")
    files = {"file": ("empty.csv", b"", "text/csv")}
    r = client.post("/api/datasets/upload", files=files, headers=u["headers"])
    assert r.status_code == 400, r.text
    assert _is_json(r)


def test_400_returns_json_for_non_csv_upload(client, register):
    """A non-CSV / non-Excel file (binary garbage with an .xlsx
    extension here, so the Excel parser is invoked and rejects it)
    must produce a JSON 400, never a server crash.
    """
    u = register("err400nc")
    payload = b"%PDF-1.4\n%fake binary blob that is not a real spreadsheet\n%%EOF\n"
    files = {"file": ("not_a_csv.xlsx", payload,
                      "application/vnd.openxmlformats-officedocument."
                      "spreadsheetml.sheet")}
    data = {"dataset_name": "not_a_csv"}
    r = client.post(
        "/api/datasets/upload",
        files=files,
        data=data,
        headers=u["headers"],
    )
    assert r.status_code in (400, 415, 422), (
        f"non-CSV upload returned unexpected status {r.status_code}"
    )
    assert _is_json(r), (
        f"non-CSV upload returned non-JSON body: "
        f"content-type={r.headers.get('content-type')}"
    )
    body = r.json()
    assert "detail" in body or "error" in body


# ---------------------------------------------------------------------------
# 500 — Uncaught server error envelope
# ---------------------------------------------------------------------------

def test_500_envelope_is_documented_shape(client, register, monkeypatch):
    """Force an internal exception inside an endpoint and verify the
    response is JSON with the documented ``{error, detail}`` envelope.

    The endpoint must never leak HTML or a stack trace to the client.
    """
    import models
    from fastapi.testclient import TestClient
    from backend.main import app

    def _boom(*_args, **_kwargs):  # noqa: ANN001
        raise RuntimeError("synthetic failure for 500 envelope test")

    monkeypatch.setattr(models, "list_user_projects", _boom)

    u = register("err500")
    # TestClient defaults to re-raising server exceptions; we want the
    # real HTTP envelope FastAPI emits to the network instead.
    quiet_client = TestClient(app, raise_server_exceptions=False)
    r = quiet_client.get("/api/projects", headers=u["headers"])
    # Must be a 500 (FastAPI catches unhandled exceptions).
    assert r.status_code == 500, f"expected 500, got {r.status_code}"
    # Body must be JSON — an HTML traceback page is a regression.
    assert _is_json(r), (
        f"500 body was not JSON; content-type={r.headers.get('content-type')}"
    )
    body = r.json()
    # Documented shape is {"error": "...", "detail": "..."}. We assert
    # BOTH keys must be present — the FastAPI-default {"detail": "..."}
    # is a regression because the frontend's error-toast pipeline
    # always reads ``response.json().error`` for the displayed title.
    assert isinstance(body, dict), f"500 body is not a JSON object: {body}"
    missing = [k for k in ("error", "detail") if k not in body]
    assert not missing, (
        f"500 envelope is missing required keys {missing}; got {body}"
    )
