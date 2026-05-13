"""Regression coverage for the cascade-delete bug the user hit:

  psycopg2.errors.ForeignKeyViolation:
    update or delete on table "chat_sessions" violates foreign key
    constraint "chat_artifacts_session_id_fkey" on table "chat_artifacts"
  psycopg2.errors.ForeignKeyViolation:
    update or delete on table "dataset_records" violates foreign key
    constraint "project_semantic_tables_dataset_id_fkey" on table
    "project_semantic_tables"

Both errors come from `models.py` cascade helpers that miss (or order
incorrectly) the FKs that point at `chat_sessions.id` and
`dataset_records.id`. These tests build the exact graph that triggered
the failure and assert the helpers wipe it cleanly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import models
from models import SessionLocal


# ---------------------------------------------------------------------------
# Shared graph builder
# ---------------------------------------------------------------------------

def _seed_full_graph(db, *, user_id: int, project_id: int,
                     dataset_id: int, session_id: int) -> dict:
    """Build the worst-case dependency graph against a project/dataset/session.

    Touches every FK that points at chat_sessions.id, dataset_records.id
    and projects.id so the cascade helpers have to clear all of them.
    """
    art = models.ChatArtifact(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        dataset_id=dataset_id,
        kind="chart",
        title="cascade-fixture",
        params={}, result={"x": 1},
        pinned=True,
    )
    db.add(art)

    db.add(models.ChatHistory(
        dataset_id=dataset_id,
        session_id=session_id,
        user_message="hi",
        ai_response="hello",
    ))

    pst = models.ProjectSemanticTable(
        project_id=project_id,
        dataset_id=dataset_id,
        role="fact",
    )
    db.add(pst)

    rep = models.Report(
        user_id=user_id,
        project_id=project_id,
        dataset_id=dataset_id,
        title="r",
        notes=None,
        dataset_label="ds",
    )
    db.add(rep)
    db.commit()
    db.refresh(art)
    db.refresh(pst)
    db.refresh(rep)
    return {"artifact_id": art.id, "pst_id": pst.id, "report_id": rep.id}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_delete_chat_session_wipes_artifacts_without_fk_violation(
    client: TestClient, register, project, upload_dataset, chat_session,
    tiny_three_row_csv,
):
    """Reproduces the screenshot's first error — deleting a chat session
    that has chat_artifacts attached must NOT raise FK violation."""
    u, pid = project()
    headers = u["headers"]
    user_id = u["user"]["id"]
    ds_id = upload_dataset(headers, pid, "delcasc_chat", tiny_three_row_csv)
    sid = chat_session(headers, pid, "to-delete")

    db = SessionLocal()
    try:
        seeded = _seed_full_graph(db, user_id=user_id, project_id=pid,
                                  dataset_id=ds_id, session_id=sid)

        # The bug: this used to raise ForeignKeyViolation because the
        # ChatArtifact rows blocked the chat_sessions delete.
        ok = models.delete_chat_session(db, sid, user_id)
        assert ok is True

        assert db.query(models.ChatSession).filter_by(id=sid).count() == 0
        assert db.query(models.ChatArtifact).filter_by(
            id=seeded["artifact_id"]).count() == 0
        assert db.query(models.ChatHistory).filter_by(
            session_id=sid).count() == 0
        # Sibling rows for OTHER tables must survive — the helper only
        # owns chat_session-scoped data.
        assert db.query(models.ProjectSemanticTable).filter_by(
            id=seeded["pst_id"]).count() == 1
        assert db.query(models.Report).filter_by(
            id=seeded["report_id"]).count() == 1
    finally:
        db.close()


def test_delete_project_wipes_semantic_tables_before_datasets(
    client: TestClient, register, project, upload_dataset, chat_session,
    tiny_three_row_csv,
):
    """Reproduces the screenshot's second error — deleting a project
    whose dataset is referenced by project_semantic_tables (and the
    semantic-model + reports + artifacts) must NOT raise FK violation."""
    u, pid = project()
    headers = u["headers"]
    user_id = u["user"]["id"]
    ds_id = upload_dataset(headers, pid, "delcasc_proj", tiny_three_row_csv)
    sid = chat_session(headers, pid, "proj-chat")

    db = SessionLocal()
    try:
        _seed_full_graph(db, user_id=user_id, project_id=pid,
                         dataset_id=ds_id, session_id=sid)

        # Add a project_relationship and a semantic_model + question to
        # make sure those project-level FKs (some of which also reach
        # back into dataset_records) don't trip the delete either.
        ds2_id = upload_dataset(headers, pid, "delcasc_proj2",
                                tiny_three_row_csv)
        db.add(models.ProjectRelationship(
            project_id=pid,
            left_dataset_id=ds_id, left_column="id",
            right_dataset_id=ds2_id, right_column="id",
        ))
        db.add(models.ProjectSemanticModel(
            project_id=pid, description="x", confirmed=False,
        ))
        db.add(models.ProjectModelQuestion(
            project_id=pid, kind="weak_join", prompt="?",
        ))
        db.commit()

        # The bug: this used to raise ForeignKeyViolation because
        # DatasetRecord was being deleted before the rows pointing at
        # it (project_semantic_tables, project_relationships).
        ok = models.delete_project(db, pid, user_id)
        assert ok is True

        # Project + every owned dataset/session/artifact/PST/PR/PM/PMQ
        # must be gone.
        assert db.query(models.Project).filter_by(id=pid).count() == 0
        assert db.query(models.DatasetRecord).filter(
            models.DatasetRecord.id.in_([ds_id, ds2_id])).count() == 0
        assert db.query(models.ChatSession).filter_by(
            project_id=pid).count() == 0
        assert db.query(models.ChatArtifact).filter_by(
            project_id=pid).count() == 0
        assert db.query(models.ProjectSemanticTable).filter_by(
            project_id=pid).count() == 0
        assert db.query(models.ProjectRelationship).filter_by(
            project_id=pid).count() == 0
        assert db.query(models.ProjectSemanticModel).filter_by(
            project_id=pid).count() == 0
        assert db.query(models.ProjectModelQuestion).filter_by(
            project_id=pid).count() == 0
        # Reports survive, but their project_id and dataset_id are
        # nulled (so the recent-reports list still shows them).
        rep_rows = db.query(models.Report).filter_by(user_id=user_id).all()
        assert len(rep_rows) == 1
        assert rep_rows[0].project_id is None
        assert rep_rows[0].dataset_id is None
    finally:
        db.close()


def test_delete_dataset_record_wipes_semantic_table_and_nullifies_report(
    client: TestClient, register, project, upload_dataset, chat_session,
    tiny_three_row_csv,
):
    """Single-dataset delete must clear ProjectSemanticTable +
    ProjectRelationship rows that reference it, and null out
    Report.dataset_id / ChatArtifact.dataset_id."""
    u, pid = project()
    headers = u["headers"]
    user_id = u["user"]["id"]
    ds_id = upload_dataset(headers, pid, "delcasc_ds", tiny_three_row_csv)
    sid = chat_session(headers, pid, "ds-chat")

    db = SessionLocal()
    try:
        seeded = _seed_full_graph(db, user_id=user_id, project_id=pid,
                                  dataset_id=ds_id, session_id=sid)

        ok = models.delete_dataset_record(db, ds_id, user_id)
        assert ok is True

        assert db.query(models.DatasetRecord).filter_by(id=ds_id).count() == 0
        assert db.query(models.ProjectSemanticTable).filter_by(
            id=seeded["pst_id"]).count() == 0
        rep = db.query(models.Report).filter_by(id=seeded["report_id"]).one()
        assert rep.dataset_id is None
        art = db.query(models.ChatArtifact).filter_by(
            id=seeded["artifact_id"]).one()
        assert art.dataset_id is None
    finally:
        db.close()


def test_bulk_delete_dataset_records_wipes_dependents(
    client: TestClient, register, project, upload_dataset, chat_session,
    tiny_three_row_csv,
):
    """Bulk delete shares the FK fan-out with the single-row helper."""
    u, pid = project()
    headers = u["headers"]
    user_id = u["user"]["id"]
    sid = chat_session(headers, pid, "bulk-chat")
    ds_a = upload_dataset(headers, pid, "delcasc_bulk_a", tiny_three_row_csv)
    ds_b = upload_dataset(headers, pid, "delcasc_bulk_b", tiny_three_row_csv)

    db = SessionLocal()
    try:
        seeded_a = _seed_full_graph(db, user_id=user_id, project_id=pid,
                                    dataset_id=ds_a, session_id=sid)
        seeded_b = _seed_full_graph(db, user_id=user_id, project_id=pid,
                                    dataset_id=ds_b, session_id=sid)

        summary = models.bulk_delete_dataset_records(db, [ds_a, ds_b],
                                                    user_id)
        assert summary["deleted_count"] == 2
        assert sorted(summary["deleted_ids"]) == sorted([ds_a, ds_b])
        assert db.query(models.DatasetRecord).filter(
            models.DatasetRecord.id.in_([ds_a, ds_b])).count() == 0
        assert db.query(models.ProjectSemanticTable).filter(
            models.ProjectSemanticTable.dataset_id.in_([ds_a, ds_b])
        ).count() == 0
        # Bulk delete must also null out the nullable FKs (parity with
        # the single-row helper) so historical Report/ChatArtifact rows
        # survive without dangling FKs.
        for art_id in (seeded_a["artifact_id"], seeded_b["artifact_id"]):
            assert db.query(models.ChatArtifact).filter_by(
                id=art_id).one().dataset_id is None
        for rep_id in (seeded_a["report_id"], seeded_b["report_id"]):
            assert db.query(models.Report).filter_by(
                id=rep_id).one().dataset_id is None
    finally:
        db.close()
