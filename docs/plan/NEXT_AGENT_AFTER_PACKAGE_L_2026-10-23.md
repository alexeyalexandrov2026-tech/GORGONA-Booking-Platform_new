# Next agent — after package L (BEAUTY-01 complete), 2026-10-23

Read this first, then `NEXT_AGENT_PACKAGE_L7C_2026-10-23.md` sections 5-7 (hard rules, slice process,
lessons): they still apply word for word, with the additions below.

## 0. The goal (owner)

Production for **all 39 directions at once**; package L (BEAUTY-01) was a build order of stage 3, not a
separate launch. Never plan or estimate a single-industry launch. Neutral words: specialist, service, visit,
materials, prepaid balance; for transport: carrier, trip, load, stop.

## 1. State (verified 2026-10-23)

- Package L is complete: L1-L7c screens and flows, L8 review fixes (15 findings), L8c acceptance, L9 closing
  the two named gaps. The [acceptance record](evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md) shows
  **L-01..L-12 PASS**.
- Branches are **stacked** and each pushed for CI only, **no PR**. The last head carries everything:
  `codex/package-l9b-commission-reversal` at `8b6b37d` (CI SUCCESS run 40040514685). Earlier heads:
  L8a `ef71142`, L8b1 `c9434b7`, L8b2 `ee68362`, L8c `58c1c72`, L9a `78e5df2` — all CI green
  (L8a's own run failed on two flaky specs, fixed in `c9434b7`).
- Last full suite: **2563 passed, 4 skipped**. Next migration **0074**.
- Worktree in use: `C:/Users/alexa/.codex/worktrees/package-l7b2b/Gorgona Booking`; Python interpreter:
  `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking/api/.venv/Scripts/python.exe`
  (do not touch that worktree otherwise; never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`).
- Latest run folders (copy their `runner.py`, `run_gates.py`, `write_record.py`):
  `GorgonaBookingTests/package-l9-zod-20261023-ed84938`, `package-l9b-20261023-78e5df2`.

## 2. Waiting for the owner (do not act without their word)

1. Mark BEAUTY-01 technically accepted in the readiness registry.
2. Bring `main` up to the package L chain (fast-forward or merge). `main` still lacks Next.js 16.4.2 and
   zod 4.6.7 (security fixes) until this happens.

## 3. Next: stage 3, TMS-01..03 (carrier first)

From the master plan's stage 3 (`GORGONA_MASTER_PLAN.md`, rows TMS-01..03):

- **TMS-01** an interstate trip with several loads and stops, partial delivery and vehicle replacement keeps
  its history.
- **TMS-02** a dispatcher works only within the scope each carrier granted; revocation and expiry forbid
  operations.
- **TMS-03** stale telematics and unknown hours-of-service never give a positive clearance; a repeated event
  never changes a delivery twice.

Start as package L did: read the plan sections for TMS, write `PACKAGE_M_PLAN_<date>.md` with M-01.. criteria
and slices (carrier first, then the independent dispatcher, then broker/3PL — build order, not launches), commit
the design, then failing tests first. Ask the owner in Russian before anything that needs their word.

## 4. New lessons from L8-L9 (add to the L7c handoff's list)

- **Never pipe `write_record.py` to `tail` before a commit**: run it, check its exit code, then commit with
  `&&`. A hidden failure let a code commit go out before its record once (L9b).
- **Write evidence files before `git add`**: the GateGuard hook blocks the first Write of a file; a commit in
  the same step then carries the placeholder (happened in L8c and L9b). Check the file content first.
- **Python on Windows writes CRLF with `write_text`**: use `write_bytes(text.encode())`, and normalise
  `\r\n` when matching; an edit script failed silently on CRLF and a chained run continued (L9b dev-7).
- **Chain with `&&`, not `;`**, when a later step depends on an earlier one.
- **Long Python heredocs break in this shell**: write scripts with the Write tool into the scratchpad.
- **New management routes must be registered in `web/lib/management-contracts.ts`** (strict response
  contracts), and the web unit examples in `web/tests/*-contracts.spec.ts` must carry new fields.
- **Test dates**: `booking_support.at()` is in 2031; anything relative to now (cancellation windows,
  no-shows) needs visits a few hours from now (`fee_policy_support.soon_visit`, `past_visit`).
- **Shared seeders**: `_started_visits` (desk wrapper) also seeds L9a's missed visits; wrappers that reuse it
  must check only their own visits.
- **npm audit can turn red without any change** (a new advisory appeared mid-day); name it in the record and
  fix it in its own commit with its own gates.
- A credited visit invoice no longer blocks a commission (L9 decision 85): redemptions settle, refunds are
  reversed by `POST .../commission/reversal`.
