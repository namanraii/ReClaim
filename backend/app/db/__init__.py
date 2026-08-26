"""
Database configuration and session management
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Use SQLite for testing if PostgreSQL is not available
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./reclaim.db"
)

# SQLite specific configuration
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
