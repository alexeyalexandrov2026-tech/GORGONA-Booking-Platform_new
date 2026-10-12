# Независимый обзор исправлений I4 — 2026-10-12

**PASS — ограниченный независимый обзор финальных исходников. Неисправленных actionable находок в девяти проверенных файлах не обнаружено.** Это не самостоятельное выполнение полного integration/browser suite и не приёмка Package I.

Проверена собственная ветка codex/package-i4-corrections-review, checkout C:/Users/alexa/.codex/worktrees/package-i4-corrections-review/Gorgona Booking, HEAD/base 490652b3f01a1b3de2df2d2e6257fced6caf32e2. Шесть runtime/contract файлов и три test-файла находятся вне коммита; точные байты и проверки — [SOURCE_SHA256.json](SOURCE_SHA256.json). Вердикт относится к этим хешам, не к историческому CI и не к будущему коммиту.

## Исправления и проверенные границы

- **R2-1 / privacy: PASS чтением.** home опирается на неизменяемый staff_resource_owners с единственным tenant/user, а не membership-specific active profile. Новое active membership должно покрывать исходный home: same-home и company-wide допускаются, другое location даёт None. Новый swap при None либо скрытом филиале закрывается до lookup именованных смен. Tenant/location RLS не снят на новых read-путях. Receipt replay проверяется до privacy; прежние participant history/request-shift чтения сохранены. Handover/pickup не получили новый запрет. Desk при same-home reinvitation использует тот же стабильный home. Пять новых API случаев охватывают visible/hidden, branch/company-wide, сохранённый replay/history и mismatched home; их execution здесь NOT TESTED.
- **R2-2 / quota: PASS чтением после CR-1.** Actor/business transaction advisory lock предшествует receipt claim и COUNT; SQL COUNT видит свежий READ COMMITTED снимок после ожидания. Claim до COUNT сохраняет результат реальной команды при заполненном лимите; реальная команда quota lock не берёт. Квота применяется только к новой отмене. Savepoint откатывает новый claim при TooManyDiscardsError, даже если внешний вызывающий код поймал исключение. На API-пути одна операция имеет одну внешнюю authorized_tenant transaction; принятого обратного пути quota/receipt блокировок не найдено. Cancel/resolve продолжают работать при module off/not accepted. Изменение не удлиняет существующий 24-hour receipt lifetime.
- **R2-3 / reason: PASS чтением.** Server projection различает correct/decline и системные clock actions по событию, не содержимому reason. Approval переносит human только от предыдущего correct; опубликованный SQL guard разрешает approve исключительно последнего proposed (correct/clock_out), поэтому одного predecessor достаточно. Та же as-of проекция обслуживает load/list/history; прежние effective/version поля не изменены. UI проверяет reason_source. API regressions включают все четыре строки, approval-copy и decline; реальный browser spec проверяет Clock-in в карточке и history и отсутствие системного текста на clock-in/clock-out approval. Execution этих интеграционных/browser случаев здесь NOT TESTED.

## Независимая обратная связь CR-1 / P2 — исправлена

Исходный проверенный срез имел предположение READ COMMITTED только в комментарии workforce_desk.py:303–325. При REPEATABLE READ сериализация advisory lock не обновляет уже установленный снимок COUNT: две транзакции, увидевшие 19 отмен до первой новой записи, могут обе разрешить отмену разных ключей. Runtime-проба этого сценария рецензентом **NOT TESTED**; находка получена чтением исходников и [официальной семантики PostgreSQL 18](https://www.postgresql.org/docs/18/transaction-iso.html), без заимствования чужого вердикта. Исходная обратная связь/хеши сохранены отдельно в INDEPENDENT_REVIEW_INITIAL.md и SOURCE_SHA256_INITIAL.json.

Финальная правка workforce_desk.py:307–311 проверяет SHOW transaction_isolation и закрывает новую нерешённую отмену вне read committed существующим DatabaseUnavailableError (HTTP 503); она стоит до claim/lock, после возврата уже известного исхода. Отказ не оставляет квитанцию. Шесть новых regression случаев проверяют все три неподдерживаемых уровня и сохранённые cancelled outcomes. Guards на схему/разрешения/модуль не ослаблены. После правки повторно прочитаны оба изменившихся файла; два отличия от исходной девятифайловой hash-таблицы проверены.

## Качество тестов и compatibility

Concurrent test требует две реально наблюдаемые PostgreSQL lock waiters конкретного actor/business и две незавершённые задачи: до исправления оба ждут INSERT, после него один INSERT и один actor advisory lock. После снятия барьера обязательны 200/429, ровно 20 отмен, ноль незавершённых квитанций. Дополнительный cap test наблюдает ожидание точной верхней транзакции настоящего clock-in writer, затем committed; savepoint test ловит ошибку внутри продолжающейся transaction. Проверки содержательные и не ограничены последовательным COUNT.

reason_source — новое обязательное поле strict API/web DTO schema_version=1. Согласованные API/web должны выпускаться вместе: старый strict web отвергает дополнительное поле. Это явная release/compatibility boundary закрытого, ещё не принятого workforce; совместимость с более ранним web deployment здесь не заявляется. SQL/receipt history не мигрируется и не переписывается; provenance вычисляется из существующих immutable событий. Новых migrations/dependencies, изменений published 0001–0035 и readiness в данном diff нет.

## Свежие собственные проверки финальных байтов

Инструменты: Git/PowerShell, существующий доверенный Python package-g-ledger-review/api/.venv, Ruff, mypy, pytest; evidence-engineering SKILL, официальная документация PostgreSQL. Новые инструменты/пакеты не устанавливались.

| Проверка | Точный исход |
|---|---|
| git status / branch / HEAD | 8 tracked изменений + 1 новый regression файл; собственная ветка/base указаны выше; runtime не изменялся рецензентом |
| git diff --check 490652b3f01a1b3de2df2d2e6257fced6caf32e2 | PASS, exit 0, после финальной копии; повторено после записи отчёта |
| python -m ruff check --no-cache (4 изменённых Python source + новый regression файл) | PASS, All checks passed!, exit 0 |
| python -m ruff format --check --no-cache (те же 5 файлов) | PASS, 5 files already formatted, exit 0 |
| python -m mypy src tests --cache-dir <external independent-review/mypy-cache-final> из собственного api | PASS, no issues found in 265 source files, exit 0 |
| python -m pytest -p no:cacheprovider --basetemp <external independent-review/pytest-unit-final> -q api/tests/unit/test_timesheet_contracts.py api/tests/unit/test_workforce_desk_contracts.py | PASS, 18 passed / 0.16s, exit 0 |
| SHA256 9 файлов / source delta | Девять финальных byte hashes сохранены; 2 изменились с initial; больше изменений не обнаружено. Сравнение с тестируемой копией главного исполнителя выполняет он отдельно |

Отчёт/JSON записаны только вне Git; product/test исходники рецензент не редактировал. Собственный PostgreSQL не запускался; чужой кластер не использовался.

## NOT TESTED / оставшиеся границы

Самостоятельные PostgreSQL/API integration/Playwright, web typecheck/lint/unit/build/audit, полный suite, exact-SHA CI, контейнеры, production/deployment, screen reader и load/soak не выполнялись этим рецензентом. Проверки главного исполнителя должны быть сохранены как отдельная свежая evidence для тех же хешей. Старые числа PASS не принимались за свои результаты. Push/PR/merge, CodeRabbit, production migrations, provider/funds/credential действия не выполнялись. Package I не принят; WORK-01/CORE-04 остаются planned. Review PASS не повышает readiness.
