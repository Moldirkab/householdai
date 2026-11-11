from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def migrate() -> None:
    """Add columns introduced after the first version to an existing database."""
    from sqlalchemy import inspect, text
    cols = {c["name"] for c in inspect(engine).get_columns("households")}
    if "data_source" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE households ADD COLUMN data_source VARCHAR(10) DEFAULT 'user'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
