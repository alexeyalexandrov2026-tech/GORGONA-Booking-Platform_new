# Передача следующему агенту — Package I corrections, 2026-10-12

**Исправления закоммичены локально. Полный suite PASS. Приёмка BLOCKED: нет CI
точного SHA, а публикация — решение владельца.**
Этот документ — актуальный вход. [Готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md).

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`.
- Ветка: `codex/package-i4-review-corrections` — локальная, не опубликована.
- Коммиты поверх `490652b`: `2bca502` — исправления второго обзора (R2-1, R2-2, R2-3,
  CR-1); `3b9734c` — проверка сообщения о конфликте в двух browser-спеках; затем
  коммит с документами (HEAD). После него рабочая копия чистая.
- [Разбор сбоя и свежие проверки](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md),
  [проверки с argv и хешами логов](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_CHECKS.json),
  [хеши исходников](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_SOURCE_PROOF.json),
  [авторский обзор](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_AUTHOR_REVIEW.md).
- Сохранённый первый FAIL: [VALIDATION.md](evidence/2026-10-12-i4-review-corrections/VALIDATION.md),
  [CHECKS.json](evidence/2026-10-12-i4-review-corrections/CHECKS.json), [SOURCE_PROOF.json](evidence/2026-10-12-i4-review-corrections/SOURCE_PROOF.json),
  [независимый обзор девяти файлов](evidence/2026-10-12-i4-review-corrections/INDEPENDENT_REVIEW.md). Эти файлы описывают
  состояние до коммитов и не менялись.

Сначала status, branch, HEAD, log, worktrees и remotes. Затем сверка:
`git rev-parse HEAD:<путь>` для одиннадцати файлов должен совпасть с `git_blob_oid`
в FOLLOWUP_SOURCE_PROOF.json. Один исполнитель на checkout и на кластер PostgreSQL.

Другие копии сохранены, их не трогать и не синхронизировать автоматически:
acceptance `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i` на 0356eb5; review2
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking` на 490652b;
reviewer `C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking`
на 490652b со своими dirty-копиями девяти файлов; primary owner
`C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` на 2f16380 (dirty).

## Что выполнено

- R2-1 stable home/privacy, R2-2 сериализованная квота отмен с savepoint, R2-3
  происхождение причины и CR-1 guard READ COMMITTED реализованы предыдущим
  исполнителем. Байты не менялись с ограниченного независимого обзора (девять
  совпадающих хешей) и закоммичены как есть.
- Сбой полного прогона (1 failed, 1525 passed, 4 skipped) разобран. В
  `counterparties.spec.ts:139` локатор `getByRole("alert")` совпадал и с пустым
  объявителем маршрута Next.js. Без сообщения проверка проходила впустую, с
  сообщением падала на двух совпадениях; исход решала гонка. Mobile падал следом,
  потому что модуль выключает desktop-сценарий. То же было в `documents.spec.ts:161`.
  Обе проверки теперь называют сообщение. Продуктовый код не менялся.
- Проверки на итоговых байтах: full **PASS: 1526 passed, 4 skipped in 997.19s (0:16:37)**; focused browser desktop/mobile
  PASS 3 из 3; Ruff, format и mypy PASS на 265 файлах; web typecheck, lint, format,
  102 unit и 23 страницы PASS. Исходники и `web/out` во время full не менялись.

## Что не сделано

- CI точного SHA: NOT TESTED. Ветка локальная; push — решение владельца. Старый CI
  для c6b8e34 эти исходники не проверял.
- Независимый обзор двух изменённых спеков: NOT DONE, есть только авторский.
- Production npm audit: FAIL, 2 high (next, source-map-js); remediation — отдельный scope.
- Контейнеры (3) и внешний tenant site (1): 4 skipped. Screen reader, HawkScan,
  load/soak, deployment/production: NOT TESTED. Browser-пробы review 2 (timezone ≠ UTC,
  company-wide) не повторялись.
- I-12: BLOCKED до CI точного SHA. Пакет не принят; WORK-01/CORE-04 planned.

## Следующая последовательность

1. Прочитать AGENTS.md, текущую часть CLOUD_CODE_HANDOFF.md, master, status, план
   пакета I, ADR-0025 и evidence; проверить Git, remote и CI до любых изменений.
2. Получить решение владельца о публикации ветки. Только после прямого разрешения:
   push, затем CI точного SHA с реальными логами. CI для c6b8e34 этой проверкой не считать.
3. По решению владельца — независимый обзор двух спеков или всего диапазона
   `490652b..HEAD` исполнителем, который их не писал.
4. После зелёного CI обновить запись о приёмке I-12. Готовность не повышать без
   отдельного решения владельца.
5. Если исходники снова меняются — свежие focused, static/web и полный serial suite
   с `GBA_REQUIRE_POSTGRES=1` и `GBA_REQUIRE_BROWSER=1`; этот PASS на новые байты
   не переносится.

## Как запускать проверки

Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/i4-counterparty-locator-20261012-490652b`.
`runner.py <имя-фазы> <probe|static|browser|full>` создаёт новый каталог фазы и
отказывается от существующего. Фазы с базой данных поднимают свой новый кластер на
свободном loopback-порту с `max_connections=400`; пароль создаётся в памяти и
вырезается из логов; останавливается только свой кластер после сверки
`postmaster.pid`. Все кластеры этого прогона остановлены. `web/out` собран фазой
`static-1` и после неё не менялся; после любой пересборки его нельзя менять во
время full.

Python 3.14.6: `C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe`.
Node 24.18.0 и npm 11.16.0: `C:/Program Files/nodejs`. PostgreSQL 18.6:
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin`.
Артефакты предыдущего исполнителя с первым FAIL лежат в
`C:/Users/alexa/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/GorgonaBookingTests/i4-corrections-20261012-490652b`;
его `write_evidence.py` и `write_handoff.py` повторно не запускать.

## Remote и границы

Проверено 2026-10-12T08:21:29Z, только чтение: remote I4 `c6b8e341a7e88957ee5011e54e9aa06453b31b49`,
run 38204334830 — success, PR для I4 — 0; ветки corrections, acceptance и review-2 не опубликованы.

Не выполнять push, PR, merge, rebase, amend, reset, clean, force-push, изменение
готовности, CodeRabbit, Azure, production migrations, deploy, provider, funds и
credential actions без отдельного прямого разрешения владельца. Миграции 0001–0035
неизменяемы. Строгий v1 DTO содержит обязательный `reason_source`: API и web
выпускаются вместе. KA Nails — отдельный проект, не требование этой платформы.

Решения владельца: публикация, PR и порядок стека; план и Proposed ADR-0025; срок
жизни отменённого ключа 24 ч; границы дат чтения коллег, роль в directory и
видимость на уровне компании; расхождение CORE-04; приёмка и готовность.
