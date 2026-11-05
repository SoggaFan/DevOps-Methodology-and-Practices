# Лабораторная работа №4 — контейнеризация и проверка окружения

## 1. Обычный запуск на Linux VM

Для защиты используйте виртуальную машину Linux с Docker Engine и Docker Compose v2. Команды ниже выполняются из корня репозитория.

Первое создание файла настроек:

```bash
cp .env.example .env
chmod 600 .env
```

Если `.env` уже существует, **не перезаписывайте его**. Добавьте в него `POSTGRES_APP_PASSWORD` — отдельный пароль роли приложения `fishing_app`. Пароли администратора (`POSTGRES_PASSWORD`) и приложения должны быть разными. Не коммитьте `.env`.

Сначала проверьте конфигурацию до первого запуска или пересоздания окружения:

```bash
make container-check
make up
make db-bootstrap
make migrate
make container-check
```

До запуска Compose `make container-check` выполняет статическую проверку политики. Если контейнеры уже существуют, команда также требует успешных runtime-проверок. После запуска повторная команда подтверждает состояние фактических контейнеров.

`db-bootstrap` можно безопасно повторять. Он нужен в том числе для старого уже созданного volume: сценарии `/docker-entrypoint-initdb.d` автоматически запускаются только при первоначальной инициализации пустого volume. `migrate` повторно применяет идемпотентную SQL-схему/начальные данные и права приложения.

Ожидаемые адреса в обычном режиме:

- API/Swagger: `http://127.0.0.1:8000/docs`;
- health endpoint: `http://127.0.0.1:8000/health`.

Порт API опубликован только на loopback хоста. Порт PostgreSQL (`5432`) на хост не опубликован: сервис БД доступен контейнеру API внутри закрытой сети Compose.

## 2. Что реализовано и как это проверяется

| Пункт задания | Реализация | Проверка |
|---|---|---|
| 1. Dockerfile и `.dockerignore` | `Dockerfile`, `.dockerignore` | `docker compose build api`, анализ build context |
| 2. Воспроизводимая сборка | Базовый Python image закреплён digest; зависимости приложения закреплены версиями в `requirements.txt`; образы Compose используют версии, не `latest` | `docker compose build --no-cache api`; `docker image inspect fishing-firm-api:0.4.0` |
| 3. Non-root | В образе пользователь UID/GID `10001:10001`; capabilities сброшены | `docker compose exec api id -u` должно вывести UID не `0` |
| 4. Переменные окружения | `DATABASE_URL`, `POSTGRES_*`, `APP_PORT`; секреты не копируются в образ | `docker compose config`; проверить `.env` и `docker inspect` контейнера, не публикуя пароль |
| 5. Graceful shutdown | exec-form `CMD`, `STOPSIGNAL SIGTERM`, Uvicorn graceful timeout, `stop_grace_period` | `make container-persistence-check` |
| 6. Compose приложения и БД | `docker-compose.yml` | `docker compose config --quiet` |
| 7. Сеть, volume, healthcheck, порядок запуска | внутренняя сеть `backend`, named volume `postgres_data`, `depends_on: service_healthy`, healthcheck у БД и API | `docker compose ps`; `make container-check` |
| 8. Нет лишнего порта БД | у `db` отсутствует `ports` | `make container-check`; `docker compose ps` |
| 9. Сохранность после пересоздания | named volume с фиксированным именем; автоматический lifecycle-тест создаёт временную запись, пересоздаёт контейнеры/образ и проверяет запись | `make container-persistence-check` (только на тестовой VM; перезапускает БД и API) |
| 10. Миграция/backup/restore в контейнерах | `make migrate`, `make backup`, `make restore`, `make restore-new-volume` | см. раздел 4 ниже |
| 11. Ресурсы | API: 1 CPU, 256 MiB RAM, 128 PID; PostgreSQL: 1 CPU, 512 MiB RAM, 256 PID; Nginx-профиль: 0.5 CPU, 64 MiB RAM, 64 PID | `docker inspect` или `make container-check` |
| 12. `make container-check` | `scripts/container_check.py`: статические policy checks и runtime smoke checks | `make container-check` после запуска сервисов |
| 13. Запрещённые конфигурации | нет `latest`; образ API запускается не от root; секреты исключены из build context; healthchecks обязательны; DB ports закрыты | `make container-check` |
| 14. Gate перед изменениями среды | перед первым запуском/пересозданием — успешный `make container-check`; `make scale-up` запускает gate как prerequisite | после запуска повторить `make container-check`; lifecycle-проверка тоже запускает gate перед изменениями |

