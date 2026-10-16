# K1d verification authority and trusted routing — local validation

**PASS for this bounded local, synthetic slice.**
Branch `codex/package-k1d-receipt-routing`, parent `46ab31dd6f41ae820a85a09f19fd5812584fc89d`,
source commit `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4`. [CHECKS.json](CHECKS.json) was generated before the source commit;
it binds every source blob, the exact commands, exit codes and log digests of every phase,
including the failures below. Nothing is published; no K acceptance or admission is claimed.
Executor: Claude, after the owner's «ok» to take the K1c handoff. Self-review only.

## What changed

- `api/src/gorgona_booking/db/migrations/0046_provider_receipt_routing.sql` (new)
- `api/src/gorgona_booking/db/provider_receipt_guard.py`
- `api/src/gorgona_booking/providers/authenticated_receipts.py`
- `api/tests/integration/test_provider_attestation_anchor.py` (new)
- `api/tests/integration/test_provider_receipt_routing.py` (new)
- `api/tests/integration/test_provider_routing_upgrade.py` (new)
- `api/tests/integration/test_provider_receipt_attestations.py` (K1c tests ported)
- `api/tests/integration/test_provider_attestation_upgrade.py` (bounded to 0045)
- `api/tests/integration/test_location_access.py` (restores the two new company policies)

Migration 0046 adds `gba.provider_verification_configs` and `gba.provider_receipt_routes`,
a composite key and an insert trigger from attestations to configs, and a refusal when K1c
attestations already exist. The caller-supplied `ReceiptVerifierBinding` and
`receive_signed_receipt` are removed; `receive_routed_receipt(pool, ingress_id, raw,
signature, key_store=…)` is the only entry point. The schema guard now covers six tables,
policy roles by name, the partial unique index and the privileges of both groups.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| D-01 | Routed receipt attests with the active config; no journals | `test_raw_signed_receipt_commits_minimal_attestation_and_no_money` ×3 | PASS |
| D-02 | Unknown ingress, missing/wrong key, revoked config/connection store nothing; no IDs, refs or keys in the error | `test_routing_and_authority_refusals_store_nothing` ×4, `test_bad_signature_is_refused_after_reading_only_authority_rows` ×2 | PASS |
| D-03 | Company A's ingress cannot store company B's event | `test_company_ingress_cannot_store_another_companys_event` | PASS |
| D-04 | Rotation: version 2 by trigger; old key refused; two active versions refused; supplied version/author replaced | `test_rotation_moves_verification_to_the_next_version_only`, `test_owner_supplied_version_and_author_are_replaced` | PASS |
| D-05 | Direct SQL denials for runtime, writer and owner; secret-like refs; permanence | anchor test; 10 runtime + 9 writer statements; config/route provisioning ×17; attest with missing/foreign/revoked config ×3; permanence for owner and superuser; one-way revocation ×2 | PASS |
| D-06 | Config revocation waits behind an in-flight receipt; next receipt refused | `test_config_revocation_waits_for_an_inflight_receipt_then_refuses_the_next` (observed `pg_locks` transaction wait) | PASS |
| D-07 | 0045 with attestation: 0046 refused, nothing changed; nonempty 0045 without: rows and checksums unchanged | `test_provider_routing_upgrade.py` ×2 | PASS |
| D-08 | Schema drift stops writer and runtime receipts | `test_authority_schema_drift_stops_routed_and_runtime_receipts` ×6 | PASS |
| D-09 | K1c tests through the routed entry point; full suite | ported module; full suite | PASS: 28 ported K1c cases; full suite green |

## Gates

| Gate | Exact observed outcome |
|---|---|
| New cases | 60 (1 anchor, 57 routing, 2 upgrade) |
| Final focused, PostgreSQL 18.6, own cluster | PASS: 404 passed in 267.91s (0:04:27) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 1988 passed, 4 skipped in 1970.01s (0:32:50); skips: 3 container checks and 1 optional tenant-site check, not requested in this run (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: exit 0; 312 source files |
| Web typecheck, lint, format, unit, build | PASS: exit 0; 114 unit tests (web unchanged) |
| Runtime npm audit | PASS: 0 vulnerabilities |
| Development npm audit | FAIL: 5 high, existing; dependencies unchanged; not required |
| Exact K CI, independent review | NOT TESTED: no publication authorization; self-review only |
| Real provider account, keys, admission | BLOCKED: separate owner authorization |

## Failures kept in the record

1. **red-1, product RED for R1.** On the baseline the anchor test failed: `DID NOT RAISE
   CheckViolation`; the writer attested with a random `verification_config_id`.
2. **red-2.** Four collection `ImportError`s: the routed entry point did not exist yet.
3. **dev-1.** 3 failed, 131 passed: the race monitor's pattern missed a quoted identifier, and
   the upgrade tests assumed an empty shared test database. Both were test defects.
4. **dev-2, a design defect.** 1 failed, 58 passed: 0046 added its validated key although a K1c
   attestation without authority existed. The migration owner works without a company context,
   so forced row security hid the row from the key validation. The design assumed the opposite.
   Fix: an explicit check under a temporary owner policy, as migration 0042 does, dropped in the
   same transaction. dev-3: 60 passed.

The same blind spot may affect earlier migrations that added keys over existing data on
forced-row-security tables. Most of them key a column added in the same migration, so old rows
hold NULL. A separate read-only audit has been suggested; nothing published was changed.

## Self-review (not independent)

- The writer remains a trusted global verifier: its process holds every key in its key store
  and can attest for any route. K1d makes the database choose the key and the company; it does
  not make SQL verify a MAC.
- Only authority rows are read before the signature check. An unknown ingress costs one indexed
  read. There is still no HTTP route, quota or acknowledgement.
- Revocation is one-way and serialized with in-flight receipts, but who revoked and when is not
  recorded. Configs have no expiry; rotation is an operator action.
- Provisioning is owner SQL only; there is no operator tool and no production key store.
- The secret-reference check refuses common Stripe key prefixes only; it is a guard against
  accidents, not proof that a value is not secret.
- Login roles are checked for their own extra rights only when they run the guard; the groups
  are checked on every run.
- R3 from the K1c review stays: 0044/0045 compare binding fields with `<>`. The new 0046
  functions use `is distinct from`.

## Unchanged

FIN-02 and STOCK-01 `planned`; ADR-0026 and ADR-0027 Proposed; H4 declarations and manual
attestation unchanged; connections `not_admitted` and test-mode only; migrations 0001–0045
unchanged, next 0047; main `fedd0f1`, published J `df88c20`; K not published.
