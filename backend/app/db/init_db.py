"""
Database initialization script
Creates all tables and indexes
"""

from . import Base, engine
from .models import *


def init_db():
    """Initialize database with all tables"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")


if __name__ == "__main__":
    init_db()
