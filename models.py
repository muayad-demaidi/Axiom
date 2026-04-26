import os
import hashlib
import secrets
import bcrypt
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, JSON, Boolean, ForeignKey, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Please configure a PostgreSQL database.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """Model for user accounts"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    subscription_type = Column(String(50), default="free")
    subscription_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    analysis_count = Column(Integer, default=0)
    storage_used = Column(Float, default=0.0)
    phone = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    gender = Column(String(20), nullable=True)
    specialty = Column(String(100), nullable=True)
    specialty_other = Column(String(255), nullable=True)
    trial_start = Column(DateTime, default=datetime.utcnow)
    trial_end = Column(DateTime, nullable=True)
    session_token = Column(String(128), nullable=True, index=True)
    session_expires = Column(DateTime, nullable=True)
    last_dataset_id = Column(Integer, nullable=True)
    # AI assistant response mode persisted across sessions. One of
    # "simple" (friendly default, plain language) or "expert" (full
    # technical detail, code, metrics). Mirrors the in-session value
    # at ``st.session_state.assistant_mode`` so the picker reflects
    # the user's preference immediately on login / dashboard load.
    assistant_mode = Column(String(16), nullable=True, default="simple")


class PasswordResetToken(Base):
    """One-time tokens for password reset email links."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SupportMessage(Base):
    """Model for support messages"""
    __tablename__ = "support_messages"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)


class Subscription(Base):
    """Model for subscription plans"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_type = Column(String(50), nullable=False)
    status = Column(String(50), default="active")
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    amount = Column(Float, nullable=True)


class Project(Base):
    """A user-owned analysis project that groups one or more datasets ('sheets').

    Replaces the old "single bag of datasets per user" model so the post-login
    landing page can offer a real Projects browser. A project is the unit users
    actually think in: a folder for a piece of analysis work that may pull
    together several CSV/Excel files.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    last_opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    # Per-project override for the AI/UI mode. NULL means "fall back to
    # the user's assistant_mode preference"; a value here forces this
    # project into Guided or Expert regardless of the user-level pick.
    # Stored as the API vocabulary ("guided" / "expert") so the column
    # is self-explanatory in the database — the legacy `assistant_mode`
    # column on User keeps using "simple" for backwards compatibility.
    mode = Column(String(16), nullable=True)
    # Soft-archive flag for the projects management workspace. NULL =
    # active project; a timestamp = "user archived this on this date".
    # We keep the row (and all its data) so Restore is non-destructive
    # and the projects index just filters on this column.
    archived_at = Column(DateTime, nullable=True, index=True)


class ProjectKnowledgeBase(Base):
    """Optional reference attached to a project that biases AI answers.

    One row per project (uniqueness enforced via the unique constraint on
    ``project_id``). Stores extracted plain text plus metadata about the
    source so the panel can render "PDF · brief.pdf · 12,034 chars · added
    Apr 22". The extracted text is injected into the AI assistant's system
    prompt whenever any sheet in the project is being analysed.
    """
    __tablename__ = "project_knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, unique=True, index=True)
    source_kind = Column(String(16), nullable=False)  # 'text' | 'pdf' | 'url'
    source_label = Column(String(512), nullable=False)
    content_text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ProjectLearnedNote(Base):
    """An auto-appended record of an AI exchange inside a project.

    Every successful chat reply or AI-generated insight inside an open
    project is stamped here so the assistant's context grows over time.
    Notes are scoped strictly to the owning project — we never leak one
    project's history into another.
    """
    __tablename__ = "project_learned_notes"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    kind = Column(String(16), nullable=False)  # 'chat' | 'insight'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DatasetRecord(Base):
    """Model to store uploaded dataset records for historical tracking"""
    __tablename__ = "dataset_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    dataset_name = Column(String(255), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    period_month = Column(Integer, nullable=True)
    period_year = Column(Integer, nullable=True)
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)
    columns_info = Column(JSON, nullable=True)
    data_hash = Column(String(64), nullable=False)
    summary_stats = Column(JSON, nullable=True)
    file_size = Column(Float, nullable=True)
    source_parquet = Column(LargeBinary, nullable=True)
    parse_meta = Column(JSON, nullable=True)
    step_recipes = Column(JSON, nullable=True)
    active_step_index = Column(Integer, nullable=True)
    # When set, this dataset is pinned to the top of the user's recent
    # list. The timestamp doubles as a sort key so the most recently
    # pinned items show first within the pinned group.
    pinned_at = Column(DateTime, nullable=True, index=True)
    

class DatasetRelationship(Base):
    """User-confirmed relationship between two of their datasets.

    Mirrors a Power BI model edge: a left dataset/column points at a
    right dataset/column with a stated cardinality and the join type
    that should be used when the joined view is materialised.
    """
    __tablename__ = "dataset_relationships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    left_dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                             nullable=False, index=True)
    left_column = Column(String(255), nullable=False)
    right_dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                              nullable=False, index=True)
    right_column = Column(String(255), nullable=False)
    cardinality = Column(String(8), nullable=False, default="1:N")
    join_type = Column(String(16), nullable=False, default="left")
    created_at = Column(DateTime, default=datetime.utcnow)


class ProjectSemanticTable(Base):
    """Per-dataset role/grain/PK metadata used by the multi-CSV copilot.

    One row per dataset attached to a project. Holds the auto-detected
    role and grain plus the user-confirmed overrides — `confirmed=True`
    means the user has explicitly accepted the role/grain/PK on this
    table, otherwise the chat is free to refresh them on its own."""
    __tablename__ = "project_semantic_tables"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                        nullable=False, index=True, unique=True)
    role = Column(String(16), nullable=False, default="fact")
    grain = Column(JSON, nullable=True)
    pk_columns = Column(JSON, nullable=True)
    fk_columns = Column(JSON, nullable=True)
    suspicious = Column(JSON, nullable=True)
    role_signals = Column(JSON, nullable=True)
    columns_meta = Column(JSON, nullable=True)
    confirmed = Column(Boolean, default=False, nullable=False)
    profiled_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class ProjectRelationship(Base):
    """Persisted cross-dataset join with confidence/evidence/status.

    Coexists with the legacy ``DatasetRelationship`` (which only stored
    user-confirmed edges). This table keeps the full proposal history so
    the analyst copilot can re-show evidence and the chat can label
    inferred vs. confirmed joins at query time.
    """
    __tablename__ = "project_relationships"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    left_dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                             nullable=False, index=True)
    left_column = Column(String(255), nullable=False)
    right_dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                              nullable=False, index=True)
    right_column = Column(String(255), nullable=False)
    cardinality = Column(String(8), nullable=False, default="1:N")
    join_type = Column(String(16), nullable=False, default="left")
    # status: "proposed" | "confirmed" | "rejected"
    status = Column(String(16), nullable=False, default="proposed", index=True)
    # band: "high" | "medium" | "low" | "inferred"
    band = Column(String(16), nullable=False, default="medium")
    confidence = Column(Float, nullable=False, default=0.0)
    evidence = Column(JSON, nullable=True)
    overlap_score = Column(Float, nullable=True)
    name_score = Column(Float, nullable=True)
    dtype_score = Column(Float, nullable=True)
    # When the user confirms a relationship we keep their explicit
    # choice frozen — subsequent re-profiles never overwrite it.
    user_locked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ProjectSemanticModel(Base):
    """Project-level semantic model: free-text business description +
    confirmation flag. One row per project."""
    __tablename__ = "project_semantic_models"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    confirmed = Column(Boolean, default=False, nullable=False)
    last_refreshed_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class ProjectModelQuestion(Base):
    """Open clarification question the chat surfaces in the proactive
    question bar (weak join, ambiguous grain, summary-link, role-pick).

    `status` lifecycle: open → answered | dismissed."""
    __tablename__ = "project_model_questions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    kind = Column(String(32), nullable=False)
    prompt = Column(Text, nullable=False)
    target = Column(JSON, nullable=True)
    options = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="open", index=True)
    answer = Column(JSON, nullable=True)
    external_id = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime, nullable=True)


