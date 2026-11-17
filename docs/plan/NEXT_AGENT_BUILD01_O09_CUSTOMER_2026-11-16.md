# Передача следующему агенту GORGONA BUILD-01 O-09

Рабочая копия `C:/Users/alexa/.codex/worktrees/package-o8-customer-answer`.
Ветка экрана `codex/package-o9-customer-proposal-screen`, ветка серверной
проверки `codex/package-o8-customer-answer`. База экрана
`850e21645bda03cc3324f92c0269f9ea2160f700`; API исходного принятия
`9bf449d69c67e967ff119ee25f0467a781ef1a89`. Рабочий remote
`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Перед правками
сверь `git status --short --branch`, `git rev-parse HEAD` и последний CI
этой ветки. [CI серверной базы](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44018377878)

## Готовый запрос для продолжения

> Продолжи O-09 в указанной рабочей копии. Проверь CI точного SHA экрана и
> разбери сбои, если они появятся. Затем открой текущий код изменений
> договора и приёмки. Реализуй следующий отдельный сценарий ответа
> клиента на изменение договора через действующий grant, с проверкой
> компании, проекта, области филиала, версии документа и источника
> ответа. Сохрани неделегируемость construction.approve. Повтори клиентский
> сценарий и тесты обновления схемы с реальным PostgreSQL. После проверки
> продолжи приёмку и работу над операторской выдачей ссылки в рамках плана.
> Записывай точные SHA, результаты проверок и процент по реестру сценариев.
> Цель выпуска охватывает все 39 направлений. Публикация допустима на
> рабочей ветке для CI. PR, merge, production, миграции production и
> включение модуля требуют отдельного решения владельца.

## Что уже проверено

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
- FAIL: аудит зависимости Next.js вернул код 1 и одну находку moderate для
  16.4.2. Первая сборка остановилась на предупреждении, повторная завершилась
  с кодом 0. Статический экспорт проверен. Связки `use cache` и
  `unstable_cache` в исходниках web нет.
  [Уведомление Next.js](https://github.com/vercel/next.js/security/advisories/GHSA-mfr8-8qww-v76h)
- NOT TESTED: production, реальный IdP и выдача ссылок из операторского
  экрана. Полный CI надо сверить по текущему SHA. BUILD-01 остаётся открытым.

## Повтор проверок

Собери web с `npm run build`. Используй локальную одноразовую PostgreSQL
18 с `GBA_TEST_ADMIN_DSN`, `GBA_REQUIRE_POSTGRES=1` и
`GBA_REQUIRE_BROWSER=1`. Секрет DSN держи вне Git и результатов. Из `api`:

```text
uv run pytest -q tests/integration/test_location_access.py tests/integration/test_o8_construction_customer_answer.py tests/integration/test_o8_construction_customer_company.py tests/integration/test_o9_customer_proposal_browser.py
uv run pytest -q tests/integration/test_h3_upgrade.py tests/integration/test_inventory_upgrade.py tests/integration/test_stock_upgrade.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Из `web` запусти `npm run typecheck`, `npm run lint`,
`npm run format:check` и `npm run test:unit`. Клиентская ссылка имеет вид
`/construction/customer/?business=<uuid>&project=<uuid>&grant=<uuid>`.
Подробности о реализованных и открытых сценариях есть в
[реестре реализации](GORGONA_IMPLEMENTATION_STATUS.md).
