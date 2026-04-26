"""Section 1 + 3: semantic_model.py unit and edge-case tests."""
from __future__ import annotations

import pandas as pd
import pytest

import semantic_model as sm


# ---------------------------------------------------------------------------
# profile_table
# ---------------------------------------------------------------------------

def test_profile_table_on_empty_dataframe_returns_safe_payload():
    profile = sm.profile_table("empty", pd.DataFrame())
    assert profile["name"] == "empty"
    assert int(profile.get("rows", 0)) == 0
    # Profiling an empty frame must never raise — every consumer
    # (model API, chat tool, refresh job) depends on this.
    assert "role" in profile
    assert profile.get("columns") == [] or profile.get("columns") is None or \
           isinstance(profile.get("columns"), list)


def test_profile_table_on_typical_frame_extracts_columns_meta():
    df = pd.DataFrame({
        "id": list(range(1, 21)),
        "amount": [10.0 + i for i in range(20)],
        "country": ["LB", "JO"] * 10,
    })
    profile = sm.profile_table("orders", df)
    assert profile["rows"] == 20
    assert isinstance(profile.get("columns"), list)
    names = {c["name"] for c in profile["columns"]}
    assert {"id", "amount", "country"}.issubset(names)


# ---------------------------------------------------------------------------
# confidence_band
# ---------------------------------------------------------------------------

def test_confidence_band_high_requires_strong_overlap_and_dtype():
    # All three thresholds met → "high".
    assert sm.confidence_band(0.95, 0.7, 0.95) == "high"


def test_confidence_band_identical_name_high_band():
    # name_score effectively drives the overall score; with strong
    # overlap + matching dtypes the proposal lands in the "high" band.
    band = sm.confidence_band(0.92, 0.85, 1.0)
    assert band == "high"


def test_confidence_band_no_overlap_drops_to_inferred():
    # Names + dtypes match but values don't overlap → "inferred".
    assert sm.confidence_band(0.30, 0.0, 1.0) == "inferred"


def test_confidence_band_medium_then_low():
    assert sm.confidence_band(0.70, 0.4, 0.9) == "medium"
    assert sm.confidence_band(0.50, 0.2, 0.5) == "low"


# ---------------------------------------------------------------------------
# propose_relationships_for_project
# ---------------------------------------------------------------------------

def _profiles_and_frames():
    customers = pd.DataFrame({
        "customer_id": list(range(1, 11)),
        "country": ["LB", "JO"] * 5,
    })
    orders = pd.DataFrame({
        "order_id": list(range(101, 121)),
        "customer_id": [(i % 10) + 1 for i in range(20)],
        "amount": [10 * i for i in range(20)],
    })
    profs = [
        sm.profile_table("customers", customers),
        sm.profile_table("orders", orders),
    ]
    frames = {"customers": customers, "orders": orders}
    return profs, frames


def test_propose_relationships_finds_customer_id_link():
    profiles, frames = _profiles_and_frames()
    proposals = sm.propose_relationships_for_project(profiles, frames)
    assert proposals, "expected at least one proposal"
    assert any(
        p.left_column == "customer_id" or p.right_column == "customer_id"
        for p in proposals
    )


def test_propose_relationships_skips_empty_frames():
    customers = pd.DataFrame({"id": [1, 2, 3]})
    empty = pd.DataFrame()
    profiles = [
        sm.profile_table("customers", customers),
        sm.profile_table("empty", empty),
    ]
    frames = {"customers": customers, "empty": empty}
    proposals = sm.propose_relationships_for_project(profiles, frames)
    # Empty side means no overlap can be measured — the function must
    # silently skip rather than crash.
    assert proposals == [] or all(p.left_table != "empty" and p.right_table != "empty"
                                  for p in proposals)


# ---------------------------------------------------------------------------
# generate_clarification_questions edge cases
# ---------------------------------------------------------------------------

def _make_proposal(**overrides) -> sm.ProposedRelationship:
    base = dict(
        left_table="orders", left_column="customer_id",
        right_table="customers", right_column="customer_id",
        cardinality="N:1", confidence=0.6, band="medium",
        evidence=["identical column names", "strong value overlap"],
        overlap_score=0.6, name_score=0.95, dtype_score=1.0,
    )
    base.update(overrides)
    return sm.ProposedRelationship(**base)


def test_clarification_summary_link_refusal_question():
    profiles = [
        {"name": "monthly_summary", "role": "summary", "rows": 12,
         "grain": {"kind": "month"}, "columns": [], "role_signals": []},
        {"name": "transactions", "role": "fact", "rows": 5000,
         "grain": {"kind": "row"}, "columns": [], "role_signals": []},
    ]
    proposal = _make_proposal(
        left_table="monthly_summary", right_table="transactions",
        left_column="month", right_column="month_id",
    )
    questions = sm.generate_clarification_questions(profiles, [proposal])
    assert any(q.kind == "summary_link" for q in questions), (
        "expected a summary_link question for summary↔fact join"
    )


