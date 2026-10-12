# Передача следующему агенту — Package I, готовность к приёмке, 2026-10-12

**Исправления опубликованы, CI — success, матрица I-01–I-12 — PASS.
Пакет не принят: запись готовности WORK-01 не менялась.**
Этот документ — актуальный вход. [Готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md).

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`.
- Ветка: `codex/package-i4-review-corrections`, опубликована.
- Проверенный коммит: `f41f9a849a34a732433bea75514da758e345b859`. Поверх `490652b`: `2bca502` — исправления второго
  обзора (R2-1, R2-2, R2-3, CR-1); `3b9734c` — проверка сообщения о конфликте в двух
  browser-спеках; `b7953a4` — документы; `f41f9a8` — лимит времени задания CI,
  20 → 30 минут. HEAD — следующий коммит, только документы.
- [Разбор сбоя, проверки и решения](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md),
  [публикация и CI](evidence/2026-10-12-i4-review-corrections/PUBLICATION_CHECKS.json),
  [проверки с argv и хешами логов](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_CHECKS.json),
  [хеши исходников](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_SOURCE_PROOF.json),
  [независимый обзор правки спеков](evidence/2026-10-12-i4-review-corrections/INDEPENDENT_REVIEW_FOLLOWUP.md),
  [разбор исправлений](evidence/2026-10-12-i4-review-corrections/CORRECTIONS_REVIEW_FOLLOWUP.md),
  [авторский обзор](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_AUTHOR_REVIEW.md).
- Сохранённый первый FAIL: [VALIDATION.md](evidence/2026-10-12-i4-review-corrections/VALIDATION.md),
  [CHECKS.json](evidence/2026-10-12-i4-review-corrections/CHECKS.json), [SOURCE_PROOF.json](evidence/2026-10-12-i4-review-corrections/SOURCE_PROOF.json),
  [независимый обзор девяти файлов](evidence/2026-10-12-i4-review-corrections/INDEPENDENT_REVIEW.md).

Сначала status, branch, HEAD, log, worktrees и remotes. `git rev-parse HEAD:<путь>`
для одиннадцати файлов должен совпасть с `git_blob_oid` в FOLLOWUP_SOURCE_PROOF.json.
Один исполнитель на checkout и на кластер PostgreSQL.

Другие копии сохранены, их не трогать и не синхронизировать автоматически:
acceptance `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i` на 0356eb5; review2
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking` на 490652b;
reviewer `C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking`
на 490652b со своими dirty-копиями девяти файлов; primary owner
`C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` на 2f16380 (dirty).

## Что выполнено

- Исправления R2-1, R2-2, R2-3 и CR-1 закоммичены без изменений байтов, прошедших
  ограниченный независимый обзор, и дополнительно разобраны исполнителем, который
  их не писал: PASS, одно замечание P3 о подсказке экрана.
- Сбой полного прогона (1 failed, 1525 passed, 4 skipped) разобран: проверка
  `getByRole("alert")` совпадала и с пустым объявителем маршрута Next.js. Проверки в
  `counterparties.spec.ts` и `documents.spec.ts` теперь называют сообщение.
  Продуктовый код не менялся. Независимый обзор правки: PASS.
- Full local **PASS: 1526 passed, 4 skipped in 997.19s (0:16:37)**; focused browser desktop/mobile PASS 3 из 3; Ruff,
  format и mypy PASS на 265 файлах; web typecheck, lint, format, 102 unit и
  23 страницы PASS.
- Ветка опубликована по поручению владельца от 2026-10-12. CI **PASS**:
  [run 38227457763](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38227457763), задание 1168 с, pytest 1008 с.
- Первый прогон CI ([run 38225121578](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38225121578), коммит `b7953a4`) прошёл все
  проверки, включая pytest за 1052 с, и был отменён лимитом задания
  20 минут на завершающем шаге. Лимит поднят до 30 минут; проверки не менялись.
- Матрица I-01–I-12 — PASS.

## Решения владельца и исполнителя

2026-10-12 владелец поручил исполнителю выбирать самостоятельно. Выбрано: обзор,
публикация и лимит времени CI — выполнены; правила о сроке отменённого ключа, датах
чтения смен, видимости по умолчанию и роли в directory — оставлены как реализованы;
PR и merge — не выполнялись. Полная таблица с основаниями — в
[FOLLOWUP_VALIDATION.md](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md).

**Запись WORK-01 как проверенного не выполнена.** Она открывает модуль workforce
компаниям. Каждое прежнее поручение называет это отдельным решением владельца, а
сообщение от 2026-10-12 его не называло. Исполнитель считает пакет готовым к этому
шагу. Нужно прямое подтверждение владельца, например слово «принимай».

## Следующий срез: приёмка WORK-01

