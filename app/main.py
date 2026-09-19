import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.schemas import BoatIn, BoatOut, CatchIn, CatchOut, CrewIn, CrewOut, FishTypeIn, FishTypeOut, TripIn, TripOut, UserOut
from app.security import hash_password, verify_password

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://fishing:fishing@localhost:5432/fishing")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change_me_admin")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


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


def ensure_admin_user(db: Session) -> None:
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    if user:
        return
    db.add(
        User(
            username=ADMIN_USERNAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            is_active=True,
        )
    )
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin_user(db)
    yield


app = FastAPI(title="Fishing Firm API", version="0.2.0", lifespan=lifespan)
basic_security = HTTPBasic()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(credentials: HTTPBasicCredentials = Depends(basic_security), db: Session = Depends(get_db)) -> User:
    user = db.scalar(select(User).where(User.username == credentials.username))
    if not user or not user.is_active or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "service": "fishing-firm-api"}


@app.post("/auth/login", response_model=UserOut)
def login(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/api/boats", response_model=list[BoatOut])
def list_boats(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(Boat).order_by(Boat.id)))


@app.post("/api/boats", response_model=BoatOut, status_code=status.HTTP_201_CREATED)
def create_boat(payload: BoatIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.scalar(select(Boat).where(Boat.registration_no == payload.registration_no)):
        raise HTTPException(409, "Катер с таким регистрационным номером уже существует")
    boat = Boat(**payload.model_dump())
    db.add(boat)
    db.commit()
    db.refresh(boat)
    return boat


@app.get("/api/crews", response_model=list[CrewOut])
def list_crews(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(Crew).order_by(Crew.id)))


@app.post("/api/crews", response_model=CrewOut, status_code=status.HTTP_201_CREATED)
def create_crew(payload: CrewIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    crew = Crew(**payload.model_dump())
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew


@app.get("/api/fish-types", response_model=list[FishTypeOut])
def list_fish_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(FishType).order_by(FishType.id)))


@app.post("/api/fish-types", response_model=FishTypeOut, status_code=status.HTTP_201_CREATED)
def create_fish_type(payload: FishTypeIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.scalar(select(FishType).where(FishType.name == payload.name)):
        raise HTTPException(409, "Такой сорт рыбы уже существует")
    fish = FishType(**payload.model_dump())
    db.add(fish)
    db.commit()
    db.refresh(fish)
    return fish


@app.get("/api/trips", response_model=list[TripOut])
def list_trips(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(Trip).order_by(Trip.departure_date.desc(), Trip.id.desc())))


@app.post("/api/trips", response_model=TripOut, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
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
def list_catches(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.scalars(select(Catch).order_by(Catch.id)))


@app.post("/api/catches", response_model=CatchOut, status_code=status.HTTP_201_CREATED)
def create_catch(payload: CatchIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
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


@app.get("/api/reports/catch-by-trip")
def catch_report(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
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


@app.get("/api/reports/catch-by-period")
def catch_report_by_period(date_from: date, date_to: date, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if date_to < date_from:
        raise HTTPException(422, "Дата окончания периода не может быть раньше даты начала")
    trip_count = db.scalar(
        select(func.count(Trip.id)).where(Trip.departure_date.between(date_from, date_to))
    ) or 0
    total_weight = db.scalar(
        select(func.coalesce(func.sum(Catch.weight_kg), 0))
        .join(Trip, Trip.id == Catch.trip_id)
        .where(Trip.departure_date.between(date_from, date_to))
    ) or 0
    total_cans = db.scalar(
        select(func.coalesce(func.sum(Catch.cans), 0))
        .join(Trip, Trip.id == Catch.trip_id)
        .where(Trip.departure_date.between(date_from, date_to))
    ) or 0
    return {
        "date_from": date_from,
        "date_to": date_to,
        "trip_count": int(trip_count),
        "total_weight_kg": float(total_weight),
        "total_cans": int(total_cans),
    }
