import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in .env")

# Special handling for SQLite
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, future=True, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        future=True,
        pool_pre_ping=True,   # test connection health before each use; discards stale ones
        pool_recycle=1800,    # recycle connections after 30 min (before PG closes idle ones)
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
