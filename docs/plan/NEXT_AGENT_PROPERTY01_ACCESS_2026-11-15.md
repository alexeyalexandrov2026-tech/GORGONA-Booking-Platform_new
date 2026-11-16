# PROPERTY-01 · передача после проверки доступа ко всем маршрутам

## Где всё лежит

- Репозиторий: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
- Ветка этого среза: `codex/package-property-01-access`. Код и дизайн: `2b124b52a0908268ccb4878a55ed1cada80fa091`
  (test(property): check who may reach every property route). HEAD — коммит с этим файлом.
- База среза: `adbc7e048f17c11632410f8fbea1234cc3f3babf` на `codex/package-property-01-lease-release`.
  Её тест — `2f8aaf6b68bc2cc82bfa4548f9d17162c9de70e8`, её база — `e79f11a8b35ea3052da5cee4f9cd1180652b91f9`
  на `codex/package-property-01-lease-screen`.
- Сравнения: https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/compare/e79f11a8b35ea3052da5cee4f9cd1180652b91f9...adbc7e048f17c11632410f8fbea1234cc3f3babf
  и https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/compare/adbc7e048f17c11632410f8fbea1234cc3f3babf...codex/package-property-01-access
- Работа шла на рабочем компьютере Grok Bot (`/workspace/gorgona`, `/workspace/gorgona-b`), не на `gorgona-dev`.
  VM не запускали, `budget-vm-stopper` не трогали. PostgreSQL 18.7 — бинарники pgdg в
  `/workspace/pg18root`, кластеры `/workspace/pg18data` (порт 55432) и `/workspace/pg18data-dev` (55433),
  окружение — `/workspace/gorgona-env.sh`, логи — `/workspace/gorgona-logs`. Docker там нет, поэтому
  контейнерные проверки идут только в GitHub CI.
- Документы среза: [дизайн доступа](PACKAGE_PROPERTY01_ACCESS_DESIGN_2026-11-15.md),
  [доказательства](evidence/2026-11-15-property-access/CHECKS.json),
  [передача освобождения срока](NEXT_AGENT_PROPERTY01_LEASE_RELEASE_2026-11-15.md),
  [доказательства освобождения](evidence/2026-11-15-property-lease-release/CHECKS.json).

## Что сделано

1. **Освобождение срока в браузере** (`codex/package-property-01-lease-release`). Закрыт пробел
   экрана договора. После продления и акта договор прекращается днём заселения. Экран освобождает
   срок: первый запрос обрывается сетью, повтор идёт с тем же ключом. Вторая вкладка получает
   конфликт ревизии. В базе ревизия 3, последний день равен дню заселения, события
   `[(2, extend), (3, release)]`. Изменены только тесты.
2. **Доступ ко всем 19 маршрутам Property** (этот срез, шаг 7 плана без схемы).
   `test_property_access.py` сверяет матрицу с путями OpenAPI. Чужая компания, `artist`,
   `front_desk` и поддержка платформы получают 403 на всех 19 маршрутах, ничего не записав.
   Менеджер своего филиала читает 6 маршрутов и получает 403 на 13. Менеджер другого филиала
   видит пустые списки, 404 на объектах и 403 на остальном. Приостановленный и отозванный
   менеджер получает 403 везде, повтор его прежнего ключа тоже отклоняется. После
   восстановления повтор возвращает исходный ответ. Отозванное членство восстановить нельзя
   (409), авторство ревизии сохраняется. Схема, API и экран не менялись, миграции нет.
3. Реестр `GORGONA_IMPLEMENTATION_STATUS.md` дополнен записями об экране договора (в срезе
   `e79f11a` её не было), об освобождении срока и о доступе.

## Что проверено

- **PASS** — исходный `e79f11a`: `test_property_leases.py`, `test_property_lease_terms.py`,
  `test_property_move_in.py` 25 passed in 40.86s; браузер 1 passed in 49.56s (Playwright 10 passed, 42.4s);
  typecheck, ESLint, 179 web unit, Ruff, mypy, `git diff --check`, сборка web.
