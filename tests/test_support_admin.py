"""Backend smoke tests for the admin Support inbox endpoints.

Exercises the live FastAPI app via TestClient (no mocks):
  - public POST /api/support/contact persists a row
  - admin gate: anonymous → 401, non-admin → 403
  - admin GET /api/support/messages returns newest-first
  - admin PATCH /api/support/messages/{id} flips the handled flag
  - only_unhandled=true filters out handled rows
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.main import app
import models


client = TestClient(app)


def _unique_email(tag: str) -> str:
    return f"support+{tag}+{int(time.time() * 1000)}@axiom.test"


def _register_user(*, admin: bool = False) -> dict:
    email = _unique_email("admin" if admin else "user")
    body = {
        "email": email,
        "username": email.split("@")[0],
        "password": "Pass1234!",
        "full_name": "Support Smoke",
    }
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    if admin:
        # Promote directly in the DB; there's no public promote endpoint.
        db = models.get_db()
        try:
            user = db.query(models.User).filter(models.User.id == payload["user"]["id"]).first()
            assert user is not None
            user.is_admin = True
            db.commit()
        finally:
            db.close()
    return payload


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _submit_contact(name: str, email: str, message: str) -> int:
    r = client.post(
        "/api/support/contact",
        json={"name": name, "email": email, "message": message},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)
    return body["id"]


def test_admin_inbox_lists_messages_newest_first_and_marks_handled():
    admin = _register_user(admin=True)
    admin_headers = _auth(admin["token"])

    a_id = _submit_contact("Alice", _unique_email("a"), "First message please look")
    # Tiny gap so created_at ordering is stable on fast machines.
    time.sleep(0.01)
    b_id = _submit_contact("Bob", _unique_email("b"), "Second message thanks")

    r = client.get("/api/support/messages", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    msgs = body["messages"]
    assert "total" in body and isinstance(body["total"], int)
    assert body["total"] >= 2
    assert body["offset"] == 0
    ids = [m["id"] for m in msgs]
    # Newest first, both present.
    pos_a = ids.index(a_id)
    pos_b = ids.index(b_id)
    assert pos_b < pos_a, "Newer message should appear before older one"

    by_id = {m["id"]: m for m in msgs}
    assert by_id[a_id]["handled"] is False
    assert by_id[a_id]["email"]
    assert by_id[a_id]["name"] == "Alice"
    assert by_id[a_id]["message"].startswith("First message")

    # Mark a_id handled.
    r = client.patch(
        f"/api/support/messages/{a_id}",
        json={"handled": True},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["handled"] is True

    # only_unhandled=true should now exclude a_id but keep b_id.
    r = client.get(
        "/api/support/messages?only_unhandled=true",
        headers=admin_headers,
    )
    assert r.status_code == 200
    open_ids = {m["id"] for m in r.json()["messages"]}
    assert a_id not in open_ids
    assert b_id in open_ids

    # Reopen a_id and confirm it returns to the open queue.
    r = client.patch(
        f"/api/support/messages/{a_id}",
        json={"handled": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["handled"] is False
    r = client.get(
        "/api/support/messages?only_unhandled=true",
        headers=admin_headers,
    )
    assert a_id in {m["id"] for m in r.json()["messages"]}


def test_non_admin_cannot_access_inbox():
    user = _register_user(admin=False)
    user_headers = _auth(user["token"])

    r = client.get("/api/support/messages", headers=user_headers)
    assert r.status_code == 403

    # Patch is also gated.
    r = client.patch(
        "/api/support/messages/1",
        json={"handled": True},
        headers=user_headers,
    )
    assert r.status_code == 403


def test_anonymous_cannot_access_inbox():
    r = client.get("/api/support/messages")
    assert r.status_code == 401
    r = client.patch("/api/support/messages/1", json={"handled": True})
    assert r.status_code == 401


def test_patch_unknown_id_returns_404():
    admin = _register_user(admin=True)
    r = client.patch(
        "/api/support/messages/999999999",
        json={"handled": True},
        headers=_auth(admin["token"]),
    )
    assert r.status_code == 404


def test_list_supports_offset_pagination_with_total():
    admin = _register_user(admin=True)
    headers = _auth(admin["token"])

    # Submit a small batch with stable ordering.
    submitted: list[int] = []
    for i in range(5):
        submitted.append(_submit_contact(f"User{i}", _unique_email(f"p{i}"), f"Msg {i} please"))
        time.sleep(0.005)

    # First page, limit 2.
    r = client.get("/api/support/messages?limit=2&offset=0", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    page1_ids = [m["id"] for m in body["messages"]]
    assert len(page1_ids) == 2
    assert body["total"] >= 5
    assert body["limit"] == 2
    assert body["offset"] == 0

    # Second page, offset 2.
    r = client.get("/api/support/messages?limit=2&offset=2", headers=headers)
    assert r.status_code == 200, r.text
    body2 = r.json()
    page2_ids = [m["id"] for m in body2["messages"]]
    assert len(page2_ids) == 2
    # No overlap between pages.
    assert not (set(page1_ids) & set(page2_ids))
    # Same `total` for the same query.
    assert body2["total"] == body["total"]


def test_me_endpoint_exposes_is_admin_flag():
    admin = _register_user(admin=True)
    user = _register_user(admin=False)

    r = client.get("/api/auth/me", headers=_auth(admin["token"]))
    assert r.status_code == 200
    assert r.json().get("is_admin") is True

    r = client.get("/api/auth/me", headers=_auth(user["token"]))
    assert r.status_code == 200
    assert r.json().get("is_admin") is False
