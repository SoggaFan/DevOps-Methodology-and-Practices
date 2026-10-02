# ЛР2 — Развертывание приложения в Linux-среде

## Схема

| Узел | Адрес | Назначение |
|---|---|---|
| app-server | 192.168.56.10 | FastAPI + systemd |
| db-server | 192.168.56.11 | PostgreSQL |
| client/admin | 192.168.56.1 или адрес вашего ПК | проверка API и SSH |

Адреса являются примером. Перед настройкой заменить их на адреса своей лабораторной сети.

## 1. Две Linux-машины без GUI

Рекомендуется использовать серверную установку Debian-like OS без графической оболочки. На каждой ВМ должны быть доступны SSH и пакетный менеджер.

Проверка:

```bash
cat /etc/os-release
uname -a
```

## 2. Постоянные адреса и SSH-ключи

Проверить интерфейсы:

```bash
ip -br a
ip route
```

Задать постоянные адреса в используемом менеджере сети. В отчете зафиксировать:

- имя интерфейса;
- IP app-server;
- IP db-server;
- маску/префикс;
- шлюз, если он используется.

На Windows создать ключ:

```powershell
ssh-keygen -t ed25519 -C "lr2-admin"
```

Добавить открытый ключ на сервер:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh devops@192.168.56.10 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

Повторить для db-server.

## 3. Администратор и приложение

На серверах создать отдельного администратора:

```bash
sudo adduser devops
sudo usermod -aG sudo devops
```

На app-server создать отдельного системного пользователя приложения:

```bash
sudo useradd --system --create-home --home-dir /opt/fishing-firm --shell /usr/sbin/nologin fishing
```

Проверка, что приложение не запускается от root:

```bash
ps -eo user,pid,cmd | grep '[u]vicorn'
```

## 4. Запрет root по SSH

Проверить `/etc/ssh/sshd_config`:

```text
PermitRootLogin no
PubkeyAuthentication yes
```

После проверки ключевого входа:

```bash
sudo sshd -t
sudo systemctl restart ssh
```

Проверить новым SSH-сеансом до закрытия текущего.

## 5. Развертывание приложения без контейнеров

На app-server установить Python и подготовить приложение:

```bash
sudo ./deploy/app/install.sh
```

