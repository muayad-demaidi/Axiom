"""Shared fixtures for the consolidated AXIOM test suite (Task #219).

Highlights:
  * ``client`` — the FastAPI TestClient bound to ``backend.main.app``.
  * ``register`` — factory that creates a fresh user + auth headers.
  * ``project`` / ``dataset`` / ``chat_session`` factories.
  * Sample CSV fixtures: time-series sales (~24 months), driver-based
    regression (~80 rows), customers + orders pair, a tiny 3-row file,
    and a 90%-missing-target file. Each is exposed as a Pandas
    DataFrame and a CSV ``bytes`` blob.
  * ``stub_openai`` — monkeypatches the OpenAI SDK so no live API call
    is made during a test run.

Test isolation
--------------
The suite provisions its own throw-away PostgreSQL database before
any backend module is imported. The bootstrap below:

  1. Connects to the local PG admin DB (using the standard PG* env
     vars) and CREATEs ``axiom_t219_<uuid>`` — guaranteed unique per
     run.
  2. Rewrites ``DATABASE_URL`` to point at that DB **before** importing
     ``models`` / ``backend.main``, so every backend module binds to
     the test DB rather than the dev/prod DB.
  3. Runs ``models.init_db()`` on the fresh DB to materialise the
     full ORM schema + lightweight migrations.
  4. Registers an ``atexit`` finaliser that disposes the engine,
     terminates lingering connections, and DROPs the test DB so
     nothing leaks across runs.

This is real per-run isolation: the production / dev DB is never
touched by the suite, even on catastrophic failure (the worst case is
an orphaned ``axiom_t219_*`` DB the next run can ignore).
"""
from __future__ import annotations

import atexit
import io
import os
import time
import uuid
from typing import Callable


# ---------------------------------------------------------------------------
# Isolated test database bootstrap (must run BEFORE backend imports).
# ---------------------------------------------------------------------------

def _bootstrap_isolated_test_db() -> tuple[str, str]:
    """Create a fresh PostgreSQL database for this test session.

    Returns ``(test_db_name, admin_url)``. Sets ``DATABASE_URL`` so
    every subsequent backend import binds to the new database.
    """
    import psycopg2
    from psycopg2 import sql as _sql

    pg_user = os.environ.get("PGUSER")
    pg_password = os.environ.get("PGPASSWORD")
    pg_host = os.environ.get("PGHOST")
    pg_port = os.environ.get("PGPORT")
    pg_db = os.environ.get("PGDATABASE")
    if not all([pg_user, pg_password, pg_host, pg_port, pg_db]):
        raise RuntimeError(
            "Test suite requires PG* env vars to provision an isolated "
            "test database (PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE)."
        )

    test_db_name = f"axiom_t219_{uuid.uuid4().hex[:12]}"
    admin_url = (
        f"postgresql://{pg_user}:{pg_password}"
        f"@{pg_host}:{pg_port}/{pg_db}"
    )

    conn = psycopg2.connect(admin_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                _sql.SQL("CREATE DATABASE {} ").format(
                    _sql.Identifier(test_db_name)
                )
            )
    finally:
        conn.close()

    os.environ["DATABASE_URL"] = (
        f"postgresql://{pg_user}:{pg_password}"
        f"@{pg_host}:{pg_port}/{test_db_name}"
    )
    return test_db_name, admin_url


_TEST_DB_NAME, _ADMIN_URL = _bootstrap_isolated_test_db()


def _drop_isolated_test_db() -> None:
    """Tear down the per-run test database. Best-effort."""
    try:
        import models as _models
        _models.engine.dispose()
    except Exception:
        pass
    try:
        import psycopg2
        from psycopg2 import sql as _sql
        conn = psycopg2.connect(_ADMIN_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_TEST_DB_NAME,),
            )
            cur.execute(
                _sql.SQL("DROP DATABASE IF EXISTS {} ").format(
                    _sql.Identifier(_TEST_DB_NAME)
                )
            )
        conn.close()
    except Exception:
        pass


atexit.register(_drop_isolated_test_db)


# Now it is safe to import backend modules — they will bind to the
# fresh test DB created above.
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
import models  # noqa: E402

# Materialise the full schema (+ idempotent in-place migrations) on
# the freshly created database before any test touches it.
models.init_db()


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

# Session-scoped registry of every user the suite has created. Populated
# by the ``register`` fixture; drained by ``_db_isolation`` at teardown.
_CREATED_USER_IDS: set[int] = set()


