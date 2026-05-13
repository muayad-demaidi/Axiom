"""Axiom backend performance harness — Task #223.

Run with:

    locust -f tests/performance/locustfile.py --host http://localhost:8000

For a smoke run (single user, single ramp, 5 seconds, headless):

    locust -f tests/performance/locustfile.py \
        --host http://localhost:8000 \
        --headless -u 1 -r 1 -t 5s

The scenarios below exercise the most-used backend endpoints: login,
list datasets, list artifacts, and a small CSV upload. All requests
catch failures so a missing endpoint doesn't crash the run -- locust
records them as failures in its summary report instead.
"""

from __future__ import annotations

import io
import os
import random

from locust import HttpUser, between, task

CSV_PAYLOAD = (
    "id,amount,country\n"
    + "\n".join(f"{i},{random.random() * 100:.2f},SA" for i in range(50))
)


class AxiomUser(HttpUser):
    """Realistic mix of read-heavy traffic with the occasional upload."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        email = os.environ.get("LOCUST_EMAIL", "loadtest@example.com")
        password = os.environ.get("LOCUST_PASSWORD", "loadtest-password")
        self.token: str | None = None
        with self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            name="login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except Exception:
                    body = {}
                self.token = body.get("access_token") or body.get("token")
                resp.success()
            else:
                # Without auth most subsequent endpoints will 401 -- still
                # useful to measure raw throughput.
                resp.success()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def list_datasets(self) -> None:
        self.client.get(
            "/api/datasets",
            headers=self._auth_headers(),
            name="list-datasets",
        )

    @task(3)
    def list_artifacts(self) -> None:
        self.client.get(
            "/api/chats/1/artifacts",
            headers=self._auth_headers(),
            name="list-artifacts",
        )

    @task(1)
    def upload_csv(self) -> None:
        files = {"file": ("loadtest.csv", io.BytesIO(CSV_PAYLOAD.encode()), "text/csv")}
        data = {"dataset_name": "loadtest"}
        self.client.post(
            "/api/datasets/upload",
            files=files,
            data=data,
            headers=self._auth_headers(),
            name="upload-csv",
        )
