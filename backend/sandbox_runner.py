"""Isolated child interpreter for the code sandbox.

Run as ``python -m backend.sandbox_runner``. Reads a JSON job from stdin
(``{"code": str, "frames": {name: parquet_path}}``), applies POSIX
resource limits where available, executes the validated user code with a
restricted namespace, and writes a single JSON line to stdout
(``{ok, result, stdout}`` or ``{ok: False, error}``).

This file owns NO authority of its own: it never touches the DB, secrets,
or network. It only loads the parquet files the trusted parent prepared
and runs code that already passed the AST gate (re-checked here for
defense in depth).
"""
from __future__ import annotations

import json
import sys


def _apply_limits() -> None:
    """Cap CPU time, address space, and open files on POSIX (Render)."""
    try:
        import resource
        from backend.sandbox import CPU_SECONDS, ADDRESS_SPACE_BYTES
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(
            resource.RLIMIT_AS, (ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES)
        )
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
        except Exception:
            pass
    except Exception:
        # resource is unavailable on Windows (local dev only). The AST gate
        # and the parent's wall-clock timeout remain in force.
        pass


def main() -> None:
    _apply_limits()
    try:
        job = json.loads(sys.stdin.read() or "{}")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"bad job: {exc}"}))
        return
    from backend.sandbox import execute_in_namespace
    out = execute_in_namespace(job.get("code", ""), job.get("frames", {}))
    # Single JSON line on stdout — the parent reads the last line.
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
