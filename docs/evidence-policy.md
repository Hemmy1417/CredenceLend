# Evidence policy

## What a borrower commits

`submit_evidence(category, url, sha256, issuer_or_protocol, description,
claimed_value, currency)` records a location and the sha256 of the exact bytes
that location must serve. Nothing is fetched at submission; every assessment
fetches under consensus and verifies the hash before reading a byte.

| Field | Rule |
|---|---|
| `category` | one of nine: ONCHAIN_ACTIVITY, REPAYMENT_HISTORY, LENDING_POSITIONS, LIQUIDATION_RECORD, INCOME_STATEMENT (structured JSON); ATTESTATION, REGISTRY_RECORD, CREDIT_REPORT, BORROWER_STATEMENT (text) |
| `url` | `https` only; no credentials, no port but 443, no IP literal of any form, no localhost or `.local` / `.internal` / `.home.arpa` / `.lan` names, no fragment, backslash, encoded dot or separator, dot-segment or empty segment; at most 300 characters. Stored canonically. |
| `sha256` | 64 lowercase hex characters |
| `issuer_or_protocol`, `description` | required text, bounded, no control characters |
| `claimed_value`, `currency` | the borrower's own claim (-1 for none). Never a fact: code checks it against the verified document (`CLAIM_OVERSTATED`). |

At most 8 active and 24 total items per borrower. The same bytes cannot be
committed twice by one borrower, nor the same location while it is active.
Evidence is never withdrawn: `relocate_evidence` points an item at a new
location (the sha256 is unchanged, so only the same bytes can be read), and
`retire_evidence` is allowed only for an item an assessment recorded as stale.
A borrower cannot shop for a better assessment by dropping the inconvenient
document.

## Identity

The borrower is the signing wallet (`gl.message.sender_address`). There is no
declared identity field. A structured document counts only if its `wallet`
field is exactly that wallet (lowercase hex, full address); a text document
counts only if its text names it. A document about another wallet is the hard
fact `WALLET_MISMATCH`, an address one digit away included (case A06).

## Provenance: the lender pins the sources

A policy lists, per category, the `trusted_prefixes` its documents must come
from. A prefix is a canonical https path ending in `/` with no query.

- A category the policy does not list is **not allowed**: its items are never
  fetched and never counted (receipt `allowed: false`, row `NOT_ALLOWED`).
- A listed category is allowed only from one of its own prefixes. A prefix for
  one category does not admit another category; a lookalike folder beside a
  trusted one (`.../lendhub-verified/` next to `.../lendhub/`) is not the
  trusted prefix.
- `BORROWER_STATEMENT` is the exception: it is allowed from anywhere and never
  trusted. It is shown to the panel so it can explain or be contradicted, and it
  never supplies a fact, a count or coverage. A policy cannot require it.

The category a borrower declares is a claim. A structured document must say the
same thing about itself (`document_type` equal to the category) or it does not
parse; the panel prompt names every declared label as the borrower's claim.

## Structured documents (issuer JSON)

Every structured document carries `document_type`, `wallet`, `issuer` and an
`as_of` date, plus its category's fields. Amounts are integers in minor units;
a float, a boolean, a string, a negative number, NaN, an integer above 10^15 or
a 5000-digit integer makes the document `UNPARSEABLE` (cases A24, A25).

| Category | Fields code reads | Code checks |
|---|---|---|
| ONCHAIN_ACTIVITY | months_active, transaction_count, volume_minor | wallet, date |
| REPAYMENT_HISTORY | total_loans; loans (loan_id, principal_minor, opened, status) | listed loans = total_loans (else `DOCUMENT_ALTERED`, case A10); same loan reported differently across exports (`RECORD_CONFLICT`, case A14) |
| LENDING_POSITIONS | positions (collateral_minor, debt_minor) | wallet, date |
| LIQUIDATION_RECORD | events (date, amount_minor, loan_id, cause) | wallet, date |
| INCOME_STATEMENT | period_months, total_minor, lines | lines sum to the total (else `DOCUMENT_ALTERED`, case A02) |

## Text documents

Attestations, registry records, credit reports and statements are read by the
panel only if their bytes verified and they name the borrower's wallet. Before
any model sees them, code scans every examined document for instruction
phrases (`INJECTION_MARKER`) and for zero-width or bidirectional characters and
hiding styles (`HIDDEN_TEXT`); either is a hard fact and the panel is not
convened.

## Receipts

Every item gets a receipt in the record: `source_locator`, `source_identity`
(the trusted prefix it matched), `trusted`, `allowed`, `source_reachable`,
`retrieved_at`, `content_hash`, `hash_verified`, `status`, `freshness_status`
(FRESH, STALE, FUTURE_DATED, UNDATED for text), `relevance_status`,
`authenticity_status` with its deciding layer, `conflict_status`, `counted`, a
`summary` and a fixed per-category `limitations` note.

## Registries

`evidence_registry` records, per sha256, the first wallet to commit those
bytes and the commitment sequence; `loan_registry` records, per
`issuer|loan_id`, the earliest commitment that named that loan in a document
about the committing wallet. An examined document first committed by another
wallet, or naming a loan another wallet committed first, is
`CROSS_BORROWER_REUSE` (cases A05, A28). Order is by commitment sequence, not by
assessment order, so a later copy never taints the first committer; loans in a
document about someone else are never registered to the wallet that committed
it (so an impostor cannot pre-register a victim's loans). Adversarial cases read
both registries and never write them.

## What is not accepted

Private credentials, API keys, cookies, session tokens or seed phrases have no
field and must never be put in a URL. Everything committed is public on-chain,
and every fetched document must be publicly reachable; this contract is not for
private financial records.
