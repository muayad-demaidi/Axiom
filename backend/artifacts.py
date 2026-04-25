"""Routes for chat artifacts, dataset preview/profile/insights/suggestions,
and the per-session "Final Report" (JSON for live preview + PDF download).

Artifacts are tool-call outputs persisted under a chat session. The chat
endpoint creates them when a tool is invoked; this router exposes CRUD
operations and the report compilation that consumes them.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import models  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session
from .datasets import load_dataset_dataframe
from .insights import build_profile, surprise_insights, suggested_questions
from . import insights as insights_mod

router = APIRouter(tags=["artifacts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_session(db, session_id: int, user_id: int):
    sess = models.get_chat_session(db, session_id, user_id)
    if not sess:
        raise HTTPException(404, "Chat session not found")
    return sess


def _require_dataset_for_user(db, dataset_id: int, user_id: int):
    # Strict: never fall back to legacy `user_id IS NULL` rows here, since
    # these endpoints expose previews + column-level stats over the wire.
    record = models.get_dataset_record_strict(db, dataset_id, user_id=user_id)
    if not record:
        raise HTTPException(404, "Dataset not found")
    return record


def _artifact_view(a) -> dict:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "project_id": a.project_id,
        "dataset_id": a.dataset_id,
        "kind": a.kind,
        "title": a.title,
        "params": a.params or {},
        "result": a.result or {},
        "pinned": bool(a.pinned),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Dataset preview / profile / insights / suggestions
# ---------------------------------------------------------------------------

@router.get("/api/datasets/{dataset_id}/preview")
async def dataset_preview(
    dataset_id: int,
    rows: int = 20,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """First N rows + column metadata so the chat can render an
    interactive table the moment a file lands."""
    record = _require_dataset_for_user(db, dataset_id, user.id)
    df = load_dataset_dataframe(record)
    n = max(1, min(rows, 200))
    return jsonify(
        {
            "id": record.id,
            "filename": record.filename,
            "dataset_name": record.dataset_name,
            "rows": int(len(df)),
            "cols": int(df.shape[1]),
            "columns": [
                {"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns
            ],
            "preview": df.head(n).to_dict(orient="records"),
        }
    )


@router.get("/api/datasets/{dataset_id}/profile")
async def dataset_profile(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Per-column profile with caching on `summary_stats.profile`."""
    record = _require_dataset_for_user(db, dataset_id, user.id)
    cached = (record.summary_stats or {}).get("_axiom_profile")
    if cached:
        return jsonify(cached)
    df = load_dataset_dataframe(record)
    profile = build_profile(df)
    try:
        ss = dict(record.summary_stats or {})
        ss["_axiom_profile"] = profile
        record.summary_stats = ss
        db.commit()
    except Exception:
        db.rollback()
    return jsonify(profile)


