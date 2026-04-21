"""Power Query-style ordered step history for the ingestion pipeline.

Each step records what was done and a snapshot of the dataframe at that
point so the user can navigate back and forth without re-running anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class Step:
    name: str
    summary: str
    df: pd.DataFrame
    meta: dict = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return 0 if self.df is None else len(self.df)

    @property
    def cols(self) -> int:
        return 0 if self.df is None else len(self.df.columns)


class StepHistory:
    """Ordered list of pipeline steps with an active pointer."""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.active_index: int = -1

    # ---- mutation -------------------------------------------------------

    def add(self, name: str, summary: str, df: pd.DataFrame,
            meta: Optional[dict] = None) -> None:
        snap = df.copy() if df is not None else df
        self.steps.append(Step(name=name, summary=summary, df=snap, meta=meta or {}))
        self.active_index = len(self.steps) - 1

    def replace_after(self, idx: int, name: str, summary: str,
                      df: pd.DataFrame, meta: Optional[dict] = None) -> None:
        """Drop everything after idx (inclusive) and append a new step."""
        self.steps = self.steps[:idx]
        self.add(name, summary, df, meta)

    def drop_later(self) -> None:
        """Discard steps after the active one."""
        self.steps = self.steps[: self.active_index + 1]

    def go_to(self, idx: int) -> None:
        if 0 <= idx < len(self.steps):
            self.active_index = idx

    def redo_latest(self) -> None:
        if self.steps:
            self.active_index = len(self.steps) - 1

    # ---- access ---------------------------------------------------------

    def is_empty(self) -> bool:
        return not self.steps

    def current(self) -> Optional[Step]:
        if not self.steps or self.active_index < 0:
            return None
        return self.steps[self.active_index]

    def current_df(self) -> Optional[pd.DataFrame]:
        s = self.current()
        return s.df if s is not None else None

    def latest(self) -> Optional[Step]:
        return self.steps[-1] if self.steps else None

    def find_last(self, name: str) -> Optional[Step]:
        for s in reversed(self.steps):
            if s.name == name:
                return s
        return None

    def has_later_steps(self) -> bool:
        return self.active_index < len(self.steps) - 1

    def __len__(self) -> int:
        return len(self.steps)
