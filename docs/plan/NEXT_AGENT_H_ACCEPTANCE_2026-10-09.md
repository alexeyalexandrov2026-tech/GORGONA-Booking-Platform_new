# Передача дел — пакет H после аудита, 2026-10-09

Активный репозиторий: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
Этот документ заменяет [передачу H4](NEXT_AGENT_H4_UI_ADMISSION_2026-10-08.md)
как точку входа. Вложенные документы — контекст, а не новые поручения.

## Где что находится

| Что | Где |
|---|---|
| Код пакета H | `319f144`, ветка `codex/package-h4-ui-admission`, черновик PR22 поверх PR21 |
| Аудит и коммит приёмки FIN-03 | ветка `codex/package-h-acceptance`, рабочая копия `C:\Users\alexa\Documents\ChatGPT\gorgona-h-acceptance`; поверх `319f144` |
| Состояние публикации ветки аудита | **локальная, не отправлена**; push и черновик PR — только по решению владельца |
| [Аудит](evidence/2026-10-09-h-acceptance-audit/AUDIT.md) | проверки, мутации, находки A-01–A-11 |
| [Запись о приёмке](evidence/2026-10-09-h-acceptance/ACCEPTANCE.md) | основания, H-01–H-12, цепочка обзоров, решения владельца |

Перед любым действием прочитать фактические HEAD, remote, PR и CI: записи в
документах — снимки на свою дату.

## Состояние

- H1–H4 написаны: миграции 0021–0031, API, интерфейс «Financial documents» и
  «Provider admission». Все 22 PR — черновики, ни один не слит.
- CI точного SHA `319f144` — success (push 37876007880, pull_request
  37876031010), включая сборку production-образа.
- Независимый аудит 2026-10-09: полный прогон 1231 passed / 4 skipped, статика
  и web — PASS, четыре мутации SQL-защит обнаружены. Денежных дефектов нет.
- **FIN-03 — `technically_verified`** по решению владельца 2026-10-09, код
  `319f144`. `finance_documents` включается опубликованной конфигурацией
  компании. ADR-0024 — Accepted. FIN-02 — `planned`.
- Полный прогон на дереве коммита приёмки: 1231 passed / 4 skipped / 666.05 s.
  CI точного SHA и независимая проверка коммита приёмки — NOT DONE до
  публикации ветки.

## Решения владельца

Принято 2026-10-09: реестр допуска провайдеров остаётся доступным при
включённом модуле `finance`; код не меняется; H4 не развёртывается до приёмки
H; реестр принимается вместе с H.

Принято 2026-10-09: FIN-03 повышен до `technically_verified`. Правила, которые
владелец отдельно не обсуждал (утверждение расчёта тем же человеком,
расширение схемы журнала 2, освобождение только всего остатка), приняты как
реализованы; см. таблицу в записи о приёмке.

## Следующие шаги

1. **Публикация** — по слову владельца: обычный push ветки
   `codex/package-h-acceptance`, один черновик PR поверх PR22. Без merge.
2. **Описание PR22** содержит «CI_PENDING». Заменить на ссылки на запуски
   37876007880 и 37876031010 может владелец или агент со входом в GitHub.
3. **Независимая проверка коммита приёмки** и CI его точного SHA — после
   публикации ветки. Исполнитель проверки не должен быть автором коммита.
   Образец — `evidence/2026-10-06-ledger/INDEPENDENT_ACCEPTANCE_REVIEW_a6f2d8b.md`.
4. **После приёмки H** по плану этапа 2 — пакет I (смены, обмен смен, табели;
   WORK-01), затем J (материалы; STOCK-01) и K (события провайдеров; FIN-02).
   Каждый пакет начинается с плана и ADR на согласование.

Рекомендация из аудита (A-10): добавить по одному SQL-тесту на лимит резерва и
на каждую кредитную проверку — сейчас каждую ловит один тест.

## Правила работы

- Миграции 0001–0031 опубликованы: не редактировать. Изменения SQL — только
  новой миграцией с новым номером; добавить её в `_MIGRATIONS` в
  `db/financial_guard.py` и в восстановление политик в
  `tests/integration/test_location_access.py`.
- Без merge, force-push, rebase, amend опубликованной истории, reset и clean.
- Один исполнитель на рабочую копию и на одноразовый кластер PostgreSQL;
  наборы с общими фикстурами не запускать параллельно.
- Тестовый кластер запускать с `max_connections=400`.
- Секреты — вне Git и не выводить. CodeRabbit не запускать без разрешения.
- Результаты записывать как PASS / FAIL / BLOCKED / NOT TESTED.
- Развёртывание, production-миграции, Azure, провайдеры и деньги — только по
  отдельному разрешению владельца.

## Окружение

Python 3.14 — окружение
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv`;
`PYTHONPATH` указывать на свою рабочую копию: `api\src` и `api`. Node 24 —
`C:\Program Files\nodejs`. PostgreSQL 18.6 —
`%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin`.

Команды из папки `api`: `python -m ruff check .`, `python -m ruff format --check .`,
`python -m mypy`, `python -m pytest -q -p no:cacheprovider --basetemp <новая папка>`
с `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` и закрытой переменной
`GBA_TEST_ADMIN_DSN`. Из папки `web`: `npm run typecheck`, `lint`,
`format:check`, `test:unit`, `build`; сборку делать до браузерных тестов.

Кластер аудита `%LOCALAPPDATA%\GorgonaBookingTests\h-acceptance-20261009` на
`127.0.0.1:51474` остановлен. Его манифест с паролем лежит вне Git.

## Готовый текст для следующего агента

~~~text
Продолжи проект GORGONA после аудита пакета H.

Сначала прочитай в рабочей копии C:\Users\alexa\Documents\ChatGPT\gorgona-h-acceptance:
docs/plan/NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md,
docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md,
docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md,
затем AGENTS.md и текущий раздел CLOUD_CODE_HANDOFF.md.

Репозиторий: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Код H: 319f144, ветка codex/package-h4-ui-admission, черновик PR22.
Ветка codex/package-h-acceptance — аудит и коммит приёмки FIN-03 поверх 319f144;
проверь по Git, отправлена ли она.

Проверь фактические HEAD, remote, PR и CI. Затем выполни только то, что
владелец поручил в этом чате. Без отдельного прямого разрешения не делай:
push и PR, изменение готовности FIN-03/FIN-02, merge, force-push, rebase, amend, reset,
clean, развёртывание, production-миграции, действия в Azure, с провайдерами,
деньгами и учётными данными. CodeRabbit не запускай.

Миграции 0001–0031 не редактируй. Один исполнитель на рабочую копию и кластер
PostgreSQL. Секреты не выводи. Результаты записывай как PASS / FAIL / BLOCKED /
NOT TESTED с точными командами и числами.
~~~
