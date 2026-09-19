# API — Fishing Firm

Base URL: `http://localhost:8000`

Документация FastAPI: `GET /docs` и `GET /openapi.json`.

## Аутентификация

Бизнес-операции API защищены HTTP Basic. Для входа используется учетная запись администратора, созданная при старте приложения из переменных окружения `ADMIN_USERNAME` и `ADMIN_PASSWORD`. Пароль хранится в БД только в виде хеша scrypt.

### POST `/auth/login`

Проверяет логин и пароль из HTTP Basic.

Пример:
```bash
curl -s -X POST http://localhost:8000/auth/login \
  -u 'admin:change_me_admin'
```

Успешный ответ содержит `id`, `username` и `is_active`.

### GET `/auth/me`

Возвращает текущего пользователя и требует HTTP Basic credentials.

Пример:
```bash
curl -s http://localhost:8000/auth/me \
  -u 'admin:change_me_admin'
```

Все `/api/*` endpoints требуют корректные учетные данные. Без них или при неверном пароле возвращается HTTP 401.

## Служебный endpoint

### GET `/health`

Проверяет доступность БД и API.

Пример ответа:

```json
{"status":"ok","service":"fishing-firm-api"}
```

## Катера

- `GET /api/boats` — список катеров.
- `POST /api/boats` — добавить катер.

Тело:

```json
{"name":"Океан","registration_no":"RF-100","capacity_kg":1000}
```

## Команды

- `GET /api/crews`
- `POST /api/crews`

```json
{"name":"Команда Восток","captain":"Сидоров С.С."}
```

## Сорта рыбы

- `GET /api/fish-types`
- `POST /api/fish-types`

```json
{"name":"Минтай","latin_name":"Gadus chalcogrammus"}
```

## Рейсы

- `GET /api/trips`
- `POST /api/trips`

```json
{
  "boat_id": 1,
  "crew_id": 1,
  "departure_date": "2026-09-01",
  "return_date": "2026-09-05",
  "notes": "Пробный рейс"
}
```

## Улов

- `GET /api/catches`
- `POST /api/catches`

```json
{
  "trip_id": 1,
  "fish_type_id": 1,
  "cans": 50,
  "weight_kg": 700
}
```

Перед созданием система проверяет сумму улова рейса и грузоподъемность катера.

## Отчеты

### GET `/api/reports/catch-by-trip`

Возвращает массу улова по каждому рейсу.

### GET `/api/reports/catch-by-period`

Параметры:

- `date_from=YYYY-MM-DD`
- `date_to=YYYY-MM-DD`

Возвращает количество рейсов, общую массу улова и общее количество банок за период.

## Коды ошибок

- `401` — отсутствует или неверный логин/пароль;
- `404` — связанная сущность не найдена;
- `409` — дубликат уникального значения;
- `422` — ошибка валидации или превышение грузоподъемности.
