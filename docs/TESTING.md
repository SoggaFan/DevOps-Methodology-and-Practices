# Проверочный контур ЛР3

## Единый сценарий первоначальной настройки

На Linux/macOS/в CI из корня репозитория:

```bash
make setup
make verify
```

`make setup` создаёт `.venv` и устанавливает зафиксированные runtime- и development-зависимости. Для запуска приложения и команд, работающих с PostgreSQL, заранее настройте `.env` по образцу `.env.example` и запустите доступную БД.

В Windows PowerShell, если GNU Make недоступен, эквивалент первоначальной настройки:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Проверки в PowerShell:

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
.\.venv\Scripts\python.exe -m ruff format --check app tests
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m bandit -q -r app
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml --cov-fail-under=65
```

## Команды Makefile

- `make setup` — создать виртуальное окружение и установить закреплённые зависимости.
- `make run` — локально запустить FastAPI; для подключения к БД задайте `DATABASE_URL` или заполните `.env`.
- `make test` — запустить unit- и API/DB-интеграционные тесты, сформировать JUnit XML и coverage XML.
- `make quality` — проверить форматирование и статический анализ Ruff.
- `make security` — выполнить SAST проверку Bandit.
- `make coverage` — вывести отчёт покрытия после запуска тестов.
- `make migrate` — применить Alembic-миграции, если `alembic.ini` присутствует; до подключения миграционного инструмента используется SQL baseline проекта.
- `make backup` — сохранить дамп PostgreSQL в `backup.sql` (переопределяется через `BACKUP_FILE=...`).
- `make restore` — восстановить SQL-дамп `BACKUP_FILE` в настроенную через Compose БД. Используйте только проверенную копию и следуйте сценарию восстановления из документации ЛР3.
- `make verify` — обязательный gate: `quality` + `security` + тесты с покрытием.
- `make up`, `make down`, `make container-check` — контейнерное окружение и быстрый smoke-check.

## Тестовая БД и изоляция данных

- По умолчанию локальные тесты используют in-memory SQLite: они не требуют контейнеров и не обращаются к пользовательской БД.
- Если задан `TEST_DATABASE_URL`, тесты используют его. Для PostgreSQL база должна называться с суффиксом `_test` или `_tests`; fixture откажется выполнять очистку схемы, если имя не выглядит как тестовая БД.
- Каждый API-тест получает чистую схему, созданную по SQLAlchemy metadata; тестовые записи удаляются между тестами.
- CI поднимает отдельный PostgreSQL 17 сервис и запускает тот же `make verify` против `fishing_test`.
- Никогда не указывайте в `TEST_DATABASE_URL` рабочую/учебную БД с полезными данными.

## Покрытие требований ТЗ

| Требование ТЗ | Проверки |
|---|---|
| FR-01: доступность API и БД | `test_health_checks_database`, `test_health_reports_database_error_as_503` |
| FR-02: создание/просмотр катеров, уникальность и положительная вместимость | `test_create_and_list_boats`, `test_duplicate_boat_registration_returns_409`, проверки `BoatIn` |
| FR-03: создание/просмотр команд и валидация полей | `test_create_and_list_crews`, `test_crew_requires_nontrivial_name_and_captain` |
| FR-04: создание/просмотр сортов рыбы, уникальность | `test_create_and_list_fish_types`, `test_duplicate_fish_type_returns_409` |
| FR-05: рейсы, внешние ключи и даты | `test_create_and_list_trips`, `test_trip_rejects_unknown_boat`, `test_trip_rejects_unknown_crew`, проверки дат `TripIn` и API |
| FR-06: записи улова и ссылки на рейс/сорт | `test_create_and_list_catches`, тесты отсутствующих ссылок и положительных значений |
| FR-07: ограничение вместимости катера | `test_catch_capacity_rule_sums_existing_catches` |
| FR-08: отчёт по рейсам | `test_trip_report_aggregates_catch_weight` |
| FR-09: период отчёта, даты и фильтр | `test_period_report_filters_by_inclusive_date_range`, `test_period_report_rejects_reversed_date_range` |
| Статические файлы UI | `test_root_serves_web_interface`, `test_static_assets_are_served` |

Порог покрытия строк кода задаётся в `pyproject.toml` и не должен снижаться без обоснования. Покрытие строк — измеримый индикатор, но не заменяет матрицу сценариев выше.

## Отчёты

`make test` создаёт:

- `reports/junit.xml` — результаты тестов;
- `reports/coverage.xml` — машинно-читаемый отчёт покрытия;
- сводку покрытия в терминале.

В CI оба файла загружаются как artifact даже если проверка завершается ошибкой.

## Изменение правила ради проверки (mutation-style check)

Чтобы проверить, что тест защищает бизнес-правило, в отдельной временной ветке измените условие ограничения улова, например удалите сравнение суммарного улова с грузоподъёмностью. Затем выполните `make test`: `test_catch_capacity_rule_sums_existing_catches` должен упасть. После демонстрации восстановите исходное условие, повторно запустите `make verify` и не сохраняйте мутированное правило в PR.
