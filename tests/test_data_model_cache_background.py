"""Integration test: background writers invalidate the bundle cache.

Closes Task #276 round-3 review concern #3 — the original cache
invalidation only fired from the data-model router's own write paths,
so an out-of-band writer (the upload-time discovery background task in
``backend.cross_predict.discover_relationships_after_upload``) could
leave a stale bundle in cache for up to the 30 s TTL window.

This test exercises the real path:

  1. Register a user, create a project.
  2. Upload dataset #1 (no joins possible yet).
  3. Hit GET /api/projects/{id}/data-model — primes the cache with
     "zero relationships".
  4. Manually run ``discover_relationships_after_upload`` to simulate
     the background task that fires after a second upload (we run it
     synchronously so we can assert deterministically).
  5. Hit GET /api/projects/{id}/data-model again — the response MUST
     reflect the freshly-written relationship rows immediately, not
     after the TTL elapses. That only works because the background
     writer now calls ``_invalidate_bundle_cache(project_id)``.
"""
from __future__ import annotations

import io

import pandas as pd

import semantic_model as sm

from backend import data_model as dm
from backend import cross_predict as cp
from backend.cross_predict import discover_relationships_after_upload


def _csv(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def test_background_discover_invalidates_cache(
    client, register, upload_dataset, monkeypatch
):
    u = register("bg")
    pid = int(client.post(
        "/api/projects", json={"name": "bg-cache"}, headers=u["headers"]
    ).json()["id"])

    customers = pd.DataFrame({
        "customer_id": list(range(1, 31)),
        "name": [f"c{i}" for i in range(1, 31)],
    })
    orders = pd.DataFrame({
        "order_id": list(range(1, 61)),
        "customer_id": [(i % 30) + 1 for i in range(60)],
        "amount": [i * 2.5 for i in range(60)],
    })

    upload_dataset(u["headers"], pid, "customers", _csv(customers))

    # Stub the proposer so the background task is guaranteed to add at
    # least one high-confidence join — keeps this test focused on the
    # cache-invalidation contract rather than re-litigating the
    # heuristic thresholds in semantic_model.suggest_relationships.
    def _stub_proposer(profiles, frames, max_per_pair=3):
        names = [p["name"] for p in profiles]
        if len(names) < 2:
            return []
        ln, rn = names[0], names[1]
        return [sm.ProposedRelationship(
            left_table=ln, left_column="customer_id",
            right_table=rn, right_column="customer_id",
            cardinality="1:N",
            confidence=0.99, band="high",
            evidence=["stubbed by tests/test_data_model_cache_background.py"],
            overlap_score=1.0, name_score=1.0, dtype_score=1.0,
        )]
    monkeypatch.setattr(cp.sm, "propose_relationships_for_project",
                        _stub_proposer)

    # Stub profile_table so this test doesn't depend on the heavier
    # profiling pipeline succeeding for these tiny synthetic frames —
    # we're testing the cache-invalidation contract, not profiling.
    def _stub_profile(name, df):
        return {"name": name, "rows": len(df), "columns": list(df.columns)}
    monkeypatch.setattr(cp.sm, "profile_table", _stub_profile)

    url = f"/api/projects/{pid}/data-model"
    first = client.get(url, headers=u["headers"]).json()
    assert first["relationships"] == [], (
        f"baseline must have no relationships yet; got {first['relationships']!r}"
    )

    # Verify the cache really was populated by that GET — the next
    # call should be a hit, proving we're testing real invalidation
    # rather than a perpetually-cold path.
    with dm._BUNDLE_CACHE_LOCK:
        assert (pid, u["user"]["id"]) in dm._BUNDLE_CACHE, (
            "GET should have primed the bundle cache"
        )

    # Uploading the second dataset fires the
    # ``discover_relationships_after_upload`` background task — TestClient
    # drives FastAPI's BackgroundTasks synchronously after the response,
    # so by the time the next line returns the discovery has run, the
    # high-confidence join has been persisted, AND (crucially) the
    # invalidation hook in cross_predict has cleared this project's
    # bundle cache entry. This mirrors production exactly.
    upload_dataset(u["headers"], pid, "orders", _csv(orders))

    # The cache key for this project must have been evicted by the
    # background writer's invalidation hook. Without that hook, this
    # entry would survive in the cache for up to the 30 s TTL and the
    # next read would return the stale "zero relationships" payload.
    with dm._BUNDLE_CACHE_LOCK:
        assert (pid, u["user"]["id"]) not in dm._BUNDLE_CACHE, (
            "background writer must invalidate the bundle cache for the "
            "affected project; otherwise the freshly-discovered joins are "
            "invisible until the 30 s TTL elapses (Task #276 R3 concern #3)"
        )

    second = client.get(url, headers=u["headers"]).json()
    rels = second["relationships"]
    assert len(rels) >= 1, (
        f"GET right after the upload-time background discovery must "
        f"surface the new joins; got {rels!r}"
    )
