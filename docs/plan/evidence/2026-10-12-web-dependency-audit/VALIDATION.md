# Аудит зависимостей web: production-находки устранены, 2026-10-12

**Итог.** Production-аудит (`npm audit --omit=dev`): было FAIL, 2 high — стало **PASS,
0 находок**. Полный аудит вместе с инструментами разработки (`npm audit`): было FAIL,
7 high — осталось **FAIL, 5 high**. Все пять — одна цепочка `braces`, для которой
исправленной версии не существует; в production-образ она не попадает.

Ветка `codex/web-dependency-audit`, опубликована 2026-10-12 с разрешения владельца. Основа — `4630ca3`,
опубликованная вершина `codex/package-i4-review-corrections`; та ветка не менялась.
CI: **PASS**, [run 38315410876](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38315410876) на `8a1a7ab`: задание 1204 с, pytest 1057 с; текст логов не читался.
Машиночитаемые данные: [CHECKS.json](CHECKS.json) — запись до публикации;
[CI_RESULT.json](CI_RESULT.json) — публикация и CI.

## Основание

2026-10-12 исполнитель в отчёте о приёмке Package I назвал четыре возможных следующих
среза и рекомендовал начать с аудита зависимостей. Владелец ответил: «continue».
Исполнитель понял это как согласие начать рекомендованный срез и сказал об этом в
начале работы. Публикацию новой ветки это согласие не включало. После локальных
проверок исполнитель спросил о публикации, и владелец выбрал «Publish and read CI».

## Что было найдено

