# Независимый обзор исправлений I4 — исходный срез, 2026-10-12

**FAIL чтением: одна средняя находка CR-1/P2.** Проверены собственные копии девяти файлов относительно 490652b3f01a1b3de2df2d2e6257fced6caf32e2 в ветке codex/package-i4-corrections-review. Исходники не закоммичены; точные байты зафиксированы в SOURCE_SHA256_INITIAL.json. Это независимый обзор исходников, не самостоятельное выполнение PostgreSQL/browser suite.

## CR-1 / P2: новая отмена допускает неподдерживаемый снимок транзакции

- Где: api/src/gorgona_booking/business/workforce_desk.py:303–325.
- Причина: блокировка actor/business сериализует транзакции, но COUNT после ожидания обновляется только при READ COMMITTED. Требование есть в комментарии; cancel_command, authorized_tenant и create_runtime_pool не проверяют и не устанавливают этот уровень.
- Сценарий для воспроизведения: записать 19 действующих маркеров для одной пары actor/business; начать две REPEATABLE READ транзакции и установить их снимки до первого нового маркера; обе вызвать cancel_command с разными ключами. Вторая ждёт advisory lock первой, затем её прежний снимок по-прежнему видит 19, поэтому обе могут выдать отмену. Настройка default_transaction_isolation на соединении/роли/БД также достигает API-пути.
- Уровень доказательства: вывод из прочитанного кода и официальной семантики PostgreSQL; самостоятельная runtime-проба этого сценария NOT TESTED. Не заявляется наблюдение 21 маркера в этом обзоре.
- Правка: после возврата уже известного исхода, до новой квитанции/блокировки, явно отклонять неподдерживаемую изоляцию; либо гарантировать её на входе транзакции. Существующий gba.lock_ledger уже использует fail-closed проверку current_setting('transaction_isolation'). Регрессия должна проверять отказ без новой квитанции и доступность известных исходов при неподдерживаемой изоляции.
- [Официальная документация PostgreSQL 18](https://www.postgresql.org/docs/18/transaction-iso.html): REPEATABLE READ сохраняет снимок первого обычного запроса; следующий COUNT после ожидания блокировки не получает новую видимость.

## Проверка остальных исправлений

- R2-1: PASS ограниченного чтения. staff_resource_owners неизменяем и уникален по tenant/user; current membership уникально по tenant/user. Совпадающее либо company-wide новое членство покрывает исходный home; несовпадающий филиал даёт None, новый swap закрывается. Tenant/location RLS сохраняется. Проверка квитанции предшествует privacy, прежние participant history/shift-version чтения сохранены. Изменены только home и new-swap отказ; handover/pickup не получили новый запрет.
- R2-2: исходная гонка при READ COMMITTED закрыта чтением: actor quota → receipt; реальные команды quota lock не берут. Claim предшествует COUNT, поэтому ожидаемая реальная команда при заполненном лимите возвращает committed. Вложенная транзакция откатывает новый claim при исключении quota; самостоятельная DB-проверка NOT TESTED. CR-1 пока исключает общий PASS.
- R2-3: PASS ограниченного чтения. SQL определяет reason_source по событиям correct/decline; approve наследует human только от предыдущего correct. SQL guard разрешает approve исключительно для последнего proposed, который образуется correct/clock_out. As-of load/list/history используют одну проекцию; UI больше не сравнивает содержание строки. API regression проверяет четыре совпадающие строки, approval и decline, browser проверяет Clock-in в карточке и history и скрытие двух системных причин. Выполнение этих regressions здесь NOT TESTED.
- Проверка тестов: новая concurrent-проба требует две реально наблюдаемые PostgreSQL блокировки конкретного actor/business (до правки два INSERT, после правки один INSERT и один quota lock), двух незавершённых задач и конечных кодов 200/429, ровно 20 маркеров, нуля незавершённых квитанций. Это содержательная гонка, не только последовательный счётчик. Browser использует настоящий correction input; не подменяет HTTP-ответ.
- Compatibility boundary: reason_source — новое обязательное поле строгих API/web DTO schema_version=1. API и web должны выпускаться согласованно; старый strict web отвергает дополнительное поле. Workforce остаётся закрыт/не принят, релиз в этом обзоре не выполнялся.
- Новых миграций, зависимостей, readiness изменений, изменений published 0001–0035 в девятифайловом diff нет.

## Самостоятельные проверки

Python: существующее доверенное окружение package-g-ledger-review/api/.venv, без нового окружения/пакетов.

1. git status --short / branch / rev-parse: собственная ветка codex/package-i4-corrections-review, HEAD 490652b3f01a1b3de2df2d2e6257fced6caf32e2; 8 tracked изменённых файлов и 1 новый regression-файл.
2. git diff --check 490652b3f01a1b3de2df2d2e6257fced6caf32e2: PASS, exit 0.
3. python -m ruff check --no-cache для четырёх изменённых Python-source файлов и regression-файла: PASS, All checks passed, exit 0.
4. python -m ruff format --check --no-cache для тех же пяти файлов: PASS, 5 files already formatted, exit 0.
5. python -m mypy src tests --cache-dir <private independent-review/mypy-cache> из собственного api: PASS, no issues found in 265 source files, exit 0.
6. SHA256 девяти файлов сохранены в SOURCE_SHA256_INITIAL.json; это идентификация проверенных байтов, не сравнение с тестируемой копией главного исполнителя.

## NOT TESTED / ограничения

Не запускались самостоятельные PostgreSQL, API integration, Playwright, web build/unit или CI. Не использовался чужой кластер. Не выполнялись push/PR/merge, CodeRabbit, deployment, production migrations, provider/credential действия. Нет утверждения о приёмке Package I либо production readiness. Исторические числа PASS главного исполнителя не принимались за собственные результаты.
