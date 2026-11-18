# Передача следующему агенту GORGONA BUILD-01 O-09

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

> Продолжи приёмку пакета O в указанной рабочей копии. Полный CI
> кода dc9ee75 прошёл. Сверь повторный CI ветки приёмки после изменения
> тестового переключателя Workforce и разбери сбои. Общий набор O1–O9
> уже дал 97 PASS, три новые гонки
> отдельно прошли. Открой PACKAGE_O_ACCEPTANCE_2026-11-17.md и доведи
> запись O-10 до фактического результата полного CI.
> Подготовь итоговую приёмку пакета с точными SHA и границами CI,
> сохранив неделегируемость construction.approve, изоляцию компаний и
> разделение клиентских цен и внутренних затрат.
> Записывай точные SHA, результаты проверок и процент по реестру сценариев.
> Цель выпуска охватывает все 39 направлений. Публикация допустима на
> рабочей ветке для CI. PR, merge, production, миграции production и
> включение модуля требуют отдельного решения владельца.

## Что уже проверено

- PASS: все 33 файла O1–O9 одним набором, 97 тестов за 605,29 с, без
  пропусков. Новые гонки в `b0807b8` отдельно проверены в наборе из пяти
  тестов за 19,41 с. O-01 согласован с принятым ADR-0035.
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
- NOT TESTED: production и реальный IdP. Результат полного CI текущей
  ветки нужно проверить перед приёмкой.
  Полный CI надо сверить по текущему SHA. BUILD-01 остаётся открытым.

## Повтор проверок

Собери web с `npm run build`. Используй локальную одноразовую PostgreSQL
18 с `GBA_TEST_ADMIN_DSN`, `GBA_REQUIRE_POSTGRES=1` и
`GBA_REQUIRE_BROWSER=1`. Секрет DSN держи вне Git и результатов. Из `api`:

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