| Пакет | Запись | Уровень | Затронутые версии | Суть | Исправлено в |
|---|---|---|---|---|---|
| `next` | [GHSA-cjq9-62q9-8jv4](https://github.com/advisories/GHSA-cjq9-62q9-8jv4) | high | `>=16.0.0 <16.3.8` | подделка запросов со стороны сервера (SSRF) в оптимизаторе изображений | 16.3.8 |
| `next` | [GHSA-3w37-wq28-93x7](https://github.com/advisories/GHSA-3w37-wq28-93x7) | moderate | `>=16.3.0 <16.3.8` | утечка содержимого Draft Mode в обычные ответы через `use cache` | 16.3.8 |
| `next` | [GHSA-4jqv-mc3x-m676](https://github.com/advisories/GHSA-4jqv-mc3x-m676) | moderate | `>=16.0.0 <16.3.8` | отравление кэша страниц SSG и ISR при самостоятельном размещении | 16.3.8 |
| `next` | [GHSA-f87g-xv8r-7p7x](https://github.com/advisories/GHSA-f87g-xv8r-7p7x) | moderate | `>=16.0.0 <16.3.8` | раскрытие данных через маршруты изображений метаданных | 16.3.8 |
| `next` | [GHSA-mcj8-r9mp-w47p](https://github.com/advisories/GHSA-mcj8-r9mp-w47p) | moderate | `>=16.0.0 <16.3.8` | отравление кэша SSG/ISR: подмена содержимого между пользователями и отказ в обслуживании | 16.3.8 |
| `next` | [GHSA-39w2-rjm5-chcv](https://github.com/advisories/GHSA-39w2-rjm5-chcv) | low | `>=16.0.0 <16.3.8` | раскрытие данных в MCP-endpoint сервера разработки | 16.3.8 |
| `braces` | [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | high | `<=3.0.3` | переполнение стека на глубоко вложенных шаблонах, отказ в обслуживании | исправленной версии нет |
| `source-map-js` | [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) | high | `>=1.0.0 <1.2.2` | отказ в обслуживании при разборе source map | 1.2.2 |

`next` и `source-map-js` входят в production-зависимости (`source-map-js` — через
`postcss`, который нужен `next`). `braces` приходит только с инструментом проверки кода:
`eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob` → `micromatch` → `braces`.
Остальные четыре из пяти оставшихся строк аудита — эти же пакеты цепочки, отмеченные
из-за `braces`.

## Насколько это касалось платформы

Это оценка по конфигурации; атаками она не проверялась.

- Web собирается как статический экспорт (`output: "export"` в `web/next.config.ts`).
  Production-образ содержит только готовые файлы `web/out` и Python API (`Dockerfile`):
  Node и сервера Next в нём нет. Оптимизатора изображений, ISR, Draft Mode и сервера
  разработки в развёрнутой системе нет.
- `source-map-js` и `braces` работают только при сборке и проверке кода.

Известного пути атаки на развёрнутую систему через эти находки исполнитель не видит.
Обновление убирает их из production-аудита и из среды сборки.

## Что изменено

- `web/package.json`: `next` 16.3.7 → 16.3.8 и `eslint-config-next` 16.3.7 → 16.3.8.
  Второе на аудит не влияет: пара выпускается вместе и оставлена одной версии.
- `web/package-lock.json`: изменились 13 пакетов, добавленных и
  удалённых нет: `@next/env`, `@next/eslint-plugin-next`, `@next/swc-darwin-arm64`, `@next/swc-darwin-x64`, `@next/swc-linux-arm64-gnu`, `@next/swc-linux-arm64-musl`, `@next/swc-linux-x64-gnu`, `@next/swc-linux-x64-musl`, `@next/swc-win32-arm64-msvc`, `@next/swc-win32-x64-msvc`, `eslint-config-next`, `next`, `source-map-js`.
  `source-map-js` 1.2.1 → 1.2.2, остальные 16.3.7 → 16.3.8.
- 16.3.8, а не 16.4.0: это наименьшее обновление, закрывающее все шесть записей о
  `next` (все затрагивают версии до 16.3.8). 16.4.0 — следующая минорная версия.
- Код приложения, тесты, миграции и API не менялись.

Порядок: правка двух строк `package.json`; `npm install --package-lock-only`;
`npm update source-map-js --package-lock-only`; сверка lock-файла со списком ожидаемых
пакетов; `npm ci --ignore-scripts` — так же зависимости ставит CI и сборка образа.

## Что осталось

- **Полный аудит: FAIL, 5 high.** `braces` 3.0.3 — последняя выпущенная версия, запись
  [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) исправленной
  версии не называет. `@next/eslint-plugin-next` 16.3.8 и 16.4.0 по-прежнему требуют
  `fast-glob` 3.3.1. Единственное, что предлагает npm, — понизить `eslint-config-next`
  до 14.2.35, то есть на две мажорные версии; это не применено.
- По оценке исполнителя риск невелик: шаблоны для `braces` задаёт конфигурация самого
  проекта, а не внешний ввод, и в production-образ пакет не попадает. Эти пять строк
  записаны ещё в аудите E0 от 2026-10-04.
- Дальше: следить за выпуском исправленного `braces` или версии
  `@next/eslint-plugin-next` без `fast-glob`.

## Проверки

Основа всех прогонов — `4630ca3`; «до» — без изменений, «после» — с обновлением.

| Проверка | До | После |
|---|---|---|
| `npm audit --omit=dev --json` | FAIL: exit 1, 2 high (`next`, `source-map-js`) | **PASS: exit 0, 0 находок** |
| `npm audit --json` | FAIL: exit 1, 7 high | **FAIL: exit 1, 5 high** (цепочка `braces`) |
| Ruff check и format, mypy (265 файлов) | PASS | PASS |
| Web typecheck, lint, format | PASS | PASS |
| Web unit, 102 теста | PASS | PASS |
| Web build, Next 16.3.8, 23 страницы | PASS на 16.3.7 | PASS |
| Full local, новый кластер PostgreSQL | не повторялся; на дереве приёмки было 1531 passed, 4 skipped | **PASS: 1531 passed, 4 skipped in 1023.50s (0:17:03)** |
| Исходники не менялись во время прогонов | да | да |
| `web/out` не менялся во время full | — | да, 154 файла |
| CI | — | **PASS**, [run 38315410876](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38315410876) на `8a1a7ab`: задание 1204 с, pytest 1057 с; текст логов не читался. Записано следующим коммитом |

Full запускался после `npm ci` на той сборке `web/out`, которую создала фаза статики
«после». Пропущенные 4 теста — те же, что и раньше: три теста контейнера и тест
встраивания сайта, помеченные BLOCKED без своих переменных окружения.

## Не проверено

- Сборку production-образа и пакеты `@next/swc` для Linux проверил только CI; локально
  установлен пакет для Windows, а тесты контейнера пропущены. Текст логов CI не читался.
- HawkScan: не запускался — в этой среде нет `hawk` и ключа.
- Поведение Next 16.3.8 вне того, что покрывают тесты; настоящий screen reader,
  нагрузка, развёртывание и production.

## Откат

`git revert ab3e6b6`, затем `npm ci --ignore-scripts` в `web`.
