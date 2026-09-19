import os
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.main import BoatIn, CatchIn, TripIn
from app.security import hash_password, verify_password


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


def test_period_report_rejects_reversed_range():
    from app.main import catch_report_by_period

    with pytest.raises(Exception) as exc_info:
        catch_report_by_period(date_from=date(2026, 9, 30), date_to=date(2026, 9, 1), db=None)

    assert "не может быть раньше" in str(exc_info.value)


# Optional DB-backed smoke tests. To enable, set TEST_DATABASE_URL.
if os.getenv("TEST_DATABASE_URL"):
    from fastapi.testclient import TestClient
    from app.main import ADMIN_PASSWORD, ADMIN_USERNAME, app

    ADMIN = (ADMIN_USERNAME, ADMIN_PASSWORD)

    @pytest.fixture(scope="module")
    def client():
        with TestClient(app) as test_client:
            yield test_client

    def test_health_with_database(client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_web_interface_is_public(client):
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/styles.css").status_code == 200

    def test_authentication_flow_with_database(client):
        login = client.post("/auth/login", auth=ADMIN)
        assert login.status_code == 200
        assert login.json()["username"] == ADMIN_USERNAME

        unauthorized = client.get("/api/boats")
        assert unauthorized.status_code == 401
        assert unauthorized.headers["www-authenticate"] == "Basic"

        assert client.get("/api/boats", auth=(ADMIN_USERNAME, "wrong-password")).status_code == 401
        assert client.get("/api/boats", auth=ADMIN).status_code == 200

        me = client.get("/auth/me", auth=ADMIN)
        assert me.status_code == 200
        assert me.json()["username"] == ADMIN_USERNAME

    @pytest.mark.parametrize(
        "path",
        [
            "/api/boats",
            "/api/crews",
            "/api/fish-types",
            "/api/trips",
            "/api/catches",
            "/api/reports/catch-by-trip",
            "/api/reports/catch-by-period",
        ],
    )
    def test_api_endpoints_require_authentication(client, path):
        assert client.get(path).status_code == 401
        assert client.get(path, auth=ADMIN).status_code == 200

    def test_business_flow_and_period_report_with_auth(client):
        boat = client.post("/api/boats", auth=ADMIN, json={"name": "Океан", "registration_no": "RF-100", "capacity_kg": 1000})
        crew = client.post("/api/crews", auth=ADMIN, json={"name": "Восток", "captain": "Сидоров С.С."})
        fish = client.post("/api/fish-types", auth=ADMIN, json={"name": "Минтай", "latin_name": "Gadus chalcogrammus"})
        assert (boat.status_code, crew.status_code, fish.status_code) == (201, 201, 201)

        trip = client.post(
            "/api/trips",
            auth=ADMIN,
            json={"boat_id": boat.json()["id"], "crew_id": crew.json()["id"], "departure_date": "2026-09-01", "return_date": "2026-09-05"},
        )
        assert trip.status_code == 201

        ok = client.post("/api/catches", auth=ADMIN, json={"trip_id": trip.json()["id"], "fish_type_id": fish.json()["id"], "cans": 50, "weight_kg": 700})
        too_much = client.post("/api/catches", auth=ADMIN, json={"trip_id": trip.json()["id"], "fish_type_id": fish.json()["id"], "cans": 50, "weight_kg": 400})
        assert ok.status_code == 201
        assert too_much.status_code == 422

        report = client.get(
            "/api/reports/catch-by-period",
            auth=ADMIN,
            params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
        )
        assert report.status_code == 200
        assert any(row["trip_id"] == trip.json()["id"] and row["total_weight_kg"] == 700 for row in report.json())

        reversed_range = client.get(
            "/api/reports/catch-by-period",
            auth=ADMIN,
            params={"date_from": "2026-09-30", "date_to": "2026-09-01"},
        )
        assert reversed_range.status_code == 422
