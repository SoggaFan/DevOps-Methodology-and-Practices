import os
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Date, ForeignKey, Numeric, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://fishing:fishing@localhost:5432/fishing")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Boat(Base):
    __tablename__ = "boats"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    registration_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    trips: Mapped[list["Trip"]] = relationship(back_populates="boat")


class Crew(Base):
    __tablename__ = "crews"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    captain: Mapped[str] = mapped_column(String(100), nullable=False)
    trips: Mapped[list["Trip"]] = relationship(back_populates="crew")


class FishType(Base):
    __tablename__ = "fish_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    latin_name: Mapped[str | None] = mapped_column(String(120))
    catches: Mapped[list["Catch"]] = relationship(back_populates="fish_type")


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[int] = mapped_column(primary_key=True)
    boat_id: Mapped[int] = mapped_column(ForeignKey("boats.id"), nullable=False)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crews.id"), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    boat: Mapped[Boat] = relationship(back_populates="trips")
    crew: Mapped[Crew] = relationship(back_populates="trips")
    catches: Mapped[list["Catch"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class Catch(Base):
    __tablename__ = "catches"
    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    fish_type_id: Mapped[int] = mapped_column(ForeignKey("fish_types.id"), nullable=False)
    cans: Mapped[int] = mapped_column(nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    trip: Mapped[Trip] = relationship(back_populates="catches")
    fish_type: Mapped[FishType] = relationship(back_populates="catches")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Fishing Firm API", version="0.1.0", lifespan=lifespan)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def web_interface():
    return FileResponse(WEB_DIR / "index.html")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "service": "fishing-firm-api"}


@app.get("/api/boats", response_model=list[BoatOut])
def list_boats(db: Session = Depends(get_db)):
    return list(db.scalars(select(Boat).order_by(Boat.id)))


@app.post("/api/boats", response_model=BoatOut, status_code=status.HTTP_201_CREATED)
def create_boat(payload: BoatIn, db: Session = Depends(get_db)):
    if db.scalar(select(Boat).where(Boat.registration_no == payload.registration_no)):
        raise HTTPException(409, "Катер с таким регистрационным номером уже существует")
    boat = Boat(**payload.model_dump())
    db.add(boat)
    db.commit()
    db.refresh(boat)
    return boat


@app.get("/api/crews", response_model=list[CrewOut])
def list_crews(db: Session = Depends(get_db)):
    return list(db.scalars(select(Crew).order_by(Crew.id)))


@app.post("/api/crews", response_model=CrewOut, status_code=status.HTTP_201_CREATED)
def create_crew(payload: CrewIn, db: Session = Depends(get_db)):
    crew = Crew(**payload.model_dump())
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew


@app.get("/api/fish-types", response_model=list[FishTypeOut])
def list_fish_types(db: Session = Depends(get_db)):
    return list(db.scalars(select(FishType).order_by(FishType.id)))


@app.post("/api/fish-types", response_model=FishTypeOut, status_code=status.HTTP_201_CREATED)
def create_fish_type(payload: FishTypeIn, db: Session = Depends(get_db)):
    if db.scalar(select(FishType).where(FishType.name == payload.name)):
        raise HTTPException(409, "Такой сорт рыбы уже существует")
    fish = FishType(**payload.model_dump())
    db.add(fish)
    db.commit()
    db.refresh(fish)
    return fish


@app.get("/api/trips", response_model=list[TripOut])
def list_trips(db: Session = Depends(get_db)):
    return list(db.scalars(select(Trip).order_by(Trip.departure_date.desc(), Trip.id.desc())))


@app.post("/api/trips", response_model=TripOut, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripIn, db: Session = Depends(get_db)):
    if payload.return_date and payload.return_date < payload.departure_date:
        raise HTTPException(422, "Дата возвращения не может быть раньше даты выхода в рейс")
    if not db.get(Boat, payload.boat_id):
        raise HTTPException(404, "Катер не найден")
    if not db.get(Crew, payload.crew_id):
        raise HTTPException(404, "Команда не найдена")
    trip = Trip(**payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@app.get("/api/catches", response_model=list[CatchOut])
def list_catches(db: Session = Depends(get_db)):
    return list(db.scalars(select(Catch).order_by(Catch.id)))


@app.post("/api/catches", response_model=CatchOut, status_code=status.HTTP_201_CREATED)
def create_catch(payload: CatchIn, db: Session = Depends(get_db)):
    trip = db.get(Trip, payload.trip_id)
    if not trip:
        raise HTTPException(404, "Рейс не найден")
    if not db.get(FishType, payload.fish_type_id):
        raise HTTPException(404, "Сорт рыбы не найден")
    current_weight = db.scalar(select(func.coalesce(func.sum(Catch.weight_kg), 0)).where(Catch.trip_id == payload.trip_id))
    if Decimal(current_weight) + payload.weight_kg > trip.boat.capacity_kg:
        raise HTTPException(422, "Превышена грузоподъемность катера")
    item = Catch(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/reports/catch-by-period")
def catch_report_by_period(
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "Дата окончания периода не может быть раньше даты начала")

    stmt = (
        select(
            Trip.id,
            Boat.name,
            Trip.departure_date,
            func.coalesce(func.sum(Catch.weight_kg), 0).label("total_weight_kg"),
        )
        .join(Boat, Boat.id == Trip.boat_id)
        .outerjoin(Catch, Catch.trip_id == Trip.id)
        .group_by(Trip.id, Boat.name, Trip.departure_date)
        .order_by(Trip.departure_date, Trip.id)
    )
    if date_from:
        stmt = stmt.where(Trip.departure_date >= date_from)
    if date_to:
        stmt = stmt.where(Trip.departure_date <= date_to)

    rows = db.execute(stmt).all()
    return [
        {
            "trip_id": trip_id,
            "boat": boat,
            "departure_date": departure_date,
            "total_weight_kg": float(total_weight),
        }
        for trip_id, boat, departure_date, total_weight in rows
    ]


@app.get("/api/reports/catch-by-trip")
def catch_report(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Trip.id, Boat.name, func.coalesce(func.sum(Catch.weight_kg), 0).label("total_weight_kg"))
        .join(Boat, Boat.id == Trip.boat_id)
        .outerjoin(Catch, Catch.trip_id == Trip.id)
        .group_by(Trip.id, Boat.name)
        .order_by(Trip.id)
    ).all()
    return [
        {"trip_id": trip_id, "boat": boat, "total_weight_kg": float(total_weight)}
        for trip_id, boat, total_weight in rows
    ]
