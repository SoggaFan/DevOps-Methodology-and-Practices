# Быстрая демонстрация через curl

После `make up`.

## 1. Служебная проверка

```bash
curl -s http://localhost:8000/health
```

## 2. Аутентификация

В `.env` заданы `ADMIN_USERNAME` и `ADMIN_PASSWORD`.

```bash
source .env
curl -s -X POST http://localhost:8000/auth/login \
  -u "$ADMIN_USERNAME:$ADMIN_PASSWORD"
```

Проверить текущего пользователя:

```bash
curl -s http://localhost:8000/auth/me \
  -u "$ADMIN_USERNAME:$ADMIN_PASSWORD"
```

Проверить защиту без логина и пароля:

```bash
curl -i http://localhost:8000/api/boats
```

Проверить отказ с неправильным паролем:

```bash
curl -i http://localhost:8000/api/boats \
  -u "$ADMIN_USERNAME:wrong-password"
```

Проверить успешный доступ:

```bash
curl -s http://localhost:8000/api/boats \
  -u "$ADMIN_USERNAME:$ADMIN_PASSWORD"
```

Ожидается `401 Unauthorized`.

## 3. Работа с защищенным API

Для всех защищенных запросов используйте те же логин и пароль.

```bash
source .env
AUTH="-u $ADMIN_USERNAME:$ADMIN_PASSWORD"

curl -s http://localhost:8000/api/boats $AUTH
curl -s http://localhost:8000/api/crews $AUTH
curl -s http://localhost:8000/api/fish-types $AUTH
```

## 4. Создать сущности

```bash
curl -s -X POST http://localhost:8000/api/boats $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"name":"Океан","registration_no":"RF-100","capacity_kg":1000}'

curl -s -X POST http://localhost:8000/api/crews $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"name":"Команда Восток","captain":"Сидоров С.С."}'

curl -s -X POST http://localhost:8000/api/fish-types $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"name":"Минтай","latin_name":"Gadus chalcogrammus"}'
```

## 5. Рейс и улов

```bash
curl -s -X POST http://localhost:8000/api/trips $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"boat_id":1,"crew_id":1,"departure_date":"2026-09-01","return_date":"2026-09-05","notes":"Пробный рейс"}'

curl -s -X POST http://localhost:8000/api/catches $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"trip_id":1,"fish_type_id":1,"cans":50,"weight_kg":700}'
```

Попробовать превысить грузоподъемность:

```bash
curl -s -X POST http://localhost:8000/api/catches $AUTH \
  -H 'Content-Type: application/json' \
  -d '{"trip_id":1,"fish_type_id":1,"cans":50,"weight_kg":400}'
```

Ожидается HTTP 422.

## 6. Отчеты

```bash
curl -s http://localhost:8000/api/reports/catch-by-trip $AUTH
curl -s 'http://localhost:8000/api/reports/catch-by-period?date_from=2026-09-01&date_to=2026-09-30' $AUTH
```

Проверка ошибки диапазона:

```bash
curl -i 'http://localhost:8000/api/reports/catch-by-period?date_from=2026-09-30&date_to=2026-09-01' $AUTH
```

Ожидается HTTP 422.
