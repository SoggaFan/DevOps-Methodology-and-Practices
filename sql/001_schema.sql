CREATE TABLE IF NOT EXISTS boats (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    registration_no VARCHAR(50) NOT NULL UNIQUE,
    capacity_kg NUMERIC(10,2) NOT NULL CHECK (capacity_kg > 0)
);
CREATE TABLE IF NOT EXISTS crews (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    captain VARCHAR(100) NOT NULL
);
CREATE TABLE IF NOT EXISTS fish_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    latin_name VARCHAR(120)
);
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    boat_id INT NOT NULL REFERENCES boats(id),
    crew_id INT NOT NULL REFERENCES crews(id),
    departure_date DATE NOT NULL,
    return_date DATE,
    notes TEXT,
    CHECK (return_date IS NULL OR return_date >= departure_date)
);
CREATE TABLE IF NOT EXISTS catches (
    id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    fish_type_id INT NOT NULL REFERENCES fish_types(id),
    cans INT NOT NULL CHECK (cans > 0),
    weight_kg NUMERIC(10,2) NOT NULL CHECK (weight_kg > 0)
);
