# Лабораторная работа №6 — Continuous Delivery и проверка работающего релиза

## 1. Архитектура выпуска

Для предэксплуатационной среды используется отдельный Compose-проект `fishing-firm-preprod`:

- отдельный API-контейнер получает только опубликованный образ из Docker Hub;
- отдельный PostgreSQL-контейнер использует собственный named volume `fishing-firm-preprod-postgres-data`;
- настройки и пароли находятся в `/opt/fishing-firm-preprod/.env` на Linux-сервере, а не в образе и не в Git;
- API доступен только на loopback-адресе сервера, порт по умолчанию `18000`;
- `/health` проверяет API и БД, `/version` сообщает тег и commit SHA;
- после публикации образа успешный CI запускает deploy job для `main`;
- ручной workflow позволяет развернуть заданный полный SHA-тег или вернуть предыдущий успешный релиз.

Схема потока:

```text
feature branch → PR → CI checks → merge to main
                                  ↓
                           Docker Hub :<commit-sha>
                                  ↓
                   GitHub Actions / SSH fishing-deploy
                                  ↓
                docker pull → preprod Compose → smoke checks
                                  ↓
               accepted release OR automatic rollback + failed job
```

На целевом сервере нет секции `build:` и нет Dockerfile в deploy Compose. Образ только скачивается из registry (`docker pull`); `docker compose up` вызывается с `--no-build --pull never`.

## 2. Что добавлено в проект

| Файл | Назначение |
|---|---|
| `deploy/preprod/compose.yml` | Изолированная pre-production среда, отдельная БД и volume |
| `deploy/preprod/.env.example` | Шаблон серверных настроек без действующих паролей |
| `deploy/preprod/host-setup.sh` | Создание пользователя `fishing-deploy`, SSH-доступа, sudo-ограничения и серверных файлов |
| `deploy/preprod/remote-release.sh` | Pull конкретного SHA, запуск, health/smoke-check и автоматический rollback |
| `deploy/preprod/release-smoke-check.py` | Проверка `/health`, `/version` и GET-сценариев веб-интерфейса |
| `.github/workflows/ci.yml` | Автоматический preprod deploy после успешной публикации образа из `main` |
| `.github/workflows/preprod-release.yml` | Ручное развертывание SHA-тега или rollback |
| `app/main.py` | Endpoint `GET /version` |
| `tests/test_api.py` | Тест endpoint версии |

## 3. Подготовка Linux-сервера

Требуется отдельная Ubuntu VM/сервер с Docker Engine и Docker Compose v2, доступом к Docker Hub и SSH-доступом с GitHub Actions runner. Сервер должен быть достижим по SSH из GitHub-hosted runner; firewall должен разрешать выбранный SSH-порт.

### 3.1. Создать отдельную SSH-учётную запись

На доверенном компьютере создать отдельную пару ключей для pipeline:

```bash
ssh-keygen -t ed25519 -f fishing-preprod-deploy -C "github-actions-preprod"
```

Скопировать **только публичный** файл `fishing-preprod-deploy.pub` на Linux-сервер (например, через `scp`). На Linux-сервере из корня клона репозитория выполнить установку, передав публичный ключ:

```bash
sudo ./deploy/preprod/host-setup.sh "$(cat fishing-preprod-deploy.pub)"
```

Скрипт создаёт пользователя `fishing-deploy`, каталог `/opt/fishing-firm-preprod`, копирует Compose/SQL/smoke-check файлы и устанавливает root-owned команду `/usr/local/sbin/fishing-preprod-release`. Пользователь `fishing-deploy` **не добавляется** в группу `docker`; через sudo ему разрешена только эта команда. При изменении серверных release-скриптов повторно запустить `host-setup.sh`; существующий `.env` скрипт не перезаписывает.

### 3.2. Настроить серверный `.env`

Открыть файл:

```bash
sudo nano /opt/fishing-firm-preprod/.env
```

