# ЛР1 — Рыболовная фирма

Минимальная информационная система учета деятельности рыболовной фирмы. Проект разработан по ТЗ из `docs/TECHNICAL_SPECIFICATION.md` и требованиям ЛР1 по дисциплине «Методология и практики DevOps».

## 1. Что реализовано

- HTTP API на FastAPI.
- Реляционная БД PostgreSQL 17.
- 5 связанных сущностей: `boats`, `crews`, `fish_types`, `trips`, `catches`.
- Проверка внешних ключей при создании рейса и улова.
- Бизнес-правило: суммарная масса улова рейса не может превышать грузоподъемность катера.
- Обработка ошибок HTTP 404/409/422.
- `GET /health` с проверкой соединения с БД.
- Базовая аутентификация пользователей по логину и паролю через HTTP Basic.
- Отчет по рейсам и отчет за период.
- Конфигурация через переменные окружения.
- Docker Compose для API и PostgreSQL.
- SQL-схема и начальные данные.
- Тесты и Makefile.
- Git-процесс: feature-ветка, несколько коммитов, PR/MR, merge, конфликт и тег `v0.1.0`.

## 2. Документы проекта

- `docs/TECHNICAL_SPECIFICATION.md` — формальное ТЗ.
- `docs/API.md` — описание API.
- `docs/DB_SCHEMA.md` — схема БД и связи.
- `docs/GIT_DEFENSE.md` — сценарий защиты Git.
- `docs/DEMO.md` — пошаговая демонстрация API.

## 3. Быстрый запуск

```bash
cp .env.example .env
make up
make container-check
```

Swagger UI:

```text
http://localhost:8000/docs
```

Проверка:

```bash
curl http://localhost:8000/health
```

Ожидается HTTP 200 и JSON с `status = ok`.

### БД

База доступна внутри Docker-сети. Для защиты:

```bash
docker compose exec db psql -U fishing -d fishing
```

Внутри:

```sql
\dt
SELECT * FROM boats;
SELECT * FROM crews;
SELECT * FROM fish_types;
SELECT * FROM trips;
SELECT * FROM users;
SELECT * FROM catches;
```

## 4. Аутентификация

Для ЛР1 используется HTTP Basic: логин и пароль передаются в заголовке `Authorization`. Данные администратора задаются в `.env` через `ADMIN_USERNAME` и `ADMIN_PASSWORD` и автоматически создаются в таблице `users`.

Проверить вход можно так:

```bash
source .env
curl -s -X POST http://localhost:8000/auth/login \
  -u "$ADMIN_USERNAME:$ADMIN_PASSWORD"
```

Проверить защищенный endpoint:

```bash
curl -i http://localhost:8000/api/boats

curl -s http://localhost:8000/api/boats \
  -u "$ADMIN_USERNAME:$ADMIN_PASSWORD"
```

Веб-интерфейс (`http://localhost:8000/`) при открытии показывает форму входа. После ввода логина и пароля администратора открывается рабочая панель; кнопка «Выйти» в шапке сбрасывает сессию. Учётные данные хранятся только в `sessionStorage` вкладки браузера. Сама страница и статические файлы (`/`, `/static/*`), а также `/health` и `/docs` доступны без входа, а все данные — только через защищённые `/api/*`.

В Swagger (`/docs`) нажмите `Authorize` и введите логин и пароль. После этого Swagger сможет вызывать защищенные `/api/*` endpoints.

Для локальной учебной работы HTTP Basic проще токен-авторизации и не требует отдельного хранения токена на клиенте. В реальной эксплуатации такой способ следует использовать только поверх HTTPS.

## 4. API

### Аутентификация

- `POST /auth/login` — проверка логина и пароля;
- `GET /auth/me` — текущий пользователь по HTTP Basic.

Все `/api/*` требуют корректные учетные данные HTTP Basic. `GET /health` остается публичным для health-check.

### Служебный

- `GET /health`

### Справочники

- `GET/POST /api/boats`
- `GET/POST /api/crews`
- `GET/POST /api/fish-types`

### Операционные сущности

- `GET/POST /api/trips`
- `GET/POST /api/catches`

### Отчеты

- `GET /api/reports/catch-by-trip`
- `GET /api/reports/catch-by-period?date_from=2026-09-01&date_to=2026-09-30`

Полное описание — в `docs/API.md`.

## 5. Главное бизнес-правило

Для одного рейса:

```text
SUM(catches.weight_kg) <= boats.capacity_kg
```

Если новая запись нарушает правило, API отвечает `422`.

## 6. Проверка требований ТЗ

```bash
make verify
make container-check
```

Матрица соответствия «требование → реализация → проверка» находится в приложении А файла `docs/TECHNICAL_SPECIFICATION.md`.

## 7. Git-процесс

Каждая новая функция выполняется по цепочке:

```text
задача → feature-ветка → несколько коммитов → локальная проверка → push → PR/MR → review → merge → tag
```

Пример:

```bash
git switch main
git pull --rebase
git switch -c feature/catch-capacity-rule
make verify
git add .
git commit -m "feat: validate catch capacity"
git push -u origin feature/catch-capacity-rule
```

После ревью выполняется merge в `main`.

## 8. Конфликт слияния

```bash
git switch main
git switch -c conflict-demo
# изменить одну строку README.md и сделать commit
# в main изменить ту же строку и сделать commit
git switch conflict-demo
git merge main
```

После возникновения конфликта исправить файл и:

```bash
git add README.md
git commit -m "chore: resolve merge conflict"
```

## 9. Версия

```bash
git tag -a v0.1.0 -m "ЛР1: первая минимально рабочая версия"
git push origin v0.1.0
```

## 10. Что не должно попасть в Git

`.env`, `.venv/`, кэши Python, `backup.sql`, локальные файлы IDE и другие служебные файлы.

Проверка:

```bash
git ls-files .env
```

Команда не должна выводить `.env`.

## 11. Команды Makefile

- `make setup`
- `make run`
- `make test`
- `make quality`
- `make migrate`
- `make backup`
- `make restore`
- `make verify`
- `make up`
- `make down`
- `make container-check`
