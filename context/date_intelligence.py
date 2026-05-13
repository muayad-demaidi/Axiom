"""Date intelligence — fiscal year detection, date dimension table, and
period-over-period comparison helpers.

All public functions are pure (no Streamlit side-effects) except
`detect_fiscal_year` which optionally surfaces a confirmation prompt
when confidence is medium.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st
from replit import db


# --------------------------------------------------------------------------
# Fiscal year detection
# --------------------------------------------------------------------------

def _candidate_date_columns(df: pd.DataFrame) -> list[str]:
    cands: list[str] = []
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            cands.append(col)
            continue
        if s.dtype == object:
            sample = s.dropna().astype(str).head(50)
            if sample.empty:
                continue
            try:
                parsed = pd.to_datetime(sample, errors="coerce", dayfirst=True)
                if parsed.notna().mean() > 0.7:
                    cands.append(col)
            except Exception:
                pass
    return cands


def detect_fiscal_year(df: pd.DataFrame) -> dict:
    """Infer the fiscal-year start month from the first usable date column.

    Heuristic: the modal month of the *minimum* date in each calendar year
    is treated as the likely fiscal-year start. Confidence is the share of
    years that agree on that month.
    """
    result = {
        "detected_start_month": 1,
        "confidence": 0.0,
        "basis_column": None,
        "sample_dates": [],
    }

    cols = _candidate_date_columns(df)
    if not cols:
        return result

    col = cols[0]
    s = df[col]
    if not pd.api.types.is_datetime64_any_dtype(s):
        s = pd.to_datetime(s, errors="coerce", dayfirst=True)
    s = s.dropna()
    if s.empty:
        return result

    by_year = s.groupby(s.dt.year).min().dt.month
    if by_year.empty:
        return result

    modal_month = int(by_year.mode().iloc[0])
    confidence = float((by_year == modal_month).mean())

    result.update(
        detected_start_month=modal_month,
        confidence=round(confidence, 3),
        basis_column=col,
        sample_dates=[d.strftime("%Y-%m-%d") for d in s.head(5)],
    )
    return result


def _fiscal_confirm_key(dataset_id) -> str:
    return f"fiscal_confirm_{dataset_id}"


def confirm_fiscal_year_with_user(detection: dict, dataset_id) -> int:
    """If confidence is medium, prompt the user once per dataset_id and
    persist the answer in replit.db. High confidence -> silent. Low
    confidence -> default to calendar year (Jan).

    Returns the chosen fiscal-start month (1..12).
    """
    conf = detection.get("confidence", 0.0)
    detected = int(detection.get("detected_start_month", 1) or 1)

    cache_key = _fiscal_confirm_key(dataset_id)
    cached = db.get(cache_key)
    if cached is not None:
        try:
            return int(cached)
        except (TypeError, ValueError):
            pass

    if conf > 0.95:
        st.session_state[f"fiscal_silent_log_{dataset_id}"] = detection
        db[cache_key] = detected
        return detected

    if conf <= 0.60:
        st.info(
            "Fiscal-year start could not be detected with confidence — "
            "defaulting to the calendar year (January)."
        )
        db[cache_key] = 1
        return 1

    # Medium confidence: surface a single confirm widget
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    st.warning(
        f"Detected fiscal-year start: **{months[detected - 1]}** "
        f"(confidence {conf:.0%}, based on column `{detection.get('basis_column')}`). "
        "Confirm or change below."
    )
    chosen = st.selectbox(
        "Fiscal year starts in",
        months,
        index=detected - 1,
        key=f"fiscal_pick_{dataset_id}",
    )
    if st.button("Confirm fiscal year", key=f"fiscal_btn_{dataset_id}"):
        m = months.index(chosen) + 1
        db[cache_key] = m
        st.success(f"Saved. Fiscal year for this dataset starts in {chosen}.")
        return m

    return detected


# --------------------------------------------------------------------------
# Date dimension table
# --------------------------------------------------------------------------

def build_date_table(
    df: pd.DataFrame,
    date_col: str,
    fiscal_start_month: int = 1,
) -> pd.DataFrame:
    """Return a date dimension DataFrame for every date in `df[date_col]`."""
    series = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True).dropna().drop_duplicates()
    if series.empty:
        return pd.DataFrame(
            columns=[
                "date", "fiscal_year", "fiscal_quarter", "fiscal_month",
                "calendar_year", "calendar_month", "is_weekend",
            ]
        )

    fiscal_start_month = int(fiscal_start_month or 1)
    if not 1 <= fiscal_start_month <= 12:
        fiscal_start_month = 1

    s = pd.DatetimeIndex(sorted(series))
    cal_year = s.year.astype(int)
    cal_month = s.month.astype(int)

    # fiscal_month: 1 when calendar month == fiscal_start_month, wraps to 12
    fiscal_month = ((cal_month - fiscal_start_month) % 12) + 1
    # fiscal_year is labelled by the year the fiscal year ENDS in
    fiscal_year = np.where(cal_month >= fiscal_start_month, cal_year + 1, cal_year)
    if fiscal_start_month == 1:
        fiscal_year = cal_year
    fiscal_quarter = ((fiscal_month - 1) // 3) + 1

    return pd.DataFrame({
        "date": s,
        "fiscal_year": fiscal_year.astype(int),
        "fiscal_quarter": fiscal_quarter.astype(int),
        "fiscal_month": fiscal_month.astype(int),
        "calendar_year": cal_year,
        "calendar_month": cal_month,
        "is_weekend": s.dayofweek.isin([5, 6]),
    })


# --------------------------------------------------------------------------
# Period-over-period comparison
# --------------------------------------------------------------------------

def compare_periods(
    df: pd.DataFrame,
    metric_col: str,
    date_col: str,
    mode: str = "YoY",
    fiscal_start_month: int = 1,
) -> pd.DataFrame:
    """Aggregate `metric_col` by period and produce a current/prior comparison.

    Mode  | period grain
    ------|--------------------
    YoY   | fiscal year
    QoQ   | fiscal quarter
    MoM   | calendar month
    """
    if metric_col not in df.columns or date_col not in df.columns:
        return pd.DataFrame(
            columns=["period", "current_value", "prior_value", "change", "pct_change"]
        )

    work = df[[date_col, metric_col]].copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce", dayfirst=True)
    work[metric_col] = pd.to_numeric(work[metric_col], errors="coerce")
    work = work.dropna(subset=[date_col, metric_col])
    if work.empty:
        return pd.DataFrame(
            columns=["period", "current_value", "prior_value", "change", "pct_change"]
        )

    dim = build_date_table(work, date_col, fiscal_start_month).set_index("date")
    work = work.set_index(date_col).join(dim, how="left")

    mode = (mode or "YoY").upper()
    if mode == "YOY":
        grouped = work.groupby("fiscal_year")[metric_col].sum()
        labels = grouped.index.astype(str)
    elif mode == "QOQ":
        idx = work["fiscal_year"].astype(str) + "-Q" + work["fiscal_quarter"].astype(str)
        grouped = work.assign(_p=idx).groupby("_p")[metric_col].sum()
        labels = grouped.index.astype(str)
    elif mode == "MOM":
        idx = work["calendar_year"].astype(str) + "-" + work["calendar_month"].astype(str).str.zfill(2)
        grouped = work.assign(_p=idx).groupby("_p")[metric_col].sum()
        labels = grouped.index.astype(str)
    else:
        raise ValueError(f"Unknown mode: {mode!r} (use YoY, QoQ or MoM)")

    grouped = grouped.sort_index()
    current = grouped.values.astype(float)
    prior = np.concatenate([[np.nan], current[:-1]])
    change = current - prior
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(np.abs(prior) > 1e-12, change / prior * 100.0, np.nan)

    return pd.DataFrame({
        "period": list(labels),
        "current_value": current,
        "prior_value": prior,
        "change": change,
        "pct_change": pct,
    })