Обязательно изменить (удобно сгенерировать значения командами `openssl rand -hex 32`, используя разный результат для каждого пароля):

- `POSTGRES_PASSWORD` — длинный пароль администратора БД;
- `POSTGRES_APP_PASSWORD` — другой длинный пароль пользователя приложения;
- `IMAGE_REPOSITORY` — `docker.io/<DockerHubUsername>/fishing-firm`.

`IMAGE_TAG`, `APP_VERSION` и `APP_COMMIT` при первом выпуске обновит release-скрипт. Файл должен принадлежать root и иметь права `600`:

```bash
sudo chown root:root /opt/fishing-firm-preprod/.env
sudo chmod 600 /opt/fishing-firm-preprod/.env
```

### 3.3. Дать серверу доступ на чтение Docker Hub

В Docker Hub создать отдельный Access Token с правом **Read** для нужного repository. На сервере выполнить вход именно для root Docker client, не помещая токен в командную историю:

```bash
read -rsp "Docker Hub read-only token: " DOCKERHUB_TOKEN; echo
printf '%s' "$DOCKERHUB_TOKEN" | sudo docker login --username '<DockerHubUsername>' --password-stdin
unset DOCKERHUB_TOKEN
```

Проверить, что команда завершилась `Login Succeeded`. Учетные данные будут сохранены в root Docker config; deploy-пользователю они не выдаются.

### 3.4. Добавить настройки GitHub Actions

В репозитории открыть **Settings → Environments** и создать окружение `preproduction`. При наличии такой возможности ограничить deployment branch веткой `main`; можно включить Required reviewers для ручного одобрения. В GitHub Free обязательное approval для приватного репозитория может быть недоступно — само ограничение workflow на `main` всё равно действует.

В Variables окружения `preproduction` добавить:

| Variable | Значение |
|---|---|
| `PREPROD_HOST` | DNS-имя или IP Linux-сервера |
| `PREPROD_PORT` | SSH-порт, обычно `22` |
| `PREPROD_USER` | `fishing-deploy` |

В Secrets окружения `preproduction` добавить:

| Secret | Значение |
|---|---|
| `PREPROD_SSH_KEY` | Содержимое приватного файла `fishing-preprod-deploy` |
| `PREPROD_KNOWN_HOSTS` | Проверенная строка host key для этого сервера из `known_hosts` |

В существующих repository Actions secrets должны быть настроены `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN` (Read & Write token), которые уже использует job `publish` ЛР5.

Host key нельзя слепо доверять результату `ssh-keyscan`: сверить fingerprint с администратором сервера, затем сохранить соответствующую строку `known_hosts` в `PREPROD_KNOWN_HOSTS`. При нестандартном SSH-порту запись обычно имеет вид `[host]:port ...`.

## 4. Автоматический выпуск

1. Разработать функцию в отдельной feature-ветке.
2. Выполнить локально `make verify` и проверки изменённого поведения.
3. Push и открыть PR в `main`; обязательные CI jobs должны пройти.
4. После merge push в `main` запускает существующие CI jobs. Job `publish-image` публикует Docker Hub image с полным `github.sha`.
5. Только после успешного `publish-image` job `deploy-preprod` подключается по SSH как `fishing-deploy` и выполняет:

```bash
sudo /usr/local/sbin/fishing-preprod-release deploy <40-character-commit-sha>
```

Для job tag берётся из `github.sha`; вводить его вручную для автоматического выпуска не нужно. Для просмотра preprod из браузера можно открыть SSH-туннель `ssh -L 18000:127.0.0.1:18000 fishing-deploy@<host>` и обратиться к `http://127.0.0.1:18000/` локально.

### Сквозной выпуск функции (задание 12)

