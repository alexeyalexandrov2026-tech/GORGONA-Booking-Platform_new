# PROPERTY-01 · продолжение после экрана договора

На `gorgona-dev` используй `/home/gorgona/gorgona`, репозиторий
`alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`, ветку
`codex/package-property-01-lease-screen`. База `6a179d6e8edfef6c293f173dbeb6bafef4a5bb91`.
Сверь HEAD и `origin`. Миграция 0118 не понадобилась.

`GET /property/leases` по-прежнему отдаёт список компании. Необязательный `object_id`
ограничивает страницу одним помещением и сохраняет курсор `after`. Экран Property
запрашивает только выбранный юнит. Исходный договор, текущий срок, история и акт
видны менеджеру или владельцу со scope всей компании. Запись хранит ожидаемую ревизию
срока и ключ повтора до успеха; конфликт ревизии не повторяется с новой ревизией.
Филиал этот раздел не видит и не запрашивает.

- **PASS** — PostgreSQL 18, `test_property_leases.py`, `test_property_lease_terms.py`,
  `test_property_move_in.py`: 25 passed in 55.67s. Фильтр по юниту, прежняя компания
  и отказ филиала входят в этот прогон.
- **PASS** — браузер на том же PostgreSQL, desktop и mobile:
  `test_property_browser.py` 1 passed in 58.21s. Регистрация, пересечение срока,
  повтор с тем же ключом, конфликт ревизии, акт, скачивание файла, axe и филиал.
- **PASS** — контракты экрана, 7 passed. Ruff, ESLint, Prettier, `tsc --noEmit` и
  `git diff --check`.
- **NOT TESTED** — приёмка пакета, production и публичная витрина. Освобождение срока
  есть в интерфейсе; браузерный сценарий покрыл продление, а не release.

Дальше по [плану PROPERTY-01](PACKAGE_PROPERTY01_PLAN_2026-11-14.md). Публичная витрина,
обращения и заявки ждут решений из
[дизайна публикаций](PACKAGE_PROPERTY01_LISTINGS_DESIGN_2026-11-15.md).
Ветка для CI входит в текущую работу. PR, слияние и production остаются отдельными
решениями владельца.
