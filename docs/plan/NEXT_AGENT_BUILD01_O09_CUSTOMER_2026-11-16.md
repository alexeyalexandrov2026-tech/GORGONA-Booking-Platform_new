# Передача следующему агенту GORGONA после технической приёмки BUILD-01

Рабочая копия `C:/Users/alexa/.codex/worktrees/package-o8-customer-answer`.
Текущая ветка `codex/package-o-acceptance`.
Производственный код `dc9ee75dbfb2c3cac0f5b29774f309ec59fe5519`
(`codex/package-o9-customer-access`).
Дополнительные гонки `b0807b80dbda8b39bbcb0616b2ddcdd883e0355c`.
Экран клиентской приёмки `9f12e96a9e266c3a6bdd639cd5db7a2f61aa899b`
(`codex/package-o9-customer-acceptance-screen`).
API клиентской приёмки `6a6cd8c` (`codex/package-o9-customer-acceptance`).
Экран изменения договора `917989cb75cd77996f6179a919759eb2aedbbc24`
(`codex/package-o9-customer-change-screen`). API изменения договора
`98e1064555232ac879b3a2a4acdbe8a4b874614d`
(`codex/package-o9-customer-change-answer`). Исходный экран предложения
`6e7dcee510ea4efac2a15c0d6f781cd9485bd85e`
(`codex/package-o9-customer-proposal-screen`). База экрана
`850e21645bda03cc3324f92c0269f9ea2160f700`
(`codex/package-o8-customer-answer`), API исходного принятия
`9bf449d69c67e967ff119ee25f0467a781ef1a89`. Рабочий remote
`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Перед правками
сверь `git status --short --branch`, `git rev-parse HEAD` и последний CI
этой ветки. [CI экрана](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44019373237)
[CI серверной базы](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44018377878)

## Готовый запрос для продолжения

> O-01–O-10 технически приняты. Полный CI на `3ea5d28` дал 2949 PASS
> и один пропуск проверки внешнего сайта. Локально 100 PASS по O1–O9
> с дополнительными гонками. Используй PACKAGE_O_ACCEPTANCE_2026-11-17.md
> как запись приёмки. Продолжай открытые работы этапа 4. В RENT-01
> остаётся R-09, ответ клиента через grant. Пакет R уже проверяет,
> что сотрудники записывают только бумажный ответ или ответ по email.
> Начни с сопоставления личности арендатора с действующим grant и
> версии условий, видимой клиенту. Для PROPERTY-01 смотри границы ниже.
> Сохраняй неделегируемость construction.approve, изоляцию компаний
> и разделение клиентских цен и внутренних затрат.
> Записывай точные SHA, результаты проверок и процент по реестру сценариев.
> Цель выпуска охватывает все 39 направлений. Публикация допустима на
> рабочей ветке для CI. PR, merge, production, миграции production и
> включение модуля требуют отдельного решения владельца.

## Что уже проверено

- PASS — на `c4a9c67` все 33 файла O1–O9 и дополнительные гонки одним
  набором, 100 тестов за 539,46 с, без пропусков, exit 0. PostgreSQL 18.7
  и Chromium были обязательными. O-01 согласован с принятым ADR-0035.
  [Текущая запись приёмки](PACKAGE_O_ACCEPTANCE_2026-11-17.md)
- PASS: операторский доступ в Chromium desktop/mobile, 2 сценария за
  22,6 с, целевой pytest 38 PASS за 43,32 с. Сохранение привязки с
  потерянным ответом не добавляет вторую ревизию. Девять прав проходят
  issue и accept. Клиент использует все три вида полученных ссылок.
  После отзыва grant повторная подготовка ссылок получает отказ.
  API unit 878 PASS, web unit 190 PASS, сборка и статические проверки
  прошли. Лимит прав согласован с существующей миграцией 0119.
- PASS: клиентский экран приёмки на desktop/mobile, 2 Chromium-сценария
  за 10,0 с, 1 pytest за 23,10 с. Устаревший hash, потеря ответа,
  подменённый hash квитанции, равные три ключа и тела повтора, редактирование
  после 422 и обе записи в БД проверены. Четыре другие регрессии прошли
  в первом наборе. Web unit 188 PASS, сборка 33 страниц, typecheck, lint,
  формат, Ruff и mypy на 570 файлах прошли с кодом 0.
  Оба замечания независимого обзора экрана исправлены и проверены.
- PASS: 60 проверок за 112,02 с на PostgreSQL 18.7 для приёмки через grant,
  миграции 0121, прежней приёмки, гарантии, филиалов и обновлений старой
  схемы. 877 API unit-тестов за 31,59 с, Ruff, формат и mypy на 569 файлах.
  Повторная авторизация предшествует возврату старой квитанции. Новый
  ответ сверяет review_hash с актуальным объёмом под блокировкой проекта.
  Независимый обзор выявил пропущенный общий счётчик замечаний в hash,
  исправление проверено тестом и повторным обзором.
- PASS: 8 интеграционных проверок за 108,41 с на PostgreSQL 18.7,
  включая Chromium desktop/mobile для исходного предложения и изменения
  договора, прежние сценарии управления и дополнительный отказ по grant
  другого филиала. Новый экран одобряет, отклоняет и повторяет ответ с тем
  же телом и ключом. Отзыв через реальный API между чтением и ответом
  прекращает доступ и сохраняет отсутствие третьего решения.
- PASS: Next.js и ESLint-конфигурация обновлены до 16.4.6. Установка по
  lockfile, сборка 32 страниц и `npm audit --omit=dev` вернули код 0.
  187 web unit-тестов, typecheck, lint и формат прошли. Независимый
  read-only обзор исходников не выявил дефектов, reviewer тесты не запускал.
- FAIL: полный `npm audit` вернул код 1 с 15 находками в dev-зависимостях
  (6 moderate, 9 high). Это отдельная оставшаяся задача зависимостей.
- PASS: 43 интеграционных проверки за 92,77 с на PostgreSQL 18.7 для
  ответа на изменение договора, миграции 0120 и прежних сценариев. Проверены
  одобрение, отказ, повтор, отказ по неверному или отозванному grant,
  отсутствие затрат в ответе, отклонение старой версии назначения и чужого
  проекта. В БД остаются компания, grant и фактический автор ответа.
- PASS: PostgreSQL `18.7-1.pgdg13+2`, 26 тестов за 60,63 с для исправления
  тестового восстановления RLS и списков таблиц. Результат до исправления
  воспроизводился четырьмя отказами RLS после теста `missing_boundary`.
- PASS: на экране работает исходное предложение, клавиатурное принятие
  и повтор с прежним `Idempotency-Key` после потерянного ответа. Два прогона
  Chromium, desktop и mobile, завершились с кодом 0. Ответ на ссылку с
  отозванным grant скрывает данные предложения, а в БД для каждого проекта
  осталась одна запись с правильными grant и подписантом.
- PASS: обязательные для этого изменения Ruff, mypy, web typecheck, lint,
  формат, 186 web unit-тестов и повторная статическая сборка на 31 страницу.
- PASS — полный [CI `3ea5d28`](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44242186256),
  2949 тестов за 4194,42 с, exit 0. Один опциональный тест внешнего
  сайта пропущен. Техническая приёмка O-01–O-10 завершена.
- NOT TESTED — production и реальный IdP. В реестре BUILD-01 остаётся
  `planned` до отдельного решения владельца.

Отдельное обновление транзитивных dev-зависимостей `1ccb684` находится
на `codex/package-o-web-dev-dependencies`. Статические проверки, сборка и
190 web unit-тестов прошли. Полный CI — 2949 PASS, 1 skip за
3702,34 с, exit 0. Аудит production-зависимостей дал 0 находок.
14 записей полного аудита сводятся к одной находке в `picomatch`.
[Handoff зависимостей](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/blob/1ccb6846bafd1776cecdf7955e2ecfdf37e580b2/docs/plan/NEXT_AGENT_BUILD01_O09_CUSTOMER_2026-11-16.md)
[CI зависимостей](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44243266269)

[Критерии RENT-01](PACKAGE_RENT_PLAN_2026-11-03.md) и
[границы R-09](PACKAGE_R9_DESIGN_2026-11-13.md).

## Результаты старого handoff PROPERTY-01

- `codex/package-property-01-lease-release`, `adbc7e0` — полный CI
  PASS, 2926 тестов и 1 пропуск за 4091,18 с.
  [CI освобождения срока](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43793355920)
- `codex/package-property-01-access`, `21dc638` — полный CI
  PASS, 2930 тестов и 1 пропуск за 3389,93 с. Этот коммит уже предок
  текущей ветки приёмки BUILD-01.
  [CI доступа](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43799983687)

Упомянутая в [старом handoff](NEXT_AGENT_PROPERTY01_ACCESS_2026-11-15.md)
миграция 0118 уже занята. Последняя миграция в общей цепочке — 0121.
Решения владельца по новым таблицам PROPERTY-01, витрине и учёту
депозитов остаются открыты.

## Повтор проверок

Собери web с `npm run build`. Используй локальную одноразовую PostgreSQL
18 с `GBA_TEST_ADMIN_DSN`, `GBA_REQUIRE_POSTGRES=1` и
`GBA_REQUIRE_BROWSER=1`. Секрет DSN держи вне Git и результатов. В PowerShell
из `api` общий пакет собирается из 33 файлов.

```powershell
$tests = @(rg --files tests/integration | Where-Object { $_ -match '[\\/]test_o[1-9].*\.py$' } | Sort-Object)
uv run pytest -q -ra @tests
```

Для отдельных путей можно повторить меньшие наборы из `api`.

```text
uv run pytest -q tests/integration/test_location_access.py tests/integration/test_o2_construction_contract.py tests/integration/test_o8_construction_customer_answer.py tests/integration/test_o8_construction_customer_company.py tests/integration/test_o9_customer_change_answer.py tests/integration/test_o9_customer_proposal_browser.py tests/integration/test_o9_customer_change_browser.py
uv run pytest -q tests/integration/test_h3_upgrade.py tests/integration/test_inventory_upgrade.py tests/integration/test_stock_upgrade.py
uv run pytest -q tests/integration/test_o9_customer_acceptance.py tests/integration/test_o6a_construction_acceptance.py tests/integration/test_o6b_construction_warranty.py
uv run pytest -q tests/integration/test_o9_customer_acceptance_browser.py tests/integration/test_o7c2_construction_acceptance_browser.py
uv run pytest -q tests/integration/test_o9_customer_access_browser.py tests/integration/test_o8_construction_customer_company.py tests/integration/test_delegations.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Из `web` запусти `npm run typecheck`, `npm run lint`,
`npm run format:check` и `npm run test:unit`. Клиентская ссылка имеет вид
`/construction/customer/?business=<uuid>&project=<uuid>&grant=<uuid>`.
Для изменения договора используй
`/construction/customer/change/?business=<uuid>&project=<uuid>&grant=<uuid>&number=<integer>`.
Для приёмки используй
`/construction/customer/acceptance/?business=<uuid>&project=<uuid>&grant=<uuid>`.
Подробности о реализованных и открытых сценариях есть в
[реестре реализации](GORGONA_IMPLEMENTATION_STATUS.md).
