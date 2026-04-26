"""Single-command runner for the AXIOM end-to-end test suite (Task #219).

Runs every test under ``tests/`` via pytest with a JSON report, then
emits a consolidated summary to stdout containing:

  * Total / passed / failed / skipped counts.
  * Each failing test with its file path, line number, and a short
    one-line message.
  * Every ``MANUAL_REVIEW_REQUIRED:`` marker emitted by the suite.

The exit code is 0 on a fully green run and 1 on any failure.

Usage::

    python scripts/run_full_suite.py
    python scripts/run_full_suite.py tests/test_units_predictions.py

Dependencies (``pytest`` and ``pytest-jsonreport``) are installed in
the project environment already.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


def _have_pytest_jsonreport() -> bool:
    try:
        import pytest_jsonreport  # noqa: F401
        return True
    except Exception:
        return False


def _run_pytest(extra_args: list[str], json_path: str | None) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=line", "-rN"]
    if json_path:
        cmd += ["--json-report", f"--json-report-file={json_path}"]
    cmd += extra_args
    # Stream pytest output line-by-line so the user sees progress on
    # long suites instead of a single delayed dump.
    proc = subprocess.Popen(
        cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    captured_lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured_lines.append(line)
    rc = proc.wait()
    return rc, "".join(captured_lines)


def _parse_text_summary(output: str) -> dict:
    """Fallback summary built from the pytest stdout when the JSON
    report plugin isn't available. Recognizes the standard
    ``X passed, Y failed, Z skipped in T.TTs`` line."""
    summary = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0,
               "total": 0, "duration": 0.0}
    final = re.search(
        r"=+\s*([^=]*?)\s+in\s+([\d.]+)s\s*=+\s*$",
        output.strip(),
        re.MULTILINE,
    )
    if not final:
        return summary
    body, dur = final.group(1), float(final.group(2))
    summary["duration"] = dur
    for token in body.split(","):
        m = re.search(r"(\d+)\s+(\w+)", token.strip())
        if not m:
            continue
        n, kind = int(m.group(1)), m.group(2).lower()
        if kind in summary:
            summary[kind] = n
    summary["total"] = sum(summary.get(k, 0)
                           for k in ("passed", "failed", "skipped", "errors"))
    return summary


def _failures_from_json(report: dict) -> list[dict]:
    out: list[dict] = []
    for test in report.get("tests", []):
        if test.get("outcome") not in ("failed", "error"):
            continue
        call = test.get("call", {}) or {}
        crash = call.get("crash") or {}
        message = (crash.get("message") or call.get("longrepr")
                   or test.get("longrepr") or "(no message)")
        # Keep only the most informative single line for the summary.
        first_meaningful = next(
            (ln for ln in str(message).splitlines() if ln.strip()),
            "(no message)",
        )
        message_short = first_meaningful.strip()[:240]
        nodeid = test.get("nodeid", "")
        # Prefer the failing line from the crash record (the actual
        # assertion site) over the function definition line.
        file_path = (crash.get("path") or nodeid.split("::")[0])
        if file_path.startswith(str(ROOT) + os.sep):
            file_path = file_path[len(str(ROOT)) + 1:]
        line = crash.get("lineno")
        if line is None:
            line = test.get("lineno", "?")
        out.append({
            "nodeid": nodeid,
            "file": file_path,
            "line": line,
            "message": message_short,
        })
    return out


def _failures_from_text(output: str) -> list[dict]:
    """Fallback failure parser using pytest's --tb=line output."""
    out: list[dict] = []
    pattern = re.compile(r"^(tests/[^:]+):(\d+):\s*(\w+):\s*(.*)$",
                         re.MULTILINE)
    for path, line, kind, msg in pattern.findall(output):
        out.append({
            "nodeid": path,
            "file": path,
            "line": int(line),
            "message": f"{kind}: {msg}".strip(),
        })
    return out


