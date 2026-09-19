# PR-001: Отчёт по улову за период

**Задача:** TASK-008

**Ветка:** `feature/catch-period-report`

## Описание

Добавлен endpoint `GET /api/reports/catch-by-period` с необязательными параметрами `date_from` и `date_to`. Отчёт использует агрегирование SQL и возвращает рейсы с суммарным весом улова, включая рейсы без улова.

## Коммиты

1. `docs: define catch period report task`
2. `feat: add catch report for period`
3. `docs: add change acceptance rules`

## Проверка

- `python -m compileall app tests` — пройдена.
- `make verify` — в чистом окружении не завершилась из-за отсутствия `psycopg` и невозможности скачать зависимости из сети; причина относится к окружению, не к компиляции исходников.
- Для полноценной проверки в проектном окружении выполнить `make setup`, затем `make verify`.

## Решение ревью

Изменение принято в учебный `main` после просмотра diff и фиксации ограничений проверки окружения.
