# Настройка удалённого Git-репозитория

В архиве сохранена вся локальная Git-история лабораторной. Перед защитой `origin` необходимо привязать к реальному GitHub или GitLab-репозиторию преподавателя/студента. Локальный путь `../fishing-firm-remote.git`, который использовался в учебной заготовке, не является заменой удалённому хостингу.

## GitHub

```bash
git remote remove origin
git remote add origin https://github.com/<USERNAME>/<REPOSITORY>.git
git push -u origin main
git push origin --tags
git push origin feature/catch-period-report
```

Затем открыть ветку `feature/catch-period-report` и создать Pull Request в `main`.

## GitLab

```bash
git remote remove origin
git remote add origin https://gitlab.com/<USERNAME>/<REPOSITORY>.git
git push -u origin main
git push origin --tags
git push origin feature/catch-period-report
```

Затем создать Merge Request `feature/catch-period-report → main`.

## Контрольные проверки перед push

```bash
git status
git remote -v
git branch -a
git log --oneline --decorate --graph --all -20
git tag -n
make verify
git ls-files .env
```

Команда `git ls-files .env` не должна выводить `.env`.

> Важно: URL с `<USERNAME>` и `<REPOSITORY>` является шаблоном. Его нужно заменить на реальный удалённый репозиторий перед защитой.
