# Architecture

CredenceLend is one GenLayer Intelligent Contract, `contracts/credencelend.py`.
It has no frontend, no backend and no payouts. A lender publishes a lending
policy; a borrower commits evidence; one consensus round produces an immutable
assessment; any lender or contract reads it.

## The decision

> Given this lending policy, is the evidence this borrower committed from the
> policy's approved sources authentic, current, consistent and sufficient, and
> if so, what bounded score, risk band, exposure and LTV does it support?

## The boundary

| Decided by code (deterministic, identical on every node) | Decided by consensus (a model panel, compared finding by finding) |
|---|---|
| Identity: the borrower is the signing wallet | Whether a text document shows signs of manipulation |
| Which documents the policy allows, and from which prefixes | Whether the borrower's own statement asserts facts the records contradict |
| Hash verification of every byte before anything reads it | Whether two issuers' documents give incompatible accounts |
| Every number, read from structured issuer documents | Whether a liquidation is plausibly explained, with quotes from both sides |
| Wallet binding, freshness, arithmetic, omitted loans, future dates | Whether a document contains an instruction the marker list missed |
| Injection markers and hidden text | |
| Duplicate and cross-borrower registries | |
| Score, band, exposure, LTV, verdict, reason codes, summary | |
| Appeals, reassessment, freshness, history | |

The model is never asked for a number and never asked whether to lend. Its
answers are findings with quotes; code turns findings into a verdict.

## State

| Map | Key | Holds |
|---|---|---|
| `policies` | `policy_id@version` | owner, status (ACTIVE / SUPERSEDED / REVOKED), canonical definition, `definition_hash`, case ids |
| `policy_heads` | `policy_id` | latest version |
| `borrowers` | wallet | declared purpose, `metadata_hash`, evidence ids |
| `evidence` | `EV-nnnnnn` | category, canonical URL, sha256, issuer label, claim, `committed_seq`, retired, stale_seen |
| `assessments` | `CA-nnnnnn` or `AC-nnnnnn-R1` | the full canonical record with `record_digest` |
| `history` | `wallet\|policy_id` | assessment ids, at most 12 |
| `appeals`, `appeal_of` | `AP-nnnnnn`, assessment id | the appeal and its one-per-assessment index |
| `cases` | `AC-nnnnnn` | adversarial cases and their observed results |
| `evidence_registry` | sha256 | `seq\|wallet` of the first commitment of those bytes |
| `loan_registry` | `issuer\|loan_id` | `seq\|wallet` of the earliest commitment naming that loan |

Every map is keyed; no view scans an unbounded collection. Records are written
once and never modified; a reassessment is a new record that names the one it
answers.

## One assessment

```text
request_credit_assessment(wallet, policy_id)
  |
  |- code: policy ACTIVE? caller = borrower or lender? cooldown elapsed?
  |- code: items = the borrower's active evidence, each with allowed/trusted
  |        from the policy's per-category prefixes
  |
  +- gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
  |    every node, independently:
  |      fetch each ALLOWED item; sha256 the raw bytes BEFORE reading them
  |      structured items -> integer facts (or UNPARSEABLE)
  |      text items -> wallet link, injection markers, hidden text
  |      _plan: code indicators; which questions the panel can still change
  |      panel only if needed -> findings, each quote grounded in own bytes
  |    validator: gate the leader payload with its OWN texts, then compare
  |      rows, facts, scans, panel state and every finding's state and layer
  |
  |- code: gate the ratified payload again (_parse_payload)
  |- code: registries -> CROSS_BORROWER_REUSE
  |- code: _derive -> verdict, score, band, exposure, LTV, reason codes
  +- store the record; append history; register loans; mark stale items
```

The panel is not convened when an allowed document could not be examined,
when a hard fact is already present, or when nothing is left to ask (for
example a borrower whose evidence is all structured). The record states which
(`panel_state`, `panel_reason`).

## Single file

The brief sketches `models.py`, `policy.py`, `evidence.py`, `scoring.py`,
`adjudication.py` and `security.py`. A multi-file contract needs the
`py-genlayer-multi` runner; this contract pins the single-file runner that
StudioNet runs and that `genvm-lint check` validates
(`py-genlayer:1jb45aa8...`). The file keeps the same separation as sections, in
this order: constants and enums, pure helpers (URL admission, policy
definitions, evidence input, structured documents, scans, grounding), the round
plan, the nondeterministic procedure, the structural gate, derivation (score,
band, verdict, summary, receipts), storage records, then the contract class.
Every helper above the class is a pure function the test suite calls directly.

## Where each brief requirement lives

| Brief | Symbol |
|---|---|
| Borrower profile, identity | `register_borrower`, `BorrowerProfile` |
| Lending policy, versions | `_parse_definition`, `register_policy`, `publish_policy_version`, `revoke_policy_version` |
| Evidence item and admission | `submit_evidence`, `_evidence_input_error`, `_url_parts` |
| Evidence receipt | `_receipts` |
| Credit assessment | `request_credit_assessment`, `_assess`, `_derive` |
| Score model | `_score`, `_band` |
| Adversarial test case | `register_adversarial_case`, `run_adversarial_case`, `replay_adversarial_case` |
| Appeals and reassessment | `submit_appeal`, `request_reassessment` |
| Freshness and consumption | `_freshness`, `assessment_status`, `is_eligible` |
| Consensus | `_node_round`, `_parse_payload`, `_first_difference`, `_validator_decision` |