При ручном варианте:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl
sudo mkdir -p /opt/fishing-firm
sudo chown root:fishing /opt/fishing-firm
python3 -m venv /opt/fishing-firm/.venv
sudo /opt/fishing-firm/.venv/bin/pip install -r /opt/fishing-firm/requirements.txt
```

## 6. PostgreSQL и минимальные права

На db-server:

```bash
sudo ./deploy/db/setup-db.sh
```

Принцип:

- `postgres` используется для администрирования и создания схемы;
- `fishing_app` используется приложением;
- `fishing_app` не получает `CREATE`, `DROP`, `SUPERUSER` и другие административные права;
- для `SERIAL` предоставляется `USAGE, SELECT` на последовательности.

Проверить права:

```bash
sudo -u postgres psql -d fishing
```

```sql
\du
\dp
\ddp
```

Подключение приложения должно использовать `fishing_app`.

## 7. Сетевой доступ PostgreSQL

В `postgresql.conf` разрешить прослушивание лабораторного интерфейса, например:

```text
listen_addresses = '192.168.56.11'
```

В `pg_hba.conf` добавить доступ только от app-server:

```text
host    fishing    fishing_app    192.168.56.10/32    scram-sha-256
```

После изменений:

```bash
sudo systemctl restart postgresql
sudo systemctl status postgresql
```

## 8. Конфигурация отдельно от исходников

На app-server:

```bash
sudo install -d -o root -g fishing -m 0750 /etc/fishing-firm
sudo cp deploy/app/fishing-firm.env.example /etc/fishing-firm/fishing-firm.env
sudo chown root:fishing /etc/fishing-firm/fishing-firm.env
sudo chmod 640 /etc/fishing-firm/fishing-firm.env
sudo nano /etc/fishing-firm/fishing-firm.env
```

Указать реальный адрес DB-сервера:

```text
DATABASE_URL=postgresql+psycopg://fishing_app:REAL_PASSWORD@192.168.56.11:5432/fishing
```

Этот файл не добавлять в Git.

## 9. systemd

Установить unit:

```bash
sudo install -m 0644 deploy/app/fishing-firm.service /etc/systemd/system/fishing-firm.service
sudo systemctl daemon-reload
sudo systemctl enable --now fishing-firm
```

Проверки:

```bash
systemctl status fishing-firm
systemctl is-enabled fishing-firm
systemctl is-active fishing-firm
```

Перезапуск и остановка:

```bash
sudo systemctl restart fishing-firm
sudo systemctl stop fishing-firm
sudo systemctl start fishing-firm
```

## 10. Автоперезапуск

В unit используется:

```text
Restart=on-failure
RestartSec=5
```

Проверка:

```bash
systemctl show fishing-firm -p Restart -p RestartUSec
journalctl -u fishing-firm -n 50 --no-pager
```

Для демонстрации можно временно отправить процессу сигнал:

```bash
sudo systemctl kill fishing-firm --kill-who=main --signal=SIGKILL
sleep 7
systemctl status fishing-firm
```

Сервис должен автоматически запуститься снова.

## 11. Firewall

На app-server:

```bash
sudo ./deploy/firewall/app-ufw.sh
```

Разрешается:

- TCP/22 — только из административной сети;
- TCP/8000 — от клиентов лабораторной сети.

На db-server:

```bash
sudo ./deploy/firewall/db-ufw.sh
```

Разрешается:

- TCP/22 — только из административной сети;
- TCP/5432 — только от `192.168.56.10`.

Проверка:

```bash
sudo ufw status numbered
sudo ss -lntp
```

## 12. Не контейнерный запуск

Проверить процесс:

```bash
ps -ef | grep '[u]vicorn'
```

Ожидается пользователь `fishing`, а не `root`.

Проверить порт:

```bash
sudo ss -lntp | grep ':8000'
```

Проверить журнал:

```bash
journalctl -u fishing-firm -n 100 --no-pager
journalctl -u fishing-firm -f
```

## 13. Проверка БД с app-server

```bash
curl http://192.168.56.10:8000/health
```

При работающей БД ожидается HTTP 200.

С app-server можно проверить порт DB:

```bash
nc -vz 192.168.56.11 5432
```

С постороннего узла эта проверка должна завершиться недоступностью.

## 14. Проверка отказа БД

На db-server:

```bash
sudo systemctl stop postgresql
```

На app-server:

```bash
systemctl status fishing-firm
curl -i http://192.168.56.10:8000/health
journalctl -u fishing-firm -n 30 --no-pager
```

Приложение как process может оставаться активным, но `/health` должен вернуть HTTP 503 с `database unavailable`.

После:

```bash
sudo systemctl start postgresql
curl http://192.168.56.10:8000/health
```

ожидается HTTP 200.

## 15. Перезагрузка двух машин

На db-server:

```bash
sudo reboot
```

После возврата:

```bash
systemctl is-active postgresql
```

На app-server:

```bash
sudo reboot
```

После возврата:

```bash
systemctl is-enabled fishing-firm
systemctl is-active fishing-firm
curl http://192.168.56.10:8000/health
```

## 16. Изменение параметра службы и восстановление

Например, временно изменить `RestartSec=5` на `RestartSec=10`:

```bash
sudo systemctl edit fishing-firm
```

Внести:

```text
[Service]
RestartSec=10
```

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl restart fishing-firm
systemctl show fishing-firm -p RestartUSec
```

После демонстрации удалить override:

```bash
sudo systemctl revert fishing-firm
sudo systemctl daemon-reload
sudo systemctl restart fishing-firm
systemctl show fishing-firm -p RestartUSec
```

## 17. Что показать на защите

1. `systemctl status fishing-firm` и `systemctl is-enabled fishing-firm`.
2. Перезагрузку app-server и повторную проверку автоматического запуска.
3. `systemctl stop postgresql` + `/health` → 503 + `journalctl`.
4. `ps -ef`, `ss -lntp`, `journalctl`.
5. Временный `RestartSec=10` и возврат к `5`.
6. Firewall и список открытых портов.
7. Подключение к БД с app-server и отказ подключения с постороннего узла.
8. `ls -l` для проверки прав на `/opt/fishing-firm` и `/etc/fishing-firm/fishing-firm.env`.
9. `git status` и `git ls-files .env` — секреты не должны быть в репозитории.