def test_clarification_low_overlap_emits_weak_join_question():
    profiles = [
        {"name": "orders", "role": "fact", "rows": 100,
         "grain": {"kind": "row"}, "columns": [], "role_signals": []},
        {"name": "customers", "role": "dimension", "rows": 10,
         "grain": {"kind": "id"}, "columns": [], "role_signals": []},
    ]
    proposal = _make_proposal(band="low", overlap_score=0.2)
    questions = sm.generate_clarification_questions(profiles, [proposal])
    assert any(q.kind == "weak_join" for q in questions)


def test_clarification_caps_at_twelve_questions():
    # Generate more than 12 weak proposals — output must be capped.
    profiles = []
    proposals = []
    for i in range(20):
        profiles.append({
            "name": f"t{i}", "role": "fact", "rows": 100,
            "grain": {"kind": "row"}, "columns": [], "role_signals": [],
        })
    for i in range(20):
        proposals.append(_make_proposal(
            left_table=f"t{i}", right_table=f"t{i+1 if i+1<20 else 0}",
            band="low", overlap_score=0.2,
        ))
    questions = sm.generate_clarification_questions(profiles, proposals)
    assert len(questions) <= 12


# ---------------------------------------------------------------------------
# safe_query_model refusals + warnings
# ---------------------------------------------------------------------------

def test_safe_query_refuses_summary_to_fact_row_join():
    monthly = pd.DataFrame({"month": ["2024-01", "2024-02"], "total": [100, 200]})
    txns = pd.DataFrame({
        "txn_id": [1, 2, 3], "month_id": ["2024-01", "2024-02", "2024-02"],
        "amount": [10, 20, 30],
    })
    profiles = [
        sm.profile_table("monthly", monthly),
        sm.profile_table("txns", txns),
    ]
    # Force the roles so the refusal kicks in regardless of heuristics.
    for p in profiles:
        if p["name"] == "monthly":
            p["role"] = "summary"
        else:
            p["role"] = "fact"
    confirmed = [{
        "left_table": "monthly", "left_column": "month",
        "right_table": "txns", "right_column": "month_id",
    }]
    spec = {
        "tables": ["monthly", "txns"],
        "metrics": [{"table": "txns", "column": "amount", "agg": "sum"}],
    }
    res = sm.safe_query_model(
        spec, profiles, confirmed, [],
        {"monthly": monthly, "txns": txns},
    )
    assert res.refusals, "expected a summary↔fact refusal"
    assert "summary" in res.refusals[0].lower()


def test_safe_query_refuses_when_no_relationship_exists():
    a = pd.DataFrame({"x": [1, 2, 3]})
    b = pd.DataFrame({"y": [1, 2, 3]})
    profiles = [sm.profile_table("a", a), sm.profile_table("b", b)]
    spec = {"tables": ["a", "b"],
            "metrics": [{"table": "a", "column": "x", "agg": "sum"}]}
    res = sm.safe_query_model(spec, profiles, [], [], {"a": a, "b": b})
    assert res.refusals
    assert any("no relationship" in r.lower() or "confirm a join" in r.lower()
               for r in res.refusals)


def test_safe_query_warns_on_n_to_n_fanout():
    # Both sides duplicate the join key → N:N fan-out warning.
    a = pd.DataFrame({"k": [1, 1, 2, 2], "x": [10, 20, 30, 40]})
    b = pd.DataFrame({"k": [1, 1, 2, 2], "y": [100, 200, 300, 400]})
    profiles = [sm.profile_table("a", a), sm.profile_table("b", b)]
    for p in profiles:
        p["role"] = "fact"
    confirmed = [{"left_table": "a", "left_column": "k",
                  "right_table": "b", "right_column": "k",
                  "cardinality": "N:N"}]
    spec = {"tables": ["a", "b"],
            "metrics": [{"table": "a", "column": "x", "agg": "sum"}]}
    res = sm.safe_query_model(spec, profiles, confirmed, [], {"a": a, "b": b})
    # The documented behavior is to emit a fan-out warning on N:N joins.
    flagged = " ".join(res.warnings + res.refusals).lower()
    assert ("many-to-many" in flagged or "n:n" in flagged
            or "fan" in flagged or "inflated" in flagged), (
        f"expected fan-out warning on N:N join, got warnings={res.warnings} "
        f"refusals={res.refusals}"
    )


def test_safe_query_low_overlap_warning_via_inferred_path():
    a = pd.DataFrame({"k": [1, 2, 3, 4], "x": [10, 20, 30, 40]})
    b = pd.DataFrame({"k": [99, 98, 97, 96], "y": [1, 2, 3, 4]})  # zero overlap
    profiles = [sm.profile_table("a", a), sm.profile_table("b", b)]
    for p in profiles:
        p["role"] = "fact"
    inferred = [{"left_table": "a", "left_column": "k",
                 "right_table": "b", "right_column": "k",
                 "overlap_score": 0.0}]
    spec = {"tables": ["a", "b"],
            "metrics": [{"table": "a", "column": "x", "agg": "sum"}]}
    res = sm.safe_query_model(spec, profiles, [], inferred, {"a": a, "b": b})
    # Inferred path should be at least labeled (or zero rows + warning).
    assert (res.inferred_joins or res.warnings or res.refusals or
            len(res.rows) == 0)