Для этой работы сквозной функцией является определение версии работающего приложения через `/version` и проверка выпуска в pre-production. Пример рабочего цикла разработчика:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/lr6-continuous-delivery
make verify
# После локальной проверки оформить commit и отправить ветку.
git add app/main.py tests/test_api.py deploy/preprod .github docs/LR6_CONTINUOUS_DELIVERY.md README.md docs/API.md .gitignore
git commit -m "feat: add pre-production continuous delivery"
git push -u origin feature/lr6-continuous-delivery
```

Далее открыть PR в `main`, дождаться обязательных CI jobs и review, выполнить merge. После публикации Docker Hub image с SHA запускается автоматический deploy, затем post-deploy проверки. В GitHub Actions видны все этапы и итоговая запись deployment environment.

## 5. Проверки после развертывания

Release-скрипт принимает выпуск только после всех проверок:

1. Docker containers `db` и `api` находятся в состоянии `healthy`.
2. `GET /health` возвращает HTTP 200 и `status=ok` (включая запрос к БД).
3. `GET /version` возвращает ожидаемые `version` и `commit`, совпадающие с SHA-тегом выпуска.
4. `GET /api/boats`, `/api/crews` и `/api/fish-types` возвращают HTTP 200 и непустые JSON-массивы; `/api/trips` возвращает JSON-массив; `/api/reports/catch-by-period` возвращает все ожидаемые поля отчёта. Это read-only запросы, которые веб-интерфейс выполняет при загрузке данных и отчёта.

Если любая проверка после замены API не прошла, скрипт восстанавливает предыдущий `.env` и контейнер с предыдущим образом. Даже когда rollback удался, команда возвращает ненулевой код: новый выпуск считается неуспешным и GitHub Actions job остаётся красным.

При ошибке pull (неверный тег, отсутствующий образ или недоступный registry) текущий `.env` и работающий API не заменяются: образ скачивается до переключения конфигурации.

## 6. Ручное развертывание и rollback

Открыть **Actions → Manual pre-production release → Run workflow**. Workflow разрешает операции только при запуске с `main`.

- `operation = deploy`: указать `image_tag` — полный 40-символьный commit SHA, который уже опубликован в Docker Hub.
- `operation = rollback`: оставить `image_tag` пустым, чтобы развернуть предыдущий успешный тег, сохранённый на сервере. При необходимости можно задать полный SHA явно.

Workflow и серверный `flock` используют одну группу блокировки. Поэтому автоматический и ручной выпуск не выполняются одновременно; конфликтующий вызов ждёт на уровне GitHub concurrency либо получает отказ от серверного lock.

## 7. Сценарии демонстрации отказов на защите

| Сценарий | Ожидаемое поведение |
|---|---|
| Неверный SHA-тег | `docker pull` завершается ошибкой; текущий релиз остаётся запущенным |
| Отсутствующая переменная | `docker compose config --quiet` завершается ошибкой до замены API |
| Неуспешный healthcheck | выпуск не принимается; выполняется попытка автоматического возврата предыдущего SHA |
| API запущен, но пользовательский сценарий неисправен | smoke-check `/api/boats`, `/api/crews` или `/api/fish-types` падает; выполняется rollback |
| Docker Hub недоступен | pull не проходит; активный контейнер не заменяется |
| Ручной возврат | workflow `rollback` разворачивает previous tag и снова проверяет release |

Для демонстрации не портить `main` и не менять действующий образ. Использовать отдельный опубликованный тестовый тег/ветку или заведомо неверный SHA; после теста вернуть стабильный SHA через ручной workflow.

## 8. Ограничения и операции, выполняемые вручную

Изменения в репозитории подготавливают CI/CD-механику, но не создают удалённый сервер, GitHub Variables/Secrets, Docker Hub token или сетевые правила автоматически. Для первого фактического выпуска необходимо выполнить разделы 3.1–3.4. Без них deploy job корректно завершится ошибкой конфигурации, а не выдаст ложный статус успешного релиза.

Preprod использует отдельный volume. Не запускать `docker compose down -v` и не удалять `fishing-firm-preprod-postgres-data` во время демонстрации rollback.
