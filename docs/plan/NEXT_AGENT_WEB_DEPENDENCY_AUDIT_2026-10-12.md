# Передача следующему агенту — аудит зависимостей web, 2026-10-12

**Production-аудит зависимостей чист. Ветка локальная: публикация и CI ждут разрешения
владельца.** Этот документ — актуальный вход. [Готовый prompt](NEXT_AGENT_WEB_DEPENDENCY_AUDIT_PROMPT_2026-10-12.md).
Состояние Package I описывает [handoff приёмки](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md); оно не изменилось.

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`.
- Ветка: `codex/web-dependency-audit`, локальная, не опубликована. Основа — `4630ca3`, опубликованная
  вершина `codex/package-i4-review-corrections`; та ветка не менялась.
- Коммиты поверх основы: обновление зависимостей (два файла) и документы. Точные SHA
  читать из `git log`: коммит не может записать собственный.
- [Запись о срезе](evidence/2026-10-12-web-dependency-audit/VALIDATION.md), [её проверки](evidence/2026-10-12-web-dependency-audit/CHECKS.json).

Сначала status, branch, HEAD, log, worktrees и remotes. `git rev-parse HEAD:<путь>` для
двух файлов из `changed_sources` в CHECKS.json должен совпасть с `git_blob_oid`. Один
исполнитель на checkout и на кластер PostgreSQL.

Другие копии сохранены, их не трогать и не синхронизировать автоматически:
acceptance `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i` на 0356eb5; review2
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking` на 490652b;
reviewer `C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking`
на 490652b со своими dirty-копиями девяти файлов; primary owner
`C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` на 2f16380 (dirty).

## Что выполнено

- `next` 16.3.7 → 16.3.8, `eslint-config-next` 16.3.7 → 16.3.8, `source-map-js`
  1.2.1 → 1.2.2. В lock-файле изменились 13 пакетов, только из этих семейств.
- Production-аудит (`npm audit --omit=dev`): FAIL, 2 high → **PASS, 0 находок**.
- Проверки обновлённого дерева: full local **PASS: 1531 passed, 4 skipped in 1023.50s (0:17:03)**; Ruff, format и mypy PASS
  на 265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS.
- Код приложения, тесты, миграции и API не менялись. WORK-01 и CORE-04 остаются
  `technically_verified`.

## Основание

2026-10-12 исполнитель рекомендовал начать с аудита зависимостей; владелец ответил:
«continue». Исполнитель понял это как согласие начать этот срез и сказал об этом в
начале работы. Отменить обновление можно одним `git revert` коммита с двумя файлами и
`npm ci --ignore-scripts` в `web`.

## Что не сделано и пределы

- Публикация и CI: не выполнялись. Сборку production-образа и пакеты `@next/swc` для
  Linux проверит только CI.
- Полный `npm audit`: FAIL, 5 high — одна цепочка `braces` только в инструментах
  разработки. Исправленной версии `braces` не существует; понижать `eslint-config-next`
  ради аудита нельзя. Подробности — в записи о срезе.
- PR и merge: не выполнялись. Стек неслитых веток растёт; порядок слияния — решение
  владельца.
- Текст логов CI прежних запусков не читался: без входа в GitHub он недоступен.
- Не проверено: настоящий screen reader, HawkScan, нагрузка, развёртывание и
  production; ситуации экранов «Персонала» из раздела «NOT TESTED» второго обзора.
- Пределы приёмки Package I и открытые вопросы пакета H перечислены в
  [handoff приёмки](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md).

## Возможные следующие срезы

Выбор за владельцем; каждый — отдельный срез со своей веткой и проверками.

1. Публикация этой ветки и чтение CI её вершины — по прямому разрешению владельца.
2. План слияния стека веток и PR.
3. Следующий пакет этапа 2 по master plan.
4. Проверка экранов «Персонала» в ситуациях, перечисленных как непроверенные.

## Как запускать проверки

Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/web-dependency-audit-20261012-4630ca3`.
`runner.py <имя-фазы> <static|full|focused> [файлы pytest]` создаёт новый каталог фазы и
отказывается от существующего. Фаза `static` записывает оба аудита и не останавливается
на них. Фазы с базой данных поднимают свой новый кластер на свободном loopback-порту с
`max_connections=400`; пароль создаётся в памяти и вырезается из логов; останавливается
только свой кластер после сверки `postmaster.pid`. Все кластеры этого прогона
остановлены. После изменения зависимостей web: `npm ci --ignore-scripts`, затем фаза
`static`, затем `full`. После пересборки `web/out` нельзя менять во время full.

Python 3.14.6: `C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe`
(с `PYTHONPATH` на `api/src` и `api` код импортируется из проверяемой копии).
Node 24.18.0 и npm 11.16.0: `C:/Program Files/nodejs`. PostgreSQL 18.6:
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin`.
CI: задание `api` занимает около 12 минут на быстрой машине GitHub и около 20 на
медленной; лимит задания — 30 минут.

## Границы

Не выполнять push, PR, merge, rebase, amend, reset, clean, force-push, изменение
готовности, CodeRabbit, Azure, production migrations, deploy, provider, funds и
credential actions без отдельного прямого разрешения владельца. Разрешение на
публикацию от 2026-10-12 относится только к ветке `codex/package-i4-review-corrections`.
Миграции 0001–0035 неизменяемы. Статусы `pilot_accepted` и `production_approved`
требуют отдельных решений владельца. KA Nails — отдельный проект, не требование
этой платформы.
