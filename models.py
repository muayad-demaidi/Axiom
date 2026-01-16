import os
import hashlib
import secrets
import bcrypt
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, JSON, Boolean, ForeignKey
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
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass


def save_dataset_record(db, filename, dataset_name, period_month, period_year, 
                        row_count, column_count, columns_info, data_hash, summary_stats=None):
    """Save a dataset record to the database"""
    record = DatasetRecord(
        filename=filename,
        dataset_name=dataset_name,
        period_month=period_month,
        period_year=period_year,
        row_count=row_count,
        column_count=column_count,
        columns_info=columns_info,
        data_hash=data_hash,
        summary_stats=summary_stats
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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
                    'record': record,
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


def create_user(db, email, username, password, full_name=None, is_admin=False):
    """Create a new user"""
    existing = db.query(User).filter((User.email == email) | (User.username == username)).first()
    if existing:
        return None
    
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        is_admin=is_admin,
        subscription_type="free"
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
    premium_users = db.query(User).filter(User.subscription_type == "premium").count()
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