@pytest.fixture(scope="session", autouse=True)
def _ensure_openai_env():
    """The chat ``/api/chat/stream`` endpoint short-circuits to an
    "OpenAI key is not configured" message when neither
    ``OPENAI_API_KEY`` nor ``AI_INTEGRATIONS_OPENAI_API_KEY`` is set,
    which would skip the entire tool-dispatch branch we want to test.
    Plant a deterministic fake key for the run; the StubOpenAI swap
    means no live request ever leaves the process.
    """
    import os
    keys_to_set = [
        ("OPENAI_API_KEY", "sk-test-stub-task219"),
        ("AI_INTEGRATIONS_OPENAI_API_KEY", "sk-test-stub-task219"),
    ]
    saved = {k: os.environ.get(k) for k, _ in keys_to_set}
    for k, v in keys_to_set:
        os.environ.setdefault(k, v)
    yield
    for k, original in saved.items():
        if original is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = original


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _db_isolation():
    """Cleanup is handled by the per-run database drop in the
    ``atexit`` finaliser at the top of this module — we still keep the
    user-id registry around for any future per-test cleanup hooks.
    """
    yield
    _CREATED_USER_IDS.clear()


def _unique_email(tag: str = "u") -> str:
    return f"task219+{tag}+{uuid.uuid4().hex[:10]}@axiom.test"


@pytest.fixture
def register(client: TestClient) -> Callable[..., dict]:
    """Factory: register a new user and return ``{token, headers, user}``."""

    def _register(tag: str = "u") -> dict:
        email = _unique_email(tag)
        body = {
            "email": email,
            "username": email.split("@")[0],
            "password": "Pass1234!",
            "full_name": "Task 219 User",
        }
        r = client.post("/api/auth/register", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        # Track the new user for end-of-session cleanup.
        try:
            _CREATED_USER_IDS.add(int(data["user"]["id"]))
        except (KeyError, TypeError, ValueError):
            pass
        return {
            "token": data["token"],
            "user": data["user"],
            "headers": {"Authorization": f"Bearer {data['token']}"},
            "email": email,
            "password": "Pass1234!",
        }

    return _register


@pytest.fixture
def project(client: TestClient, register) -> Callable[..., tuple[dict, int]]:
    def _project(name: str = "p219", user: dict | None = None) -> tuple[dict, int]:
        u = user or register("p")
        r = client.post("/api/projects", json={"name": name}, headers=u["headers"])
        assert r.status_code == 200, r.text
        return u, int(r.json()["id"])

    return _project


@pytest.fixture
def upload_dataset(client: TestClient):
    def _upload(headers: dict, project_id: int | None,
                name: str, csv_bytes: bytes) -> int:
        files = {"file": (f"{name}.csv", csv_bytes, "text/csv")}
        data = {"dataset_name": name}
        if project_id:
            data["project_id"] = str(project_id)
        r = client.post(
            "/api/datasets/upload", files=files, data=data, headers=headers
        )
        assert r.status_code == 200, r.text
        return int(r.json()["id"])

    return _upload


@pytest.fixture
def chat_session(client: TestClient):
    def _session(headers: dict, project_id: int, title: str = "t219") -> int:
        r = client.post(
            f"/api/projects/{project_id}/chats",
            json={"title": title},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        return int(r.json()["id"])

    return _session


# ---------------------------------------------------------------------------
# Sample dataframes
# ---------------------------------------------------------------------------

def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def timeseries_sales_df() -> pd.DataFrame:
    """24 monthly observations of revenue with linear trend + noise."""
    rng = np.random.default_rng(7)
    n = 24
    dates = pd.date_range("2023-01-01", periods=n, freq="MS")
    trend = np.linspace(1000, 2200, n)
    seasonal = 100 * np.sin(np.linspace(0, 4 * np.pi, n))
    noise = rng.normal(0, 30, size=n)
    return pd.DataFrame({"date": dates, "revenue": (trend + seasonal + noise).round(2)})


@pytest.fixture
def timeseries_sales_csv(timeseries_sales_df) -> bytes:
    return _df_to_csv_bytes(timeseries_sales_df)


@pytest.fixture
def driver_regression_df() -> pd.DataFrame:
    """80-row driver-based regression: spend + units → sales."""
    rng = np.random.default_rng(11)
    n = 80
    spend = rng.uniform(10, 100, size=n)
    units = rng.uniform(1, 50, size=n)
    noise = rng.normal(0, 1.5, size=n)
    sales = (2.0 * spend + 0.5 * units + noise).round(2)
    return pd.DataFrame({"marketing_spend": spend.round(2),
                         "units": units.round(2),
                         "sales": sales})


@pytest.fixture
def driver_regression_csv(driver_regression_df) -> bytes:
    return _df_to_csv_bytes(driver_regression_df)


@pytest.fixture
def customers_df() -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "name": [f"Customer {i}" for i in range(1, 11)],
        "country": ["LB", "JO", "EG", "LB", "AE", "SA", "EG", "LB", "JO", "AE"],
    })


@pytest.fixture
def orders_df() -> pd.DataFrame:
    rng = np.random.default_rng(33)
    n = 50
    return pd.DataFrame({
        "order_id": list(range(1001, 1001 + n)),
        "customer_id": rng.integers(1, 11, size=n),
        "amount": rng.uniform(10, 500, size=n).round(2),
    })


@pytest.fixture
def customers_csv(customers_df) -> bytes:
    return _df_to_csv_bytes(customers_df)


