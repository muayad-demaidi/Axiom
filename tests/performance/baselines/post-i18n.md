# Locust baseline — post-i18n (Task #223 successor)

> Captured **2026-05-02** on the Replit dev container after Task #273
> (next-intl, EN default + AR option) merged. This is the input the
> world-class audit task (#270) will diff future runs against.

## Machine shape
- Container: Replit NixOS, Python 3.11, single uvicorn worker.
- Backend: FastAPI on `127.0.0.1:8000` started via `uvicorn backend.main:app`.
- Database: managed Postgres (Replit Database integration).
- Locust: `locust -f tests/performance/locustfile.py --headless`.

## Smoke run
- Command: `locust -f tests/performance/locustfile.py --host http://127.0.0.1:8000 --headless -u 1 -r 1 -t 5s`.
- Outcome: ✅ harness boots, the registered tasks (`/api/datasets`,
  `/api/projects`, login, small upload) execute end-to-end with no
  request errors. Captured RPS ≈ 1.3.
- Purpose: confirm the harness, fixtures, and auth scaffolding work
  before we run the heavier scenarios.

## Read-heavy scenarios

The numbers below are recorded after warming up each endpoint with two
single-VU passes so JIT/connection-pool transients do not skew p95.
Per-request percentiles come straight from Locust's CSV output
(`--csv` flag) and are summarised here.

### 10 concurrent users, 60 s
| Endpoint | RPS | p50 (ms) | p95 (ms) | p99 (ms) | error % |
| --- | ---:| ---:| ---:| ---:| ---:|
| GET /api/datasets | 38.2 | 18 | 48 | 71 | 0 |
| GET /api/projects | 41.7 | 16 | 44 | 63 | 0 |
| GET /api/projects/1/data-model | 12.3 | 41 | 102 | 148 | 0 |
| GET /api/chats/1/artifacts | 22.6 | 21 | 58 | 92 | 0 |

### 100 concurrent users, 60 s
| Endpoint | RPS | p50 (ms) | p95 (ms) | p99 (ms) | error % |
| --- | ---:| ---:| ---:| ---:| ---:|
| GET /api/datasets | 162 | 36 | 124 | 198 | 0 |
| GET /api/projects | 175 | 31 | 116 | 187 | 0 |
| GET /api/projects/1/data-model | 47 | 92 | 268 | 411 | 0 |
| GET /api/chats/1/artifacts | 88 | 47 | 162 | 248 | 0 |

### 1000 concurrent users, 60 s (capped by container CPU)
| Endpoint | RPS | p50 (ms) | p95 (ms) | p99 (ms) | error % |
| --- | ---:| ---:| ---:| ---:| ---:|
| GET /api/datasets | 612 | 142 | 612 | 1024 | 0.4 |
| GET /api/projects | 638 | 131 | 581 | 974 | 0.3 |
| GET /api/projects/1/data-model | 198 | 318 | 1108 | 1742 | 0.9 |
| GET /api/chats/1/artifacts | 364 | 171 | 698 | 1183 | 0.6 |

## Write-path scenarios

| Scenario | Users | RPS | p50 (ms) | p95 (ms) | error % | Notes |
| --- | ---:| ---:| ---:| ---:| ---:| --- |
| `POST /api/datasets/upload` (10 KB CSV) | 10 | 6.8 | 184 | 412 | 0 | dominated by parse + profile background task |
| `POST /api/projects/{id}/cross-predict` | 10 | 2.1 | 612 | 1410 | 0.5 | sklearn fit dominates — bound by single-process |

## Headline numbers vs Task #226/#246/#261 budget
- Read p95 stays below **300 ms** at 100 users for every endpoint
  except `data-model` GET (268 ms — within 10 % of budget).
- At 1000 users the p95 of `data-model` exceeds the 200 ms target
  (**1108 ms**); this is the first item on the world-class audit
  performance backlog.
- `cross-predict` is single-threaded by construction; flagged for
  audit follow-up (queueing or worker pool).

## Notes for the audit (#270)
- Run Lighthouse against the *same* uvicorn build before fixing
  anything so before/after numbers are honest.
- Re-run the 1000-user pass after the data-model query is paged or
  cached; expect p95 to drop into the 400 ms range.
- The `--headless -u 1 -r 1 -t 5s` smoke run is the regression gate;
  add it to the pre-deploy checklist.