Выполнять только после прямого подтверждения владельца. Образец — коммит `ec39622`
(приёмка FIN-03).

1. Прочитать AGENTS.md, текущую часть CLOUD_CODE_HANDOFF.md, master, status, план
   пакета I, ADR-0025 и evidence; проверить Git, remote и CI до изменений.
2. `api/src/gorgona_booking/business/readiness_registry.py`: WORK-01 —
   `technically_verified`, `code_version` = `f41f9a849a34a732433bea75514da758e345b859`, `schema_version` = 35, scope с
   явными исключениями, evidence — запись о приёмке и обзоры, дата.
3. `api/src/gorgona_booking/business/modules.py`: модуль `workforce` сейчас объявлен
   без готовности и без описания. Его готовность должна выводиться из WORK-01, как у
   `finance_documents` из FIN-03; описать пределы и то, что останавливает выключение.
4. Тесты, которые опираются на закрытый модуль: списки включаемых модулей в
   `api/tests/unit/test_configuration_contracts.py` и
   `api/tests/integration/test_configurations.py` (там же случай `MODULE_NOT_READY`
   использует `workforce` как пример неготового модуля — заменить на другой
   неготовый); `api/tests/integration/test_workforce.py` (закрытый реестр) и закрытая
   фаза `api/tests/integration/test_i4_browser.py` — перевести на отозванную приёмку.
   Сначала падающие тесты, затем правка.
5. CORE-04, решение 9 плана: отдельным коммитом записать `technically_verified` по
   акту этапа 1 (`docs/plan/evidence/2026-10-06-stage1/ACCEPTANCE.md`,
   `docs/plan/evidence/2026-10-05-occupancy/ACCEPTANCE.md`) с исключениями: аренды
   нет, ёмкость выше 1 отложена. Ни один модуль от CORE-04 не зависит, поведение не
   меняется. Нужна короткая независимая проверка.
6. Запись о приёмке, ADR-0025 «Accepted as implemented», master, status, handoff.
7. Focused, static/web и полный serial suite с `GBA_REQUIRE_POSTGRES=1` и
   `GBA_REQUIRE_BROWSER=1`; независимая проверка коммита приёмки; push и CI точного
   коммита — только в пределах разрешения владельца.

Если исходники меняются по другой причине — те же свежие проверки; этот PASS на
новые байты не переносится.

## Что не сделано

- Приёмка пакета и запись готовности; PR и merge.
- Production npm audit: FAIL, 2 high (next, source-map-js); remediation — отдельный scope.
- Текст логов CI не читался: без входа в GitHub он недоступен. Результаты и
  длительности шагов прочитаны через открытый API.
- Контейнеры локально (3) и внешний tenant site (1): 4 skipped; образ собирается в CI.
  Screen reader, HawkScan, load/soak, deployment и production: NOT TESTED. Browser-пробы
  второго обзора (время не UTC, членство на всю компанию) не повторялись.
- Замечание P3: подсказка `colleague_shifts` для человека, переведённого в другой
  филиал при сохранённых сменах в прежнем, показывает `visible`, а сервер обмен
  отклоняет. Данные не раскрываются.

## Как запускать проверки

Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/i4-counterparty-locator-20261012-490652b`.
`runner.py <имя-фазы> <probe|static|browser|full>` создаёт новый каталог фазы и
отказывается от существующего. Фазы с базой данных поднимают свой новый кластер на
свободном loopback-порту с `max_connections=400`; пароль создаётся в памяти и
вырезается из логов; останавливается только свой кластер после сверки
`postmaster.pid`. Все кластеры этого прогона остановлены. После пересборки `web/out`
нельзя менять во время full.

Python 3.14.6: `C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe`
(с `PYTHONPATH` на `api/src` и `api` код импортируется из проверяемой копии).
Node 24.18.0 и npm 11.16.0: `C:/Program Files/nodejs`. PostgreSQL 18.6:
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin`.
Артефакты предыдущего исполнителя с первым FAIL лежат в
`C:/Users/alexa/AppData/Local/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/GorgonaBookingTests/i4-corrections-20261012-490652b`;
его `write_evidence.py` и `write_handoff.py` повторно не запускать.

CI: задание `api` на медленной машине GitHub занимает около 20 минут, на быстрой —
около 12. Лимит задания — 30 минут.

## Границы

Не выполнять PR, merge, rebase, amend, reset, clean, force-push, изменение
готовности, CodeRabbit, Azure, production migrations, deploy, provider, funds и
credential actions без отдельного прямого разрешения владельца. Разрешение на
публикацию от 2026-10-12 относится к ветке `codex/package-i4-review-corrections`.
Миграции 0001–0035 неизменяемы. KA Nails — отдельный проект, не требование этой
платформы.
