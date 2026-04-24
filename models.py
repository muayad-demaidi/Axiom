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
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS source_parquet BYTEA",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS parse_meta JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS step_recipes JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS active_step_index INTEGER",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id)",
        "CREATE INDEX IF NOT EXISTS ix_dataset_records_project_id ON dataset_records(project_id)",
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
               ChatSession.__table__):
        try:
            _t.create(bind=engine, checkfirst=True)
        except Exception:
            pass
    # ChatHistory needs a `session_id` column on older deployments so
    # session-aware writes don't 500 against legacy schemas.
    _migrations.extend([
        "ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES chat_sessions(id)",
        "CREATE INDEX IF NOT EXISTS ix_chat_history_session_id ON chat_history(session_id)",
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

    ``mode`` must be one of ``"simple"`` / ``"expert"``; any other value
    is silently coerced to ``"simple"`` to match the picker default and
    avoid storing junk that the system prompt builder would have to
    re-validate downstream.
    """
    if user_id is None:
        return None
    cleaned = (str(mode or "")).strip().lower()
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
    # Cascade: remove the messages too.
    db.query(ChatHistory).filter(ChatHistory.session_id == session_id).delete(
        synchronize_session=False
    )
    db.delete(sess)
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


def create_user(db, email, username, password, full_name=None, is_admin=False,
                phone=None, country=None, gender=None, specialty=None, specialty_other=None):
    """Create a new user"""
    existing = db.query(User).filter((User.email == email) | (User.username == username)).first()
    if existing:
        return None
    
    now = datetime.utcnow()
    user = User(
        email=email,
        username=username,
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
    """Authenticate a user by email/username and password"""
    user = db.query(User).filter(
        (User.email == email_or_username) | (User.username == email_or_username)
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
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


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
    """
    q = db.query(DatasetRecord).filter(DatasetRecord.user_id == user_id)
    if project_id is not None:
        q = q.filter(DatasetRecord.project_id == project_id)
    return q.order_by(DatasetRecord.upload_date.desc()).all()


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


def list_user_projects(db, user_id):
    """All projects a user owns, newest activity first, with a sheet count.

    Returns a list of dicts (not ORM objects) so downstream UI code is
    decoupled from SQLAlchemy and the dataset count comes back in a single
    query rather than N+1.
    """
    if user_id is None:
        return []
    from sqlalchemy import func
    rows = (db.query(Project,
                     func.count(DatasetRecord.id).label("sheet_count"),
                     func.coalesce(func.sum(DatasetRecord.row_count), 0).label("total_rows"))
              .outerjoin(DatasetRecord, DatasetRecord.project_id == Project.id)
              .filter(Project.user_id == user_id)
              .group_by(Project.id)
              .order_by(Project.last_opened_at.desc().nullslast(),
                        Project.created_at.desc())
              .all())
    out = []
    for proj, sheet_count, total_rows in rows:
        out.append({
            "id": proj.id,
            "name": proj.name,
            "description": proj.description,
            "created_at": proj.created_at,
            "updated_at": proj.updated_at,
            "last_opened_at": proj.last_opened_at,
            "sheet_count": int(sheet_count or 0),
            "total_rows": int(total_rows or 0),
        })
    return out


def get_project(db, project_id, user_id):
    """Fetch a project iff it belongs to ``user_id``; otherwise None."""
    if project_id is None or user_id is None:
        return None
    return (db.query(Project)
              .filter(Project.id == project_id, Project.user_id == user_id)
              .first())


def update_project(db, project_id, user_id, name=None, description=None):
    """Rename / re-describe a project. Returns the project or None."""
    proj = get_project(db, project_id, user_id)
    if proj is None:
        return None
    if name is not None:
        name = name.strip()
        if name:
            proj.name = name[:255]
    if description is not None:
        proj.description = (description or "").strip() or None
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
    if ds_ids:
        (db.query(DatasetRelationship)
           .filter(DatasetRelationship.user_id == user_id,
                   (DatasetRelationship.left_dataset_id.in_(ds_ids))
                   | (DatasetRelationship.right_dataset_id.in_(ds_ids)))
           .delete(synchronize_session=False))
        (db.query(DatasetRecord)
           .filter(DatasetRecord.id.in_(ds_ids))
           .delete(synchronize_session=False))
    # Knowledge-base and learned-notes for this project must be cleared
    # explicitly — there's no ON DELETE CASCADE on those FK columns.
    (db.query(ProjectLearnedNote)
       .filter(ProjectLearnedNote.project_id == project_id)
       .delete(synchronize_session=False))
    (db.query(ProjectKnowledgeBase)
       .filter(ProjectKnowledgeBase.project_id == project_id)
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
    Returns True on success."""
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
    db.delete(rec)
    db.commit()
    return True


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