# Marker text can span any characters except a newline — we
# specifically allow embedded ``"`` and ``'`` since the in-source form
# is often produced by joining adjacent string literals.
_MARKER_RE = re.compile(r"MANUAL_REVIEW_REQUIRED:[^\n]+")

# Source-side: tests that hard-code multi-fragment markers via Python's
# implicit string concatenation (``"foo " "bar"``) need their fragments
# re-joined before we can extract the full marker text. This regex
# matches the gap between two adjacent string literals so we can
# collapse them into one.
_PY_STRING_JOIN_RE = re.compile(
    r'("[^"\n]*")\s+(?=")|'
    r"('[^'\n]*')\s+(?=')"
)


def _collect_manual_review_markers(output: str) -> list[str]:
    markers: list[str] = []
    # 1. Pytest output (tests that printed the marker at runtime). With
    #    pytest -q the captured stdout is only emitted on failures, so
    #    runtime-only markers can vanish — see step 3 for the evidence
    #    fallback that keeps them visible.
    for line in output.splitlines():
        m = _MARKER_RE.search(line)
        if m:
            markers.append(m.group(0).strip().rstrip(".\""))
    # 2. Static scan: any test source file that hard-codes the marker
    #    string also counts, so a passing test that didn't get a chance
    #    to print still surfaces in the report. We pre-join adjacent
    #    string literals so multi-line concatenated markers extract
    #    cleanly into a single line.
    def _join_adjacent_strings(text: str) -> str:
        # Repeatedly collapse ``"abc" "def"`` -> ``"abcdef"`` until no
        # more joins fire. Keeps the regex simple and side-effect-free.
        prev = None
        while prev != text:
            prev = text
            text = re.sub(
                r'"([^"\n]*)"\s+"([^"\n]*)"',
                lambda m: '"' + m.group(1) + m.group(2) + '"',
                text,
            )
        return text
    for path in TESTS_DIR.glob("**/*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        joined = _join_adjacent_strings(text)
        for m in _MARKER_RE.findall(joined):
            markers.append(m.strip().rstrip(".\""))
    # 3. Evidence file fallback — runtime tests that emit markers via
    #    ``Path("tests/_evidence/manual_review.txt").write_text(...)``
    #    are picked up here even when pytest swallowed the captured
    #    stdout for passing cases.
    evidence = TESTS_DIR / "_evidence" / "manual_review.txt"
    if evidence.exists():
        for line in evidence.read_text(encoding="utf-8").splitlines():
            m = _MARKER_RE.search(line)
            if m:
                markers.append(m.group(0).strip().rstrip(".\""))
    # Normalize whitespace + drop trailing punctuation so the same
    # marker can't appear twice just because pytest wrapped it.
    def _norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip(" .\"")
    normalized = [_norm(m) for m in markers if m]
    # Keep the longest representative for each "marker family":
    # prefer the longest string that contains every shorter sibling.
    sorted_unique = sorted(set(normalized), key=len, reverse=True)
    deduped: list[str] = []
    for marker in sorted_unique:
        if not any(marker != kept and marker in kept for kept in deduped):
            deduped.append(marker)
    return deduped


# Map a test nodeid to the endpoint(s) / component(s) it exercises.
# The mapping is heuristic — we look at the nodeid and group failures
# under the human-readable surface they cover so the runner output
# answers "which endpoints/components are broken right now?" directly.
_NODEID_TO_SURFACE = [
    # (substring_in_nodeid, surface_label)
    ("test_500_envelope_is_documented_shape", "ALL endpoints (500 JSON envelope)"),
    ("test_401_returns_json_on_protected", "Protected endpoints (401 JSON envelope)"),
    ("test_404_returns_json_for_missing_dataset", "GET /api/datasets/{id}"),
    ("test_404_returns_json_for_missing_project", "DELETE /api/projects/{id}"),
    ("test_404_returns_json_for_missing_chat", "GET /api/chats/{id}/messages"),
    ("test_422_returns_json_envelope_on_invalid_register",
     "POST /api/auth/register"),
    ("test_422_returns_json_envelope_on_invalid_predict",
     "POST /api/predict"),
    ("test_400_returns_json_for_predict_on_missing_column",
     "POST /api/predict (400 path)"),
    ("test_400_returns_json_for_unknown_model_method",
     "POST /api/model (400 path)"),
    ("test_400_returns_json_for_empty_csv_upload",
     "POST /api/datasets/upload (400 path — empty body)"),
    ("test_400_returns_json_for_non_csv_upload",
     "POST /api/datasets/upload (400 path — non-CSV file)"),
    ("test_401_returns_json_for_invalid_jwt",
     "Protected endpoints (401 JSON envelope — invalid JWT)"),
    ("test_404_returns_json_for_predict_on_missing_dataset",
     "POST /api/predict (404 path — missing dataset)"),
    ("test_chat_predict_graceful_arabic_explanation_for_sparse_target",
     "Chat predict_column (Arabic graceful sparse-target notice)"),
    ("tests/test_units_analysis.py",
     "backend/insights.py (build_profile + surprise_insights + suggested_questions)"),
    ("test_health_returns_json", "GET /api/health"),
    ("test_register_login_me_round_trip", "Auth (register/login/me)"),
    ("test_patch_me_updates_assistant_mode", "PATCH /api/auth/me"),
    ("test_forgot_endpoint_returns_json", "POST /api/auth/forgot"),
    ("test_projects_crud_round_trip", "Projects CRUD"),
    ("test_datasets_upload_list_get", "Datasets (upload/list/get)"),
    ("test_analysis_statistics_endpoint", "POST /api/statistics"),
    ("test_analysis_predict_endpoint", "POST /api/predict"),
    ("test_analysis_model_endpoint", "POST /api/model"),
    ("test_analysis_clean_endpoint", "POST /api/clean"),
    ("test_analysis_transform_endpoint", "POST /api/transform"),
    ("test_chat_session_lifecycle", "Chat sessions CRUD"),
    ("test_artifact_dataset_views",
     "GET /api/datasets/{id}/(preview|profile|insights|suggestions)"),
    ("test_artifact_seed_and_listing",
     "POST /api/chats/{id}/seed-profile, GET /api/chats/{id}/artifacts"),
    ("test_data_model_get_refresh", "Data model GET + refresh"),
    ("test_data_model_patch_table",
     "PATCH /api/projects/{id}/data-model/tables/{ds}"),
    ("test_data_model_post_relationship_and_put_description",
     "POST relationships + PUT description"),
    ("test_data_model_patch_question_404_returns_json",
     "PATCH /api/projects/{id}/data-model/questions/{q}"),
    ("test_predict_guided_analyze_and_run",
     "Predict-guided (analyze + run)"),
    ("test_support_contact_returns_json", "POST /api/support/contact"),
    ("test_bi_field_meta_and_modeling", "BI field-meta + modeling"),
    ("test_bi_pivot_endpoint", "POST /api/bi/pivot"),
    ("test_bi_explain_and_dashboard_get", "GET /api/bi/{id}/dashboard"),
    ("test_report_pdf_endpoint_returns_pdf_bytes", "POST /api/report/pdf"),
    ("test_chat_tool_profile_dataset", "Chat tool: profile_dataset"),
    ("test_chat_tool_make_chart", "Chat tool: make_chart"),
    ("test_chat_tool_predict_column", "Chat tool: predict_column"),
    ("test_chat_tool_cluster_dataset", "Chat tool: cluster_dataset"),
    ("test_chat_tool_query_model_returns_rows", "Chat tool: query_model"),
    ("test_chat_tool_list_and_explain_model",
     "Chat tools: list_model + explain_model"),
    ("test_full_user_journey", "10-step end-to-end user journey"),
    ("test_frontend_components", "Frontend components"),
    ("tests/test_units_semantic_model.py", "backend/semantic_model.py"),
    ("tests/test_units_predictions.py", "backend/predictions.py"),
    ("tests/test_units_data_modules.py",
     "backend/data_analyzer + data_cleaner + data_visualizer"),
]


def _surface_for(nodeid: str) -> str:
    for needle, label in _NODEID_TO_SURFACE:
        if needle in nodeid:
            return label
    # Fallback: derive from the file name.
    return nodeid.split("::")[0]


def _format_summary(summary: dict, failures: list[dict],
                    markers: list[str]) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 78)
    lines.append("AXIOM consolidated test report (Task #219)")
    lines.append("=" * 78)
    lines.append(
        f"  total={summary.get('total', 0)}  "
        f"passed={summary.get('passed', 0)}  "
        f"failed={summary.get('failed', 0)}  "
        f"errors={summary.get('errors', 0)}  "
        f"skipped={summary.get('skipped', 0)}  "
        f"duration={summary.get('duration', 0):.2f}s"
    )
    lines.append("")
    lines.append("Failures:")
    if failures:
        for f in failures:
            lines.append(
                f"  - {f['file']}:{f['line']}  ({f['nodeid']})"
            )
            lines.append(f"      {f['message']}")
    else:
        lines.append("  (none)")
    lines.append("")
    # Structured "broken endpoints/components" section. This lets the
    # reader see at a glance which API surfaces / UI components are
    # currently broken without having to map test names back manually.
    lines.append("Broken endpoints / components:")
    if failures:
        seen: set[str] = set()
        for f in failures:
            label = _surface_for(f["nodeid"])
            if label in seen:
                continue
            seen.add(label)
            lines.append(f"  - {label}  ←  {f['file']}:{f['line']}")
    else:
        lines.append("  (none — every endpoint and component test passed)")
    lines.append("")
    lines.append("Manual-review flags:")
    if markers:
        for m in markers:
            lines.append(f"  - {m}")
    else:
        lines.append("  (none)")
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    extra_args = argv[1:] or [str(TESTS_DIR)]
    use_json = _have_pytest_jsonreport()
    json_path = None
    if use_json:
        fd, json_path = tempfile.mkstemp(prefix="axiom-tests-", suffix=".json")
        os.close(fd)
    try:
        rc, raw_output = _run_pytest(extra_args, json_path)

        summary = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0,
                   "total": 0, "duration": 0.0}
        failures: list[dict] = []
        if json_path and os.path.exists(json_path) and \
                os.path.getsize(json_path) > 0:
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    report = json.load(fh)
                rsum = report.get("summary", {})
                summary["passed"] = rsum.get("passed", 0)
                summary["failed"] = rsum.get("failed", 0)
                summary["skipped"] = rsum.get("skipped", 0)
                summary["errors"] = rsum.get("error", 0)
                summary["total"] = rsum.get("total", 0)
                summary["duration"] = report.get("duration", 0.0)
                failures = _failures_from_json(report)
            except Exception as exc:  # pragma: no cover
                print(f"[runner] failed to parse JSON report: {exc}",
                      file=sys.stderr)
                summary = _parse_text_summary(raw_output)
                failures = _failures_from_text(raw_output)
        else:
            summary = _parse_text_summary(raw_output)
            failures = _failures_from_text(raw_output)

        markers = _collect_manual_review_markers(raw_output)
        report_text = _format_summary(summary, failures, markers)
        print(report_text)

        # Persist captured runner output as evidence for code review.
        # Two files: the raw streaming pytest output and the
        # consolidated summary (mirrors what the runner just printed).
        evidence_dir = TESTS_DIR / "_evidence"
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            (evidence_dir / "last_run_pytest_output.txt").write_text(
                raw_output, encoding="utf-8"
            )
            (evidence_dir / "last_run_summary.txt").write_text(
                report_text + "\n", encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover
            print(f"[runner] could not write evidence files: {exc}",
                  file=sys.stderr)
        return rc
    finally:
        if json_path and os.path.exists(json_path):
            try:
                os.unlink(json_path)
            except OSError:
                pass


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
