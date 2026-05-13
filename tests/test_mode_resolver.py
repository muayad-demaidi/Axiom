"""Unit tests for the shared Guided/Expert mode resolver (Task #244).

Covers:
  * each of the four priority levels firing in isolation
  * the legacy ``"simple"`` → ``"guided"`` aliasing
  * garbage / unknown values falling through instead of being returned
  * ``None`` user / ``None`` project edge cases
  * a mixed scenario where two layers are set and the higher-priority
    one wins
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import models  # noqa: F401  (imports happen via conftest bootstrap)
from backend.auth import get_db_session
from backend.mode_resolver import _normalize, resolve_mode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, headers_token: str = "x", *, assistant_mode=None):
    """Create a real DB-backed user. Returns the ORM row."""
    import uuid
    email = f"task244+{uuid.uuid4().hex[:10]}@axiom.test"
    user = models.User(
        email=email,
        username=email.split("@")[0],
        password_hash="x",
        full_name="t244",
        assistant_mode=assistant_mode,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_project(db, user_id: int, *, mode=None):
    proj = models.Project(user_id=user_id, name="t244-proj", mode=mode)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@pytest.fixture
def db():
    gen = get_db_session()
    session = next(gen)
    try:
        yield session
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("guided", "guided"),
        ("Guided", "guided"),
        ("  GUIDED  ", "guided"),
        ("simple", "guided"),  # legacy DB alias
        ("SIMPLE", "guided"),
        ("expert", "expert"),
        ("Expert", "expert"),
        ("  expert  ", "expert"),
        (None, None),
        ("", None),
        ("   ", None),
        ("nonsense", None),
        ("guided-mode", None),
        (123, None),
    ],
)
def test_normalize_mode_value(raw, expected):
    assert _normalize(raw) == expected


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------

def test_priority_1_project_override_wins(db):
    user = _make_user(db, assistant_mode="simple")
    proj = _make_project(db, user.id, mode="expert")
    assert resolve_mode(
        db, user, project_id=proj.id, request_mode="guided"
    ) == "expert"


def test_priority_2_request_mode_used_when_no_project_override(db):
    user = _make_user(db, assistant_mode="simple")
    proj = _make_project(db, user.id, mode=None)
    assert resolve_mode(
        db, user, project_id=proj.id, request_mode="expert"
    ) == "expert"


def test_priority_3_user_preference_used_when_no_project_or_request(db):
    user = _make_user(db, assistant_mode="expert")
    proj = _make_project(db, user.id, mode=None)
    assert resolve_mode(
        db, user, project_id=proj.id, request_mode=None
    ) == "expert"


def test_priority_4_default_guided_when_nothing_set(db):
    user = _make_user(db, assistant_mode=None)
    assert resolve_mode(db, user, project_id=None, request_mode=None) == "guided"


# ---------------------------------------------------------------------------
# Aliasing & garbage handling
# ---------------------------------------------------------------------------

def test_legacy_simple_user_alias_resolves_to_guided(db):
    user = _make_user(db, assistant_mode="simple")
    assert resolve_mode(db, user, project_id=None, request_mode=None) == "guided"


def test_garbage_request_mode_falls_through_to_user_pref(db):
    user = _make_user(db, assistant_mode="expert")
    assert resolve_mode(
        db, user, project_id=None, request_mode="banana"
    ) == "expert"


def test_garbage_at_every_layer_falls_through_to_default(db):
    user = _make_user(db, assistant_mode="banana")
    proj = _make_project(db, user.id, mode="banana")
    assert resolve_mode(
        db, user, project_id=proj.id, request_mode="banana"
    ) == "guided"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_user_returns_default(db):
    assert resolve_mode(db, None, project_id=None, request_mode=None) == "guided"


def test_none_user_with_request_mode_uses_request(db):
    assert resolve_mode(
        db, None, project_id=None, request_mode="expert"
    ) == "expert"


def test_none_project_id_skips_project_layer(db):
    user = _make_user(db, assistant_mode="expert")
    assert resolve_mode(
        db, user, project_id=None, request_mode=None
    ) == "expert"


def test_unknown_project_id_does_not_break_resolution(db):
    user = _make_user(db, assistant_mode="expert")
    # 999_999 belongs to nobody — get_project returns None and we fall
    # through to the request/user/default layers.
    assert resolve_mode(
        db, user, project_id=999_999, request_mode=None
    ) == "expert"


def test_project_owned_by_another_user_is_ignored(db):
    owner = _make_user(db, assistant_mode="simple")
    other = _make_user(db, assistant_mode="expert")
    proj = _make_project(db, owner.id, mode="guided")
    # ``other`` does not own the project, so the project's "guided"
    # override must NOT be picked up — we should fall through to the
    # other user's "expert" preference.
    assert resolve_mode(
        db, other, project_id=proj.id, request_mode=None
    ) == "expert"


# ---------------------------------------------------------------------------
# Mixed-priority scenarios
# ---------------------------------------------------------------------------

def test_mixed_two_layers_set_higher_priority_wins(db):
    user = _make_user(db, assistant_mode="expert")
    proj = _make_project(db, user.id, mode="guided")
    # Project says guided, user says expert → project wins.
    assert resolve_mode(
        db, user, project_id=proj.id, request_mode=None
    ) == "guided"


def test_mixed_request_overrides_user_when_no_project(db):
    user = _make_user(db, assistant_mode="expert")
    assert resolve_mode(
        db, user, project_id=None, request_mode="guided"
    ) == "guided"


def test_user_attribute_missing_does_not_crash(db):
    """A user-like object without ``assistant_mode`` should fall through
    to the default cleanly — getattr returns None and we hit step 4."""
    fake_user = SimpleNamespace(id=None)
    assert resolve_mode(
        db, fake_user, project_id=None, request_mode=None
    ) == "guided"
