# AXIOM — World-Class Audit (Task #270)

**Audit date:** 2026-05-02
**Build under audit:** post-Task #273 (next-intl, EN default + AR option) and post Task #223 frontend test pass.
**Auditor:** main agent (this session).
**Status:** Initial pass. Findings are ranked **Critical / High / Medium / Low**. Items already fixed in this session are noted with **✅ FIXED**; remaining work is summarised in the [Backlog](#backlog).

---

## Executive summary

AXIOM is in solid shape end-to-end:

- Backend tests pass on the consolidated runner (`scripts/run_full_suite.py tests/`), and the frontend Vitest suite is now **34 / 34 green** across 8 component test files (Settings language selector added this session).
- Critical numeric correctness is locked down by the canonical parser pinning (`tests/test_numeric_parser_dmbtr.py` and the API parity test) so the BI surface no longer drifts.
- i18n is wired correctly: `<html lang>` and `dir` flip on the route segment, the `NEXT_LOCALE` cookie is honoured by middleware, and the Settings page round-trips the choice through `PATCH /api/auth/me`.
- The marketing tree owns its own `robots.ts` and `sitemap.ts`; OG images and Inter/JetBrains fonts are loaded with `display: swap`.

The audit found one Critical (no `manifest.webmanifest` shipped, no `viewport`/`themeColor` on the locale layout — both **✅ FIXED** this session), three Highs (data-model query at 1k users, missing per-page metadata audit on marketing, no automated Lighthouse run), and a small set of Medium / Low polish items captured in the [Backlog](#backlog).

---

## 1. Functional & integration coverage

| Area | Status | Notes |
| --- | --- | --- |
| Auth (register / login / forgot / reset) | ✅ | Covered by `tests/test_api_endpoints.py` and the `tests/test_e2e_journey.py` 10-step flow. |
| Dataset upload + profile | ✅ | `_db_isolation` autouse fixture cleans across runs; profile artefact persists. |
| Chat tool dispatch (`profile_dataset`, `make_chart`, `predict_column`, `cluster_dataset`, `query_model`, `list_model`, `explain_model`) | ✅ | Each variant exercised in `tests/test_api_endpoints.py`. |
| BI aggregation (KPI, pivot, dashboard, reconciliation) | ✅ | Pinned by `test_bi_pivot_dmbtr_parity_kpi_pivot_canonical` and the parser invariants in `replit.md`. |
| Predictive flow (Prophet / sklearn) | ✅ | Unit + endpoint tested. |
| Daily Pulse scheduler | ⚠️ | Single-worker assumption documented in `replit.md`. **Re-flag before scaling out.** |
| Frontend component tests | ✅ | 34 / 34 green; `setup.ts` mocks `next-intl`, `next/navigation` (incl. `useParams`), `next/image`, `next/dynamic`. |
| End-to-end flows in real browser | ⚠️ | Playwright dep installed; only one project configured. **Add an EN project + locale-switch step.** |

**Verdict:** Functional coverage is strong. The only gap is browser-driven flows under both locales — captured as backlog item B-1.

---

## 2. Performance baseline

The full Locust write-up lives at [`tests/performance/baselines/post-i18n.md`](../../tests/performance/baselines/post-i18n.md). Headlines:

- Read endpoints stay under the **300 ms p95** budget at 100 concurrent users for everything except `GET /api/projects/{id}/data-model` (268 ms — within 10 %).
- At 1000 concurrent users the same endpoint blows the budget at **p95 = 1108 ms** (4× over the 300 ms target). This is the first item on the perf backlog.
- Write paths (`upload`, `cross-predict`) are dominated by parse + sklearn; both are single-process bound today.

**Verdict:** Read p95 is healthy at the realistic load. Single-worker write paths and the data-model query are the two hot spots.

---

## 3. Security posture

The repo carries first-class security primitives we can lean on:

- JWT + bcrypt for auth (`backend/auth.py`), tokens stored client-side via `setToken` and never logged.
- Strict envelope contract for 4xx / 5xx (`tests/test_error_handling.py`) — required `error` + `detail` keys mean we cannot accidentally leak stack traces.
- `replit.md` parser invariants prevent silent numeric corruption (a high-impact integrity issue for a BI product).
- Secrets are read from environment; no hard-coded keys in the tree (verified via `rg`).

Recommended follow-ups (not blockers):

- Run `runDependencyAudit`, `runSastScan`, and `runHoundDogScan` from the `security_scan` skill on a regular cadence and attach the report to the audit doc.
- Add a CSP header to the marketing routes; today nothing is set, which Lighthouse will flag.
- Confirm the Resend integration template doesn't echo user input verbatim.

---

## 4. Accessibility

Manual spot-check of the EN/AR Settings page and the chat workspace:

- Form controls are properly labelled (radios in Settings have explicit `htmlFor`/`id` pairs — that's what made the new test trivial to write against `getElementById`).
- The chat panel auto-scroll calls `scrollIntoView` on a ref; jsdom-side stub added for tests, no production impact.
- Buttons enforce a minimum 44 px tap target on the Settings save action — good. Other actions across the workspace should be re-checked for the same.

Backlog: run `axe` against `/`, `/features`, `/pricing`, `/app/upload`, and `/app/settings` under both locales (B-2).

---

## 5. Arabic / RTL polish

- `localeDir()` returns `rtl` for `ar` and the `[locale]/layout.tsx` tree honours it on `<html>`. ✅
- The catalogue (`messages/ar.json`) covers every key the EN catalogue exposes for `common.*`, `settings.*`, and the marketing surfaces touched in #273.
- Tailwind logical properties (`ms-auto`, `ps-*`, `pe-*`) are used in the new Settings UI so spacing flips correctly in RTL — verified in source.
- One literal Arabic greeting still lives in `ChatPanel.tsx` (line 116, "أهلًا بك"). Not a regression but should move to the catalogue (B-3).

---

## 6. SEO

- `robots.ts` and `sitemap.ts` are present, dynamic (sitemap pulls glossary/guides/compare via `getAllGlossary` etc.), and honour `SITE.url`. ✅
- `metadata` block on the locale layout sets `metadataBase`, `title`/`template`, `openGraph`, `twitter`, and `icons`. ✅
- **Now also sets `manifest`** so iOS/Android can install the app. ✅ FIXED
- Per-page `generateMetadata` audit not yet performed — captured as B-4.

---

## 7. PWA / mobile

- **Was missing `manifest.webmanifest` and a `viewport` block.** Both shipped this session: a minimal but valid manifest at `frontend/public/manifest.webmanifest`, and `export const viewport` in the locale layout with `width=device-width, initial-scale=1` plus theme-coloured chrome for light/dark. ✅ FIXED
- Service worker / offline strategy is intentionally out of scope for this audit (the app needs the backend to do anything useful).

---

## 8. Lighthouse / Core Web Vitals

Not yet captured. The locust baseline is the input; Lighthouse should run against the same uvicorn build before any optimisation lands (so before/after deltas are honest). Captured as B-5.

---

## Backlog

| ID | Severity | Area | Description |
| --- | --- | --- | --- |
| B-1 | High | Tests | Add a second Playwright project pinned to `locale: "en"` plus an explicit locale-switch step that asserts `<html dir>` flips. |
| B-2 | High | A11y | Run `axe` against the marketing + workspace surfaces under both locales. Track in a follow-up audit doc. |
| B-3 | Medium | Arabic | Move the hardcoded "أهلًا بك" greeting in `ChatPanel.tsx` into `messages/*.json` so it adapts to EN. |
| B-4 | High | SEO | Walk every marketing page (`/about`, `/contact`, `/features`, `/pricing`, glossary/guides/compare) and confirm `generateMetadata` returns the right title/description/canonical. |
| B-5 | High | Perf | Capture a Lighthouse baseline against the post-i18n build, then re-run after the data-model query is paged or cached. |
| B-6 | Medium | Perf | Page (or cache) `GET /api/projects/{id}/data-model` so 1000-user p95 drops below 400 ms. |
| B-7 | Medium | Security | Wire the `security_scan` skill into a scheduled run; attach the latest report under `docs/audits/`. |
| B-8 | Low | Polish | Add a `<link rel="apple-touch-icon">` set + 192/512 PNG variants for the manifest's maskable purpose. |

---

## Items fixed in this session

- ✅ Added `frontend/public/manifest.webmanifest` and wired it via the locale layout's `metadata.manifest`.
- ✅ Added `export const viewport` (with `themeColor` for light + dark) to `frontend/src/app/[locale]/layout.tsx`.
- ✅ Added `useParams` to the test `next/navigation` mock so locale-aware client pages render in Vitest.
- ✅ MSW handlers for `/api/auth/me` (GET + PATCH) plus `/api/users/me` aliases.
- ✅ Added `frontend/src/tests/utils/i18n.ts` so component tests can resolve translations against the same JSON catalogues the app ships.
- ✅ New `SettingsLanguage` test (3 cases: rendering, save-disabled-by-default, PATCH + cookie).
- ✅ Locust post-i18n baseline at `tests/performance/baselines/post-i18n.md`.
