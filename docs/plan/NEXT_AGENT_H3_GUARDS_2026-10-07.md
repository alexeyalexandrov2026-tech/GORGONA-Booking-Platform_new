# Next agent handoff — H3 settlement guards, 2026-10-07

This continues the published H2 delivery; read
[the H2 handoff](NEXT_AGENT_H2_2026-10-07.md) first for everything not changed
here. Production, provider actions, money transmission, merge and readiness
promotion remain unauthorized.

## State

- Repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
- Branch `codex/package-h3-settlement-guards`, checkout
  `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-guards`, from published H2
  `e93ca5cae9400b7e9c2207089dda0ee101b7517d` (draft PR16, unmerged).
- This file does not record its own commit. Read the actual HEAD, origin, the
  draft PR stacked on PR16 (if published) and its exact-SHA CI. Nothing is
  merged; do not merge.
- The H2 checkout `gorgona-h2-settlements` is clean at `e93ca5c`.

## What this slice did

An independent static money/state review of H2
([report](evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md))
found no break of `P + C + R <= A`, but three money-relevant gaps and one guard
gap. They are fixed by forward migration `0025_settlement_guards.sql` and the
service, with red → green evidence and an upgrade check on a populated `0024`
database: [validation](evidence/2026-10-07-h3-settlement-guards/VALIDATION.md).

- F1 one identity for an external fact (`gba.external_identity_key(value,
  rule)`): NFKC, invisible format characters removed, ends trimmed, Unicode
  lowercase. Interior whitespace is kept (`preserve`, the only rule) because
  manual attestations have no provider contract; raw text is stored unchanged.
- F2 cash accounts and issued control accounts stay disjoint across the book.
- F3 payment posting date on or after the accrual; the attested external date
  is not after today in the business time zone (`gba.business_timezone`: the
  one zone of the business's locations, else UTC).
- F4 readiness guard approves column-level `references` and both helpers.
- The four H2 test gaps (FK drift, `opening` legacy entry, recovery while OFF,
  settlement-row deletes) now have tests.

Final local full suite with mandatory PostgreSQL and browser: 1053 passed, 4 skipped, 445.56s
(3 container checks NOT TESTED locally, optional tenant site).

## Next steps, in order

1. Exact-SHA CI of the published head, then an independent review of `0025`
   and the `confirm` changes.
2. Owner review of the five decisions in the validation file, above all the UTC
   fallback for a business whose locations span time zones.
3. Deploy note for later: the H2 application fails closed against a `0025`
   database, so migration and application go together.
4. Then the rest of H3 on top of this branch: credits, refund obligations and
   guarded corrections, as described in the H2 handoff. New migrations start at
   `0026`; `0025` becomes frozen once published.

## Working notes

- Same rules as H2: add each migration to `_MIGRATIONS`; the latest packaged
  function wins; restore damaged functions with `packaged_function`.
- `0025` creates no table, so it has no scope footer and the definition count
  stays 63.
- Keep SQL and test sources ASCII: write invisible or full-width characters as
  `\uXXXX` escapes (SQL regular expressions, Python strings). Tool inputs that
  decode JSON escapes can silently turn `\u00ad` into the invisible character.
- Write files with LF endings (`.gitattributes` is `eol=lf`); a Windows
  text-mode write produces CRLF.
- The private cluster on port 51470 under
  `%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007` was stopped after the
  runs. Its credential file stays there, outside Git. Clusters 51454, 51455,
  51458, 51456, 51460 and 51462 were not touched.
