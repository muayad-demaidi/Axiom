"""Tests for the proactive question detector."""
import pandas as pd
import pytest

from proactive_questions import (
    detect_questions, resolve_answer, Question, QuestionOption,
)


def _kinds(qs):
    return sorted({q.kind for q in qs})


def test_no_questions_for_empty_df():
    assert detect_questions(pd.DataFrame()) == []


def test_mixed_dtypes_detected():
    df = pd.DataFrame({
        "amount": ["10", "20", "30", "Pending", "40", "50", "Pending",
                   "60", "70", "80", "90", "100", "Pending", "110",
                   "120", "Pending", "130", "140", "Pending", "150", "160"]
    })
    qs = detect_questions(df, ds_key="t1")
    assert "mixed_dtypes" in _kinds(qs)
    q = next(q for q in qs if q.kind == "mixed_dtypes")
    assert q.target_column == "amount"
    actions = {o.action for o in q.options}
    assert "drop_column" in actions and "skip" in actions


def test_clean_numeric_object_column_no_question():
    df = pd.DataFrame({"price": [str(i) for i in range(50)]})
    qs = detect_questions(df, ds_key="t2")
    assert "mixed_dtypes" not in _kinds(qs)


def test_ambiguous_dates_detected():
    # All values fit both DD/MM and MM/DD (no part > 12).
    df = pd.DataFrame({
        "d": ["01/02/2024", "03/04/2024", "05/06/2024",
              "07/08/2024", "09/10/2024", "11/12/2024",
              "02/03/2024", "04/05/2024", "06/07/2024",
              "08/09/2024"]
    })
    qs = detect_questions(df, ds_key="t3")
    assert "ambiguous_date" in _kinds(qs)


def test_unambiguous_dates_skipped():
    # 31/01 forces DD/MM — no question raised.
    df = pd.DataFrame({
        "d": ["31/01/2024", "28/02/2024", "15/06/2024",
              "01/12/2024", "22/07/2024", "13/09/2024",
              "30/11/2024", "29/04/2024", "17/03/2024",
              "25/05/2024"]
    })
    qs = detect_questions(df, ds_key="t4")
    assert "ambiguous_date" not in _kinds(qs)


def test_multi_currency_detected():
    df = pd.DataFrame({
        "price": ["$10", "$20", "$30", "EUR 40", "EUR 50",
                  "$60", "$70", "EUR 80", "$90", "$100",
                  "$110", "$120"]
    })
    schema = [{"column": "price", "inferred_type": "currency"}]
    qs = detect_questions(df, schema=schema, ds_key="t5")
    assert "multi_currency" in _kinds(qs)


def test_single_currency_no_question():
    df = pd.DataFrame({"price": [f"${i}" for i in range(20)]})
    schema = [{"column": "price", "inferred_type": "currency"}]
    qs = detect_questions(df, schema=schema, ds_key="t6")
    assert "multi_currency" not in _kinds(qs)


def test_hijri_dates_flagged_via_schema():
    df = pd.DataFrame({"birth": ["1445-03-12", "1445-04-15"]})
    schema = [{"column": "birth", "inferred_type": "date_hijri",
               "notes": "Hijri calendar"}]
    qs = detect_questions(df, schema=schema, ds_key="t7")
    assert "hijri_dates" in _kinds(qs)


def test_near_duplicates_detected():
    base = {"name": ["Alice"], "city": ["Beirut"], "role": ["eng"],
            "team": ["A"], "level": ["mid"]}
    rows = []
    for _ in range(3):
        rows.append({"name": "Alice", "city": "Beirut", "role": "eng",
                     "team": "A", "level": "mid"})
        rows.append({"name": "Alice ", "city": "Beirut", "role": "eng",
                     "team": "A", "level": "mid"})  # trailing space
    rows.extend([{"name": f"u{i}", "city": "x", "role": "y",
                  "team": "z", "level": "w"} for i in range(10)])
    df = pd.DataFrame(rows)
    qs = detect_questions(df, ds_key="t8")
    assert "near_duplicates" in _kinds(qs)


def test_resolve_answer_skip_returns_none():
    q = Question(id="x", kind="mixed_dtypes", prompt="", context="",
                 options=[QuestionOption(label="Skip", action="skip")])
    assert resolve_answer(q, q.options[0]) is None


def test_resolve_answer_drop_column_substep():
    q = Question(id="x", kind="mixed_dtypes", prompt="", context="",
                 options=[QuestionOption(label="Drop", action="drop_column",
                                         payload={"column": "c"})])
    out = resolve_answer(q, q.options[0])
    assert out == {"substep_key": "drop_column", "params": {"column": "c"}}


def test_resolve_answer_insert_substep():
    q = Question(id="x", kind="near_duplicates", prompt="", context="",
                 options=[QuestionOption(
                     label="Trim", action="insert_substep",
                     payload={"substep_key": "trim_whitespace"})])
    out = resolve_answer(q, q.options[0])
    assert out == {"substep_key": "trim_whitespace", "params": {}}


def test_resolve_answer_record_decision_emits_substep():
    """Non-skip answers must always produce an Applied Steps entry."""
    q = Question(id="x", kind="multi_currency", prompt="", context="",
                 options=[QuestionOption(
                     label="Treat all as $", action="record_decision",
                     payload={"column": "price", "decision": "treat_as_$"})])
    out = resolve_answer(q, q.options[0])
    assert out is not None
    assert out["substep_key"] == "record_decision"
    assert out["params"]["column"] == "price"
    assert "treat_as_$" in out["params"]["decision"]


def test_resolve_answer_cast_column_emits_decision_step():
    """Cast answers fall back to a TODO decision step rather than no-op."""
    q = Question(id="x", kind="ambiguous_date", prompt="", context="",
                 options=[QuestionOption(
                     label="DD/MM/YYYY", action="cast_column",
                     payload={"column": "d", "target_type": "date",
                              "date_order": "DMY"})])
    out = resolve_answer(q, q.options[0])
    assert out is not None
    assert out["substep_key"] == "record_decision"
    assert out["params"]["column"] == "d"
    assert "DMY" in out["params"]["decision"]
    assert out["params"]["note"]


def test_record_decision_substep_runs_as_pass_through():
    """The record_decision substep must execute without changing data."""
    import pandas as pd
    from data_cleaner import run_substep
    df = pd.DataFrame({"a": [1, 2, 3]})
    out, summary, _ = run_substep(
        "record_decision", df,
        {"column": "a", "decision": "keep_as_text"},
    )
    assert out.equals(df)
    assert "keep_as_text" in summary


def test_question_ids_are_stable_per_dataset():
    df = pd.DataFrame({
        "amount": ["10", "20", "30", "Pending", "40", "50", "Pending",
                   "60", "70", "80", "90", "100", "Pending", "110",
                   "120", "Pending", "130", "140", "Pending", "150", "160"]
    })
    a = detect_questions(df, ds_key="same")
    b = detect_questions(df, ds_key="same")
    c = detect_questions(df, ds_key="other")
    a_ids = {q.id for q in a}
    b_ids = {q.id for q in b}
    c_ids = {q.id for q in c}
    assert a_ids == b_ids
    assert a_ids.isdisjoint(c_ids)