@router.get("/api/datasets/{dataset_id}/insights")
async def dataset_insights(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record = _require_dataset_for_user(db, dataset_id, user.id)
    cached = (record.summary_stats or {}).get("_axiom_insights")
    if cached is not None:
        return jsonify({"insights": cached})
    df = load_dataset_dataframe(record)
    items = surprise_insights(df)
    try:
        ss = dict(record.summary_stats or {})
        ss["_axiom_insights"] = items
        record.summary_stats = ss
        db.commit()
    except Exception:
        db.rollback()
    return jsonify({"insights": items})


@router.get("/api/datasets/{dataset_id}/suggestions")
async def dataset_suggestions(
    dataset_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record = _require_dataset_for_user(db, dataset_id, user.id)
    df = load_dataset_dataframe(record)
    return jsonify({"suggestions": suggested_questions(df)})


@router.post("/api/datasets/{dataset_id}/auto-profile")
async def dataset_auto_profile(
    dataset_id: int,
    rows: int = 20,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """One-shot endpoint the chat fires the moment a file lands.

    Returns preview + profile + surprise insights + suggested questions
    in a single payload. Profile + insights are cached on the dataset's
    `summary_stats` JSON blob so subsequent calls are instant.
    """
    record = _require_dataset_for_user(db, dataset_id, user.id)
    df = load_dataset_dataframe(record)
    n = max(1, min(rows, 200))

    ss = dict(record.summary_stats or {})
    profile = ss.get("_axiom_profile")
    if not profile:
        profile = build_profile(df)
        ss["_axiom_profile"] = profile
    insights_items = ss.get("_axiom_insights")
    if insights_items is None:
        insights_items = surprise_insights(df)
        ss["_axiom_insights"] = insights_items
    try:
        record.summary_stats = ss
        db.commit()
    except Exception:
        db.rollback()

    return jsonify(
        {
            "id": record.id,
            "filename": record.filename,
            "dataset_name": record.dataset_name,
            "rows": int(len(df)),
            "cols": int(df.shape[1]),
            "columns": [
                {"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns
            ],
            "preview": df.head(n).to_dict(orient="records"),
            "profile": profile,
            "insights": insights_items,
            "suggestions": suggested_questions(df),
        }
    )


# ---------------------------------------------------------------------------
# Artifact CRUD
# ---------------------------------------------------------------------------

@router.get("/api/chats/{session_id}/artifacts")
async def list_artifacts(
    session_id: int,
    kind: str | None = None,
    pinned_only: bool = False,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_session(db, session_id, user.id)
    rows = models.list_chat_artifacts(
        db, session_id, user.id, kind=kind, pinned_only=pinned_only
    )
    return [_artifact_view(a) for a in rows]


class ArtifactPinRequest(BaseModel):
    pinned: bool


@router.patch("/api/artifacts/{artifact_id}/pin")
async def pin_artifact(
    artifact_id: int,
    req: ArtifactPinRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    a = models.set_artifact_pin(db, artifact_id, user.id, req.pinned)
    if not a:
        raise HTTPException(404, "Artifact not found")
    return _artifact_view(a)


@router.delete("/api/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    ok = models.delete_chat_artifact(db, artifact_id, user.id)
    if not ok:
        raise HTTPException(404, "Artifact not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Final report (JSON view + PDF download)
# ---------------------------------------------------------------------------

def _gather_report_payload(
    db, sess, user_id: int, pinned_only: bool = True
) -> dict[str, Any]:
    """Compose everything the report renderer needs from one session."""
    artifacts = models.list_chat_artifacts(
        db, sess.id, user_id, pinned_only=pinned_only
    )
    by_kind: dict[str, list] = {
        "profile": [], "prediction": [], "chart": [],
        "cluster": [], "insight": [], "qa": [],
    }
    dataset_ids: set[int] = set()
    for a in artifacts:
        by_kind.setdefault(a.kind, []).append(_artifact_view(a))
        if a.dataset_id:
            dataset_ids.add(a.dataset_id)

    # Conversational turns make for a "Q & A" appendix.
    msgs = models.get_session_messages(db, sess.id)
    qa = [
        {
            "id": m.id,
            "user": m.user_message,
            "ai": m.ai_response,
            "ts": m.timestamp.isoformat() if m.timestamp else None,
        }
        for m in msgs
        if (m.user_message or "").strip()
    ]

    # Dataset cards (the report should show what data backed each
    # artifact, not just the artifacts in isolation).
    datasets: list[dict] = []
    for did in dataset_ids:
        rec = models.get_dataset_record(db, did, user_id=user_id)
        if not rec:
            continue
        datasets.append(
            {
                "id": rec.id,
                "name": rec.dataset_name or rec.filename,
                "rows": rec.row_count,
                "cols": rec.column_count,
            }
        )

    # Session-wide LLM synthesis (cached as a hidden artifact so we don't
    # reburn tokens every time the user refreshes the report page).
    synthesis = _get_or_build_synthesis(db, sess, user_id, by_kind)

    # Deterministic ±10/±25 % what-if recommendations for every prediction
    # artifact (computed here so both the JSON view and the PDF stay in
    # lockstep).
    what_if: list[dict] = []
    for art in by_kind.get("prediction", []):
        rows = insights_mod.what_if_recommendations(art.get("result") or {})
        if rows:
            what_if.append(
                {
                    "title": art.get("title") or "Prediction",
                    "target": (art.get("result") or {}).get("target"),
                    "rows": rows,
                }
            )

    return {
        "session": {
            "id": sess.id,
            "project_id": sess.project_id,
            "title": sess.title,
            "created_at": sess.created_at.isoformat() if sess.created_at else None,
        },
        "datasets": datasets,
        "artifacts": by_kind,
        "qa": qa,
        "synthesis": synthesis,
        "what_if": what_if,
        "generated_at": datetime.utcnow().isoformat(),
    }


def _get_or_build_synthesis(db, sess, user_id: int, by_kind: dict) -> dict:
    """Cache the LLM synthesis as a kind='synthesis' artifact on the session.

    The cache key is the sorted tuple of artifact ids contributing to the
    summary, so adding/removing a pin invalidates it automatically.
    """
    contributors = []
    for kind in ("profile", "insight", "chart", "prediction", "cluster"):
        for a in by_kind.get(kind, []):
            contributors.append(int(a.get("id") or 0))
    cache_key = ",".join(str(x) for x in sorted(contributors))

    existing = models.list_chat_artifacts(db, sess.id, user_id, kind="synthesis")
    for a in existing:
        if (a.params or {}).get("cache_key") == cache_key:
            return a.result or {}

    synthesis = insights_mod.synthesize_session_insights(by_kind)
    try:
        models.save_chat_artifact(
            db,
            session_id=sess.id,
            user_id=user_id,
            project_id=sess.project_id,
            kind="synthesis",
            title="Session synthesis",
            params={"cache_key": cache_key},
            result=synthesis,
            dataset_id=None,
            pinned=False,
        )
    except Exception:
        pass
    return synthesis


@router.get("/api/chats/{session_id}/report")
async def report_json(
    session_id: int,
    pinned_only: bool = True,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    sess = _require_session(db, session_id, user.id)
    return jsonify(_gather_report_payload(db, sess, user.id, pinned_only=pinned_only))


@router.post("/api/chats/{session_id}/report.pdf")
async def report_pdf(
    session_id: int,
    pinned_only: bool = True,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Produce the final PDF report for a chat session.

    Layout:
      1. Cover (title, project, generated-at, dataset list)
      2. Surprise insights ribbon (text)
      3. Profile per dataset (column table)
      4. Q & A appendix (user/AI turns)
      5. Charts (rendered from artifact `result` payloads)
      6. Predictions (metrics + top features + what-if recommendation)
      7. Clusters (sizes + centroids)
    """
    try:
        from io import BytesIO

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"reportlab not available: {exc}")

    sess = _require_session(db, session_id, user.id)
    payload = _gather_report_payload(db, sess, user.id, pinned_only=pinned_only)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"AXIOM Report — {payload['session']['title']}",
    )
    styles = getSampleStyleSheet()
    story: list = []
    body_added = False  # set to True the moment we append a real artifact section

    def esc(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    # -------- Cover ----------------------------------------------------
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("AXIOM Final Report &nbsp;·&nbsp; التقرير النهائي", styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(
        Paragraph(
            f"<b>Session / الجلسة:</b> {esc(payload['session']['title'] or 'Untitled')}",
            styles["BodyText"],
        )
    )
    story.append(
        Paragraph(
            f"Generated / أنشئ بتاريخ {payload['generated_at'][:19]} UTC",
            styles["BodyText"],
        )
    )
    if payload["datasets"]:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph("<b>Datasets / مجموعات البيانات</b>", styles["Heading3"]))
        for d in payload["datasets"]:
            story.append(
                Paragraph(
                    f"• {esc(d['name'])} — {d['rows']:,} rows × {d['cols']} cols",
                    styles["BodyText"],
                )
            )
    story.append(PageBreak())

    # -------- Session synthesis (LLM) ----------------------------------
    syn = payload.get("synthesis") or {}
    if syn.get("executive_summary") or syn.get("key_findings"):
        body_added = True
        story.append(Paragraph("<b>Insights synthesis / خلاصة الجلسة</b>", styles["Heading2"]))
        if syn.get("executive_summary"):
            story.append(Paragraph(esc(syn["executive_summary"]), styles["BodyText"]))
            story.append(Spacer(1, 0.2 * cm))
        if syn.get("key_findings"):
            story.append(Paragraph("<b>Key findings / أبرز النتائج</b>", styles["Heading3"]))
            for k in syn["key_findings"]:
                story.append(Paragraph(f"• {esc(str(k))}", styles["BodyText"]))
        if syn.get("recommendations"):
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph("<b>Recommendations / التوصيات</b>", styles["Heading3"]))
            for r in syn["recommendations"]:
                story.append(Paragraph(f"• {esc(str(r))}", styles["BodyText"]))
        story.append(Spacer(1, 0.4 * cm))

    # -------- Surprise insights ----------------------------------------
    insights = payload["artifacts"].get("insight", [])
    if insights:
        body_added = True
        story.append(Paragraph("<b>Surprise insights / رؤى مفاجئة</b>", styles["Heading2"]))
        for art in insights:
            for it in (art.get("result") or {}).get("items", []):
                line = f"• [{(it.get('severity') or 'info').upper()}] {it.get('headline','')}"
                story.append(Paragraph(esc(line), styles["BodyText"]))
                if it.get("subtitle"):
                    story.append(
                        Paragraph(
                            f"<font size=8 color='#6b7280'>{esc(it['subtitle'])}</font>",
                            styles["BodyText"],
                        )
                    )
        story.append(Spacer(1, 0.4 * cm))

    # -------- Profiles -------------------------------------------------
    profiles = payload["artifacts"].get("profile", [])
    if profiles:
        body_added = True
        story.append(Paragraph("<b>Data profile / تعريف البيانات</b>", styles["Heading2"]))
        for art in profiles:
            res = art.get("result") or {}
            story.append(
                Paragraph(f"<b>{esc(art.get('title') or 'Profile')}</b>", styles["Heading3"])
            )
            cols = res.get("columns") or []
            data = [["Column", "Dtype", "Non-null", "Missing", "Unique"]]
            for c in cols[:60]:
                data.append(
                    [
                        str(c.get("name", "")),
                        str(c.get("dtype", "")),
                        f"{c.get('non_null', 0):,}",
                        f"{c.get('missing', 0):,}",
                        f"{c.get('unique', 0):,}",
                    ]
                )
            tbl = Table(data, colWidths=[6 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
            tbl.setStyle(_table_style())
            story.append(tbl)
            story.append(Spacer(1, 0.4 * cm))

    # -------- Q & A ----------------------------------------------------
    if payload["qa"]:
        body_added = True
        story.append(PageBreak())
        story.append(Paragraph("<b>Conversation transcript / نص المحادثة</b>", styles["Heading2"]))
        for turn in payload["qa"][:80]:
            story.append(
                Paragraph(
                    f"<b>You:</b> {esc((turn['user'] or '')[:800])}",
                    styles["BodyText"],
                )
            )
            ai_text = (turn["ai"] or "")[:1600]
            for block in ai_text.split("\n"):
                if block.strip():
                    story.append(Paragraph(esc(block), styles["BodyText"]))
            story.append(Spacer(1, 0.2 * cm))

    # -------- Charts ---------------------------------------------------
    charts = payload["artifacts"].get("chart", [])
    if charts:
        body_added = True
        story.append(PageBreak())
        story.append(Paragraph("<b>Charts / المخططات</b>", styles["Heading2"]))
        for art in charts:
            png = _render_chart_png(art.get("result") or {})
            title = esc(art.get("title") or "Chart")
            story.append(Paragraph(f"<b>{title}</b>", styles["Heading3"]))
            if png is not None:
                story.append(Image(io.BytesIO(png), width=15 * cm, height=8 * cm))
            else:
                story.append(
                    Paragraph(
                        "<font color='#6b7280'>Chart could not be rendered.</font>",
                        styles["BodyText"],
                    )
                )
            story.append(Spacer(1, 0.4 * cm))

    # -------- Predictions ----------------------------------------------
    preds = payload["artifacts"].get("prediction", [])
    if preds:
        body_added = True
        story.append(PageBreak())
        story.append(Paragraph("<b>Predictions / التنبؤات</b>", styles["Heading2"]))
        for art in preds:
            res = art.get("result") or {}
            story.append(
                Paragraph(
                    f"<b>{esc(art.get('title') or 'Prediction')}</b>",
                    styles["Heading3"],
                )
            )
            metrics = res.get("metrics") or {}
            metric_str = ", ".join(
                f"{k} = {v}" for k, v in metrics.items()
            )
            if metric_str:
                story.append(Paragraph(f"Metrics: {esc(metric_str)}", styles["BodyText"]))
            feats = res.get("feature_importance") or []
            if feats:
                data = [["Feature", "Importance"]]
                for f in feats[:15]:
                    data.append([str(f.get("feature", "")), f"{f.get('importance', 0):.4f}"])
                tbl = Table(data, colWidths=[8 * cm, 4 * cm])
                tbl.setStyle(_table_style())
                story.append(tbl)
            recs = (art.get("params") or {}).get("recommendation")
            if recs:
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph(f"What-if recommendation: {esc(recs)}", styles["BodyText"]))
            story.append(Spacer(1, 0.4 * cm))

    # -------- What-if recommendations ----------------------------------
    wifs = payload.get("what_if") or []
    if wifs:
        body_added = True
        story.append(PageBreak())
        story.append(
            Paragraph(
                "<b>What-if recommendations / توصيات افتراضية</b>",
                styles["Heading2"],
            )
        )
        for w in wifs:
            story.append(
                Paragraph(
                    f"<b>{esc(w.get('title') or 'Prediction')}</b> "
                    f"<font color='#6b7280'>(target / الهدف: {esc(str(w.get('target') or ''))})</font>",
                    styles["Heading3"],
                )
            )
            for feat in w.get("rows", []):
                data = [["Shift %", "New value", "Δ predicted", "Predicted value"]]
                for row in feat.get("rows", []):
                    data.append(
                        [
                            f"{row.get('shift_pct'):+d}%",
                            f"{row.get('new_value')}",
                            f"{row.get('predicted_delta'):+.4f}",
                            f"{row.get('predicted_value'):.4f}",
                        ]
                    )
                story.append(
                    Paragraph(
                        f"<b>{esc(str(feat.get('feature')))}</b> "
                        f"<font size=8 color='#6b7280'>(baseline {feat.get('baseline_value')})</font>",
                        styles["BodyText"],
                    )
                )
                tbl = Table(
                    data,
                    colWidths=[2.5 * cm, 3.5 * cm, 3.5 * cm, 4 * cm],
                )
                tbl.setStyle(_table_style())
                story.append(tbl)
                story.append(Spacer(1, 0.3 * cm))

    # -------- Clusters -------------------------------------------------
    clusters = payload["artifacts"].get("cluster", [])
    if clusters:
        body_added = True
        story.append(PageBreak())
        story.append(Paragraph("<b>Clusters / المجموعات</b>", styles["Heading2"]))
        for art in clusters:
            res = art.get("result") or {}
            story.append(
                Paragraph(
                    f"<b>{esc(art.get('title') or 'Cluster')}</b>",
                    styles["Heading3"],
                )
            )
            sizes = res.get("cluster_sizes") or {}
            if sizes:
                data = [["Cluster", "Size"]]
                for k, v in sorted(sizes.items(), key=lambda kv: int(kv[0])):
                    data.append([f"#{k}", f"{int(v):,}"])
                tbl = Table(data, colWidths=[4 * cm, 4 * cm])
                tbl.setStyle(_table_style())
                story.append(tbl)
            story.append(Spacer(1, 0.4 * cm))

    if not body_added:
        story.append(
            Paragraph("No artifacts pinned to this report yet.", styles["BodyText"])
        )

    doc.build(story)
    buf.seek(0)
    filename = f"axiom-final-report-{sess.id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _table_style():
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "LEFT"),
        ]
    )


def _render_chart_png(result: dict) -> bytes | None:
    """Render a Matplotlib PNG from an artifact's chart result payload.

    Mirrors the same chart palette the Recharts frontend uses
    (bar/line/scatter/pie/histogram/box/heatmap) so the PDF and the UI
    stay visually aligned.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    chart = (result or {}).get("chart")
    if not chart:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 4))
    try:
        if chart in ("bar", "histogram"):
            pts = result.get("points") or []
            xs = [str(p.get("x") or p.get("bin") or "") for p in pts]
            ys = [float(p.get("y") or p.get("count") or 0) for p in pts]
            ax.bar(range(len(xs)), ys, color="#1d4ed8")
            ax.set_xticks(range(len(xs)))
            ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=7)
        elif chart == "line":
            pts = result.get("points") or []
            xs = [str(p.get("x", "")) for p in pts]
            ys = [float(p.get("y", 0)) for p in pts]
            ax.plot(range(len(xs)), ys, color="#1d4ed8", linewidth=1.5)
        elif chart == "scatter":
            pts = result.get("points") or []
            xs = [float(p.get("x", 0)) for p in pts]
            ys = [float(p.get("y", 0)) for p in pts]
            ax.scatter(xs, ys, color="#1d4ed8", s=10, alpha=0.6)
        elif chart == "pie":
            pts = result.get("points") or []
            labels = [str(p.get("name", "")) for p in pts[:12]]
            sizes = [float(p.get("value", 0)) for p in pts[:12]]
            ax.pie(sizes, labels=labels, autopct="%1.0f%%", textprops={"fontsize": 7})
        elif chart == "box":
            # Use bxp() so we render the precomputed five-number summary
            # directly. boxplot() would treat [min,q1,median,q3,max] as
            # raw observations and recompute (wrong) quartiles from them.
            pts = result.get("points") or []
            stats = []
            labels = []
            for p in pts:
                stats.append(
                    {
                        "med": float(p.get("median", 0) or 0),
                        "q1": float(p.get("q1", 0) or 0),
                        "q3": float(p.get("q3", 0) or 0),
                        "whislo": float(p.get("min", 0) or 0),
                        "whishi": float(p.get("max", 0) or 0),
                        "fliers": [],
                        "label": str(p.get("column", "")),
                    }
                )
                labels.append(str(p.get("column", "")))
            if stats:
                ax.bxp(stats, showfliers=False)
                ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        elif chart == "heatmap":
            mat = result.get("matrix") or []
            cols = result.get("columns") or []
            if mat:
                im = ax.imshow(mat, cmap="coolwarm", vmin=-1, vmax=1)
                ax.set_xticks(range(len(cols)))
                ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=7)
                ax.set_yticks(range(len(cols)))
                ax.set_yticklabels(cols, fontsize=7)
                fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        else:
            return None
        ax.set_title(result.get("title") or chart.title(), fontsize=10)
        fig.tight_layout()
        out = io.BytesIO()
        fig.savefig(out, format="png", dpi=120)
        return out.getvalue()
    except Exception:
        return None
    finally:
        plt.close(fig)