class AnalysisHistory(Base):
    """Model to store analysis history"""
    __tablename__ = "analysis_history"
    
    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, nullable=False)
    analysis_type = Column(String(100), nullable=False)
    analysis_date = Column(DateTime, default=datetime.utcnow)
    results = Column(JSON, nullable=True)
    ai_insights = Column(Text, nullable=True)


class ChatSession(Base):
    """A named conversation thread inside a project.

    Projects own multiple chat sessions so users can keep separate
    investigations distinct (e.g. "Q1 revenue analysis" vs "outlier
    review") while AXIOM still pulls in the whole project's data as
    context for each one.
    """
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    title = Column(String(255), nullable=False, default="New chat")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    """Model to store chat conversations"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    # Legacy `dataset_id` kept nullable for back-compat with rows from the
    # pre-session world. New rows are always anchored on `session_id`,
    # which transitively gives us project + user.
    dataset_id = Column(Integer, nullable=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"),
                        nullable=True, index=True)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class ChatArtifact(Base):
    """Persisted output of a tool the chat model invoked.

    `kind` is one of: profile | prediction | chart | cluster | insight | qa.
    `params` records the tool inputs (so we can re-run / what-if) and
    `result` stores the rendered payload the frontend consumes
    (chart points, prediction coefficients, cluster sizes, etc.). The
    `pinned` flag controls whether the artifact appears in the Final
    Report by default.
    """
    __tablename__ = "chat_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"),
                        nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                        nullable=True, index=True)
    kind = Column(String(32), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="Artifact")
    params = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Report(Base):
    """Persisted record of a generated PDF report.

    We store metadata only (title, notes, dataset reference, snapshot
    of the dataset's display name) so users can come back later and
    re-download a previously generated report by re-running the same
    PDF endpoint with the saved parameters. Storing the PDF bytes
    themselves would bloat the DB; the deterministic regeneration is
    enough to satisfy "re-download".
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"),
                     nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"),
                        nullable=True, index=True)
    dataset_id = Column(Integer, ForeignKey("dataset_records.id"),
                        nullable=True, index=True)
    title = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    # Snapshot of the dataset's display name at generation time, so the
    # recent-reports list still has something to show if the dataset is
    # later renamed or deleted.
    dataset_label = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


