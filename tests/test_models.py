from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.main import BoatIn, CatchIn, CrewIn, FishTypeIn, TripIn


@pytest.mark.unit
@pytest.mark.parametrize("capacity", [Decimal("0"), Decimal("-0.01"), Decimal("100000.01")])
def test_boat_capacity_must_be_within_allowed_range(capacity: Decimal) -> None:
    with pytest.raises(ValidationError):
        BoatIn(name="Маяк", registration_no="RF-001", capacity_kg=capacity)


@pytest.mark.unit
def test_boat_accepts_upper_capacity_boundary() -> None:
    boat = BoatIn(name="Маяк", registration_no="RF-001", capacity_kg=Decimal("100000"))
    assert boat.capacity_kg == Decimal("100000")


@pytest.mark.unit
@pytest.mark.parametrize("cans", [0, -1])
def test_catch_requires_positive_can_count(cans: int) -> None:
    with pytest.raises(ValidationError):
        CatchIn(trip_id=1, fish_type_id=1, cans=cans, weight_kg=Decimal("1"))


@pytest.mark.unit
@pytest.mark.parametrize("weight", [Decimal("0"), Decimal("-0.1"), Decimal("100000.01")])
def test_catch_weight_must_be_within_allowed_range(weight: Decimal) -> None:
    with pytest.raises(ValidationError):
        CatchIn(trip_id=1, fish_type_id=1, cans=1, weight_kg=weight)


@pytest.mark.unit
def test_trip_rejects_return_date_before_departure() -> None:
    with pytest.raises(ValidationError, match="Дата возвращения не может быть раньше"):
        TripIn(
            boat_id=1,
            crew_id=1,
            departure_date=date(2026, 9, 10),
            return_date=date(2026, 9, 9),
        )


@pytest.mark.unit
def test_trip_accepts_same_departure_and_return_date() -> None:
    trip = TripIn(
        boat_id=1,
        crew_id=1,
        departure_date=date(2026, 9, 10),
        return_date=date(2026, 9, 10),
    )
    assert trip.return_date == trip.departure_date


@pytest.mark.unit
def test_crew_requires_nontrivial_name_and_captain() -> None:
    with pytest.raises(ValidationError):
        CrewIn(name="A", captain="И")


@pytest.mark.unit
def test_fish_type_rejects_overlong_latin_name() -> None:
    with pytest.raises(ValidationError):
        FishTypeIn(name="Треска", latin_name="x" * 121)
