# Лабораторная работа №5 — Continuous Integration

## Выбранная платформа

GitHub Actions выполняет CI при `push` в ветки, при `pull_request` в `main`/`master` и вручную (`workflow_dispatch`). Docker Hub используется как реестр опубликованных образов.

## Состав pipeline

| Job | Назначение | Условие публикации |
|---|---|---|
| `style` | Ruff format + lint через `make quality` | обязательно |
| `tests` | pytest на отдельном PostgreSQL `fishing_test`, coverage/JUnit | обязательно |
| `migration` | SQL-схема, seed и grants в отдельной PostgreSQL БД | обязательно |
| `backup` | создание и проверка pg_dump, сохранение artifact | обязательно |
| `security` | Gitleaks, pip-audit, Bandit | обязательно |
| `build` | сборка Docker-образа с SHA-тегом и передача artifact | обязательно |
| `container-check` | Compose/Docker policy и Trivy-сканирование собранного образа | обязательно |
| `publish-image` | публикация в Docker Hub | только push в main/master и успешный `needs` |

Публикация зависит от всех обязательных jobs через `needs`. Для PR и feature-веток образ не публикуется. Для main/master SHA образа соответствует `github.sha`; дополнительно обновляется `latest`.

## Настройка GitHub и Docker Hub

1. Создать Docker Hub repository `fishing-firm`.
2. В Docker Hub создать Access Token с правом Read & Write.
3. В GitHub: **Settings → Secrets and variables → Actions → New repository secret**:
   - `DOCKERHUB_USERNAME` — имя пользователя Docker Hub;
   - `DOCKERHUB_TOKEN` — Access Token, не пароль аккаунта.
4. В `.github/CODEOWNERS` заменить `@SoggaFan @OakimPala` на реальный GitHub username или команду.
5. В GitHub: **Settings → Branches → Add branch protection rule** для `main` (и `master`, если используется):
   - Require a pull request before merging;
   - Require approvals: минимум 1;
   - Require review from Code Owners;
   - Require status checks to pass before merging: выбрать `style`, `tests`, `migration`, `backup`, `security`, `build`, `container-check`;
   - Require branches to be up to date before merging;
   - запретить force push и удаление ветки;
   - включить Do not allow bypassing the above settings, если доступно.
6. Не добавлять `publish-image` в список обязательных PR-checks: он выполняется только после merge в основную ветку.

Защита CODEOWNERS действует только при включённом требовании review от Code Owners в branch protection/ruleset. Сам файл CODEOWNERS без этого правила не блокирует merge.

## Локальные команды

Для локального окружения те же проверки запускаются командами:

```bash
make setup
make quality
make test
make security
make verify
```

Для проверки миграций и backup на отдельной тестовой БД (не production):

```bash
export MIGRATION_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/fishing_ci'
psql "$MIGRATION_DATABASE_URL" -c "CREATE ROLE fishing_app LOGIN PASSWORD 'local-ci-only';"
make migration-check
make backup-check
```

Тесты используют `TEST_DATABASE_URL` и требуют имя PostgreSQL базы с суффиксом `_test` или `_tests`. Если переменная не задана, локально применяется SQLite in-memory. CI всегда задаёт отдельную PostgreSQL `fishing_test`.

## Отчёты и кэш

- `reports/junit.xml`, `reports/coverage.xml` загружаются как artifact `test-reports`, в том числе при падении тестов (`if: always()`).
- `reports/ci-backup.dump` загружается как artifact `migration-backup`.
- `setup-python` кеширует pip по `requirements.txt` и `requirements-dev.txt`.

## Демонстрация на защите

### 1. Успешный pipeline

Создать feature-ветку, внести безошибочное изменение, выполнить `make verify`, push и открыть PR. Показать зелёные jobs и отчёты.

### 2. Ошибка теста

Временно изменить ожидаемое значение в одном тесте или внести дефект в обработчик. Push в feature-ветку. Job `tests` должен стать красным. `publish-image` не запускается: он ограничен push в main/master и зависит от всех jobs.

### 3. Ошибка миграции

В тестовой ветке временно добавить заведомо некорректный SQL в migration baseline. Job `migration` завершится с ошибкой из-за `ON_ERROR_STOP=1`. Исправить и повторить pipeline.

### 4. Обнаружение секрета

В тестовой ветке добавить фиктивный маркер, например `ghp_` с тестовой строкой, не настоящий токен. Gitleaks должен обнаружить секретоподобную строку и остановить job `security`. После демонстрации удалить строку и убедиться, что она не попала в основную ветку. Не использовать действующие ключи.

### 5. Проверка контейнера

Изменить Dockerfile так, чтобы сборка или Trivy-проверка завершилась ошибкой (или использовать уязвимую тестовую зависимость в отдельной ветке). Job `container-check` должен стать красным, публикация не выполняется.

### 6. Защита критических файлов

Открыть PR с изменением `tests/`, `Makefile`, `pyproject.toml` или `.github/workflows/ci.yml`. GitHub должен запросить review от CODEOWNER. Показать, что без одобрения merge запрещён. Повторить с попыткой удалить тест или отключить job: изменение также требует review владельца.

## Почему локальные и CI-проверки совпадают

Локальная разработка и CI используют одни и те же команды Makefile (`make verify`, `make quality`, `make test`, `make security`). Это уменьшает расхождения между окружениями и позволяет воспроизвести ошибку до push. Серверный CI остаётся независимым барьером: результат локального запуска нельзя подделать или использовать вместо проверки конкретного commit. CI получает чистое окружение и отдельную тестовую БД, а branch protection запрещает merge до успешного завершения обязательных jobs и review владельца.

## Важные ограничения

- Secrets `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN` нужно создать в настройках GitHub вручную.
- CODEOWNERS placeholder необходимо заменить, а branch protection включить в настройках репозитория.
- Workflow публикует только при push непосредственно в `main`/`master`. Обычно такой push происходит после PR merge; прямые push следует запретить branch protection.
- В учебной демонстрации используйте только фиктивные секреты и отдельные тестовые ветки/БД.
