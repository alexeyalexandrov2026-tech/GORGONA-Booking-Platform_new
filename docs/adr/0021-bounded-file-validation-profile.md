# ADR-0021 — Bounded file validation before E2 persistence

Status: implemented security prerequisite, awaiting exact-commit CI. This clarifies
the initial file profile in [ADR-0020](0020-counterparties-documents-and-contracts.md);
it does not accept or enable the documents module.

## Context and observable acceptance

E2 requires deterministic format checking before bytes enter PostgreSQL and before
any upload/download route is published. The current stack has no PDF/image parser.
The owner selected raw uploads, no new dependencies, 10 MiB per file, no simulated
antivirus, and staging/production refusal until scanning is configured. Signature
checking and searches for dangerous strings do not establish PDF syntax or safety.

This increment is intentionally one reviewable prerequisite: a typed, bounded,
side-effect-free file validator and preservation of existing API CSP policies.
Acceptance: complete supported structure; exact media/size/hash/name metadata;
rejection of unsupported or ambiguous features, active PDF capabilities and limit
violations; actual red-to-green regressions; existing workflows remain unchanged.
Persistence, authorization of uploads and document UI require the next E2 increment.

## Decision and reuse

- Reuse Python stdlib `zlib`, `hashlib`, `struct`, `unicodedata`, and existing typed
  `DomainError` plus `FramingPolicyMiddleware`. No service, storage, dependency or
  second document catalog is introduced.
- Keep parsing in `business/pdf_validation.py`, format orchestration and immutable
  metadata in `file_validation.py`, domain errors in `file_errors.py`.
- Signature must agree with the declared type. A complete file is 1..10,485,760
  bytes. Metadata contains SHA-256, exact byte size, detected type, sanitized name,
  validator version `gorgona-file-profile-v1` and `not_scanned`.
- One aggregate decoded-byte budget of 32 MiB per call. Use a positive `max_length`
  of remaining+1, require `eof`, refuse overflow/tails/trailing compressed bytes;
  never use unbounded `flush()`. [Python zlib](https://docs.python.org/3.14/library/zlib.html)
- Filename: NFC, basename, no control/bidi/reserved characters; Windows reserved
  basenames checked through NFKC; detected type controls extension; at most120
  characters. An input name over4096 characters is refused.
- Preserve existing API CSP fields as an independent response policy and append
  `frame-ancestors 'none'` as another policy. A permissive existing framing field
  cannot override the additional policy. Customer HTML behavior stays governed by
  its existing embedding rules. [W3C CSP](https://www.w3.org/TR/CSP3/#multiple-policies)

## Supported profile and limits

**PDF:** versions1.0–1.7, one classic xref/trailer, generation-zero objects, direct
stream lengths, raw or Flate streams (also a one-element Flate filter array).
Validate object syntax, names/#xx aliases, references, exact xref offsets, trailer,
page-tree root/parents/counts, inherited resources and positive page geometry.
Dictionary keys, Type/Subtype and actions have an explicit supported vocabulary;
custom names are allowed inside direct resource-map dictionaries. Separately
referenced map dictionaries with custom keys can be refused by the global
vocabulary; this conservative profile does not resolve their context.
Unknown capabilities fail closed.
Bounds:4096 object numbers,100,000 tokens,32 nesting levels,127 decoded name bytes
(381 encoded),381-byte word scan. Compressed streams are inspected for active
names with the same aggregate budget.

Refuse encryption, incremental updates, object/xref streams, unsupported/indirect
filters, DecodeParms/predictors, external streams, dangling references, duplicate
keys, extra payload and active capabilities. These include JavaScript/JS, launch,
attachments/EF/FileAttachment, associated files, rich media, XFA, submission/import,
external GoToR, embedded GoToE, and3D/OnInstantiate lifecycle scripts. OpenAction
alone is allowed for a supported passive destination or local GoTo action.
[Adobe PDF reference](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.6.pdf),
[Adobe3D lifecycle](https://opensource.adobe.com/dc-acrobat-sdk-docs/library/plugin/Plugins_3D_samples.html)

**PNG:** noninterlaced8-bit gray/RGB/gray-alpha/RGBA; dimensions1..16,384,
at most16,000,000 pixels,4096 chunks; CRCs, ordering, expected decompressed scanline
length and filter codes0..4, complete IEND with no appended payload. Limited
uncompressed metadata is validated. Palette/interlaced/animated PNG, compressed
metadata and unknown chunks require a later reviewed profile.
[W3C PNG](https://www.w3.org/TR/png/)

**JPEG:** one8-bit baseline frame and one scan, gray or3 components; quantization,
Huffman table structure/symbol bounds and marker/scan/EOI structure. Interleaved
scans have at most10 blocks per MCU. [Upstream decoder](https://github.com/libjpeg-turbo/libjpeg-turbo/blob/main/src/jdinput.c)
Reject
progressive/arithmetic/lossless, restart, multi-scan, truncated or extra-payload
forms. This does **not** decode entropy coefficients or prove rendering correctness.

These compatibility limits exclude many valid real-world files, including some
signed/optimized PDFs and phone images. A later profile needs its own dependency
decision if a maintained reader/decoder is adopted, version, adversarial fixtures
and independent acceptance. Do not relax a refusal merely to accept a fixture.

## Safety and next integration

Structural validity is not a malware-free, script-safety-for-all-readers or rendering
verdict. Decoder/parser memory includes input bytes, decoded buffers and temporary
values;32 MiB is an output budget, not a measured process-memory ceiling. No public
upload route or metadata persistence is added in this increment. Documents remains
`planned`, registry version1, existing business baseline booking-only.

Next E2 integration must refuse staging/production uploads before reading bytes,
perform short initial authorization then final transactional reauthorization after
stream reading, preserve typed idempotency/audit, enforce both module gates on
counterparty links, recheck download integrity, and never preview files inline.
No antivirus is installed or simulated. [OWASP uploads](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

## Verification

See [E2-A evidence](../plan/evidence/2026-10-05-file-validation/ACCEPTANCE.md).
Existing migrations, RLS boundaries, permission map, modules and web source stay
unchanged. No merge, deployment, production migration or cloud action is authorized.
