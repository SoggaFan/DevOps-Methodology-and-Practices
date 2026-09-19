import os
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.security import hash_password, verify_password
from app.schemas import BoatIn, CatchIn, TripIn


def test_boat_capacity_must_be_positive():
    with pytest.raises(ValidationError):
        BoatIn(name="X", registration_no="X-1", capacity_kg=-1)


def test_catch_weight_must_be_positive():
    with pytest.raises(ValidationError):
        CatchIn(trip_id=1, fish_type_id=1, cans=2, weight_kg=Decimal("0"))


def test_trip_returns_after_departure():
    with pytest.raises(ValidationError):
        TripIn(boat_id=1, crew_id=1, departure_date="2026-09-10", return_date="2026-09-09")


def test_password_hash_roundtrip():
    password_hash = hash_password("correct horse battery staple")
    assert password_hash.startswith("scrypt$")
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


# Optional DB-backed smoke tests. Enable with TEST_DATABASE_URL.
if os.getenv("TEST_DATABASE_URL"):
    from fastapi.testclient import TestClient
    from app.main import app

    os.environ.setdefault("ADMIN_USERNAME", "admin")
    os.environ.setdefault("ADMIN_PASSWORD", "change_me_admin")
    client = TestClient(app)

    def test_health_with_database():
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_authentication_flow_with_database():
        login = client.post(
            "/auth/login",
            auth=(os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"]),
        )
        assert login.status_code == 200
        assert login.json()["username"] == os.environ["ADMIN_USERNAME"]

        unauthorized = client.get("/api/boats")
        assert unauthorized.status_code == 401

        bad_password = client.get(
            "/api/boats",
            auth=(os.environ["ADMIN_USERNAME"], "wrong-password"),
        )
        assert bad_password.status_code == 401

        authorized = client.get(
            "/api/boats",
            auth=(os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"]),
        )
        assert authorized.status_code == 200

        me = client.get(
            "/auth/me",
            auth=(os.environ["ADMIN_USERNAME"], os.environ["ADMIN_PASSWORD"]),
        )
        assert me.status_code == 200
        assert me.json()["username"] == os.environ["ADMIN_USERNAME"]
