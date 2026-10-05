# GORGONA — продолжение после аудита E0

Дата: 2026-10-04 America/New_York. Читать этот документ перед историческими
передачами. Репозиторий: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.

## Текущая работа и сохранение данных

Самостоятельная универсальная GORGONA; KA Nails/камеры — отдельные проекты.
Все 39 профилей и 28 критериев остаются в master plan; этап 1 еще частичен.

Рабочая копия Codex:
C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking.
Ветка codex/package-e-isolation-audit; код E0 —
4ad645fc27a2334f55e5c7c47ee1e3de8eede3a5, [draft PR #6](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/6)
в codex/universal-business-foundation. Последующий docs commit не меняет код;
все CI связывать с конкретным HEAD. CI кода PASS: push run37260931380,
541 passed / 1 optional skip / 104.95 s; PR run37260950208 также SUCCESS.
Полные результаты — в [приемке](evidence/2026-10-04-isolation-audit/ACCEPTANCE.md).

Основная копия владельца C:\Users\alexa\Documents\ChatGPT\Gorgona Booking
остается на 2f1638011987e06923468b64600de1d1f4a14020, с 14 tracked и 5 untracked
изменениями исходного пакета E. Ее не менять, не reset/clean/restore/pull поверх
работы. Все 19 файлов и 6 локальных черновиков совпали с полученным архивом;
наша версия 14 файлов E0 тоже совпадает с ними побайтно. Изменения не удалялись.

Внимание к lineage: старая цепочка PR #2–#5 заканчивается на 1542b70 и расходится
с новой основой 2f16380 от eaa6233. В старой линии миграции 0011/0012 означают
другое, permissions v4 / guard65 / booking-report; в новой 0011 departments,
0012 delegation, 0014 configuration, permissions v3 / guard29+trigger.
Не смешивать схемы/ADR автоматически. E0 построен на новой основе пакета E;
PR #1 и остальные drafts не слиты. Продолжать в своем checkout/ветке от PR #6
либо от принятой свежей основы после отдельного решения владельца.

## Что проверено

На чистом 2f16380: локальная suite 527 passed / 4 skipped / 188.66 s.
Red: 6 поведенческих регрессий + scanner (15 находок) дали 7 failed / 4 passed;
новый web regression дал 1 failed. Green: focused 30 passed / 10.04 s;
итог 538 passed / 4 skipped / 193.26 s; обязательные PostgreSQL18.6 и браузеры.
Web 42 unit PASS / 986 ms, typecheck/lint/format/build14 PASS;
Ruff format/check + mypy153 PASS. Миграций нет, discovery/RLS policies сохранены.
Три local container skips и optional tenant-site skip — не PASS.

База 2f16380 проверена GitHub CI: PR run37245079640/job111561255307,
530 passed / 1 skipped / 144.81 s; web41; mypy151. Это не CI нового E0.
На старой 1542b70 была отдельная свежая suite 546/4/196.09 s — не переносить
ее цифры на новую линию. Предыдущая передача E0 538/4/387.64 s относится к
дереву до двух последних правок; наш новый финальный запуск выполнен после них.

## Следующее по пакету E

Исходные [план](PACKAGE_E_PLAN_2026-10-04.md),
[подробная передача](NEXT_AGENT_HANDOFF_PACKAGE_E_2026-10-04.md) и
[ADR-0020](../adr/0020-counterparties-documents-and-contracts.md) сохранены.
Сведения об одобрении — из доставленного пакета; прямое поручение этой сессии —
аудит и продолжение разработки. Важные внешние действия отдельно разрешаются.

E0 теперь реализован, локально и GitHub CI проверен в PR #6 на указанном кодовом SHA.
Перед продолжением повторно проверить CI актуального HEAD и состояние PR.
Затем E1 (0015): контрагенты/контакты/дубликаты/подтвержденные booking links;
E2 (0016): документы/bytea-files; E3 (0017): agreements без провайдера э-подписи.
Пакеты E1–E3 пока planned, черновики не приняты. Неизменяемые версии, FORCE RLS,
company-only права owner/manager, gate функций модулей с общим config lock,
idempotency/expected revision и аудит без ПДн/файлов обязательны.
Guard 29→34→38→40 относится только к этой линии. Модули не включать до приемки.
PDF/PNG/JPEG до 10 485 760 байт, not_scanned, staging/production upload503 до
подключения сканера. Не выдавать сигнатурный/PDF validator за антивирус.
После E: F/CORE-04, затем FIN/WORK/STOCK и отраслевые этапы master plan.

## Среда, передача и открытые ограничения

Python3.14, Node24, PostgreSQL18.6. Один executor на тестовый кластер, suites
последовательно. Codex использовал отдельный loopback 51454; автор пакета E —
51455. Перед запуском проверить процессы/владельца. Игнорируемый
handoff/run_test_database.py в копии Codex передает DSN только окружению;
переданный package-e-drafts/run_pytest.py жестко указывает owner checkout —
не запускать его как проверку своей копии. Пароли/config/DSN не печатать и
не переносить в Git/архив. Docker отсутствует; container gates выполняет CI.
Build web/out перед browser harnesses; статические проверки и полный pytest.

Полный комплект:
C:\Users\alexa\OneDrive\Desktop\handoff777\GORGONA_COMPLETE_HANDOFF_2026-10-04.zip.
Начало: NEXT_AGENT_COMPLETE_2026-10-04.md; SNAPSHOT.json/FINAL_STATUS.json и
COMPLETE_MANIFEST.json содержат точные состояния и SHA256. Исходный архив
вложен полностью, 62 manifest hashes проверены, CRC/UTF8 и targeted credential
patterns проверены. Это не полная антивирусная проверка и не Git history bundle.
Не распаковывать исходный patch/worktree поверх текущего дерева.

Azure read-only: staging Container Apps env Failed, apps0; PostgreSQL18 Ready,
public access Disabled; Key Vault private/RBAC/purge. Ошибка последнего создания
2026-10-01 — ManagedEnvironmentCapacityHeavyUsageError. Перезапуск/смена региона/
deployment не выполнялись. End-to-end staging BLOCKED; провайдеры/пилоты/
production migrations/RPO/RTO NOT TESTED.

Полный npm audit: 5 high dev findings в одной цепочке braces, prod0. Патча пока
нет; --force downgrade не применять. Load tool без изменений: synthetic probe
PASS при двух confirm422, invalid duration/day, overlap и неверные фазовые RPS.
До исправления не использовать его PASS для OPS-02. Внешний комплект содержит
точный reproducer/JSON и матрицу необходимых регрессий.

Code Tytor review BLOCKED (reauthentication); Malwarebytes URL verdict unknown,
это не сканирование файлов. Новый независимый E0 review недоступен в этой сессии;
самостоятельный source review и тесты выполнены. Старый reviewer проверял только
load tool. Ручная WCAG/screen-reader/RTL и AI/правовые отраслевые проверки не
проводились. После каждого шага сохранять новые ADR/evidence/status/audit/handoff.
