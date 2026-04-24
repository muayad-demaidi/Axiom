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
from .support import router as support_router  # noqa: E402

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
app.include_router(support_router)


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
    inline here. The output mirrors the legacy Streamlit "Report" tab:
    a cover, summary stats (shape, dtypes, missing values, numeric
    describe), AI-generated insights, and a chart when there's at least
    one numeric column.
    """
    from datetime import datetime
    from io import BytesIO

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except Exception as exc:  # pragma: no cover - environment guard
        raise HTTPException(500, f"reportlab not available: {exc}")

    record, df = _require_dataset(db, req.dataset_id, user.id)

    dataset_label = record.dataset_name or record.filename or "dataset"
    safe_dataset_label = _escape_for_pdf(str(dataset_label))
    safe_title = _escape_for_pdf(req.title) if req.title else "AXIOM Dataset Report"

    buf = BytesIO()
    # `title` here is PDF metadata (raw string is fine), not Paragraph markup.
    title_text = req.title or f"AXIOM Report — {dataset_label}"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title_text,
    )
    styles = getSampleStyleSheet()
    story: list = []

    # ---- Cover ----------------------------------------------------------
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(safe_title, styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        f"Dataset: <b>{safe_dataset_label}</b>",
        styles["BodyText"],
    ))
    story.append(Paragraph(
        f"{len(df):,} rows × {df.shape[1]:,} columns",
        styles["BodyText"],
    ))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["BodyText"],
    ))
    if req.notes:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph(_escape_for_pdf(req.notes), styles["BodyText"]))
    story.append(PageBreak())

    # ---- Summary stats: columns table ----------------------------------
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

    # ---- Chart (if applicable) -----------------------------------------
    chart_png = _build_report_chart(df)
    if chart_png is not None:
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph("<b>Distribution preview</b>", styles["Heading2"]))
        story.append(Image(BytesIO(chart_png), width=15 * cm, height=8 * cm))

    # ---- AI insights ---------------------------------------------------
    insights_text = _build_ai_insights(df)
    if insights_text:
        story.append(PageBreak())
        story.append(Paragraph("<b>AI insights</b>", styles["Heading2"]))
        story.append(Spacer(1, 0.2 * cm))
        for para in insights_text.split("\n"):
            line = para.strip()
            if not line:
                story.append(Spacer(1, 0.15 * cm))
                continue
            story.append(Paragraph(_escape_for_pdf(line), styles["BodyText"]))

    doc.build(story)
    buf.seek(0)
    filename = f"axiom-report-{record.id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _escape_for_pdf(text: str) -> str:
    """Escape characters that reportlab's Paragraph parser treats as markup."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _build_report_chart(df) -> bytes | None:
    """Render a small distribution chart for the first numeric column.

    Falls back to ``None`` when no numeric column is available or the
    plotting backend isn't usable, so the PDF still builds.
    """
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: WPS433
    except Exception:
        return None

    col = numeric.columns[0]
    series = numeric[col].dropna()
    if series.empty:
        return None

    from io import BytesIO
    fig, ax = plt.subplots(figsize=(7.5, 4))
    try:
        ax.hist(series, bins=min(30, max(5, int(len(series) ** 0.5))),
                color="#1d4ed8", edgecolor="white")
        ax.set_title(f"Distribution of {col}")
        ax.set_xlabel(str(col))
        ax.set_ylabel("Count")
        fig.tight_layout()
        out = BytesIO()
        fig.savefig(out, format="png", dpi=120)
        return out.getvalue()
    finally:
        plt.close(fig)


def _build_ai_insights(df) -> str | None:
    """Generate AI insights for the report; degrade gracefully on failure."""
    try:
        from ai_assistant import generate_data_insights  # type: ignore
    except Exception:
        return None

    try:
        numeric = df.select_dtypes(include="number")
        analysis: dict = {
            "shape": {"rows": int(len(df)), "cols": int(df.shape[1])},
            "dtypes": {str(c): str(df[c].dtype) for c in df.columns[:30]},
            "missing": {
                str(c): int(len(df) - int(df[c].notna().sum()))
                for c in df.columns[:30]
            },
        }
        if not numeric.empty:
            analysis["numeric_describe"] = (
                numeric.describe().round(3).to_dict()
            )
        df_summary = {
            "row_count": int(len(df)),
            "column_count": int(df.shape[1]),
            "columns": [str(c) for c in df.columns],
        }
        text = generate_data_insights(df_summary, analysis)
        if not text:
            return None
        return str(text).strip()
    except Exception:
        return None
