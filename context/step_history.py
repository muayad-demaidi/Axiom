"""Power Query-style ordered step history for the ingestion pipeline.

Each step records what was done and a snapshot of the dataframe at that
point so the user can navigate back and forth without re-running anything.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from context.type_inference import (
    ColumnType,
    apply_schema,
    cast_column,
)


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

    # ---- serialization --------------------------------------------------

    _STEP_TYPE_MAP = {
        "Source": "source",
        "Promoted Headers": "promoted_headers",
        "Changed Type": "changed_type",
        "Cleaning": "cleaning",
        "Changed Type (manual)": "manual_type",
    }

    def to_recipes(self) -> list[dict]:
        """Serialize steps (without dataframes) for DB persistence."""
        out: list[dict] = []
        for s in self.steps:
            meta = s.meta or {}
            # Cleaning substeps are emitted by _apply_cleaning_substeps
            # with their substep_key in meta — keep them as a distinct
            # recipe type so rebuild knows to call the substep function.
            if meta.get("substep_key"):
                rtype = "cleaning_substep"
            else:
                rtype = self._STEP_TYPE_MAP.get(s.name, "custom")
            out.append({
                "type": rtype,
                "name": s.name,
                "summary": s.summary,
                "meta": _json_safe(meta),
            })
        return out


def _json_safe(obj: Any) -> Any:
    """Best-effort conversion of pipeline meta to JSON-friendly primitives."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    try:
        import numpy as np  # local import keeps module light
        if isinstance(obj, np.generic):
            return obj.item()
    except Exception:
        pass
    return str(obj)


def serialize_source_df(df: pd.DataFrame) -> bytes:
    """Encode the source dataframe as parquet bytes for storage."""
    buf = io.BytesIO()
    safe = df.copy()
    safe.columns = [str(c) for c in safe.columns]
    safe.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()


def deserialize_source_df(blob: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(blob), engine="pyarrow")


def rebuild_history_from_recipes(
    source_df: pd.DataFrame,
    recipes: list[dict],
    active_index: Optional[int] = None,
) -> "StepHistory":
    """Replay stored recipes against the source dataframe to rebuild a StepHistory.

    Each recipe drives a deterministic transform; we re-execute them so the
    snapshot dataframes match what the user last saw.
    """
    from data_cleaner import clean_data  # avoid circular import at module load

    history = StepHistory()
    current = source_df

    for recipe in recipes or []:
        rtype = recipe.get("type")
        name = recipe.get("name") or rtype or "Step"
        summary = recipe.get("summary") or ""
        meta = recipe.get("meta") or {}
        # Universal enable flag — honored for every non-source step kind so
        # users can disable Promoted Headers / Changed Type / manual / etc.
        # and the chain still replays correctly. Source is always on.
        enabled = bool(meta.get("enabled", True))

        if rtype == "source":
            current = source_df
            history.add(name, summary, current, meta=meta)
        elif rtype == "promoted_headers":
            if enabled:
                # Promote first row to column names if the snapshot looks
                # like an unpromoted Source view (auto-named Column1..N).
                if (len(current) > 0 and
                        all(str(c).startswith("Column") for c in current.columns)):
                    promoted = current.iloc[1:].reset_index(drop=True)
                    promoted.columns = [str(v) for v in current.iloc[0].tolist()]
                    current = promoted
            history.add(name, summary, current, meta=meta)
        elif rtype == "changed_type":
            schema_dicts = meta.get("schema") or []
            schema = [ColumnType(**{
                "column": d.get("column"),
                "inferred_type": d.get("inferred_type", "text"),
                "confidence": float(d.get("confidence", 0.0)),
                "sample_values": list(d.get("sample_values") or []),
                "notes": d.get("notes", "") or "",
            }) for d in schema_dicts if d.get("column") is not None]
            if enabled and schema:
                current = apply_schema(current, schema)
            history.add(name, summary, current, meta=meta)
        elif rtype == "cleaning":
            if enabled:
                current, _report = clean_data(current)
            history.add(name, summary, current, meta=meta)
        elif rtype == "cleaning_substep":
            from data_cleaner import SUBSTEP_FUNCS
            key = meta.get("substep_key")
            params = meta.get("substep_params") or {}
            if enabled and key in SUBSTEP_FUNCS:
                current, _summary, _details = SUBSTEP_FUNCS[key](current, **params)
            history.add(name, summary, current, meta=meta)
        elif rtype == "manual_type":
            override = meta.get("override") or {}
            if enabled and override:
                base = current.copy()
                for col, t in override.items():
                    if col in base.columns:
                        base[col] = cast_column(base[col], t)
                current = base
            history.add(name, summary, current, meta=meta)
        else:
            history.add(name, summary, current, meta=meta)

    if active_index is not None and 0 <= active_index < len(history.steps):
        history.active_index = active_index
    return history