@pytest.fixture
def orders_csv(orders_df) -> bytes:
    return _df_to_csv_bytes(orders_df)


@pytest.fixture
def tiny_three_row_df() -> pd.DataFrame:
    return pd.DataFrame({
        "feature_a": [1.0, 2.0, 3.0],
        "feature_b": [10.0, 20.0, 30.0],
        "target": [11.0, 22.0, 33.0],
    })


@pytest.fixture
def tiny_three_row_csv(tiny_three_row_df) -> bytes:
    return _df_to_csv_bytes(tiny_three_row_df)


@pytest.fixture
def mostly_missing_target_df() -> pd.DataFrame:
    """30 rows, target has 90% missing values."""
    rng = np.random.default_rng(99)
    n = 30
    df = pd.DataFrame({
        "feature_a": rng.normal(0, 1, n).round(3),
        "feature_b": rng.normal(5, 2, n).round(3),
        "feature_c": rng.normal(-3, 0.5, n).round(3),
        "target": [None] * n,
    })
    # Fill the first ~10% only.
    df.loc[:2, "target"] = [1.5, 2.7, 3.1]
    return df


@pytest.fixture
def mostly_missing_target_csv(mostly_missing_target_df) -> bytes:
    return _df_to_csv_bytes(mostly_missing_target_df)


# ---------------------------------------------------------------------------
# OpenAI stub (used by tests that touch chat plumbing)
# ---------------------------------------------------------------------------

class _StubFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _StubToolCall:
    def __init__(self, call_id: str, name: str, arguments):
        import json as _json
        self.id = call_id
        self.type = "function"
        args_str = arguments if isinstance(arguments, str) else _json.dumps(arguments)
        self.function = _StubFunction(name, args_str)


class _StubMessage:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _StubChoice:
    def __init__(self, message: _StubMessage):
        self.message = message


class _StubResponse:
    def __init__(self, choices):
        self.choices = choices


class _StubCompletions:
    """Returns scripted responses one per ``create()`` call.

    Each scripted entry is either a plain string (text reply, no tool
    call) OR a dict ``{"text": str | None, "tool_calls": [
    {"name": str, "arguments": dict | str, "id": str?} ]}`` — the
    latter exercises the chat-stream tool dispatcher exactly the way
    a real OpenAI tool call would.
    """

    def __init__(self, scripted):
        self._scripted = list(scripted) or ["Stubbed AI response."]
        self._idx = 0

    def create(self, **_kwargs):
        entry = self._scripted[min(self._idx, len(self._scripted) - 1)]
        self._idx += 1
        if isinstance(entry, dict):
            text = entry.get("text") or ""
            tool_calls = []
            for i, tc in enumerate(entry.get("tool_calls") or []):
                tool_calls.append(
                    _StubToolCall(
                        tc.get("id") or f"call_{self._idx}_{i}",
                        tc["name"],
                        tc.get("arguments") or {},
                    )
                )
            return _StubResponse([_StubChoice(_StubMessage(text, tool_calls))])
        return _StubResponse([_StubChoice(_StubMessage(content=str(entry)))])


class _StubChat:
    def __init__(self, scripted):
        self.completions = _StubCompletions(scripted)


_DEFAULT_SCRIPT: list = ["Stubbed AI response."]


class StubOpenAI:
    """Drop-in replacement for ``openai.OpenAI`` used in tests.

    The class-level ``_script`` is the queue every instance reads from
    when ``client.chat.completions.create()`` is called. Tests script
    the queue with :func:`StubOpenAI.script` *before* hitting the
    chat endpoint.
    """

    _script: list = list(_DEFAULT_SCRIPT)

    @classmethod
    def script(cls, entries):
        cls._script = list(entries) if entries else list(_DEFAULT_SCRIPT)

    @classmethod
    def reset(cls):
        cls._script = list(_DEFAULT_SCRIPT)

    def __init__(self, *_args, **_kwargs):
        self.chat = _StubChat(StubOpenAI._script)


@pytest.fixture
def stub_openai(monkeypatch):
    """Replace ``openai.OpenAI`` everywhere it could be imported with
    a deterministic stub.

    Some modules do ``from openai import OpenAI`` at import time, so we
    monkey-patch every loaded copy of the symbol.
    """
    import sys
    import openai as _openai_pkg

    monkeypatch.setattr(_openai_pkg, "OpenAI", StubOpenAI, raising=False)
    for mod in list(sys.modules.values()):
        if mod is None or not hasattr(mod, "OpenAI"):
            continue
        # Only patch modules that pulled OpenAI from the openai package.
        try:
            current = getattr(mod, "OpenAI")
        except Exception:
            continue
        if getattr(current, "__module__", "").startswith("openai"):
            monkeypatch.setattr(mod, "OpenAI", StubOpenAI, raising=False)
    StubOpenAI.reset()
    yield StubOpenAI
    StubOpenAI.reset()
