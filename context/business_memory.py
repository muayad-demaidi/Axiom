"""Business context memory — persisted in replit.db, keyed per user.

Stores the user's industry, fiscal year start month, top KPIs and currency
so that downstream modules (date intelligence, auto-discovery, AI chat,
proactive agent) can reason in the user's actual business terms.
"""
from __future__ import annotations

import json
from typing import Optional

import streamlit as st
from replit import db

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_INDUSTRIES = ["Retail", "Finance", "Healthcare", "Manufacturing", "Real Estate", "Other"]
_CURRENCIES = ["USD", "SAR", "AED", "EUR", "GBP", "Other"]


def _key(user_id: int | str) -> str:
    return f"biz_ctx_{user_id}"


def get_context(user_id: int | str) -> Optional[dict]:
    """Return the stored business profile for this user, or None."""
    if user_id is None:
        return None
    raw = db.get(_key(user_id))
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def context_is_set(user_id: int | str) -> bool:
    return get_context(user_id) is not None


def save_context(user_id: int | str, ctx: dict) -> None:
    db[_key(user_id)] = json.dumps(ctx)


def clear_context(user_id: int | str) -> None:
    k = _key(user_id)
    if k in db:
        del db[k]


def render_sidebar_badge(user_id: int | str) -> None:
    """Compact sidebar marker shown when a profile is active."""
    if context_is_set(user_id):
        st.sidebar.success("Business profile active")


def run_onboarding_wizard(user_id: int | str) -> Optional[dict]:
    """Render the onboarding form. Returns the saved context dict on submit,
    None otherwise. Caller decides when to display this (e.g. first login,
    or from the Settings section).
    """
    existing = get_context(user_id) or {}
    with st.form("biz_onboarding_form", clear_on_submit=False):
        st.markdown("#### Business profile")
        st.caption(
            "Tell AXIOM about your business so insights, "
            "comparisons and alerts use the right context."
        )

        industry = st.selectbox(
            "Industry",
            _INDUSTRIES,
            index=_INDUSTRIES.index(existing.get("industry", "Retail"))
            if existing.get("industry") in _INDUSTRIES else 0,
        )
        fiscal_year_start = st.selectbox(
            "Fiscal year starts in",
            _MONTHS,
            index=_MONTHS.index(existing.get("fiscal_year_start", "January"))
            if existing.get("fiscal_year_start") in _MONTHS else 0,
        )

        st.markdown("**Top 3 KPIs** (used to prioritise alerts and AI focus)")
        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_1 = st.text_input("KPI 1", value=existing.get("kpi_1", ""))
        with c2:
            kpi_2 = st.text_input("KPI 2", value=existing.get("kpi_2", ""))
        with c3:
            kpi_3 = st.text_input("KPI 3", value=existing.get("kpi_3", ""))

        currency = st.selectbox(
            "Reporting currency",
            _CURRENCIES,
            index=_CURRENCIES.index(existing.get("currency", "USD"))
            if existing.get("currency") in _CURRENCIES else 0,
        )

        submitted = st.form_submit_button("Save profile")

    if submitted:
        ctx = {
            "industry": industry,
            "fiscal_year_start": fiscal_year_start,
            "fiscal_start_month": _MONTHS.index(fiscal_year_start) + 1,
            "kpi_1": kpi_1.strip(),
            "kpi_2": kpi_2.strip(),
            "kpi_3": kpi_3.strip(),
            "kpis": [k.strip() for k in (kpi_1, kpi_2, kpi_3) if k and k.strip()],
            "currency": currency,
        }
        save_context(user_id, ctx)
        st.success("Business profile saved.")
        return ctx

    return None
