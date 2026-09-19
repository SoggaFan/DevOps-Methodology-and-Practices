# Схема БД — Fishing Firm

Используется PostgreSQL 17.

## Сущности

### `users`

- `id` — PK
- `username` — уникальное имя пользователя
- `password_hash` — хеш пароля, открытый пароль не хранится
- `is_active` — признак активной учетной записи
- `created_at` — дата и время создания учетной записи


### `boats`

- `id` — PK
- `name` — уникальное название
- `registration_no` — уникальный регистрационный номер
- `capacity_kg` — грузоподъемность, > 0

### `crews`

- `id` — PK
- `name` — название команды
- `captain` — капитан

### `fish_types`

- `id` — PK
- `name` — уникальное название сорта
- `latin_name` — латинское название, необязательное

### `trips`

- `id` — PK
- `boat_id` — FK → `boats.id`
- `crew_id` — FK → `crews.id`
- `departure_date`
- `return_date`
- `notes`

Ограничение: `return_date IS NULL OR return_date >= departure_date`.

### `catches`

- `id` — PK
- `trip_id` — FK → `trips.id`, `ON DELETE CASCADE`
- `fish_type_id` — FK → `fish_types.id`
- `cans` — > 0
- `weight_kg` — > 0

## Аутентификация

При старте приложения автоматически создается административная учетная запись из переменных `ADMIN_USERNAME` и `ADMIN_PASSWORD`, если пользователь с таким именем еще не существует. Пароль сохраняется в БД только в виде scrypt-хеша.

## Связи

```text
boats       1 ─────< trips >───── 1 crews
                     |
                     |
                     v
                  catches >───── 1 fish_types
```

## Содержательное правило

`SUM(catches.weight_kg)` для одного рейса не должен превышать `boats.capacity_kg`.
Это правило проверяется в приложении перед вставкой новой записи улова.
