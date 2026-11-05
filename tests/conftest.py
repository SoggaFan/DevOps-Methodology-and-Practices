"""Shared test fixtures with isolated schema/data for every API test.

Local tests default to in-memory SQLite, so they do not require Docker or a local
PostgreSQL server. CI sets TEST_DATABASE_URL to a dedicated PostgreSQL database,
which exercises the same API tests against PostgreSQL.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import Base, app, get_db


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """Create a test-only engine and reject accidental use of a non-test DB."""
    database_url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    url = make_url(database_url)

    if url.get_backend_name() == "postgresql":
        database_name = (url.database or "").lower()
        if not (database_name.endswith("_test") or database_name.endswith("_tests")):
            raise RuntimeError(
                "Refusing to run destructive test setup against a non-test PostgreSQL DB. "
                "TEST_DATABASE_URL must point to a database ending in '_test' or '_tests'."
            )
        engine = create_engine(database_url, pool_pre_ping=True)
    elif url.get_backend_name() in {"sqlite", "sqlite+pysqlite"}:
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool if url.database in (None, "", ":memory:") else None,
        )
    else:
        raise RuntimeError(f"Unsupported test database backend: {url.get_backend_name()}")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def client(test_engine: Engine) -> Generator[TestClient, None, None]:
    """Give each test a clean schema and override the app's production DB dependency."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(test_engine, autoflush=False, autocommit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
