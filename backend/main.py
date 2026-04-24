"""AXIOM FastAPI backend.

Wraps the existing Python modules behind a REST + SSE-style streaming surface
that the Next.js frontend consumes via /api/* (rewritten by next.config.mjs).
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Make the project root importable so we can reuse existing modules without
# moving them. This keeps the legacy Streamlit app and the FastAPI backend
# pointed at one source of truth during the migration window.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models  # type: ignore  # noqa: E402

# Try to ensure tables and lightweight migrations are applied at startup
# (mirrors the legacy Streamlit init).
try:
    models.init_db()
except Exception as _e:
    # Don't crash the API if migrations are deferred; log via uvicorn.
    print(f"[axiom] init_db skipped: {_e}")

from .auth_routes import router as auth_router  # noqa: E402
from .projects import router as projects_router  # noqa: E402
from .datasets import router as datasets_router  # noqa: E402
from .analysis import router as analysis_router  # noqa: E402
from .chat import router as chat_router  # noqa: E402

app = FastAPI(title="AXIOM API", version="0.2.0")

# CORS: by default we only accept same-origin requests (the Next.js
# rewrite proxies /api/*, so the browser sees same-origin). Operators can
# allow specific origins for cross-origin clients via ALLOWED_ORIGINS,
# either a comma-separated list or "*" to opt in explicitly.
_origins_env = (os.environ.get("ALLOWED_ORIGINS") or "").strip()
if _origins_env == "*":
    _allowed_origins: list[str] = ["*"]
elif _origins_env:
    _allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
else:
    _allowed_origins = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "axiom-api", "version": app.version}


app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(analysis_router)
app.include_router(chat_router)


from fastapi import Depends, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from .auth import get_current_user, get_db_session  # noqa: E402
from .analysis import _require_dataset  # noqa: E402


class ReportPdfRequest(BaseModel):
    dataset_id: int
    title: str | None = None
    notes: str | None = None


@app.post("/api/report/pdf")
async def report_pdf(
    req: ReportPdfRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Generate a per-dataset PDF summary using reportlab.

    The legacy `generate_plan_pdf.py` is a fixed Arabic marketing-plan
    document, not a parametric report generator, so we build the PDF
    inline here. The output covers basic shape, dtypes, missing-value
    counts and numeric describe() — the same building blocks the
    Streamlit dashboard surfaces in its "Report" tab.
    """
    from io import BytesIO

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except Exception as exc:  # pragma: no cover - environment guard
        raise HTTPException(500, f"reportlab not available: {exc}")

    record, df = _require_dataset(db, req.dataset_id, user.id)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=req.title or f"AXIOM Report — {record.dataset_name or record.filename}",
    )
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(req.title or "AXIOM Dataset Report", styles["Title"]))
    story.append(Paragraph(
        f"Dataset: <b>{record.dataset_name or record.filename}</b>"
        f" · {len(df):,} rows × {df.shape[1]:,} columns",
        styles["BodyText"],
    ))
    if req.notes:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(req.notes, styles["BodyText"]))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("<b>Columns</b>", styles["Heading2"]))
    cols_data = [["Column", "Dtype", "Non-null", "Missing"]]
    for col in df.columns[:50]:
        non_null = int(df[col].notna().sum())
        missing = int(len(df) - non_null)
        cols_data.append([str(col), str(df[col].dtype), f"{non_null:,}", f"{missing:,}"])
    tbl = Table(cols_data, colWidths=[6.5 * cm, 3 * cm, 3 * cm, 3 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(tbl)

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph("<b>Numeric summary</b>", styles["Heading2"]))
        desc = numeric.describe().round(3)
        head = ["stat"] + [str(c) for c in desc.columns[:6]]
        rows = [head]
        for stat, row in desc.iterrows():
            rows.append([str(stat)] + [str(v) for v in row.values[:6]])
        ntbl = Table(rows)
        ntbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(ntbl)

    doc.build(story)
    buf.seek(0)
    filename = f"axiom-report-{record.id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
