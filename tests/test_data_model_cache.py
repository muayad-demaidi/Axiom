"""Smoke tests for the data-model bundle cache (Task #276 / R-1).

The cache is a tiny in-process TTL keyed on (project_id, user_id) and is
explicitly invalidated by every write path in `backend/data_model.py`.
These tests pin the contract:
  * a hit returns the previously-built dict by identity
  * an entry expires after the TTL window
  * `_invalidate_bundle_cache(project_id)` drops every per-user entry for
    that project
"""
from __future__ import annotations

import time

from backend import data_model as dm


def _reset_cache() -> None:
    with dm._BUNDLE_CACHE_LOCK:
        dm._BUNDLE_CACHE.clear()


def test_cache_hit_returns_same_object_without_calling_bundle(monkeypatch):
    _reset_cache()
    calls: list[tuple] = []

    def fake_bundle(db, project_id, user_id):
        calls.append((project_id, user_id))
        return {"project_id": project_id, "user_id": user_id, "n": len(calls)}

    monkeypatch.setattr(dm, "_bundle", fake_bundle)
    first = dm._bundle_cached(db=None, project_id=42, user_id=1)
    second = dm._bundle_cached(db=None, project_id=42, user_id=1)
    assert first is second, "cache hit must return the cached object by identity"
    assert calls == [(42, 1)], "rebuild must run exactly once for two reads"


def test_cache_misses_for_different_user(monkeypatch):
    _reset_cache()
    calls: list[tuple] = []
    monkeypatch.setattr(
        dm, "_bundle",
        lambda db, p, u: (calls.append((p, u)) or {"p": p, "u": u}),
    )
    dm._bundle_cached(db=None, project_id=42, user_id=1)
    dm._bundle_cached(db=None, project_id=42, user_id=2)
    assert calls == [(42, 1), (42, 2)]


def test_invalidate_drops_every_user_for_project(monkeypatch):
    _reset_cache()
    calls: list[tuple] = []
    monkeypatch.setattr(
        dm, "_bundle",
        lambda db, p, u: (calls.append((p, u)) or {"p": p, "u": u}),
    )
    dm._bundle_cached(db=None, project_id=42, user_id=1)
    dm._bundle_cached(db=None, project_id=42, user_id=2)
    dm._bundle_cached(db=None, project_id=99, user_id=1)
    assert len(calls) == 3

    dm._invalidate_bundle_cache(project_id=42)
    # Both project=42 entries must be re-fetched; project=99 must not.
    dm._bundle_cached(db=None, project_id=42, user_id=1)
    dm._bundle_cached(db=None, project_id=42, user_id=2)
    dm._bundle_cached(db=None, project_id=99, user_id=1)
    assert calls == [
        (42, 1), (42, 2), (99, 1),
        (42, 1), (42, 2),  # project 99 served from cache
    ]


def test_ttl_expiry(monkeypatch):
    _reset_cache()
    calls: list[tuple] = []
    monkeypatch.setattr(
        dm, "_bundle",
        lambda db, p, u: (calls.append((p, u)) or {"p": p, "u": u}),
    )
    monkeypatch.setattr(dm, "_BUNDLE_CACHE_TTL_SECONDS", 0.01)
    dm._bundle_cached(db=None, project_id=42, user_id=1)
    time.sleep(0.05)
    dm._bundle_cached(db=None, project_id=42, user_id=1)
    assert calls == [(42, 1), (42, 1)], "expired entry must trigger a rebuild"