- **PASS** — освобождение: браузер 1 passed in 53.87s, Playwright 10 passed (47.0s), desktop и mobile, axe.
- **PASS** — доступ: 4 passed in 13.20s. Мутация (история объекта под `property.read`) роняет тест,
  после этого маршрут вернули. Все 13 файлов Property, делегирование и приглашения: 83 passed in 99.40s.
  Unit 877 passed in 21.32s. Ruff, mypy (557 файлов), `git diff --check`.
- **FAIL вне Property, не разобрано** — полный прогон на рабочем компьютере (`2f8aaf6`):
  3 failed, 2920 passed, 4 skipped in 3600.65s. `test_r6b_rental_usage::test_cards_meters_and_extensions`
  ждёт время в UTC, а рабочий компьютер настроен на America/New_York. Две проверки
  `test_stock_documents_browser` (`documents`, `pagination`) не разобраны. Решает GitHub CI.

## CI на момент передачи (2026-11-15, 22:45 по нью-йоркскому времени)

- `e79f11a`: [43784742809](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43784742809) — success.
- `adbc7e0` (lease-release): [43793355920](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43793355920) — **ещё идёт**,
  pytest запущен в 21:42. Run [43792656494](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43792656494) на `2f8aaf6` отменён следующим push.
- `2b124b5` (access): [43796127873](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43796127873) — **ещё идёт**.
  Run на коммите с этим файлом отменит его по правилу `concurrency` и проверит то же самое плюс документы.
- **Первое действие следующего агента:** дождаться этих run'ов. Если красный, исправить новым
  коммитом в той же ветке. Особенно проверь `test_stock_documents_browser` и `test_r6b_rental_usage`.

## Что не проверено

Приёмка пакета целиком, production, публичная витрина. Отказ освобождения раньше дня заселения
в браузере (на PostgreSQL покрыт). Делегирование в матрице не вызывается: набор
`DELEGABLE_PERMISSIONS` зафиксирован в `test_delegation_contracts.py` и прав Property не содержит.

## Жёсткие правила

Без pull request и слияния, без production, модуль `property` не включать, VM `gorgona-dev` и
`budget-vm-stopper` не трогать. Без изменения схемы и миграции 0118 до решения владельца. Шаги 4 и 2d
не начинать. `docs/plan/NEXT_AGENT_START_HERE.md` не считать текущей точкой.

## Следующий шаг и решения владельца

1. Довести до зелёного CI ветки `codex/package-property-01-lease-release` и `codex/package-property-01-access`.
2. Решения владельца по PROPERTY-01:
   - шаг 4 (аренда и депозит через FIN-03/FIN-01): целевые юрисдикции, модель хранения депозитов и
     средств собственника, порядок удержания и возврата;
   - шаг 2d (витрина, обращения, заявки): канал публикации и защита от злоупотреблений, состав
     персональных данных, текст и версии согласия, срок хранения, провайдер проверки кандидатов и
     правила решения человеком;
   - шаги 5 (ремонт, подрядчик с доступом к одному поручению), 6 (акт выезда, сверка) и 7
     (кабинеты арендатора и собственника с правами на срок и отзывом) требуют новых таблиц, то есть
     разрешения на миграцию **0118**. Шаг 6 по депозиту и отчётам зависит ещё и от шага 4.
3. Без схемы остаётся работа этапа 4 по BUILD-01 ([план пакета O](PACKAGE_O_PLAN_2026-10-30.md)):
   O7b2 (экран фактических затрат: привязка списаний STOCK-01, обязательств FIN-03 и часов WORK-01,
   сторно), O7c (экраны проверок, удержания, актов оплаты, приёмки, гарантии и сверки) и O8
   (приёмка BUILD-01). API для них уже есть. Следующий номер миграции — **0118**, только после решения владельца.