def init_db():
    """Initialize database tables and apply lightweight in-place migrations.

    SQLAlchemy's `create_all` only creates missing tables — it never ALTERs
    existing ones. To keep older deployments compatible when we add columns
    (e.g. the persisted step-history fields), we run idempotent
    `ADD COLUMN IF NOT EXISTS` statements right after table creation.
    """
    from sqlalchemy import text

    Base.metadata.create_all(bind=engine)

    _migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_dataset_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS assistant_mode VARCHAR(16) DEFAULT 'simple'",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS mode VARCHAR(16)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS ix_projects_archived_at ON projects(archived_at)",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS source_parquet BYTEA",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS parse_meta JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS step_recipes JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS active_step_index INTEGER",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)",
        "CREATE INDEX IF NOT EXISTS ix_dataset_records_project_id ON dataset_records(project_id)",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS ix_dataset_records_pinned_at ON dataset_records(pinned_at)",
        """CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token_hash VARCHAR(128) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash ON password_reset_tokens(token_hash)",
    ]
    # Newer tables that may not exist on older deployments need an
    # explicit create step before the in-place ALTERs above run, since
    # `create_all` only handles brand-new schemas. ``checkfirst`` makes
    # this idempotent on already-migrated DBs.
    try:
        DatasetRelationship.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass
    # New tables for the per-project knowledge base. Created explicitly so
    # older deployments pick them up without needing a migration tool.
    for _t in (ProjectKnowledgeBase.__table__, ProjectLearnedNote.__table__,
               ChatSession.__table__, ChatArtifact.__table__,
               Report.__table__,
               ProjectSemanticTable.__table__,
               ProjectRelationship.__table__,
               ProjectSemanticModel.__table__,
               ProjectModelQuestion.__table__):
        try:
            _t.create(bind=engine, checkfirst=True)
        except Exception:
            pass
    # ChatHistory needs a `session_id` column on older deployments so
    # session-aware writes don't 500 against legacy schemas.
    _migrations.extend([
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES chat_sessions(id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_history_session_id ON chat_history(session_id)",
        # Multi-CSV semantic model: clarification questions need a
        # stable identifier so we can recognize re-generated rows.
        "ALTER TABLE project_model_questions ADD COLUMN IF NOT EXISTS external_id VARCHAR(128)",
        "CREATE INDEX IF NOT EXISTS ix_project_model_questions_external_id ON project_model_questions(external_id)",
        # Make the per-user "Quick Chats" auto-project idempotent under
        # concurrent landing-page submissions.
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_projects_user_quick_chats "
        "ON projects (user_id) WHERE name = 'Quick Chats'",
        # ----------------------------------------------------------------
        # Hot-path composite indexes (perf task #226). Each index targets
        # a query that the workspace runs on every navigation: chat
        # session list per project, message history per session, artifact
        # drawer fetch per session, project list ordering on the
        # management page, and the recent-reports panel. The previous
        # single-column FK indexes only narrowed the WHERE; Postgres still
        # had to do an extra sort. Composite indexes that include the
        # ORDER BY columns let the planner walk the index in order and
        # skip the sort, which is the dominant cost on large tables.
        # All `IF NOT EXISTS` so older deployments and concurrent worker
        # boots don't fight each other.
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_project_updated "
        "ON chat_sessions (project_id, updated_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_chat_history_session_ts "
        "ON chat_history (session_id, timestamp, id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_artifacts_session_created "
        "ON chat_artifacts (session_id, created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_dataset_records_project_uploaded "
        "ON dataset_records (project_id, upload_date DESC)",
        "CREATE INDEX IF NOT EXISTS ix_projects_user_last_opened "
        "ON projects (user_id, last_opened_at DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS ix_reports_project_created "
        "ON reports (project_id, created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS ix_project_learned_notes_project_created "
        "ON project_learned_notes (project_id, created_at DESC)",
    ])
    with engine.begin() as conn:
        for stmt in _migrations:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Older Postgres versions without IF NOT EXISTS support, or
                # races between workers, shouldn't block app startup.
                pass


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def save_dataset_record(db, filename, dataset_name, period_month, period_year,
                        row_count, column_count, columns_info, data_hash, summary_stats=None,
                        user_id=None, source_parquet=None, parse_meta=None,
                        step_recipes=None, active_step_index=None, project_id=None):
    """Save a dataset record to the database"""
    record = DatasetRecord(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        dataset_name=dataset_name,
        period_month=period_month,
        period_year=period_year,
        row_count=row_count,
        column_count=column_count,
        columns_info=columns_info,
        data_hash=data_hash,
        summary_stats=summary_stats,
        source_parquet=source_parquet,
        parse_meta=parse_meta,
        step_recipes=step_recipes,
        active_step_index=active_step_index,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    # Touch the parent project so it bubbles to the top of the projects grid.
    if project_id is not None:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj is not None:
            proj.updated_at = datetime.utcnow()
            proj.last_opened_at = datetime.utcnow()
            db.commit()
    return record


def dataset_name_exists_in_project(db, project_id, name, exclude_dataset_id=None,
                                    user_id=None):
    """Return True if another sheet in ``project_id`` already uses ``name``.

    Comparison is case-insensitive and trims whitespace to match how the
    rename UI normalises input. ``exclude_dataset_id`` lets callers ignore
    the sheet currently being renamed. When ``project_id`` is None (a
    legacy unattached sheet) this always returns False — there is no
    project scope to collide within.
    """
    if project_id is None:
        return False
    cleaned = (name or "").strip()
    if not cleaned:
        return False
    from sqlalchemy import func
    q = (db.query(DatasetRecord)
           .filter(DatasetRecord.project_id == project_id,
                   func.lower(DatasetRecord.dataset_name) == cleaned.lower()))
    if exclude_dataset_id is not None:
        q = q.filter(DatasetRecord.id != exclude_dataset_id)
    if user_id is not None:
        q = q.filter(DatasetRecord.user_id == user_id)
    return db.query(q.exists()).scalar()


def update_dataset_name(db, dataset_id, user_id, name):
    """Rename a dataset (sheet). Returns the record or None.

    Scoped to ``user_id`` so users cannot rename sheets they don't own.
    Empty / whitespace-only names are rejected (returns None). The new
    name is trimmed and capped at 255 chars to match the column width.
    """
    if dataset_id is None or user_id is None:
        return None
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    rec = (db.query(DatasetRecord)
             .filter(DatasetRecord.id == dataset_id,
                     DatasetRecord.user_id == user_id)
             .first())
    if not rec:
        return None
    rec.dataset_name = cleaned[:255]
    db.commit()
    db.refresh(rec)
    return rec


def update_dataset_steps(db, dataset_id, step_recipes, active_step_index):
    """Persist updated step recipes / active pointer for a dataset."""
    rec = db.query(DatasetRecord).filter(DatasetRecord.id == dataset_id).first()
    if not rec:
        return None
    rec.step_recipes = step_recipes
    rec.active_step_index = active_step_index
    db.commit()
    return rec


def get_dataset_record(db, dataset_id, user_id=None):
    """Look up a single dataset record (optionally scoped to a user)."""
    q = db.query(DatasetRecord).filter(DatasetRecord.id == dataset_id)
    if user_id is not None:
        q = q.filter((DatasetRecord.user_id == user_id) | (DatasetRecord.user_id.is_(None)))
    return q.first()


def get_dataset_record_strict(db, dataset_id, user_id, project_id=None):
    """Look up a dataset that is strictly owned by the given user (and
    optionally bound to a specific project). Used by the new
    chat-artifact endpoints where leaking legacy `user_id IS NULL`
    rows to other authenticated users would be a real access-control
    bug."""
    if user_id is None:
        return None
    q = db.query(DatasetRecord).filter(
        DatasetRecord.id == dataset_id,
        DatasetRecord.user_id == user_id,
    )
    if project_id is not None:
        q = q.filter(DatasetRecord.project_id == project_id)
    return q.first()


def set_user_last_dataset(db, user_id, dataset_id):
    """Remember the dataset the user was last working on."""
    if user_id is None:
        return
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.last_dataset_id = dataset_id
        db.commit()


def set_user_assistant_mode(db, user_id, mode):
    """Persist the user's preferred AI assistant response mode.

    Accepts any of ``"simple"`` / ``"guided"`` / ``"expert"`` — ``"guided"``
    is the API/UI label that maps to the legacy ``"simple"`` storage value
    so old data keeps working without a migration. Any other value is
    silently coerced to ``"simple"``.
    """
    if user_id is None:
        return None
    cleaned = (str(mode or "")).strip().lower()
    if cleaned == "guided":
        cleaned = "simple"
    if cleaned not in ("simple", "expert"):
        cleaned = "simple"
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return None
    if user.assistant_mode != cleaned:
        user.assistant_mode = cleaned
        db.commit()
    return user


def find_similar_datasets(db, columns_info):
    """Find datasets with similar column structure"""
    all_records = db.query(DatasetRecord).all()
    similar = []
    
    current_cols = set(columns_info.keys()) if isinstance(columns_info, dict) else set(columns_info)
    
    for record in all_records:
        if record.columns_info:
            record_cols = set(record.columns_info.keys()) if isinstance(record.columns_info, dict) else set(record.columns_info)
            similarity = len(current_cols.intersection(record_cols)) / max(len(current_cols.union(record_cols)), 1)
            if similarity > 0.7:
                similar.append({
                    'record': {
                        'id': record.id,
                        'dataset_name': record.dataset_name,
                        'period_month': record.period_month,
                        'period_year': record.period_year,
                        'row_count': record.row_count,
                        'column_count': record.column_count,
                        'summary_stats': record.summary_stats,
                        'columns_info': record.columns_info,
                    },
                    'similarity': similarity
                })
    
    return sorted(similar, key=lambda x: x['similarity'], reverse=True)


def get_datasets_by_name(db, dataset_name):
    """Get all datasets with a specific name ordered by period"""
    return db.query(DatasetRecord).filter(
        DatasetRecord.dataset_name == dataset_name
    ).order_by(DatasetRecord.period_year, DatasetRecord.period_month).all()


def save_chat_message(db, dataset_id=None, user_message=None, ai_response=None,
                      session_id=None):
    """Save a chat message to history.

    `session_id` is the new session-anchored path; `dataset_id` is kept for
    legacy callers that haven't been migrated to sessions yet.
    """
    chat = ChatHistory(
        dataset_id=dataset_id,
        session_id=session_id,
        user_message=user_message or "",
        ai_response=ai_response or "",
    )
    db.add(chat)
    if session_id is not None:
        # bump session updated_at so the sidebar can sort by recency
        sess = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if sess is not None:
            sess.updated_at = datetime.utcnow()
    db.commit()
    return chat


def get_chat_history(db, dataset_id=None, limit=50):
    """Get chat history, optionally filtered by dataset"""
    query = db.query(ChatHistory)
    if dataset_id:
        query = query.filter(ChatHistory.dataset_id == dataset_id)
    return query.order_by(ChatHistory.timestamp.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Chat sessions (multi-conversation per project)
# ---------------------------------------------------------------------------

def create_chat_session(db, project_id, user_id, title="New chat"):
    """Create a fresh chat session inside a project the user owns."""
    proj = db.query(Project).filter(
        Project.id == project_id, Project.user_id == user_id
    ).first()
    if not proj:
        return None
    sess = ChatSession(
        project_id=project_id,
        user_id=user_id,
        title=(title or "New chat")[:255],
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def list_chat_sessions(db, project_id, user_id):
    """List a project's chat sessions, newest activity first."""
    return (
        db.query(ChatSession)
        .filter(ChatSession.project_id == project_id,
                ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .all()
    )


def get_chat_session(db, session_id, user_id):
    """Fetch a chat session if it belongs to the user, else None."""
    return (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )


def get_session_messages(db, session_id, limit=200):
    """Return messages in a session in chronological order."""
    return (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.timestamp.asc(), ChatHistory.id.asc())
        .limit(limit)
        .all()
    )


def rename_chat_session(db, session_id, user_id, title):
    sess = get_chat_session(db, session_id, user_id)
    if not sess:
        return None
    sess.title = (title or "Untitled")[:255]
    sess.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sess)
    return sess


def delete_chat_session(db, session_id, user_id):
    sess = get_chat_session(db, session_id, user_id)
    if not sess:
        return False
    # Cascade: remove every row that points back at this session.
    # Both ChatHistory and ChatArtifact have an FK to chat_sessions.id,
    # so without an explicit purge the delete would either orphan the
    # rows (ChatHistory has nullable session_id on legacy schemas) or
    # raise a foreign-key violation (ChatArtifact's session_id is NOT
    # NULL). Doing it here keeps the API endpoint clean and idempotent.
    db.query(ChatArtifact).filter(ChatArtifact.session_id == session_id).delete(
        synchronize_session=False
    )
    db.query(ChatHistory).filter(ChatHistory.session_id == session_id).delete(
        synchronize_session=False
    )
    db.delete(sess)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Chat artifacts (tool-call outputs persisted under a chat session)
# ---------------------------------------------------------------------------

