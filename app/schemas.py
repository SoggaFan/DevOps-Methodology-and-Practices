from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class UserOut(BaseModel):
    id: int
    username: str
    is_active: bool


class BoatIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    registration_no: str = Field(min_length=2, max_length=50)
    capacity_kg: Decimal = Field(gt=0, le=100000)


class BoatOut(BoatIn):
    id: int


class CrewIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    captain: str = Field(min_length=2, max_length=100)


class CrewOut(CrewIn):
    id: int


class FishTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    latin_name: str | None = Field(default=None, max_length=120)


class FishTypeOut(FishTypeIn):
    id: int


class TripIn(BaseModel):
    boat_id: int = Field(gt=0)
    crew_id: int = Field(gt=0)
    departure_date: date
    return_date: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.return_date and self.return_date < self.departure_date:
            raise ValueError("Дата возвращения не может быть раньше даты выхода в рейс")
        return self


class TripOut(TripIn):
    id: int


class CatchIn(BaseModel):
    trip_id: int = Field(gt=0)
    fish_type_id: int = Field(gt=0)
    cans: int = Field(gt=0)
    weight_kg: Decimal = Field(gt=0, le=100000)


class CatchOut(CatchIn):
    id: int
