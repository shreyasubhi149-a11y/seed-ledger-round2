"""Database connection and non-destructive initialization."""

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + str(DATA / "seed_network.db"),
)

# Support PostgreSQL URLs if configured later.
if URL.startswith("postgres://"):
    URL = URL.replace(
        "postgres://",
        "postgresql+psycopg://",
        1,
    )
elif URL.startswith("postgresql://"):
    URL = URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

connect_args = {}

if URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": 30,
    }

engine = create_engine(
    URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


if URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


def initialize():
    """Create missing tables without deleting existing records."""
    from database import models  # Register model definitions.

    table_names = inspect(engine).get_table_names()

    # Add fields used by this version to an older seed_lots table.
    if "seed_lots" in table_names:
        existing_fields = {
            column["name"]
            for column in inspect(engine).get_columns("seed_lots")
        }

        additions = {
            "available_seeds": "INTEGER NOT NULL DEFAULT 0",
            "storage_location": "VARCHAR",
            "is_available": "BOOLEAN NOT NULL DEFAULT TRUE",
            "pollination": "VARCHAR NOT NULL DEFAULT 'unknown'",
        }

        with engine.begin() as connection:
            for name, definition in additions.items():
                if name not in existing_fields:
                    connection.execute(
                        text(
                            "ALTER TABLE seed_lots "
                            f"ADD COLUMN {name} {definition}"
                        )
                    )

    Base.metadata.create_all(engine)


def get_db():
    """Provide a database session to a FastAPI route."""
    with SessionLocal() as db:
        yield db