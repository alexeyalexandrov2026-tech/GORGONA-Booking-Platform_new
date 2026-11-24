# Handoff — package O (construction, BUILD-01) after O7a; next is O7b screens (2026-11-02)

Read this file, [NEXT_AGENT_PACKAGE_O7_2026-11-02.md](NEXT_AGENT_PACKAGE_O7_2026-11-02.md) (VM and process) and the
[O7a design](PACKAGE_O7A_DESIGN_2026-11-02.md) (the O7 split) before any action.

## Where things stand

The owner's delegation covers designing, building and pushing each slice branch **for CI only, without a PR**;
not PRs, merges, `main`, readiness, enabling modules, deploy, Azure, production migrations or live providers.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| O6b | `codex/package-o6b-reconciliation` | `381deeb` | `44736e8` | `04db17c` | 0095 | run 41529536177 success |
| O7a screens: projects, estimates, contract, change orders | `codex/package-o7a-construction-screens` | `074d42c` | `6c5ea3d` | the docs commit with this file | none | pushed for CI with this commit; check it first |

Next migration stays **0096**; migrations 0001-0095 are immutable. `construction` is implemented and not enableable.

## Next: O7b

Screens for the budget per phase and line with committed and actual (O3a/O3b `GET budget`), commitments (list,
detail, create, revise), actual cost links and reversals (STOCK-01 write-off lines, FIN-03 payable lines, WORK-01
time), the schedule (versions, dependencies), daily reports per site date and completed quantities. Build on the
O7a files: `web/components/construction.tsx` (the project page loads everything through `loadProject`; add the new
parts there), `web/lib/construction-contracts.ts` (add strict schemas and register their routes in the `routes`
table), `web/lib/construction-api.ts` (`command` keeps the Idempotency-Key until success). Copy the browser test
pattern of `test_o7a_construction_browser.py` and `web/tests/construction.spec.ts` (new spec and npm script).

## How O7a ran (repeat it)

- Commits move to the VM as a git bundle (`git bundle create … 04db17c..<branch>`, `git fetch` the bundle on the
  VM, detach); uncommitted files go by `tar` over ssh and are checked by `sha256sum -c`.
- red-1 is the Python browser test before any web code (the page is absent from `web/out`); the web contracts spec
  runs apart with `npx playwright test … --project=desktop` (red-2) because the runner only runs pytest.
- Build the web on the VM (`npm run build`) before dev-1; static-1 rebuilds it.
- Record: `adapt_o7a_record.py` in `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-o7a-20261102-074d42c`
  (reads `sources.txt`, the list of changed files).
- Write files with byte-level Python edits or the editor; plain `write_text` on Windows turns LF into CRLF.
- Playwright `getByRole` and `getByLabel` names match substrings: no other region may contain "Contract", and
  labels of line fields carry their line ("Line 1 unit"), matched with `exact: true`.

Known open test defect: `test_i4_browser` fails now and then in the full suite and passes alone (separate task).
