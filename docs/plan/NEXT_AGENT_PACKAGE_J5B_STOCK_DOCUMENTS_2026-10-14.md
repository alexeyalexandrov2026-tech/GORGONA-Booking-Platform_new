# Передача следующему агенту — пакет J, срез J5b «Складские документы», 2026-10-14

**Экран «Складские документы» закоммичен (`c3da59d`); полный локальный прогон — PASS:
1735 passed, 4 skipped. Срез J5 завершён. В `main` ничего не перенесено.** Этот документ — актуальный
вход. [Готовый prompt](NEXT_AGENT_PACKAGE_J5B_STOCK_DOCUMENTS_PROMPT_2026-10-14.md),
[запись о срезе](evidence/2026-10-14-j5b-stock-documents/VALIDATION.md),
[handoff J5a](NEXT_AGENT_PACKAGE_J5_MATERIALS_2026-10-14.md),
[handoff среза J4](NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md) (там — как запускать
проверки и уроки).

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-j5b-stock-documents/Gorgona Booking`,
  ветка `codex/package-j5b-stock-documents`; код — `c3da59d`, поверх него коммит документов. Рабочая копия чистая.
- Цепочка: `main` (`fedd0f1`) → … → `codex/package-j5-screens` (`b003b75`, опубликована,
  CI PASS) → эта.
- Что опубликовано и где `main`, читать из `git ls-remote origin`.
- Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-j5b-20261014-b003b75`.

## Как устроен экран

- `web/components/stock-documents.tsx`, `web/app/stock-documents/page.tsx`, общие
  `web/components/inventory-commands.tsx` и `web/app/inventory.css`.
- Контракты документов — в `web/lib/inventory-contracts.ts`, запросы — в `inventory-api.ts`.
- Тесты: `web/tests/stock-document-contracts.spec.ts` (в `test:unit`),
  `web/tests/stock-documents.spec.ts` (`test:management:stock-documents`),
  `api/tests/integration/test_stock_documents_browser.py`.

## Урок

На телефоне `innerWidth` растёт вместе со слишком широкой страницей, поэтому проверка
`scrollWidth <= innerWidth` её не видит. В browser-тестах запасов есть и проверка
`innerWidth <= screen.width`; её стоит перенести и в другие browser-тесты платформы.

## Что делать первым

1. Status, branch, HEAD, log, worktrees, remotes, `git ls-remote origin`; если ветка не
   опубликована — опубликовать без PR и прочитать CI её вершины.
2. До приёмки: измерить M2 (сверки при истории около 100 000 движений); тесты строк J-12
   и J-13; независимый обзор J5.
3. Затем приёмка STOCK-01 по матрице J-01–J-14. Повышение готовности — отдельным коммитом
   и только по решению владельца.
4. Всегда: сначала падающий тест, затем код, `static`, `focused`, полный прогон, запись,
   локальный коммит.

## Решения владельца

2026-10-13: «i trust you, you make decisions» — публикация веток пакета J без PR ради CI и время обзора.
2026-10-14: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.» — три вопроса обзора и продолжение пакета J. Слияние в `main`,
развёртывание, готовность, Azure, провайдеры, средства и учётные данные по-прежнему требуют
отдельного прямого слова владельца.

## Границы

Не выполнять PR, merge, rebase, amend, reset, clean, force-push, изменение готовности,
CodeRabbit, Azure, production migrations, deploy, provider, funds и credential actions без
отдельного прямого разрешения владельца. Исключение — публикация веток пакета J без PR
ради CI. Миграции 0001–0041 не меняются. Другие рабочие копии не трогать.
