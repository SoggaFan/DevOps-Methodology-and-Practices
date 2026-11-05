# ЛР2 — чек-лист требований

| № | Требование | Доказательство |
|---|---|---|
| 1 | 2 Linux-машины без GUI | `/etc/os-release`, схема сети |
| 2 | постоянная адресация + SSH keys | `ip -br a`, вход по ключу |
| 3 | запрет root + отдельные пользователи | `sshd_config`, `id devops`, `id fishing` |
| 4 | права на файлы | `ls -la`, `namei -l`, `chmod/chown` |
| 5 | Python + PostgreSQL | `python3 --version`, `psql --version` |
| 6 | отдельный DB user с минимумом прав | `\du`, `\dp`, попытка DDL под `fishing_app` |
| 7 | без контейнеров | процесс uvicorn на app-server |
| 8 | systemd | `systemctl status/enable/start/stop/restart` |
| 9 | autorestart | `Restart=on-failure`, аварийное завершение процесса |
| 10 | firewall | `ufw status`, `ss -lntp`, проверка 5432 |
| 11 | настройки отдельно от кода | `/etc/fishing-firm/fishing-firm.env` |
| 12 | повторяемое развертывание | `deploy/app/install.sh`, `deploy/db/setup-db.sh`, firewall scripts |
| 13 | требования безопасности | не-root process, закрытые порты, `.env` не в Git |
