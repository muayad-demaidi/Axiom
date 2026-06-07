# AXIOM — Implementation Roadmap to the Conversational-Analyst Vision

**Vision:** Not "an AI that analyses a file" but **a conversational data
analyst that knows your business, links your project files over time,
leads the analysis, and grows with you** — a moat stateless horizontal
AI (ChatGPT/Claude) cannot copy because it never holds *your* memory.

This roadmap is sequenced by leverage × (1/risk). Each phase ships a
working, deployed, verified increment. Free-tier safe: no heavy/iterative
runtime deps, sub-second hot paths, graceful fallbacks everywhere.

---

## Phase 0 — Foundation ✅ DONE
Login (Vercel protection), file upload (pyarrow fix), Arabic/RTL, the
MASE trust guardrail, and a fast closed-form seasonal forecast engine
(195s → 0.25s). The product actually works end-to-end.

## Phase 1 — User long-term memory & learning ✅ DONE
Postgres `user_memory` (business profile + reporting preferences) and
`user_learned_facts` (durable cross-project facts), injected into the
chat agent's system prompt; `/api/memory` API. Replaces the dead
replit.db memory. *This is the keystone of "learns about the user."*

## Phase 2 — Sandboxed code interpreter 🔴 NEXT (biggest capability leap)
- **Goal:** let the agent write & run pandas/SQL to compute *anything*,
  not just the predefined tools — the thing Julius / ChatGPT ADA / Hex do.
- **Approach:** a locked-down execution tool added to the chat tool-loop.
  Restricted builtins, no network/filesystem, CPU+memory+time limits,
  the active project dataframe(s) pre-loaded as `df`/named frames.
  Start with a hardened in-process restricted exec; graduate to a
  microVM/container sandbox (e.g. E2B-style) when budget allows.
- **Security:** allowlist imports (pandas/numpy/statsmodels/plotly only),
  AST-scan to reject `__import__`, `eval`, dunder access, file/network;
  hard timeout; output size cap. Never run unreviewed code outside the
  sandbox.
- **Acceptance:** "compute the 3-month rolling median of net margin by
  region" works with no purpose-built tool; unsafe code is rejected.

## Phase 3 — Semantic memory + auto-learning 🟠
- **Goal:** the agent remembers *what was discussed* and recalls the
  relevant past automatically; it writes durable facts on its own.
- **Approach:** enable `pgvector` on Render Postgres; embed chat turns +
  dataset/column descriptions; retrieve top-k relevant memories per turn
  (RAG over the user's own history). A lightweight post-turn extractor
  distils new durable facts into `user_learned_facts` (heuristic first,
  one cheap LLM call later).
- **Acceptance:** "like we did last month" resolves to the actual prior
  analysis; preferences stated in chat persist without a form.

## Phase 4 — Smart project data fusion 🟠
- **Goal:** the daily-sales scenario — auto-detect that repeated uploads
  are the same series, append them, and roll up daily→weekly→monthly.
- **Approach:** schema-fingerprint + *semantic* column matching (embed
  column names/values so "Sales"≈"المبيعات"); extend `cross_predict`
  auto-link to propose "this looks like a new slice of <dataset> —
  append?"; a first-class time-aggregation tool.
- **Acceptance:** upload 30 daily files → one unified series + automatic
  weekly/monthly views, with the agent confirming the merge in chat.

## Phase 5 — Plan → Execute → Critic agent loop 🟡
- **Goal:** deeper, self-correcting analysis ("the model leads").
- **Approach:** wrap the tool-loop in an explicit planner that drafts a
  short analysis plan, executes steps, then a critic pass validates
  numbers/assumptions (extends the MASE-style guardrail to all outputs)
  before presenting. Bounded iterations to control cost/latency.
- **Acceptance:** complex asks yield a stated plan + validated result;
  the critic catches an injected wrong number in eval.

## Phase 6 — Live connectors + standards 🟢
- **Goal:** become a daily habit, not a one-off upload.
- **Approach:** Google Sheets / Shopify / Salla live sources (data
  refreshes itself); expose tools/data over **MCP** for standard
  integration; resurface the existing Daily/Weekly Pulse on top.
- **Acceptance:** connect a source once → dashboards stay live; weekly
  pulse email lands (needs a Resend key from the owner).

---

## Cross-cutting principles
- **Security:** sandbox all generated code; per-user data isolation;
  read-only DB role for any generated SQL; never leak one project into
  another.
- **Performance:** keep request hot paths free of iterative MLE/Stan;
  prefer closed-form or API-backed heavy compute; cache aggressively.
- **Trust:** every surfaced number is computed (never invented) and
  guardrailed (MASE for forecasts → extend to all claims).
- **Arabic-first:** every user-facing string ships in `en.json` +
  `ar.json` at exact key parity; RTL verified.
- **Ship discipline:** build → test locally → deploy → **verify live**
  (this loop caught the pyarrow, Prophet-missing, and 195s-latency bugs).
