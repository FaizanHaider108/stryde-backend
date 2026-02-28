import sys
import pathlib
from math import isclose

# ensure tests can import the `app` package when run from pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.auth import create_user
from app.lib.db import Base, get_db
from app.lib import security
from app.main import app
from app.schemas.auth import RunnerType, UserCreate

# Ensure JWT config is present for tests
security.SECRET_KEY = security.SECRET_KEY or "test-secret"
security.ALGORITHM = security.ALGORITHM or "HS256"


@pytest.fixture(scope="session")
def postgres_testing_db():
    import os

    db_url = os.getenv("DATABASE_URL")
    container = None

    if not db_url:
        try:
            from testcontainers.postgres import PostgresContainer
        except Exception:  # pragma: no cover - user environment may not have testcontainers
            pytest.skip("testcontainers not available and DATABASE_URL not set; cannot run DB tests")

        container = PostgresContainer("postgres:15-alpine")
        container.start()
        db_url = container.get_connection_url()

    engine = create_engine(db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield TestingSessionLocal
    finally:
        engine.dispose()
        if container:
            container.stop()


@pytest.fixture(scope="session", autouse=True)
def override_get_db_dependency(postgres_testing_db):
    TestingSessionLocal = postgres_testing_db

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session(postgres_testing_db):
    TestingSessionLocal = postgres_testing_db
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _create_user(db, email: str = "runner@example.com"):
    user = create_user(
        db,
        UserCreate(
            full_name="Runner One",
            email=email,
            password="secret123",
            runner_type=RunnerType.grinder,
        ),
    )
    return user


def _auth_header(email: str):
    token = security.create_access_token({"email": email})
    return {"Authorization": f"Bearer {token}"}


def test_profile_requires_auth(client):
    response = client.get("/api/v1/profile/me")
    assert response.status_code == 401


def test_update_profile_with_imperial_units(client, db_session):
    user = _create_user(db_session)
    db_session.commit()
    headers = _auth_header(user.email)

    payload = {
        "full_name": "Runner Updated",
        "gender": "female",
        "date_of_birth": "1990-01-01",
        "height": {"unit": "ft_in", "feet": 5, "inches": 7},
        "weight": {"value": 150, "unit": "lb"},
        "profile_image_s3_key": "profiles/runner.jpg",
    }

    response = client.patch("/api/v1/profile/me", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["full_name"] == "Runner Updated"
    assert data["gender"] == "female"
    assert data["profile_image_s3_key"] == "profiles/runner.jpg"
    assert data["height_ft"] == 5
    assert isclose(data["height_in"], 7.0, rel_tol=0, abs_tol=0.1)
    assert isclose(data["weight_lb"], 150.0, rel_tol=0, abs_tol=0.1)
    assert isclose(data["height_cm"], 170.18, rel_tol=0, abs_tol=0.1)
    assert isclose(data["weight_kg"], 68.04, rel_tol=0, abs_tol=0.1)


def test_get_profile_returns_metric_storage(client, db_session):
    user = _create_user(db_session, email="runner2@example.com")
    db_session.commit()
    headers = _auth_header(user.email)

    payload = {
        "height": {"value": 1.8, "unit": "m"},
        "weight": {"value": 70, "unit": "kg"},
    }
    update_resp = client.patch("/api/v1/profile/me", json=payload, headers=headers)
    assert update_resp.status_code == 200

    get_resp = client.get("/api/v1/profile/me", headers=headers)
    assert get_resp.status_code == 200
    data = get_resp.json()

    assert isclose(data["height_m"], 1.8, rel_tol=0, abs_tol=0.001)
    assert isclose(data["height_ft"], 5.0, rel_tol=0, abs_tol=0.1)
    assert data["weight_kg"] == 70
    assert isclose(data["weight_lb"], 154.32, rel_tol=0, abs_tol=0.5)
