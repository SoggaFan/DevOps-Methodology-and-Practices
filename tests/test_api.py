from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app, get_db


pytestmark = pytest.mark.integration


def create_boat(
    client: TestClient,
    *,
    name: str = "Маяк",
    registration_no: str = "RF-001",
    capacity_kg: float = 100.0,
) -> dict[str, Any]:
    response = client.post(
        "/api/boats",
        json={"name": name, "registration_no": registration_no, "capacity_kg": capacity_kg},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_crew(
    client: TestClient, *, name: str = "Северная команда", captain: str = "Иванов И.И."
) -> dict[str, Any]:
    response = client.post("/api/crews", json={"name": name, "captain": captain})
    assert response.status_code == 201, response.text
    return response.json()


def create_fish_type(
    client: TestClient, *, name: str = "Треска", latin_name: str = "Gadus morhua"
) -> dict[str, Any]:
    response = client.post("/api/fish-types", json={"name": name, "latin_name": latin_name})
    assert response.status_code == 201, response.text
    return response.json()


def create_trip(
    client: TestClient,
    *,
    boat_id: int,
    crew_id: int,
    departure_date: str = "2026-09-10",
    return_date: str | None = "2026-09-11",
) -> dict[str, Any]:
    response = client.post(
        "/api/trips",
        json={
            "boat_id": boat_id,
            "crew_id": crew_id,
            "departure_date": departure_date,
            "return_date": return_date,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_catch(
    client: TestClient,
    *,
    trip_id: int,
    fish_type_id: int,
    cans: int = 2,
    weight_kg: float = 10.0,
) -> dict[str, Any]:
    response = client.post(
        "/api/catches",
        json={
            "trip_id": trip_id,
            "fish_type_id": fish_type_id,
            "cans": cans,
            "weight_kg": weight_kg,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_root_serves_web_interface(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Рыболовная фирма" in response.text


def test_static_assets_are_served(client: TestClient) -> None:
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "site-header" in response.text


def test_health_checks_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_instance_id_header_is_present(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-instance-id")


def test_health_reports_database_error_as_503(client: TestClient) -> None:
    class UnavailableDatabase:
        def execute(self, *_args: Any, **_kwargs: Any) -> None:
            raise SQLAlchemyError("simulated database outage")

    def override_failed_db():
        yield UnavailableDatabase()

    app.dependency_overrides[get_db] = override_failed_db
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"


def test_create_and_list_boats(client: TestClient) -> None:
    boat = create_boat(client)
    response = client.get("/api/boats")
    assert response.status_code == 200
    assert response.json() == [boat]


def test_duplicate_boat_registration_returns_409(client: TestClient) -> None:
    create_boat(client)
    response = client.post(
        "/api/boats",
        json={"name": "Волна", "registration_no": "RF-001", "capacity_kg": 75},
    )
    assert response.status_code == 409


def test_invalid_boat_payload_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/boats",
        json={"name": "X", "registration_no": "RF-001", "capacity_kg": 0},
    )
    assert response.status_code == 422


def test_create_and_list_crews(client: TestClient) -> None:
    crew = create_crew(client)
    response = client.get("/api/crews")
    assert response.status_code == 200
    assert response.json() == [crew]


def test_create_and_list_fish_types(client: TestClient) -> None:
    fish_type = create_fish_type(client)
    response = client.get("/api/fish-types")
    assert response.status_code == 200
    assert response.json() == [fish_type]


def test_duplicate_fish_type_returns_409(client: TestClient) -> None:
    create_fish_type(client)
    response = client.post(
        "/api/fish-types",
        json={"name": "Треска", "latin_name": "Gadus morhua"},
    )
    assert response.status_code == 409


def test_create_and_list_trips(client: TestClient) -> None:
    boat = create_boat(client)
    crew = create_crew(client)
    trip = create_trip(client, boat_id=boat["id"], crew_id=crew["id"])
    response = client.get("/api/trips")
    assert response.status_code == 200
    assert response.json() == [trip]


def test_trip_rejects_unknown_boat(client: TestClient) -> None:
    crew = create_crew(client)
    response = client.post(
        "/api/trips",
        json={"boat_id": 999, "crew_id": crew["id"], "departure_date": "2026-09-10"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Катер не найден"


def test_trip_rejects_unknown_crew(client: TestClient) -> None:
    boat = create_boat(client)
    response = client.post(
        "/api/trips",
        json={"boat_id": boat["id"], "crew_id": 999, "departure_date": "2026-09-10"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Команда не найдена"


def test_trip_rejects_return_date_before_departure(client: TestClient) -> None:
    boat = create_boat(client)
    crew = create_crew(client)
    response = client.post(
        "/api/trips",
        json={
            "boat_id": boat["id"],
            "crew_id": crew["id"],
            "departure_date": "2026-09-10",
            "return_date": "2026-09-09",
        },
    )
    assert response.status_code == 422


def test_create_and_list_catches(client: TestClient) -> None:
    boat = create_boat(client)
    crew = create_crew(client)
    fish = create_fish_type(client)
    trip = create_trip(client, boat_id=boat["id"], crew_id=crew["id"])
    catch = create_catch(client, trip_id=trip["id"], fish_type_id=fish["id"])
    response = client.get("/api/catches")
    assert response.status_code == 200
    assert response.json() == [catch]


def test_catch_rejects_unknown_trip(client: TestClient) -> None:
    fish = create_fish_type(client)
    response = client.post(
        "/api/catches",
        json={"trip_id": 999, "fish_type_id": fish["id"], "cans": 1, "weight_kg": 1},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Рейс не найден"


def test_catch_rejects_unknown_fish_type(client: TestClient) -> None:
    boat = create_boat(client)
    crew = create_crew(client)
    trip = create_trip(client, boat_id=boat["id"], crew_id=crew["id"])
    response = client.post(
        "/api/catches",
        json={"trip_id": trip["id"], "fish_type_id": 999, "cans": 1, "weight_kg": 1},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Сорт рыбы не найден"


def test_catch_rejects_zero_cans_and_weight(client: TestClient) -> None:
    response = client.post(
        "/api/catches",
        json={"trip_id": 1, "fish_type_id": 1, "cans": 0, "weight_kg": 0},
    )
    assert response.status_code == 422


def test_catch_capacity_rule_sums_existing_catches(client: TestClient) -> None:
    boat = create_boat(client, capacity_kg=100)
    crew = create_crew(client)
    fish = create_fish_type(client)
    trip = create_trip(client, boat_id=boat["id"], crew_id=crew["id"])

    first = client.post(
        "/api/catches",
        json={"trip_id": trip["id"], "fish_type_id": fish["id"], "cans": 4, "weight_kg": 70},
    )
    second = client.post(
        "/api/catches",
        json={"trip_id": trip["id"], "fish_type_id": fish["id"], "cans": 2, "weight_kg": 31},
    )

    assert first.status_code == 201
    assert second.status_code == 422
    assert "грузоподъемность" in second.json()["detail"]


def test_trip_report_aggregates_catch_weight(client: TestClient) -> None:
    boat = create_boat(client, capacity_kg=200)
    crew = create_crew(client)
    fish = create_fish_type(client)
    trip = create_trip(client, boat_id=boat["id"], crew_id=crew["id"])
    create_catch(client, trip_id=trip["id"], fish_type_id=fish["id"], weight_kg=30)
    create_catch(client, trip_id=trip["id"], fish_type_id=fish["id"], cans=3, weight_kg=45)

    response = client.get("/api/reports/catch-by-trip")
    assert response.status_code == 200
    assert response.json() == [
        {"trip_id": trip["id"], "boat": boat["name"], "total_weight_kg": 75.0}
    ]


def test_period_report_filters_by_inclusive_date_range(client: TestClient) -> None:
    boat = create_boat(client, capacity_kg=300)
    crew = create_crew(client)
    fish = create_fish_type(client)
    first_trip = create_trip(
        client,
        boat_id=boat["id"],
        crew_id=crew["id"],
        departure_date="2026-09-01",
        return_date="2026-09-02",
    )
    second_trip = create_trip(
        client,
        boat_id=boat["id"],
        crew_id=crew["id"],
        departure_date="2026-09-20",
        return_date="2026-09-21",
    )
    create_catch(client, trip_id=first_trip["id"], fish_type_id=fish["id"], weight_kg=20)
    create_catch(client, trip_id=second_trip["id"], fish_type_id=fish["id"], weight_kg=40)

    response = client.get(
        "/api/reports/catch-by-period",
        params={"date_from": "2026-09-15", "date_to": "2026-09-30"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "trip_count": 1,
        "total_weight_kg": 40.0,
        "total_cans": 2,
    }


def test_period_report_rejects_reversed_date_range(client: TestClient) -> None:
    response = client.get(
        "/api/reports/catch-by-period",
        params={"date_from": "2026-09-30", "date_to": "2026-09-01"},
    )
    assert response.status_code == 422
    assert "не может быть раньше" in response.json()["detail"]


def test_period_report_returns_zero_totals_for_empty_database(client: TestClient) -> None:
    response = client.get("/api/reports/catch-by-period")
    assert response.status_code == 200
    assert response.json() == {"trip_count": 0, "total_weight_kg": 0.0, "total_cans": 0}
