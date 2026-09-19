# Быстрая демонстрация через curl

После `make up`:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/boats
curl -s http://localhost:8000/api/crews
curl -s http://localhost:8000/api/fish-types
```

Создать сущности:

```bash
curl -s -X POST http://localhost:8000/api/boats -H 'Content-Type: application/json' -d '{"name":"Океан","registration_no":"RF-100","capacity_kg":1000}'
curl -s -X POST http://localhost:8000/api/crews -H 'Content-Type: application/json' -d '{"name":"Команда Восток","captain":"Сидоров С.С."}'
curl -s -X POST http://localhost:8000/api/fish-types -H 'Content-Type: application/json' -d '{"name":"Минтай","latin_name":"Gadus chalcogrammus"}'
```

Создать рейс (проверьте ID в предыдущих ответах):

```bash
curl -s -X POST http://localhost:8000/api/trips -H 'Content-Type: application/json' -d '{"boat_id":1,"crew_id":1,"departure_date":"2026-09-01","return_date":"2026-09-05","notes":"Пробный рейс"}'
```

Добавить улов:

```bash
curl -s -X POST http://localhost:8000/api/catches -H 'Content-Type: application/json' -d '{"trip_id":1,"fish_type_id":1,"cans":50,"weight_kg":700}'
```

Попробовать превысить грузоподъёмность:

```bash
curl -s -X POST http://localhost:8000/api/catches -H 'Content-Type: application/json' -d '{"trip_id":1,"fish_type_id":1,"cans":50,"weight_kg":400}'
```
Ожидается HTTP 422 с сообщением о превышении грузоподъёмности.

Отчёт:

```bash
curl -s http://localhost:8000/api/reports/catch-by-trip
```
## Health check

Проверка работоспособности API:

```text
GET http://localhost:8000/health

Пример запроса:

```bash
curl http://localhost:8000/health
```
Ожидаемый HTTP-код: 200