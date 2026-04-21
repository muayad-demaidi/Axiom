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


class DatasetRecord(Base):
    """Model to store uploaded dataset records for historical tracking"""
    __tablename__ = "dataset_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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


class ChatHistory(Base):
    """Model to store chat conversations"""
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, nullable=True)
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
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS source_parquet BYTEA",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS parse_meta JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS step_recipes JSON",
        "ALTER TABLE dataset_records ADD COLUMN IF NOT EXISTS active_step_index INTEGER",
    ]
    # Newer tables that may not exist on older deployments need an
    # explicit create step before the in-place ALTERs above run, since
    # `create_all` only handles brand-new schemas. ``checkfirst`` makes
    # this idempotent on already-migrated DBs.
    try:
        DatasetRelationship.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass
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
                        step_recipes=None, active_step_index=None):
    """Save a dataset record to the database"""
    record = DatasetRecord(
        user_id=user_id,
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
    return record


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


def save_chat_message(db, dataset_id, user_message, ai_response):
    """Save a chat message to history"""
    chat = ChatHistory(
        dataset_id=dataset_id,
        user_message=user_message,
        ai_response=ai_response
    )
    db.add(chat)
    db.commit()
    return chat


def get_chat_history(db, dataset_id=None, limit=50):
    """Get chat history, optionally filtered by dataset"""
    query = db.query(ChatHistory)
    if dataset_id:
        query = query.filter(ChatHistory.dataset_id == dataset_id)
    return query.order_by(ChatHistory.timestamp.desc()).limit(limit).all()


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


def get_user_datasets(db, user_id):
    """Get datasets for a specific user"""
    return db.query(DatasetRecord).filter(DatasetRecord.user_id == user_id).order_by(DatasetRecord.upload_date.desc()).all()


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


def check_trial_active(user):
    """Check if a user's trial is still active"""
    if user.trial_end is None:
        return True
    return user.trial_end > datetime.utcnow()
