# Передача следующему агенту — Package I принят технически, 2026-10-12

**WORK-01 и CORE-04 записаны как `technically_verified`. Модуль `workforce` включаемый.
Пилота и разрешения на production нет.**
Этот документ — актуальный вход. [Готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md).

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`.
- Ветка: `codex/package-i4-review-corrections`, опубликована.
- Коммиты поверх `490652b`: `2bca502` — исправления второго обзора; `3b9734c` — проверка
  сообщения о конфликте в двух browser-спеках; `b7953a4`, `678a21e` — документы;
  `f41f9a8` — лимит времени задания CI (проверенный код приёмки); `1b925f1` — запись
  CORE-04; `75f2b9b` — приёмка WORK-01 с тестами и документами. HEAD — следующий
  коммит, только запись результата CI.
- [Запись о приёмке](evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md), [её проверки](evidence/2026-10-12-work-01-acceptance/CHECKS.json),
  [независимая проверка](evidence/2026-10-12-work-01-acceptance/INDEPENDENT_CHECK.md).
- Предыдущий срез: [разбор сбоя, обзоры и публикация](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md),
  [публикация и CI](evidence/2026-10-12-i4-review-corrections/PUBLICATION_CHECKS.json).

Сначала status, branch, HEAD, log, worktrees и remotes. `git rev-parse HEAD:<путь>`
для семи файлов из `changed_sources` в CHECKS.json записи о приёмке должен совпасть с
`git_blob_oid`. Один исполнитель на checkout и на кластер PostgreSQL.

Другие копии сохранены, их не трогать и не синхронизировать автоматически:
acceptance `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i` на 0356eb5; review2
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking` на 490652b;
reviewer `C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking`
на 490652b со своими dirty-копиями девяти файлов; primary owner
`C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` на 2f16380 (dirty).

## Что выполнено

- Исправления второго обзора, правка двух browser-спеков, независимые обзоры,
  публикация и CI: матрица I-01–I-12 — PASS на коде `f41f9a8`.
- Приёмка: WORK-01 — `technically_verified`; готовность модуля `workforce` выводится
  из WORK-01; ADR-0025 — Accepted as implemented. Компания получает модуль, только
  опубликовав конфигурацию с ним; без публикации запись отклоняется с
  `MODULE_DISABLED`, при отозванной приёмке — с `MODULE_NOT_READY`.
- CORE-04 — `technically_verified` отдельным коммитом `1b925f1` по записи пакета F и
  акту этапа 1; поведение системы от этой записи не меняется.
- Тесты включают модуль настоящей публикацией, без подмены готовности.
- Проверки дерева приёмки: full local **PASS: 1531 passed, 4 skipped in 972.96s (0:16:12)**; Ruff, format и mypy PASS на
  265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS; независимая
  проверка изменения PASS, её замечания учтены.
- CI коммита приёмки: **PASS**, [run 38236481277](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38236481277) на `75f2b9b`: задание 1037 с, pytest 899 с; текст логов не читался.

## Решение о приёмке

2026-10-12 владелец написал: «Делай, как считаешь нужным. Я доверяю тебе.
Проанализируй и делай выбор, как ты считаешь нужным.» Исполнитель довёл матрицу до
PASS и предложил выполнить приёмку по слову владельца. Владелец ответил: «Continue».
Исполнитель понял это как согласие и сказал об этом в начале работы. Отменить
каждое решение можно одним `git revert` своего коммита.

## Что не сделано и пределы

- PR и merge: не выполнялись. Стек неслитых веток растёт; порядок слияния — решение
  владельца.
- Production npm audit: FAIL, 2 high (next, source-map-js). Это препятствие для
  допуска к production всей платформы; remediation — отдельный срез.
- Текст логов CI не читался: без входа в GitHub он недоступен.
- Не проверено: настоящий screen reader, HawkScan, нагрузка, развёртывание и
  production; ситуации экранов из раздела «NOT TESTED» второго обзора; компания,
  которая модуль не включала, в браузере не показана.
- В компании без включённого модуля участник может разобрать или отбросить неясную
  команду: до 20 отметок в сутки на человека. Данные смен не создаются.
- Вне пакета: зарплата, отпуска, уведомления, геолокация, срок хранения
  персональных данных, связь смен с доступностью записи клиентов.
- Пакет H: черновик PR для `codex/package-h-acceptance` и независимая проверка
  `ec39622` остаются открытыми.

## Возможные следующие срезы

Выбор за владельцем; каждый — отдельный срез со своей веткой и проверками.

1. Remediation аудита зависимостей (next, source-map-js) с полной перепроверкой web.
2. План слияния стека веток и PR.
3. Следующий пакет этапа 2 по master plan.
4. Проверка экранов «Персонала» в ситуациях, перечисленных как непроверенные.

## Как запускать проверки

Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/i4-counterparty-locator-20261012-490652b`.
`runner.py <имя-фазы> <probe|static|browser|full|focused|focused-red> [файлы pytest]`
создаёт новый каталог фазы и отказывается от существующего. Фазы с базой данных
поднимают свой новый кластер на свободном loopback-порту с `max_connections=400`;
пароль создаётся в памяти и вырезается из логов; останавливается только свой кластер
после сверки `postmaster.pid`. Все кластеры этого прогона остановлены. После
пересборки `web/out` нельзя менять во время full.

Python 3.14.6: `C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe`
(с `PYTHONPATH` на `api/src` и `api` код импортируется из проверяемой копии).
Node 24.18.0 и npm 11.16.0: `C:/Program Files/nodejs`. PostgreSQL 18.6:
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin`.
CI: задание `api` занимает около 12 минут на быстрой машине GitHub и около 20 на
медленной; лимит задания — 30 минут.

## Границы

Не выполнять PR, merge, rebase, amend, reset, clean, force-push, изменение
готовности, CodeRabbit, Azure, production migrations, deploy, provider, funds и
credential actions без отдельного прямого разрешения владельца. Разрешение на
публикацию от 2026-10-12 относится к ветке `codex/package-i4-review-corrections`.
Миграции 0001–0035 неизменяемы. Статусы `pilot_accepted` и `production_approved`
требуют отдельных решений владельца. KA Nails — отдельный проект, не требование
этой платформы.
