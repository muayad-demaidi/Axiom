import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set. Please configure a PostgreSQL database.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DatasetRecord(Base):
    """Model to store uploaded dataset records for historical tracking"""
    __tablename__ = "dataset_records"
    
    id = Column(Integer, primary_key=True, index=True)
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
