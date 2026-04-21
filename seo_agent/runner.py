"""Orchestrator: full weekly cycle.

Steps (each guarded so a failure in one stage does not kill the run):
  1. Trend research      (sources.gather_all)
  2. Topic selection     (selector.select_topics)
  3. SERP / info-gap     (serp.fetch_top_results / information_gap_brief)
  4. Page generation     (generator.generate_*)
  5. Refresh stale pages (refresh.stale_pages / refresh_one)
  6. GEO visibility      (geo_check.run_geo_checks)
  7. Persist + email     (db / report.send_weekly_report)
"""

from __future__ import annotations
import os
import traceback
from datetime import datetime
from typing import Dict, List

from . import sources, selector, serp, generator, refresh, geo_check, report
from .config import AgentConfig, load_config, env_override
from .db import init_agent_db, get_session, AgentRun, GeoCheckResult, PageMetric
from .review import write_draft


def _bookkeep(in_t: int, out_t: int, totals: Dict) -> None:
    totals["in_tokens"] += in_t
    totals["out_tokens"] += out_t
    totals["cost"] = generator.estimate_cost(totals["in_tokens"], totals["out_tokens"])


def _budget_left(cfg: AgentConfig, totals: Dict) -> bool:
    return totals["cost"] < cfg.weekly_budget_usd


