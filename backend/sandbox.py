"""Safe-by-construction executor for agent-written analysis code.

Lets the assistant compute *anything* over the user's data (not just the
predefined tools) while never letting that code touch the host, network,
filesystem, secrets, or other users' data.

Defense in depth (independent layers):

1. **Static AST allow-list** (:func:`validate_code`) — rejects imports,
   dunder access, and dangerous builtins *before* anything runs. Works on
   every platform; the primary gate.
2. **Restricted globals** — code runs with a tiny safe ``__builtins__`` and
   only ``pd``/``np``/``math``/``datetime`` plus the injected read-only
   DataFrames. No ``open``/``eval``/``exec``/``__import__``.
3. **Separate interpreter** — execution happens in a child process via
   ``python -m backend.sandbox_runner`` (clean interpreter, no app state,
   no inherited secrets), hard-killable on overrun.
4. **Resource limits** (POSIX/Render) — CPU-seconds and address-space caps
   via ``resource``; skipped gracefully on local Windows dev (AST gate +
   wall-clock timeout still apply).
5. **Wall-clock timeout** — the parent kills the child if it overruns.
6. **Output cap** — results/stdout truncated.

Contract: submitted code must put its answer in a variable named
``result`` (DataFrame, Series, scalar, dict, or list). ``print(...)`` is
captured separately.
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

_ALLOWED_NAMES = {"pd", "np", "math", "datetime", "result"}

_SAFE_BUILTINS = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "int", "len", "list", "map", "max",
    "min", "print", "range", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "zip", "isinstance", "bin", "hex", "oct", "ord",
    "chr", "repr",
)

_FORBIDDEN_NAME_SUBSTR = ("__",)

_FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "open", "__import__", "input", "globals",
    "locals", "vars", "getattr", "setattr", "delattr", "memoryview",
    "breakpoint", "exit", "quit", "help", "object",
}

MAX_OUTPUT_CHARS = 8000
MAX_RESULT_ROWS = 200
CPU_SECONDS = 10
ADDRESS_SPACE_BYTES = 512 * 1024 * 1024


class SandboxError(Exception):
    """Raised when code is rejected by validation."""


def validate_code(code: str) -> None:
    """Static AST gate. Raises :class:`SandboxError` on any violation."""
    if not code or not code.strip():
        raise SandboxError("empty code")
    if len(code) > 20000:
        raise SandboxError("code too long")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("imports are not allowed")
        if isinstance(node, ast.Attribute):
            if any(s in node.attr for s in _FORBIDDEN_NAME_SUBSTR):
                raise SandboxError(f"access to '{node.attr}' is not allowed")
        if isinstance(node, ast.Name):
            if any(s in node.id for s in _FORBIDDEN_NAME_SUBSTR):
                raise SandboxError(f"name '{node.id}' is not allowed")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _FORBIDDEN_CALLS:
                raise SandboxError(f"call to '{fn.id}' is not allowed")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise SandboxError("global/nonlocal not allowed")


def coerce_result(value: Any) -> Any:
    """Make a result JSON-safe and bounded (shared with the runner)."""
    try:
        import pandas as pd
        import numpy as np
        if isinstance(value, pd.DataFrame):
            head = value.head(MAX_RESULT_ROWS)
            safe = head.astype(object).where(pd.notna(head), None)
            return {
                "type": "dataframe",
                "columns": [str(c) for c in head.columns],
                "rows": safe.values.tolist(),
                "row_count": int(len(value)),
                "truncated": len(value) > MAX_RESULT_ROWS,
            }
        if isinstance(value, pd.Series):
            s = value.head(MAX_RESULT_ROWS)
            def _v(v):
                if pd.isna(v):
                    return None
                if isinstance(v, (np.floating, float)):
                    return float(v)
                if isinstance(v, (np.integer, int)):
                    return int(v)
                return str(v)
            return {
                "type": "series",
                "index": [str(i) for i in s.index],
                "values": [_v(v) for v in s.values],
                "row_count": int(len(value)),
                "truncated": len(value) > MAX_RESULT_ROWS,
            }
        if isinstance(value, (np.floating, np.integer)):
            return value.item()
    except Exception:
        pass
    if isinstance(value, (dict, list, int, float, str, bool)) or value is None:
        return value
    return str(value)[:MAX_OUTPUT_CHARS]


def execute_in_namespace(code: str, frame_paths: dict) -> dict:
    """Load frames, exec ``code`` with restricted globals, return a dict.

    Trusted-harness side (runs inside the child). The harness reads the
    parquet files we wrote; the *user code* still cannot (``open`` is AST-
    blocked). Returns ``{ok, result, stdout}`` or ``{ok: False, error}``.
    """
    import builtins as _b
    import contextlib
    import datetime as _dt
    import math
    import pandas as pd
    import numpy as np

    try:
        validate_code(code)  # defense in depth: re-validate in the child
    except SandboxError as exc:
        return {"ok": False, "error": str(exc), "rejected": True}

    ns: dict[str, Any] = {"pd": pd, "np": np, "math": math, "datetime": _dt}
    for name, path in (frame_paths or {}).items():
        ns[name] = pd.read_parquet(path)
    ns["__builtins__"] = {k: getattr(_b, k) for k in _SAFE_BUILTINS if hasattr(_b, k)}

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<analysis>", "exec"), ns, ns)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "result": coerce_result(ns.get("result")),
        "stdout": buf.getvalue()[:MAX_OUTPUT_CHARS],
    }


def run_user_code(code: str, frames: dict | None = None, timeout: int = 15) -> dict:
    """Validate, then run ``code`` in an isolated child interpreter.

    ``frames`` maps a variable name to parquet bytes; each becomes a
    read-only DataFrame in scope. Never raises — returns
    ``{ok, result?, stdout?, error?, rejected?}``.
    """
    try:
        validate_code(code)
    except SandboxError as exc:
        return {"ok": False, "error": str(exc), "rejected": True}

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmpdir = tempfile.mkdtemp(prefix="axiom_sbx_")
    frame_paths: dict[str, str] = {}
    try:
        for name, raw in (frames or {}).items():
            p = os.path.join(tmpdir, f"{name}.parquet")
            with open(p, "wb") as fh:
                fh.write(raw)
            frame_paths[name] = p
        payload = json.dumps({"code": code, "frames": frame_paths})
        # Strip secrets from the child's environment — defense in depth so
        # the sandboxed process can never read DB creds / API keys even if
        # a future hole let code reach os.environ.
        _SENSITIVE = (
            "DATABASE_URL", "JWT_SECRET", "SECRET_KEY", "SESSION_SECRET",
            "OPENAI_API_KEY", "AI_INTEGRATIONS_OPENAI_API_KEY",
            "RESEND_API_KEY", "SENTRY_DSN", "ALLOWED_ORIGINS",
        )
        child_env = {k: v for k, v in os.environ.items() if k not in _SENSITIVE}
        child_env["PYTHONPATH"] = repo_root
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "backend.sandbox_runner"],
                input=payload, capture_output=True, text=True,
                timeout=timeout, cwd=repo_root, env=child_env,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timed out after {timeout}s"}
        if proc.returncode != 0 and not proc.stdout.strip():
            # Non-zero with no JSON usually means a hard resource limit
            # (CPU/memory) killed the child.
            err = (proc.stderr or "").strip()[-300:]
            return {"ok": False, "error": f"execution failed or hit a hard limit. {err}"}
        try:
            return json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": "could not parse sandbox output"}
    finally:
        try:
            for p in frame_paths.values():
                if os.path.exists(p):
                    os.remove(p)
            os.rmdir(tmpdir)
        except Exception:
            pass
