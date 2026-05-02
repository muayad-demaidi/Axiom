"""Parity test: POST /api/chat/stream must produce the same
``storage_mode`` decision after the resolver refactor as before
(Task #244).

We assert four interesting combinations and a fifth multi-layer
priority case that was previously covered by the inline 24-line
``effective_mode`` block in :mod:`backend.chat`:

  1. project=guided overrides everything → storage_mode='simple'
  2. request=expert with no project mode set → storage_mode='expert'
  3. user=guided fallback (no project / no request mode) → 'simple'
  4. default — no project, no request, no user pref → 'simple'
  5. project=guided + request=expert + user=expert → project wins → 'simple'

We capture the actual mode the chat stream forwarded to
``ai_assistant._apply_mode_directive`` by monkey-patching that helper
so the test never depends on the OpenAI stub or the full streaming
machinery — just the resolution decision.
"""
from __future__ import annotations


def _capture_storage_mode(monkeypatch):
    """Patch ``_apply_mode_directive`` to record the storage_mode it
    received. Returns the list that will be appended to."""
    captured: list[str] = []

    import ai_assistant
    original = ai_assistant._apply_mode_directive

    def _spy(system_prompt, assistant_mode):
        captured.append(assistant_mode)
        return original(system_prompt, assistant_mode)

    monkeypatch.setattr(ai_assistant, "_apply_mode_directive", _spy)
    return captured


def _drive_stream(client, headers, *, sid, pid, dsid,
                  request_assistant_mode=None):
    body = {
        "session_id": sid,
        "project_id": pid,
        "dataset_id": dsid,
        "messages": [{"role": "user", "content": "hi"}],
    }
    if request_assistant_mode is not None:
        body["assistant_mode"] = request_assistant_mode
    r = client.post("/api/chat/stream", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r


def _setup(client, register, project, upload_dataset, chat_session,
           driver_regression_csv, *, user_mode=None, project_mode=None):
    """Create a user/project/dataset/chat tuned to the test scenario."""
    u = register("modeparity")
    if user_mode is not None:
        # Use the API endpoint so storage matches the public contract
        # ("simple" for guided, "expert" for expert).
        client.patch(
            "/api/auth/me",
            json={"assistant_mode": user_mode},
            headers=u["headers"],
        )
    u, pid = project("modeparity-proj", user=u)
    if project_mode is not None:
        r = client.patch(
            f"/api/projects/{pid}",
            json={"mode": project_mode},
            headers=u["headers"],
        )
        assert r.status_code == 200, r.text
    dsid = upload_dataset(u["headers"], pid, "drivers", driver_regression_csv)
    sid = chat_session(u["headers"], pid)
    return u, pid, dsid, sid


def test_chat_stream_storage_mode_project_guided_overrides_all(
    client, register, project, upload_dataset, chat_session,
    driver_regression_csv, stub_openai, monkeypatch,
):
    """project=guided beats request=expert and user=expert → 'simple'."""
    captured = _capture_storage_mode(monkeypatch)
    stub_openai.script(["ok"])
    u, pid, dsid, sid = _setup(
        client, register, project, upload_dataset, chat_session,
        driver_regression_csv,
        user_mode="expert", project_mode="guided",
    )
    _drive_stream(client, u["headers"], sid=sid, pid=pid, dsid=dsid,
                  request_assistant_mode="expert")
    assert captured and captured[0] == "simple", captured


def test_chat_stream_storage_mode_request_expert_when_no_project_override(
    client, register, project, upload_dataset, chat_session,
    driver_regression_csv, stub_openai, monkeypatch,
):
    """No project mode + request='expert' + user=guided → 'expert'."""
    captured = _capture_storage_mode(monkeypatch)
    stub_openai.script(["ok"])
    u, pid, dsid, sid = _setup(
        client, register, project, upload_dataset, chat_session,
        driver_regression_csv,
        user_mode="guided", project_mode=None,
    )
    _drive_stream(client, u["headers"], sid=sid, pid=pid, dsid=dsid,
                  request_assistant_mode="expert")
    assert captured and captured[0] == "expert", captured


def test_chat_stream_storage_mode_user_guided_fallback(
    client, register, project, upload_dataset, chat_session,
    driver_regression_csv, stub_openai, monkeypatch,
):
    """No project mode, no request mode, user=guided → 'simple'."""
    captured = _capture_storage_mode(monkeypatch)
    stub_openai.script(["ok"])
    u, pid, dsid, sid = _setup(
        client, register, project, upload_dataset, chat_session,
        driver_regression_csv,
        user_mode="guided", project_mode=None,
    )
    _drive_stream(client, u["headers"], sid=sid, pid=pid, dsid=dsid,
                  request_assistant_mode=None)
    assert captured and captured[0] == "simple", captured


def test_chat_stream_storage_mode_default_when_nothing_set(
    client, register, project, upload_dataset, chat_session,
    driver_regression_csv, stub_openai, monkeypatch,
):
    """No project mode, no request mode, no user pref → default 'simple'."""
    captured = _capture_storage_mode(monkeypatch)
    stub_openai.script(["ok"])
    # Don't touch user_mode — fresh users default to 'simple' (guided)
    # in the DB anyway, but we explicitly pass None so this scenario
    # doesn't accidentally rely on the user-pref layer.
    u, pid, dsid, sid = _setup(
        client, register, project, upload_dataset, chat_session,
        driver_regression_csv,
        user_mode=None, project_mode=None,
    )
    _drive_stream(client, u["headers"], sid=sid, pid=pid, dsid=dsid,
                  request_assistant_mode=None)
    assert captured and captured[0] == "simple", captured