## 3. Безопасная работа с данными

`postgres_data` — отдельный именованный volume. Обычная команда `make down` удаляет контейнеры и сеть, **но не удаляет volume**.

Не выполняйте `docker compose down -v` для основной базы: флаг `-v` удаляет том и уничтожает сохранённые данные.

Для проверки пересоздания контейнеров:

```bash
make container-check
make container-persistence-check
```

Приёмочный сценарий интерактивный: его нужно запускать только на учебной VM. Он на короткое время пересоздаёт контейнеры `db` и `api`, проверяет сохранность временной записи и корректную остановку API по SIGTERM, затем удаляет временную запись и снова запускает API.

## 4. Миграции, резервная копия и восстановление

Применить текущую SQL-схему и начальные данные:

```bash
make db-bootstrap
make migrate
```

Создать архив PostgreSQL в custom формате:

```bash
make backup
```

По умолчанию создаётся `backups/fishing.dump`. Каталог и дампы исключены из Git.

Для восстановления в **текущую БД** нужна явная команда-подтверждение, поскольку она удаляет содержимое схемы `public` перед восстановлением:

```bash
make restore RESTORE_CONFIRM=YES
```

Без `RESTORE_CONFIRM=YES` команда откажется выполнять разрушительную операцию.

Для демонстрации восстановления в новый volume (рекомендуется для защиты):

```bash
make backup
make restore-new-volume
```

Целевая база запускается в отдельном Compose-проекте `fishing-restore` с новым volume `fishing-restore_restore_data`; она остаётся запущенной для проверки. Чтобы использовать другое имя, укажите `make restore-new-volume RESTORE_PROJECT=fishing-restore-2`. Скрипт откажется перезаписывать существующий restore-volume.

## 5. Дополнительное задание: Nginx, масштабирование и отказоустойчивость

Дополнительная конфигурация вынесена в `docker-compose.scale.yml` и `nginx/nginx.conf`. В этом режиме доступны два контейнера API (`api1`, `api2`) без опубликованных host-портов; наружу опубликован только Nginx на `127.0.0.1:8080`. Приложение добавляет `X-Instance-ID` к каждому HTTP-ответу.

Запуск:

```bash
make scale-up
make scale-check
```

`scale-check` делает конкурентные запросы, подтверждает ответы от обоих экземпляров, останавливает `api1` и проверяет, что запросы продолжают обслуживаться `api2`, затем восстанавливает `api1`.

Возврат к обычному одиночному режиму:

```bash
make scale-down
```

Балансировка использует `least_conn`, исключение неработающего узла через `max_fails`/`fail_timeout`, повтор запроса через `proxy_next_upstream` и ограничение частоты через `limit_req`.

### Что может мешать горизонтальному масштабированию

Сейчас приложение использует общую PostgreSQL и не сохраняет пользовательское состояние в локальной файловой системе, поэтому два экземпляра могут работать за одним балансировщиком. Ограничения при росте нагрузки — общий пул соединений к БД, возможная конкуренция за записи и необходимость согласованно выполнять будущие изменения схемы. Для масштабирования потребуется оценить размеры пулов и лимиты подключений, тайм-ауты и индексы БД, а также не добавлять локальные файлы/сессии, от которых зависит состояние клиента.

## 6. Диагностика

```bash
docker compose ps
docker compose logs --tail=100 db api
docker compose exec api id -u
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM boats;"'
make container-check
```

Если используется старый volume и API остаётся unhealthy после изменения `.env`, не удаляйте volume. Выполните `make db-bootstrap` и `make migrate`, затем повторите `make container-check`.
