# Передача следующему агенту — пакет J, срез J5a «Материалы», 2026-10-14

**Экран «Материалы» и проверка неопределённой команды запасов по ключу закоммичены
(`afda55b`); полный локальный прогон — PASS: 1734 passed, 4 skipped. Срез J5b «Складские документы» не
начат. В `main` ничего не перенесено.** Этот документ — актуальный вход.
[Готовый prompt](NEXT_AGENT_PACKAGE_J5_MATERIALS_PROMPT_2026-10-14.md),
[запись о срезе](evidence/2026-10-14-j5-screens/VALIDATION.md),
[handoff исправлений по обзору](NEXT_AGENT_PACKAGE_J_REVIEW_FIXES_2026-10-14.md),
[handoff среза J4](NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md) (там — как запускать
проверки и уроки).

## Где продолжать

- Checkout: `C:/Users/alexa/.codex/worktrees/package-j5-screens/Gorgona Booking`, ветка
  `codex/package-j5-screens`; код — `afda55b`, поверх него коммит документов. Рабочая копия чистая.
- Цепочка: `main` (`fedd0f1`) → … → `codex/package-j-review-fixes` (`5e3a801`,
  опубликована, CI PASS) → эта.
- Что опубликовано и где `main`, читать из `git ls-remote origin`.
- Каталог прогона: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-j5-20261014-5e3a801`; в нём `runner.py` и `write_record.py` этого среза.

## Как устроен экран

- Сервер: `api/src/gorgona_booking/business/inventory_commands.py`, маршруты в конце
  `api/inventory.py`, ссылка `CommandReference` в `business/inventory_contracts.py`.
- Web: `web/lib/inventory-contracts.ts` (схемы и `inventoryResponseSchema`, подключена в
  `management-contracts.ts`), `inventory-api.ts`, `inventory-recovery.ts`,
  `web/components/materials.tsx`, `web/app/materials/`.
- Тесты: `web/tests/inventory-contracts.spec.ts` (в `test:unit`), `web/tests/materials.spec.ts`
  (`test:management:materials`, фазы `GBA_J5_PHASE=nobook|enabled`),
  `api/tests/integration/test_materials_browser.py` (готовность модуля подменяется только в
  процессе теста).

## Что делать первым

1. Status, branch, HEAD, log, worktrees, remotes, `git ls-remote origin`; если ветка не
   опубликована — опубликовать без PR и прочитать CI её вершины.
2. Срез J5b в новой ветке от вершины этой: экран «Складские документы» (`/stock-documents/`)
   по образцу «Материалов» — тот же центр команд с операцией `document` и версией 0,
   формы приёмки, списания, перемещения и возврата, список и просмотр документа; менеджер
   филиала видит только перемещения своего филиала и без сумм. Browser-тест с потерей
   ответа без второго документа, называть тексты сообщений.
3. До приёмки: измерить M2; тесты строк J-12 и J-13; затем приёмка STOCK-01 по матрице
   J-01–J-14 и независимый обзор.
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
