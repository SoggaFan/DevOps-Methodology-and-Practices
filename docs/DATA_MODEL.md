# Схема данных

Схема соответствует реляционной модели PostgreSQL из `sql/001_schema.sql`.

```mermaid
erDiagram
    BOATS ||--o{ TRIPS : "используется в"
    CREWS ||--o{ TRIPS : "выходит в"
    TRIPS ||--o{ CATCHES : "содержит"
    FISH_TYPES ||--o{ CATCHES : "описывает"

    BOATS {
        int id PK
        varchar name UK
        varchar registration_no UK
        numeric capacity_kg
    }
    CREWS {
        int id PK
        varchar name
        varchar captain
    }
    FISH_TYPES {
        int id PK
        varchar name UK
        varchar latin_name
    }
    TRIPS {
        int id PK
        int boat_id FK
        int crew_id FK
        date departure_date
        date return_date
        text notes
    }
    CATCHES {
        int id PK
        int trip_id FK
        int fish_type_id FK
        int cans
        numeric weight_kg
    }
```

## Связи

- Один катер выполняет много рейсов (`boats.id → trips.boat_id`).
- Одна команда участвует во многих рейсах (`crews.id → trips.crew_id`).
- Один рейс содержит много записей улова (`trips.id → catches.trip_id`).
- Один сорт рыбы встречается во многих записях улова (`fish_types.id → catches.fish_type_id`).

## Ограничение предметной области

При добавлении улова API суммирует уже записанный вес по рейсу и отклоняет операцию с HTTP `422`, если новый суммарный вес превышает `boats.capacity_kg`.
