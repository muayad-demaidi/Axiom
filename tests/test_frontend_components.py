"""Section 6: frontend component tests.

The Next.js frontend lives in ``frontend/`` but no React test runner
(Jest/Vitest/Playwright) is configured for it. Until the project picks
a runner and wires it into CI, this file emits a single
``MANUAL_REVIEW_REQUIRED`` marker so the consolidated runner can call
out the gap explicitly instead of silently passing.
"""
from __future__ import annotations

import os

import pytest


FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
)


def _has_react_test_runner() -> bool:
    package_json = os.path.join(FRONTEND_DIR, "package.json")
    if not os.path.exists(package_json):
        return False
    with open(package_json, "r", encoding="utf-8") as fh:
        text = fh.read().lower()
    for marker in ("vitest", "jest", "@testing-library/react",
                   "playwright", "cypress"):
        if marker in text:
            return True
    return False


# Each entry is (component_path_under_frontend/, why_it_needs_coverage).
# These are the actual product-surface components that ship to users —
# enumerated explicitly so the manual-review fallback names every
# untested unit instead of waving generically at "the frontend".
_UNTESTED_COMPONENTS: list[tuple[str, str]] = [
    ("src/components/product/AppChrome.tsx",
     "top-level shell + auth/route guards"),
    ("src/components/product/ProjectWorkspace.tsx",
     "project page state machine (datasets ↔ chats ↔ artifacts)"),
    ("src/components/product/ChatPanel.tsx",
     "POST /api/chat/stream NDJSON consumer — handles tool_started/"
     "tool_finished/text/done events and re-renders on each frame"),
    ("src/components/product/FloatingComposer.tsx",
     "message composer + slash-command UI for chat workspace"),
    ("src/components/product/ArtifactDrawer.tsx",
     "renders chart / profile / prediction / cluster artifacts pinned "
     "from chat replies"),
    ("src/components/product/Charts.tsx",
     "BI chart renderer — must respect aggregation + warnings payload"),
    ("src/components/product/InteractiveTable.tsx",
     "pivot + slicer table; consumes /api/bi/<id>/pivot results"),
    ("src/components/product/PredictionCard.tsx",
     "displays /api/analysis/predict + chat predict_column results"),
    ("src/components/product/GuidedPredictionWizard.tsx",
     "drives /api/predict-guided/{analyze,run} step-through wizard"),
    ("src/components/product/GuidedPredictionCard.tsx",
     "renders the persisted guided-prediction artifact"),
    ("src/components/product/DataContextBar.tsx",
     "shows currently-attached datasets + relationships for a project"),
    ("src/components/product/DatasetPreviewCard.tsx",
     "uploaded-CSV preview + column-type override UI"),
    ("src/components/product/OpenQuestionsBar.tsx",
     "data-model open questions PATCH flow"),
    ("src/components/product/ModeAware.tsx",
     "guided ↔ expert mode renderer"),
    ("src/components/product/ModeToggle.tsx",
     "user-level guided/expert mode toggle (PATCH /api/auth/me)"),
    ("src/components/product/ProductSidebar.tsx",
     "left navigation between projects, chats, datasets, reports"),
    # Final report + data-model surfaces (page-level) — these live under
    # the app router, not the components dir, but still need coverage.
    ("src/app/app (final-report page)",
     "renders /api/chats/<id>/report and triggers /report.pdf download"),
    ("src/app/app (data-model page)",
     "drives PATCH/POST/PUT calls against /api/projects/<pid>/data-model"),
]


_FRONTEND_MARKER = (
    "MANUAL_REVIEW_REQUIRED: frontend component tests — no React "
    "test runner (Jest/Vitest/Playwright) is configured in "
    "frontend/package.json. The following components ship to users "
    "and need direct coverage once a runner is wired up:\n"
    + "\n".join(
        f"  - {path} — {reason}" for path, reason in _UNTESTED_COMPONENTS
    )
)


def test_frontend_components_manual_review_marker(capsys):
    """Emit a MANUAL_REVIEW_REQUIRED flag when no React test runner is
    wired up. The consolidated runner script greps for these markers
    in pytest's terminal output and surfaces them in the final report.

    We bypass pytest's stdout capture by writing directly to the real
    terminal stream so the marker shows up in a passing run.
    """

    if _has_react_test_runner():
        pytest.skip(
            "Frontend test runner detected — run it directly with "
            "`npm test` from frontend/."
        )

    with capsys.disabled():
        print(_FRONTEND_MARKER)