def save_chat_artifact(db, session_id, user_id, project_id, kind, title,
                       params=None, result=None, dataset_id=None, pinned=True):
    """Persist a tool-call output under a chat session."""
    a = ChatArtifact(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        dataset_id=dataset_id,
        kind=kind,
        title=(title or kind)[:255],
        params=params or {},
        result=result or {},
        pinned=bool(pinned),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def list_chat_artifacts(db, session_id, user_id, kind=None, pinned_only=False):
    """List artifacts for a session the user owns, newest first."""
    q = (
        db.query(ChatArtifact)
        .filter(
            ChatArtifact.session_id == session_id,
            ChatArtifact.user_id == user_id,
        )
    )
    if kind:
        q = q.filter(ChatArtifact.kind == kind)
    if pinned_only:
        q = q.filter(ChatArtifact.pinned.is_(True))
    return q.order_by(ChatArtifact.created_at.desc(), ChatArtifact.id.desc()).all()


def get_chat_artifact(db, artifact_id, user_id):
    return (
        db.query(ChatArtifact)
        .filter(ChatArtifact.id == artifact_id, ChatArtifact.user_id == user_id)
        .first()
    )


def set_artifact_pin(db, artifact_id, user_id, pinned):
    a = get_chat_artifact(db, artifact_id, user_id)
    if not a:
        return None
    a.pinned = bool(pinned)
    db.commit()
    db.refresh(a)
    return a


def delete_chat_artifact(db, artifact_id, user_id):
    a = get_chat_artifact(db, artifact_id, user_id)
    if not a:
        return False
    db.delete(a)
    db.commit()
    return True


def hash_password(password):
    """Hash a password using bcrypt with salt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password, hashed):
    """Verify a password against a bcrypt hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def normalize_identifier(value):
    """Canonical form for an email or username: trimmed and lowercased.

    Used so iOS Safari quirks (auto-capitalised first letter, autocomplete
    trailing spaces) and ordinary case differences don't cause logins to
    miss accounts that obviously match.
    """
    if value is None:
        return ""
    return str(value).strip().lower()


def create_user(db, email, username, password, full_name=None, is_admin=False,
                phone=None, country=None, gender=None, specialty=None, specialty_other=None):
    """Create a new user"""
    from sqlalchemy import func
    canonical_email = normalize_identifier(email)
    canonical_username = normalize_identifier(username)
    if not canonical_email or not canonical_username:
        return None
    existing = db.query(User).filter(
        (func.lower(User.email) == canonical_email)
        | (func.lower(User.username) == canonical_username)
    ).first()
    if existing:
        return None

    now = datetime.utcnow()
    user = User(
        email=canonical_email,
        username=canonical_username,
        password_hash=hash_password(password),
        full_name=full_name,
        is_admin=is_admin,
        subscription_type="tier3",
        phone=phone,
        country=country,
        gender=gender,
        specialty=specialty,
        specialty_other=specialty_other,
        trial_start=now,
        trial_end=now + timedelta(days=60)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db, email_or_username, password):
    """Authenticate a user by email/username and password.

    Comparison is case-insensitive and trims surrounding whitespace so
    accounts created with mixed-case emails (or typed on iOS Safari with
    an auto-capitalised first letter / trailing space) still match.
    """
    from sqlalchemy import func
    needle = normalize_identifier(email_or_username)
    if not needle:
        return None
    user = db.query(User).filter(
        (func.lower(User.email) == needle) | (func.lower(User.username) == needle)
    ).first()

    if user and verify_password(password, user.password_hash):
        user.last_login = datetime.utcnow()
        db.commit()
        return user
    return None


def get_user_by_id(db, user_id):
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()


def issue_session_token(db, user, days=30):
    """Generate + persist a long-lived session token for the user."""
    token = secrets.token_urlsafe(48)
    user.session_token = token
    user.session_expires = datetime.utcnow() + timedelta(days=days)
    db.commit()
    return token


def get_user_by_session_token(db, token):
    """Look up a user by an active (unexpired) session token."""
    if not token:
        return None
    user = db.query(User).filter(User.session_token == token).first()
    if not user:
        return None
    if user.session_expires and user.session_expires < datetime.utcnow():
        return None
    return user


def clear_session_token(db, user):
    """Invalidate the user's persistent session token."""
    if user is None:
        return
    user.session_token = None
    user.session_expires = None
    db.commit()


def get_user_by_email(db, email):
    """Get user by email (case-insensitive, whitespace-trimmed)."""
    from sqlalchemy import func
    needle = normalize_identifier(email)
    if not needle:
        return None
    return db.query(User).filter(func.lower(User.email) == needle).first()


def update_user_subscription(db, user_id, subscription_type, end_date=None):
    """Update user subscription"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.subscription_type = subscription_type
        user.subscription_end = end_date
        db.commit()
        return user
    return None


def get_all_users(db):
    """Get all users for admin panel"""
    return db.query(User).order_by(User.created_at.desc()).all()


def get_all_datasets(db):
    """Get all datasets for admin panel"""
    return db.query(DatasetRecord).order_by(DatasetRecord.upload_date.desc()).all()


def get_user_datasets(db, user_id, project_id=None):
    """Get datasets for a specific user, optionally scoped to one project.

    When ``project_id`` is supplied, only datasets explicitly attached to that
    project are returned. When omitted, every dataset owned by the user is
    returned (used by admin / cross-project flows like the build queue).

    Pinned datasets always come first (most recently pinned at the very
    top), so a user's flagged "working file" stays surfaced even when the
    Recent list is capped at five entries.
    """
    q = db.query(DatasetRecord).filter(DatasetRecord.user_id == user_id)
    if project_id is not None:
        q = q.filter(DatasetRecord.project_id == project_id)
    return q.order_by(
        DatasetRecord.pinned_at.desc().nullslast(),
        DatasetRecord.upload_date.desc(),
    ).all()


def set_dataset_pinned(db, dataset_id, user_id, pinned):
    """Pin or unpin a dataset for the owning user.

    Returns the updated record on success or ``None`` if the dataset
    doesn't exist or isn't owned by ``user_id``. Pinning stamps
    ``pinned_at`` with the current UTC time so the most recently pinned
    item floats to the top of the Recent list; unpinning clears it.
    Re-pinning an already-pinned dataset refreshes the timestamp so
    users can re-prioritise without an unpin step.
    """
    if dataset_id is None or user_id is None:
        return None
    rec = (db.query(DatasetRecord)
             .filter(DatasetRecord.id == dataset_id,
                     DatasetRecord.user_id == user_id)
             .first())
    if not rec:
        return None
    rec.pinned_at = datetime.utcnow() if pinned else None
    db.commit()
    db.refresh(rec)
    return rec


# ─── Project helpers ─────────────────────────────────────────────────────
# A project is a user-owned folder of related datasets ("sheets"). The
# post-login landing page shows a grid of these and the dashboard always
# operates inside one. All queries are scoped by user_id defensively to
# avoid one user reaching another's data via a forged id.

def create_project(db, user_id, name, description=None):
    """Create a new project for ``user_id``. Name is trimmed and required."""
    name = (name or "").strip()
    if not name:
        return None
    proj = Project(user_id=user_id, name=name[:255],
                   description=(description or "").strip() or None)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def get_user(db, user_id):
    """Fetch a user by id, or None."""
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def list_user_projects(db, user_id, include_archived=False):
    """All projects a user owns, newest activity first, with rollup stats.

    Returns a list of dicts (not ORM objects) so downstream UI code is
    decoupled from SQLAlchemy. The single query also pulls per-project
    rollups used by the projects management page:

    * ``sheet_count`` / ``total_rows`` — dataset counters
    * ``total_size_bytes`` — cumulative parquet payload size
    * ``chat_count`` / ``last_session_id`` — chat session aggregates
    * ``last_active_at`` — most recent of (project.last_opened_at,
      project.updated_at, last chat session.updated_at, last dataset
      upload).
    * ``status`` — derived health hint:
        - ``error`` if any dataset has a 0-row payload (parse failure)
        - ``ready`` otherwise

    By default archived projects are hidden so they don't clutter the
    main grid. Pass ``include_archived=True`` to include them too — the
    UI uses a separate fetch when the user toggles the Archived view.
    """
    if user_id is None:
        return []
    from sqlalchemy import func, case
    parquet_size = func.coalesce(
        func.sum(func.coalesce(func.octet_length(DatasetRecord.source_parquet), 0)), 0
    ).label("total_size_bytes")
    has_zero_rows = func.coalesce(
        func.sum(case((DatasetRecord.row_count == 0, 1), else_=0)), 0
    ).label("zero_row_datasets")
    last_dataset_upload = func.max(DatasetRecord.upload_date).label("last_dataset_at")
    q = (db.query(Project,
                  func.count(DatasetRecord.id).label("sheet_count"),
                  func.coalesce(func.sum(DatasetRecord.row_count), 0).label("total_rows"),
                  parquet_size,
                  has_zero_rows,
                  last_dataset_upload)
            .outerjoin(DatasetRecord, DatasetRecord.project_id == Project.id)
            .filter(Project.user_id == user_id)
            .group_by(Project.id))
    if not include_archived:
        q = q.filter(Project.archived_at.is_(None))
    rows = (q.order_by(Project.last_opened_at.desc().nullslast(),
                       Project.created_at.desc())
              .all())

    # Chat aggregates in a second query — joining them into the dataset
    # rollup would create a fan-out (sheet × chat cartesian) and inflate
    # the size sums. Two clean aggregates is simpler and faster on the
    # data sizes we actually see here.
    pids = [r[0].id for r in rows]
    chat_stats: dict[int, tuple[int, int | None, datetime | None]] = {}
    if pids:
        # Per-project chat counts...
        for pid, cnt, last_at in (
            db.query(ChatSession.project_id,
                     func.count(ChatSession.id),
                     func.max(ChatSession.updated_at))
              .filter(ChatSession.project_id.in_(pids),
                      ChatSession.user_id == user_id)
              .group_by(ChatSession.project_id)
              .all()
        ):
            chat_stats[int(pid)] = (int(cnt or 0), None, last_at)
        # ...and the most-recently-updated session id per project, used
        # by the card body to deep-link straight back into work. We do
        # this with a dedicated query rather than DISTINCT ON to keep
        # the dialect generic.
        latest_ids = (
            db.query(ChatSession.project_id, ChatSession.id)
              .filter(ChatSession.project_id.in_(pids),
                      ChatSession.user_id == user_id)
              .order_by(ChatSession.project_id,
                        ChatSession.updated_at.desc(),
                        ChatSession.id.desc())
              .all()
        )
        seen: set[int] = set()
        for pid, sid in latest_ids:
            pid = int(pid)
            if pid in seen:
                continue
            seen.add(pid)
            cnt, _prev, last_at = chat_stats.get(pid, (0, None, None))
            chat_stats[pid] = (cnt, int(sid), last_at)

    out = []
    for proj, sheet_count, total_rows, total_size, zero_rows, last_dataset_at in rows:
        chat_cnt, last_sid, last_chat_at = chat_stats.get(int(proj.id), (0, None, None))
        # last_active_at is the most generous "is this project alive"
        # signal — we want the card to surface activity from any of:
        # explicit project touches, dataset uploads, or chat updates.
        candidates = [proj.last_opened_at, proj.updated_at,
                      last_chat_at, last_dataset_at]
        last_active_at = max((c for c in candidates if c is not None),
                             default=None)
        # Status is conservative: only flag an error when we know
        # something went wrong (an empty-row dataset). Otherwise the
        # project is "ready" — there's no async "processing" state in
        # the current upload pipeline so we never need to emit it, but
        # keeping the field in the API leaves room for a future job
        # queue without changing the client contract.
        status = "error" if int(zero_rows or 0) > 0 else "ready"
        out.append({
            "id": proj.id,
            "name": proj.name,
            "description": proj.description,
            "mode": getattr(proj, "mode", None),
            "created_at": proj.created_at,
            "updated_at": proj.updated_at,
            "last_opened_at": proj.last_opened_at,
            "sheet_count": int(sheet_count or 0),
            "total_rows": int(total_rows or 0),
            "total_size_bytes": int(total_size or 0),
            "chat_count": chat_cnt,
            "last_active_at": last_active_at,
            "last_session_id": last_sid,
            "status": status,
            "is_archived": proj.archived_at is not None,
            "archived_at": proj.archived_at,
        })
    return out


def get_project(db, project_id, user_id):
    """Fetch a project iff it belongs to ``user_id``; otherwise None."""
    if project_id is None or user_id is None:
        return None
    return (db.query(Project)
              .filter(Project.id == project_id, Project.user_id == user_id)
              .first())


def update_project(db, project_id, user_id, name=None, description=None,
                   mode=None):
    """Rename / re-describe / re-mode a project. Returns the project or None.

    ``mode`` accepts the API vocabulary ("guided" / "expert"). Pass an empty
    string to clear the per-project override (i.e. fall back to the user-level
    preference). Any other value is ignored.
    """
    proj = get_project(db, project_id, user_id)
    if proj is None:
        return None
    if name is not None:
        name = name.strip()
        if name:
            proj.name = name[:255]
    if description is not None:
        proj.description = (description or "").strip() or None
    if mode is not None and hasattr(proj, "mode"):
        cleaned = (str(mode or "")).strip().lower()
        if cleaned in ("guided", "expert"):
            proj.mode = cleaned
        elif cleaned == "":
            proj.mode = None
    proj.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(proj)
    return proj


def touch_project(db, project_id, user_id=None):
    """Bump ``last_opened_at`` so the card floats to the top of the grid."""
    q = db.query(Project).filter(Project.id == project_id)
    if user_id is not None:
        q = q.filter(Project.user_id == user_id)
    proj = q.first()
    if proj is None:
        return None
    proj.last_opened_at = datetime.utcnow()
    db.commit()
    return proj


def archive_project(db, project_id, user_id):
    """Soft-archive a project. Returns the project or None if not found.

    The project keeps all its data so Restore is a non-destructive
    pure flag flip — we just stamp ``archived_at`` so the default list
    query hides it from the active grid.
    """
    proj = get_project(db, project_id, user_id)
    if proj is None:
        return None
    if proj.archived_at is None:
        proj.archived_at = datetime.utcnow()
        proj.updated_at = proj.archived_at
        db.commit()
        db.refresh(proj)
    return proj


def restore_project(db, project_id, user_id):
    """Un-archive a project so it shows in the main grid again."""
    proj = get_project(db, project_id, user_id)
    if proj is None:
        return None
    if proj.archived_at is not None:
        proj.archived_at = None
        proj.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(proj)
    return proj


def bulk_project_action(db, user_id, project_ids, action):
    """Apply ``delete``/``archive``/``restore`` to a batch of projects.

    Returns the list of ids that were successfully acted on (silently
    skipping ids that don't belong to the user, so a forged id can't
    leak ownership info via differential responses).
    """
    if not project_ids or user_id is None:
        return []
    if action not in ("delete", "archive", "restore"):
        raise ValueError(f"Unsupported bulk action: {action!r}")
    # Pre-filter to ids the user actually owns.
    owned = [
        int(pid)
        for (pid,) in db.query(Project.id)
        .filter(Project.user_id == user_id, Project.id.in_(project_ids))
        .all()
    ]
    done: list[int] = []
    for pid in owned:
        if action == "delete":
            if delete_project(db, pid, user_id):
                done.append(pid)
        elif action == "archive":
            if archive_project(db, pid, user_id) is not None:
                done.append(pid)
        elif action == "restore":
            if restore_project(db, pid, user_id) is not None:
                done.append(pid)
    return done


def delete_project(db, project_id, user_id):
    """Delete a project + every dataset and relationship inside it.

    Cascades manually because ``DatasetRecord.project_id`` is intentionally
    nullable (so legacy datasets without a project keep working) — we can't
    rely on ON DELETE CASCADE for that. Returns True on success.
    """
    proj = get_project(db, project_id, user_id)
    if proj is None:
        return False
    ds_ids = [r.id for r in db.query(DatasetRecord.id)
                                .filter(DatasetRecord.project_id == project_id,
                                        DatasetRecord.user_id == user_id)
                                .all()]
    # Wipe everything that points at the soon-to-be-gone project rows.
    # None of these FK columns have ON DELETE CASCADE in the schema, so
    # the project delete itself would otherwise raise a foreign-key
    # violation as soon as the project owns any chat session, semantic
    # table, relationship, knowledge-base entry, model, question or
    # report. The previous version only cleared a subset, which left
    # the project row stuck in the DB and surfaced as the sidebar's
    # "delete errors and stays" behaviour the user reported.
    sess_ids = [sid for (sid,) in db.query(ChatSession.id)
                                   .filter(ChatSession.project_id == project_id)
                                   .all()]
    if sess_ids:
        (db.query(ChatArtifact)
           .filter(ChatArtifact.session_id.in_(sess_ids))
           .delete(synchronize_session=False))
        (db.query(ChatHistory)
           .filter(ChatHistory.session_id.in_(sess_ids))
           .delete(synchronize_session=False))
    # Any artifacts written before sessions were enforced may still
    # carry only the project_id — sweep those too just in case.
    (db.query(ChatArtifact)
       .filter(ChatArtifact.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ChatSession)
       .filter(ChatSession.project_id == project_id)
       .delete(synchronize_session=False))
    # Knowledge-base, semantic-model, relationships and clarification
    # questions all reference the project with NOT NULL FKs. The
    # semantic-model + relationship rows ALSO carry NOT NULL FKs into
    # `dataset_records.id`, so they MUST be deleted before any
    # DatasetRecord row goes away — otherwise the dataset delete itself
    # raises a foreign-key violation (which is the bug the user hit).
    (db.query(ProjectLearnedNote)
       .filter(ProjectLearnedNote.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectKnowledgeBase)
       .filter(ProjectKnowledgeBase.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectSemanticTable)
       .filter(ProjectSemanticTable.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectRelationship)
       .filter(ProjectRelationship.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectSemanticModel)
       .filter(ProjectSemanticModel.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectModelQuestion)
       .filter(ProjectModelQuestion.project_id == project_id)
       .delete(synchronize_session=False))
    # Reports' project_id AND dataset_id are both nullable; null them
    # out instead of dropping the row so the user's "recent reports"
    # list still shows them as historical entries (the dataset is
    # about to be deleted, so the report can no longer be regenerated,
    # but the snapshot dataset_label keeps the row legible).
    (db.query(Report)
       .filter(Report.project_id == project_id)
       .update({Report.project_id: None,
                Report.dataset_id: None},
               synchronize_session=False))
    if ds_ids:
        # Some Report rows may reference these datasets without
        # carrying the project_id (legacy data, or detached reports);
        # null those too before the FK constraint kicks in.
        (db.query(Report)
           .filter(Report.dataset_id.in_(ds_ids))
           .update({Report.dataset_id: None},
                   synchronize_session=False))
        (db.query(DatasetRelationship)
           .filter(DatasetRelationship.user_id == user_id,
                   (DatasetRelationship.left_dataset_id.in_(ds_ids))
                   | (DatasetRelationship.right_dataset_id.in_(ds_ids)))
           .delete(synchronize_session=False))
        (db.query(DatasetRecord)
           .filter(DatasetRecord.id.in_(ds_ids))
           .delete(synchronize_session=False))
    db.delete(proj)
    db.commit()
    return True


# ─── Project Knowledge Base helpers ──────────────────────────────────────
# Each project optionally has one knowledge-base reference (PDF, text file,
# or URL) plus a growing list of "learned notes" appended on every AI
# exchange. Both tables are scoped strictly by project_id; callers should
# verify project ownership via ``get_project`` before invoking these.

KB_MAX_CHARS = 200_000  # hard cap per project; older content is truncated.


def get_project_knowledge_base(db, project_id):
    """Return the single KB row for a project, or None if not set."""
    if project_id is None:
        return None
    return (db.query(ProjectKnowledgeBase)
              .filter(ProjectKnowledgeBase.project_id == project_id)
              .first())


def set_project_knowledge_base(db, project_id, source_kind, source_label,
                               content_text):
    """Upsert the KB row for a project. Truncates to ``KB_MAX_CHARS``."""
    if project_id is None or not source_kind:
        return None
    text_val = (content_text or "").strip()
    if len(text_val) > KB_MAX_CHARS:
        text_val = text_val[:KB_MAX_CHARS]
    row = get_project_knowledge_base(db, project_id)
    now = datetime.utcnow()
    if row is None:
        row = ProjectKnowledgeBase(
            project_id=project_id,
            source_kind=source_kind,
            source_label=(source_label or "")[:512],
            content_text=text_val,
            char_count=len(text_val),
            created_at=now, updated_at=now,
        )
        db.add(row)
    else:
        row.source_kind = source_kind
        row.source_label = (source_label or "")[:512]
        row.content_text = text_val
        row.char_count = len(text_val)
        row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def clear_project_knowledge_base(db, project_id):
    """Drop the KB row for a project (no-op if there isn't one)."""
    row = get_project_knowledge_base(db, project_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def append_learned_note(db, project_id, kind, content):
    """Best-effort append of an AI-exchange note. Returns the row or None.

    Failures here must not propagate — the calling chat/insight flow has
    already produced its result and the user shouldn't see an error just
    because the audit trail couldn't write.
    """
    if project_id is None or not kind or not content:
        return None
    text_val = str(content).strip()
    if not text_val:
        return None
    # Cap a single note's length to avoid one massive insight crowding
    # the context window when we read it back later.
    if len(text_val) > 4000:
        text_val = text_val[:4000] + "…"
    try:
        row = ProjectLearnedNote(
            project_id=project_id, kind=kind[:16],
            content=text_val, created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


def list_learned_notes(db, project_id, limit=20):
    """Most recent learned notes for a project (newest first)."""
    if project_id is None:
        return []
    return (db.query(ProjectLearnedNote)
              .filter(ProjectLearnedNote.project_id == project_id)
              .order_by(ProjectLearnedNote.created_at.desc())
              .limit(limit)
              .all())


def clear_learned_notes(db, project_id):
    """Wipe every learned note for a project. Returns the row count."""
    if project_id is None:
        return 0
    n = (db.query(ProjectLearnedNote)
           .filter(ProjectLearnedNote.project_id == project_id)
           .delete(synchronize_session=False))
    db.commit()
    return int(n or 0)


def get_project_ai_context(db, project_id, recent_notes=10):
    """Return a dict bundle the AI assistant can drop into its prompt.

    Shape:
        {
          'kb': {'kind': 'pdf', 'label': 'brief.pdf',
                 'text': '<truncated>', 'char_count': 12034},
          'notes': [{'kind': 'chat', 'content': '...',
                     'created_at': '2026-04-22T13:01:00'}],
        }
    Either side can be empty; the assistant just skips empty pieces.
    """
    out = {'kb': None, 'notes': []}
    kb = get_project_knowledge_base(db, project_id)
    if kb is not None:
        out['kb'] = {
            'kind': kb.source_kind, 'label': kb.source_label,
            'text': kb.content_text or '',
            'char_count': int(kb.char_count or 0),
        }
    notes = list_learned_notes(db, project_id, limit=recent_notes)
    out['notes'] = [{
        'kind': n.kind, 'content': n.content,
        'created_at': n.created_at.isoformat() if n.created_at else None,
    } for n in notes]
    return out


def ensure_default_project_for_user(db, user_id):
    """One-shot back-fill: if a user has datasets but no projects, drop them
    all into a single "My First Project" so existing accounts aren't left
    looking at an empty Projects page after the migration. Idempotent — runs
    cheaply on every login.
    """
    if user_id is None:
        return None
    has_project = (db.query(Project.id)
                     .filter(Project.user_id == user_id)
                     .first() is not None)
    if has_project:
        return None
    orphan_count = (db.query(DatasetRecord.id)
                      .filter(DatasetRecord.user_id == user_id,
                              DatasetRecord.project_id.is_(None))
                      .count())
    if orphan_count == 0:
        return None
    proj = Project(user_id=user_id, name="My First Project",
                   description="Datasets imported before projects existed.")
    db.add(proj)
    db.commit()
    db.refresh(proj)
    (db.query(DatasetRecord)
       .filter(DatasetRecord.user_id == user_id,
               DatasetRecord.project_id.is_(None))
       .update({DatasetRecord.project_id: proj.id},
               synchronize_session=False))
    db.commit()
    return proj


def increment_analysis_count(db, user_id):
    """Increment user's analysis count"""
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.analysis_count = (user.analysis_count or 0) + 1
        db.commit()


def get_admin_stats(db):
    """Get statistics for admin dashboard"""
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    premium_users = db.query(User).filter(User.subscription_type != "tier1").count()
    total_datasets = db.query(DatasetRecord).count()
    total_analyses = db.query(AnalysisHistory).count()
    total_chats = db.query(ChatHistory).count()
    
    return {
        'total_users': total_users,
        'active_users': active_users,
        'premium_users': premium_users,
        'free_users': total_users - premium_users,
        'total_datasets': total_datasets,
        'total_analyses': total_analyses,
        'total_chats': total_chats
    }


def list_relationships(db, user_id):
    """All relationships defined by a user, newest first."""
    if user_id is None:
        return []
    return (db.query(DatasetRelationship)
              .filter(DatasetRelationship.user_id == user_id)
              .order_by(DatasetRelationship.created_at.desc())
              .all())


def save_relationship(db, user_id, left_dataset_id, left_column,
                      right_dataset_id, right_column,
                      cardinality="1:N", join_type="left"):
    """Persist a confirmed relationship; refuses obvious self-joins on
    identical (dataset, column) pairs because they're never meaningful.

    Defensively re-checks that *both* datasets belong to ``user_id`` so a
    spoofed dataset id from a hand-crafted form submission cannot create
    a relationship pointing at someone else's data."""
    if (left_dataset_id == right_dataset_id and left_column == right_column):
        return None
    owned = (db.query(DatasetRecord.id)
               .filter(DatasetRecord.user_id == user_id,
                       DatasetRecord.id.in_([left_dataset_id, right_dataset_id]))
               .all())
    if len({row[0] for row in owned}) != 2:
        return None
    rel = DatasetRelationship(
        user_id=user_id,
        left_dataset_id=left_dataset_id, left_column=left_column,
        right_dataset_id=right_dataset_id, right_column=right_column,
        cardinality=cardinality, join_type=join_type,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def delete_relationship(db, user_id, relationship_id):
    """Remove a relationship the user owns. Returns True if deleted."""
    rel = (db.query(DatasetRelationship)
             .filter(DatasetRelationship.id == relationship_id,
                     DatasetRelationship.user_id == user_id)
             .first())
    if not rel:
        return False
    db.delete(rel)
    db.commit()
    return True


def delete_dataset_record(db, dataset_id, user_id):
    """Remove a dataset the user owns and any relationships referencing it.
    Returns True on success.

    Cascades every FK that points at ``dataset_records.id``:
      - DatasetRelationship (NOT NULL FK, both sides) → delete
      - ProjectSemanticTable (NOT NULL FK)            → delete
      - ProjectRelationship  (NOT NULL FK, both sides)→ delete
      - ChatArtifact.dataset_id (nullable)            → null out so the
        artifact (e.g. a chart) survives even after its underlying
        dataset is gone
      - Report.dataset_id (nullable)                  → null out so the
        recent-reports list keeps the historical entry visible
    Without these, the final ``db.delete(rec)`` would hit a
    ForeignKeyViolation on any dataset that had ever been used inside
    a semantic model, a join, a chat artifact, or a report.
    """
    rec = (db.query(DatasetRecord)
             .filter(DatasetRecord.id == dataset_id,
                     DatasetRecord.user_id == user_id)
             .first())
    if not rec:
        return False
    (db.query(DatasetRelationship)
       .filter(DatasetRelationship.user_id == user_id,
               (DatasetRelationship.left_dataset_id == dataset_id)
               | (DatasetRelationship.right_dataset_id == dataset_id))
       .delete(synchronize_session=False))
    (db.query(ProjectSemanticTable)
       .filter(ProjectSemanticTable.dataset_id == dataset_id)
       .delete(synchronize_session=False))
    (db.query(ProjectRelationship)
       .filter((ProjectRelationship.left_dataset_id == dataset_id)
               | (ProjectRelationship.right_dataset_id == dataset_id))
       .delete(synchronize_session=False))
    (db.query(ChatArtifact)
       .filter(ChatArtifact.dataset_id == dataset_id)
       .update({ChatArtifact.dataset_id: None},
               synchronize_session=False))
    (db.query(Report)
       .filter(Report.dataset_id == dataset_id)
       .update({Report.dataset_id: None},
               synchronize_session=False))
    db.delete(rec)
    db.commit()
    return True


def bulk_delete_dataset_records(db, dataset_ids, user_id):
    """Delete several datasets owned by ``user_id`` in a single transaction.

    Removes any ``DatasetRelationship`` rows that reference the deleted
    datasets (either side of the join) as well as the ``DatasetRecord``
    rows themselves. Datasets that don't belong to the user are silently
    skipped — the caller never gets to delete other people's data.

    Returns a summary dict::

        {
            "deleted_count": int,
            "deleted_ids":  [int, ...],
            "total_bytes":  int,   # combined source_parquet size
        }
    """
    from sqlalchemy import func

    if not dataset_ids:
        return {"deleted_count": 0, "deleted_ids": [], "total_bytes": 0}

    ids = list({int(i) for i in dataset_ids})
    rows = (db.query(DatasetRecord.id,
                     func.coalesce(
                         func.octet_length(DatasetRecord.source_parquet), 0))
              .filter(DatasetRecord.id.in_(ids),
                      DatasetRecord.user_id == user_id)
              .all())
    owned_ids = [r[0] for r in rows]
    total_bytes = int(sum((r[1] or 0) for r in rows))

    if not owned_ids:
        return {"deleted_count": 0, "deleted_ids": [], "total_bytes": 0}

    try:
        # Same FK fan-out as the single-row delete_dataset_record:
        # every table that points at dataset_records.id needs to be
        # cleared (or nulled, for the nullable FKs) before the
        # DatasetRecord rows themselves can be removed.
        (db.query(DatasetRelationship)
           .filter(DatasetRelationship.user_id == user_id,
                   DatasetRelationship.left_dataset_id.in_(owned_ids)
                   | DatasetRelationship.right_dataset_id.in_(owned_ids))
           .delete(synchronize_session=False))
        (db.query(ProjectSemanticTable)
           .filter(ProjectSemanticTable.dataset_id.in_(owned_ids))
           .delete(synchronize_session=False))
        (db.query(ProjectRelationship)
           .filter(ProjectRelationship.left_dataset_id.in_(owned_ids)
                   | ProjectRelationship.right_dataset_id.in_(owned_ids))
           .delete(synchronize_session=False))
        (db.query(ChatArtifact)
           .filter(ChatArtifact.dataset_id.in_(owned_ids))
           .update({ChatArtifact.dataset_id: None},
                   synchronize_session=False))
        (db.query(Report)
           .filter(Report.dataset_id.in_(owned_ids))
           .update({Report.dataset_id: None},
                   synchronize_session=False))
        (db.query(DatasetRecord)
           .filter(DatasetRecord.id.in_(owned_ids),
                   DatasetRecord.user_id == user_id)
           .delete(synchronize_session=False))
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "deleted_count": len(owned_ids),
        "deleted_ids": owned_ids,
        "total_bytes": total_bytes,
    }


# Default caps for how many report rows we keep around per user / per
# project. These bound the ``reports`` table so a user who repeatedly
# clicks Generate (or scripts the endpoint) can't grow the table
# without limit. Overridable via environment variables so an operator
# can dial them up or down without a code change.
def _report_cap(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name)
    if not raw:
        return default
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    # Anything <= 0 effectively disables pruning, which is a footgun.
    # Force at least 1 so we always keep the row we just inserted.
    return max(1, n)


REPORTS_PER_USER_CAP = _report_cap("AXIOM_REPORTS_PER_USER_CAP", 50)
REPORTS_PER_PROJECT_CAP = _report_cap("AXIOM_REPORTS_PER_PROJECT_CAP", 25)


def _prune_reports_beyond_cap(db, *, user_id, project_id):
    """Delete the oldest rows in ``reports`` once the user/project cap
    is exceeded. Operates on the current open transaction (no commit
    here) so the caller can wrap the insert + prune atomically.
    """
    if user_id is None:
        return

    def _prune(filter_q, cap):
        # Pick the IDs we want to keep (newest first, up to ``cap``)
        # and then delete everything else in the same scope. Doing the
        # keep-set lookup explicitly avoids relying on subquery + LIMIT
        # in DELETE which not every dialect supports.
        keep_ids = [
            rid for (rid,) in (
                filter_q.with_entities(Report.id)
                        .order_by(Report.created_at.desc(), Report.id.desc())
                        .limit(cap)
                        .all()
            )
        ]
        if not keep_ids:
            return
        (filter_q.filter(~Report.id.in_(keep_ids))
                 .delete(synchronize_session=False))

    user_q = db.query(Report).filter(Report.user_id == user_id)
    _prune(user_q, REPORTS_PER_USER_CAP)

    if project_id is not None:
        project_q = (db.query(Report)
                       .filter(Report.user_id == user_id,
                               Report.project_id == project_id))
        _prune(project_q, REPORTS_PER_PROJECT_CAP)


def save_report_record(db, user_id, dataset_id, project_id, title, notes,
                       dataset_label):
    """Persist a row in ``reports`` for a generated PDF.

    Returns the new ``Report`` instance. Failures are surfaced to the
    caller (the PDF endpoint already built the bytes by the time we get
    here, so swallowing errors silently would hide real DB issues).

    After insert, prunes older rows for this user (and project) beyond
    the configured caps so the ``reports`` table stays bounded. The
    insert and prune share one transaction: if the prune blows up the
    insert is rolled back too, so we never half-apply.
    """
    rec = Report(
        user_id=user_id,
        dataset_id=dataset_id,
        project_id=project_id,
        title=(title or None),
        notes=(notes or None),
        dataset_label=(dataset_label or None),
    )
    db.add(rec)
    try:
        # Flush so the new row has an ID and participates in the
        # keep-set selection below, but keep the transaction open so
        # the prune can be rolled back together with the insert on
        # failure.
        db.flush()
        _prune_reports_beyond_cap(db, user_id=user_id, project_id=project_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(rec)
    return rec


def list_recent_reports(db, user_id, project_id=None, limit=10):
    """Return the user's recent reports, optionally scoped to a project.

    Ordered newest-first. ``limit`` is clamped to a sensible range so a
    badly-behaved client can't ask for the whole table.
    """
    if user_id is None:
        return []
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 10
    n = max(1, min(50, n))
    q = db.query(Report).filter(Report.user_id == user_id)
    if project_id is not None:
        q = q.filter(Report.project_id == project_id)
    return (q.order_by(Report.created_at.desc())
              .limit(n)
              .all())


def get_report_strict(db, report_id, user_id):
    """Look up a report owned by ``user_id`` (or return None)."""
    if user_id is None or report_id is None:
        return None
    return (db.query(Report)
              .filter(Report.id == report_id, Report.user_id == user_id)
              .first())


def save_support_message(db, email, name, message):
    """Create a SupportMessage record"""
    msg = SupportMessage(
        email=email,
        name=name,
        message=message
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def list_support_messages(
    db,
    only_unhandled: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """Return ``(rows, total)`` for the admin support queue, newest first.

    ``only_unhandled`` filters to rows where ``is_read`` is false so admins
    can focus on the inbox; pass ``False`` to see history. ``total`` is
    the unpaginated count (respecting ``only_unhandled``) so the caller
    can render "showing N of M" + load-more without a second round-trip.
    """
    q = db.query(SupportMessage)
    if only_unhandled:
        q = q.filter(SupportMessage.is_read.is_(False))
    total = q.count()
    rows = (
        q.order_by(SupportMessage.created_at.desc())
        .offset(int(offset))
        .limit(int(limit))
        .all()
    )
    return rows, int(total)


def set_support_message_handled(db, message_id: int, handled: bool):
    """Mark a support message handled (or un-handled). Returns the updated row or None."""
    msg = db.query(SupportMessage).filter(SupportMessage.id == int(message_id)).first()
    if msg is None:
        return None
    msg.is_read = bool(handled)
    db.commit()
    db.refresh(msg)
    return msg


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_password_reset_token(db, user, ttl_hours: int = 1, cooldown_seconds: int = 60):
    """Create a one-time password-reset token for `user`.

    Returns the raw token string (only this is shown to the user — only the
    hash is persisted).

    Rate-limiting / hygiene:
    - If a token was issued for this user within the last `cooldown_seconds`
      and is still unused & unexpired, this is treated as a duplicate request
      and ``None`` is returned (the caller should silently no-op while still
      showing the neutral confirmation message).
    - Otherwise, any previously outstanding (unused, unexpired) tokens for
      this user are invalidated by marking them used, so only the freshly
      issued link will work.
    """
    now = datetime.utcnow()
    if cooldown_seconds and cooldown_seconds > 0:
        cooldown_cutoff = now - timedelta(seconds=cooldown_seconds)
        recent = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
            PasswordResetToken.created_at > cooldown_cutoff,
        ).first()
        if recent is not None:
            return None

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now,
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)

    raw_token = secrets.token_urlsafe(48)
    record = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_reset_token(raw_token),
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(record)
    db.commit()
    return raw_token


def get_valid_password_reset_token(db, raw_token: str):
    """Return the (token, user) pair if the token is valid; else (None, None)."""
    if not raw_token:
        return None, None
    token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == _hash_reset_token(raw_token)
    ).first()
    if not token:
        return None, None
    if token.used_at is not None:
        return None, None
    if token.expires_at < datetime.utcnow():
        return None, None
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        return None, None
    return token, user


def consume_password_reset_token(db, token: "PasswordResetToken", new_password: str):
    """Atomically mark the token used and update the user's password.

    Uses a single conditional UPDATE on the token row (`used_at IS NULL AND
    expires_at > now`) so that two concurrent reset attempts can't both
    succeed: the second update will affect zero rows and we abort.
    """
    now = datetime.utcnow()
    rowcount = db.query(PasswordResetToken).filter(
        PasswordResetToken.id == token.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now,
    ).update({PasswordResetToken.used_at: now}, synchronize_session=False)

    if not rowcount:
        db.rollback()
        return None

    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        db.rollback()
        return None
    user.password_hash = hash_password(new_password)
    db.commit()
    return user


def purge_expired_password_reset_tokens(db):
    """Delete tokens that have expired or already been used."""
    now = datetime.utcnow()
    db.query(PasswordResetToken).filter(
        (PasswordResetToken.expires_at < now) | (PasswordResetToken.used_at.isnot(None))
    ).delete(synchronize_session=False)
    db.commit()


def check_trial_active(user):
    """Check if a user's trial is still active"""
    if user.trial_end is None:
        return True
    return user.trial_end > datetime.utcnow()
