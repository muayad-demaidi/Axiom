"""Integration test for the persisted Power Query-style step history.

Simulates: analyze a dataset, apply a manual override, navigate to a
non-latest step, persist; then a fresh "session" reopens the dataset and
should see the same step list, the same active pointer, and the manual
override restored.
"""
from __future__ import annotations

import pandas as pd

from context.step_history import (
    StepHistory,
    rebuild_history_from_recipes,
    serialize_source_df,
    deserialize_source_df,
)
from context.type_inference import apply_schema, cast_column, infer_schema
from data_cleaner import clean_data


def _build_initial_history(df_raw: pd.DataFrame) -> tuple[StepHistory, list, pd.DataFrame]:
    schema = infer_schema(df_raw)
    df_typed = apply_schema(df_raw, schema)
    df_clean, report = clean_data(df_typed)

    h = StepHistory()
    h.add("Source", "src", df_raw, meta={"parse": {"kind": "csv"}})
    h.add("Promoted Headers", "promoted", df_raw)
    h.add("Changed Type", "auto-typed", df_typed,
          meta={"schema": [s.to_dict() for s in schema]})
    h.add("Cleaning", "cleaned", df_clean, meta={"report": report})
    return h, schema, df_clean


def test_persist_and_reopen_round_trip():
    df_raw = pd.DataFrame({
        "id": ["1", "2", "3", "4"],
        "name": ["a", "b", "a", "c"],
        "amt": ["$1.00", "$2.50", "$3.75", "$4.25"],
    })
    h, schema, df_clean = _build_initial_history(df_raw)

    # Apply a manual override and navigate back to a non-latest step.
    base = h.current_df().copy()
    base["id"] = cast_column(base["id"], "integer")
    new_schema = infer_schema(base)
    h.add(
        "Changed Type (manual)",
        "id → integer",
        base,
        meta={
            "override": {"id": "integer"},
            "schema": [s.to_dict() for s in new_schema],
        },
    )
    h.go_to(2)  # park on the auto Changed Type step

    # Persist (what _persist_step_history would write to the DB).
    blob = serialize_source_df(df_raw)
    recipes = h.to_recipes()
    active_idx = h.active_index

    # Simulate a fresh session: rebuild from recipes alone.
    src_back = deserialize_source_df(blob)
    h2 = rebuild_history_from_recipes(src_back, recipes, active_index=active_idx)

    # Same step list, same active pointer.
    assert [s.name for s in h2.steps] == [
        "Source", "Promoted Headers", "Changed Type", "Cleaning",
        "Changed Type (manual)",
    ]
    assert h2.active_index == 2
    assert h2.current().name == "Changed Type"

    # Manual override is preserved end-to-end.
    manual = h2.find_last("Changed Type (manual)")
    assert manual is not None
    assert manual.meta.get("override") == {"id": "integer"}
    # The replayed manual step's dataframe carries the casted column.
    assert pd.api.types.is_integer_dtype(manual.df["id"])

    # Cleaning step rebuilt with the same row count as originally.
    cleaning = h2.find_last("Cleaning")
    assert cleaning is not None
    assert len(cleaning.df) == len(df_clean)


if __name__ == "__main__":
    test_persist_and_reopen_round_trip()
    print("OK")