def run_weekly_cycle(cfg: AgentConfig | None = None, dry_run: bool = False) -> Dict:
    init_agent_db()
    cfg = env_override(cfg or load_config())
    sess = get_session()
    run = AgentRun(status="running", config_snapshot=cfg.to_dict())
    sess.add(run); sess.commit(); sess.refresh(run)
    run_id = run.id
    sess.close()

    totals = {"in_tokens": 0, "out_tokens": 0, "cost": 0.0}
    errors: List[str] = []
    drafts_meta: List[Dict] = []
    refreshed_meta: List[Dict] = []
    trending_keywords: List[str] = []

    try:
        # 1. Trends
        raw, src_errs = sources.gather_all(cfg.sources_enabled)
        errors += src_errs

        # 2. Selection (re-scored with observed organic-traffic signal)
        selected = selector.select_topics(
            raw,
            top_n=max(cfg.max_new_pages_per_week * 2, 6),
            traffic_lookback_days=cfg.topic_dead_lookback_days,
            dead_factor=cfg.topic_dead_score_factor,
            winner_factor=cfg.topic_winner_score_factor,
        )
        trending_keywords = [s["topic"] for s in selected[: max(3, cfg.max_new_pages_per_week)]]

        # 3-4. SERP brief + generate
        created = 0
        dropped = 0
        for cand in selected:
            if created >= cfg.max_new_pages_per_week:
                break
            if not _budget_left(cfg, totals):
                errors.append("budget cap hit during page generation")
                break
            topic = cand["topic"]
            try:
                top = serp.fetch_top_results(topic, n=3)
                # Best-effort: also pull the current Perplexity answer so the
                # generator can compete on the LLM-cited surface, not just SEO.
                ai_ans = serp.fetch_perplexity_answer(topic)
                brief = serp.information_gap_brief(topic, top, ai_answer=ai_ans)
                kind = generator.classify_kind(topic)
                if kind == "guides":
                    data, in_t, out_t, fail = generator.generate_guide_page(cfg.openai_model, topic, brief)
                else:
                    data, in_t, out_t, fail = generator.generate_glossary_page(cfg.openai_model, topic, brief)
                _bookkeep(in_t, out_t, totals)
                if not data:
                    dropped += 1
                    errors.append(f"dropped '{topic[:80]}': {fail}")
                    continue
                if dry_run:
                    drafts_meta.append({"kind": kind, "title": data.get("term") or data.get("title"),
                                        "status": "dry_run"})
                    created += 1
                    continue
                d = write_draft(run_id=run_id, kind=kind, payload=data,
                                target_query=topic,
                                info_gain=f"Top SERP brief used. Sources: {','.join(cand.get('sources',[cand['source']]))}")
                status = "pending"
                if cfg.auto_publish:
                    from .review import approve_draft
                    res = approve_draft(d.id, reviewer="auto-publish",
                                        notes="auto_publish=True")
                    status = "published" if res.get("ok") else f"auto-publish failed: {res.get('error')}"
                drafts_meta.append({"kind": kind, "title": d.title, "status": status, "id": d.id})
                created += 1
            except Exception as e:
                dropped += 1
                errors.append(f"generation failure '{topic[:60]}': {e}")

        # 5. Refresh
        refreshed_count = 0
        try:
            stale = refresh.stale_pages(cfg.refresh_after_days)
        except Exception as e:
            stale = []
            errors.append(f"refresh scan failed: {e}")
        for page in stale:
            if refreshed_count >= cfg.max_refresh_pages_per_week:
                break
            if not _budget_left(cfg, totals):
                errors.append("budget cap hit during refresh")
                break
            try:
                data, in_t, out_t, fail = refresh.refresh_one(cfg.openai_model, page)
                _bookkeep(in_t, out_t, totals)
                if not data:
                    errors.append(f"refresh failed for {page['slug']}: {fail}")
                    continue
                if dry_run:
                    refreshed_meta.append({"kind": page["kind"], "slug": page["slug"], "status": "dry_run"})
                    refreshed_count += 1
                    continue
                d = write_draft(run_id=run_id, kind=page["kind"], payload=data,
                                target_query=f"refresh:{page['slug']}",
                                info_gain="Stats and dated language refreshed.",
                                is_refresh=True)
                status = "pending"
                if cfg.auto_publish:
                    from .review import approve_draft
                    res = approve_draft(d.id, reviewer="auto-publish",
                                        notes="auto_publish=True (refresh)")
                    status = "published" if res.get("ok") else f"auto-publish failed: {res.get('error')}"
                refreshed_meta.append({"kind": page["kind"], "slug": page["slug"],
                                       "status": status, "id": d.id})
                refreshed_count += 1
            except Exception as e:
                errors.append(f"refresh exception {page.get('slug')}: {e}")

        # 5b. Pull per-URL organic-traffic metrics (free analytics signal).
        analytics_rows = 0
        try:
            metric_rows, an_errs = sources.fetch_analytics(
                cfg.analytics_source,
                site_url=cfg.analytics_site_url,
                lookback_days=cfg.analytics_lookback_days,
            )
            errors += an_errs
            if metric_rows and not dry_run:
                sess = get_session()
                try:
                    for m in metric_rows:
                        sess.add(PageMetric(
                            period_start=m.get("period_start"),
                            period_end=m.get("period_end"),
                            source=m.get("source", cfg.analytics_source or "unknown"),
                            url=m.get("url"),
                            slug=m.get("slug") or "",
                            kind=m.get("kind"),
                            impressions=int(m.get("impressions") or 0),
                            clicks=int(m.get("clicks") or 0),
                            ctr=float(m.get("ctr") or 0.0),
                            avg_position=m.get("avg_position"),
                        ))
                    sess.commit()
                finally:
                    sess.close()
            analytics_rows = len(metric_rows)
        except Exception as e:
            errors.append(f"analytics fetch failed: {e}")

        # 6. GEO check
        geo_rate = None
        try:
            if _budget_left(cfg, totals):
                geo_results, geo_in, geo_out = geo_check.run_geo_checks(
                    cfg.geo_prompts, model=cfg.openai_model)
                _bookkeep(geo_in, geo_out, totals)
                geo_rate = geo_check.mention_rate(geo_results)
                sess = get_session()
                try:
                    for r in geo_results:
                        sess.add(GeoCheckResult(
                            run_id=run_id, prompt=r["prompt"],
                            mentioned=r["mentioned"], cited=r["cited"],
                            position=r["position"], answer_excerpt=r["answer_excerpt"],
                        ))
                    sess.commit()
                finally:
                    sess.close()
            else:
                errors.append("budget cap hit before GEO check")
        except Exception as e:
            errors.append(f"geo check failed: {e}")

        summary = {
            "finished_at": datetime.utcnow().isoformat(timespec="seconds"),
            "topics_discovered": len(raw),
            "topics_selected": len(selected),
            "drafts_created": created,
            "drafts_dropped": dropped,
            "drafts_refreshed": refreshed_count,
            "openai_input_tokens": totals["in_tokens"],
            "openai_output_tokens": totals["out_tokens"],
            "estimated_cost_usd": round(totals["cost"], 4),
            "trending_keywords": trending_keywords,
            "drafts": drafts_meta,
            "refreshed": refreshed_meta,
            "geo_mention_rate": geo_rate,
            "analytics_source": cfg.analytics_source,
            "analytics_rows_ingested": analytics_rows,
            "errors": errors,
        }

        # 7. Persist + email
        sess = get_session()
        try:
            r = sess.query(AgentRun).filter(AgentRun.id == run_id).first()
            if r:
                r.finished_at = datetime.utcnow()
                r.status = "ok" if not errors else "partial"
                r.topics_discovered = summary["topics_discovered"]
                r.topics_selected = summary["topics_selected"]
                r.drafts_created = summary["drafts_created"]
                r.drafts_refreshed = summary["drafts_refreshed"]
                r.drafts_dropped = summary["drafts_dropped"]
                r.openai_input_tokens = summary["openai_input_tokens"]
                r.openai_output_tokens = summary["openai_output_tokens"]
                r.estimated_cost_usd = summary["estimated_cost_usd"]
                r.summary = summary
                r.errors = "\n".join(errors) if errors else None
                sess.commit()
        finally:
            sess.close()

        if not dry_run and cfg.report_email_to:
            report.send_weekly_report(cfg.report_email_to, summary)

        return summary

    except Exception as e:
        tb = traceback.format_exc()
        sess = get_session()
        try:
            r = sess.query(AgentRun).filter(AgentRun.id == run_id).first()
            if r:
                r.finished_at = datetime.utcnow()
                r.status = "error"
                r.errors = tb
                sess.commit()
        finally:
            sess.close()
        return {"status": "error", "error": str(e), "traceback": tb,
                "estimated_cost_usd": totals["cost"]}
