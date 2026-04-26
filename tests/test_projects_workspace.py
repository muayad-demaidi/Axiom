"""Tests for the projects management workspace endpoints (Task #225).

Covers archive / restore / bulk actions, the enriched listing, the
trim/uniqueness rules on rename, and the include_archived query toggle.
"""
from __future__ import annotations

import io


def _make_csv(name: str = "x", rows: int = 3) -> bytes:
    buf = io.StringIO()
    buf.write("a,b\n")
    for i in range(rows):
        buf.write(f"{i},{i*2}\n")
    return buf.getvalue().encode()


def test_list_projects_returns_enriched_stats(
    client, register, project, upload_dataset, chat_session
):
    u, pid = project(name="alpha")
    upload_dataset(u["headers"], pid, "ds", _make_csv())
    chat_session(u["headers"], pid, title="hello")
    chat_session(u["headers"], pid, title="world")

    rows = client.get("/api/projects", headers=u["headers"]).json()
    me = next(r for r in rows if r["id"] == pid)

    # New rollups should be present and populated.
    assert me["sheet_count"] == 1
    assert me["chat_count"] == 2
    assert me["total_size_bytes"] > 0
    assert me["last_session_id"] is not None
    assert me["status"] in {"ready", "processing", "error"}
    assert me["is_archived"] is False
    assert me["last_active_at"] is not None


def test_archive_then_restore_round_trips(client, project):
    u, pid = project(name="archive-me")

    # Default list hides archived projects.
    r = client.post(f"/api/projects/{pid}/archive", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["is_archived"] is True

    rows = client.get("/api/projects", headers=u["headers"]).json()
    assert all(r["id"] != pid for r in rows)

    # include_archived=true brings it back.
    rows = client.get(
        "/api/projects?include_archived=true", headers=u["headers"]
    ).json()
    assert any(r["id"] == pid and r["is_archived"] is True for r in rows)

    # Restore returns it to the active grid.
    r = client.post(f"/api/projects/{pid}/restore", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["is_archived"] is False
    rows = client.get("/api/projects", headers=u["headers"]).json()
    assert any(r["id"] == pid for r in rows)


def test_bulk_archive_and_delete(client, project):
    u, p1 = project(name="b1")
    _, p2 = project(name="b2", user=u)
    _, p3 = project(name="b3", user=u)

    # Archive two of three in a single call.
    r = client.post(
        "/api/projects/bulk",
        headers=u["headers"],
        json={"action": "archive", "project_ids": [p1, p2]},
    )
    assert r.status_code == 200
    assert sorted(r.json()["processed"]) == sorted([p1, p2])

    active = client.get("/api/projects", headers=u["headers"]).json()
    assert {r["id"] for r in active} == {p3}

    # Bulk-delete the archived ones.
    r = client.post(
        "/api/projects/bulk",
        headers=u["headers"],
        json={"action": "delete", "project_ids": [p1, p2]},
    )
    assert r.status_code == 200
    assert sorted(r.json()["processed"]) == sorted([p1, p2])

    archived = client.get(
        "/api/projects?include_archived=true", headers=u["headers"]
    ).json()
    assert {r["id"] for r in archived} == {p3}


def test_bulk_action_skips_other_users_projects(client, project):
    u1, p1 = project(name="mine")
    u2 = client.post(
        "/api/auth/register",
        json={
            "email": "task225+other@axiom.test",
            "username": "task225other",
            "password": "Pass1234!",
            "full_name": "Other",
        },
    ).json()
    headers2 = {"Authorization": f"Bearer {u2['token']}"}

    r = client.post(
        "/api/projects/bulk",
        headers=headers2,
        json={"action": "delete", "project_ids": [p1]},
    )
    assert r.status_code == 200
    assert r.json()["processed"] == []  # other user can't act on it

    # Original owner still sees it.
    rows = client.get("/api/projects", headers=u1["headers"]).json()
    assert any(r["id"] == p1 for r in rows)


def test_rename_validates_blank_and_dupes(client, project):
    u, p1 = project(name="alpha")
    _, p2 = project(name="beta", user=u)

    # Blank rename rejected.
    r = client.patch(
        f"/api/projects/{p1}", headers=u["headers"], json={"name": "   "}
    )
    assert r.status_code == 400

    # Duplicate (case-insensitive) rejected.
    r = client.patch(
        f"/api/projects/{p1}", headers=u["headers"], json={"name": "Beta"}
    )
    assert r.status_code == 409

    # Trim succeeds.
    r = client.patch(
        f"/api/projects/{p1}", headers=u["headers"], json={"name": "  gamma  "}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "gamma"
    # Sanity: the listing reflects the rename.
    rows = client.get("/api/projects", headers=u["headers"]).json()
    assert any(r["id"] == p1 and r["name"] == "gamma" for r in rows)
    assert any(r["id"] == p2 and r["name"] == "beta" for r in rows)
