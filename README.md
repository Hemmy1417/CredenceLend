<p align="center"><img src="docs/assets/credencelend-mark.svg" width="140" alt="CredenceLend"/></p>

# CredenceLend - Evidence-Based Credit Assessment for DeFi Lending

**A reusable GenLayer Intelligent Contract that decides, under validator consensus, what a borrower's committed evidence supports under a lender's policy - and treats that evidence as hostile.**

A lender publishes a versioned policy that names which issuers it trusts for each kind of evidence. A borrower - the signing wallet, never a declared identity - commits documents, each bound to the sha256 of its exact bytes. One consensus round has every validator fetch and hash-verify the documents; code reads every number from structured issuer documents and decides every hard fact; a model panel is asked only what needs reading, and every finding it makes must carry quotes each validator re-checks against its own bytes. Code then computes a bounded score, a risk band, a maximum exposure and LTV, a verdict and reason codes, and stores an immutable assessment any lender or contract can read in one view.

Canonical deployment: [`0x25FEDE0811b95697A333633b611B67f8A250eE66`](https://explorer-studio.genlayer.com/address/0x25FEDE0811b95697A333633b611B67f8A250eE66) on GenLayer StudioNet, byte-identical to `contracts/credencelend.py` at commit `a261d28` (see `docs/deployment.md`).

## At a glance

| Question | Answer |
|---|---|
| What is CredenceLend | A standalone Intelligent Contract primitive: a credit-evidence assessment layer for DeFi lending. No frontend, no backend, no funds. |
| What does it decide | Whether a borrower's evidence is authentic, current, consistent and sufficient under a policy, and what score (0-100), band, exposure and LTV it supports. |
| Why GenLayer must decide it | The numbers are code. Whether an employer's attestation is genuine, whether a borrower's statement contradicts the lender's records, whether a liquidation is plausibly explained, whether a credit page is talking to its evaluator: that is reading. One model behind one backend is an authority the borrower cannot challenge and a second lender cannot reuse. |
| What evidence it uses | Only documents the borrower committed, from the prefixes the lender pinned per category. Every node verifies the hash before reading a byte. The borrower's own statement can explain; it never supplies a fact. |
| How consensus works | `gl.vm.run_nondet_unsafe` once per round. Each validator reproduces the round from its own fetch and model call, gates the leader's payload against its own bytes, and agrees only if every row, fact, scan, panel state and finding state matches. The payload carries no score: validators agree on the score by construction. |
| How a lender consumes it | `is_eligible(wallet, policy_id, as_of)` is the fail-closed shortcut; `assessment_status(assessment_id, as_of)` returns verdict, score, band, exposure, LTV, freshness and consumability; `get_assessment` is the full record with receipts and reason codes. |
| What tests prove it works | 279 Direct Mode tests on the official `genlayer-test` runner, including all 30 brief attacks, forged leaders through the captured validator closure, hostile model output, scoring boundaries and the appeal lifecycle; a mutation sweep; `genvm-lint check`; preflight; a readable sample assessment. See "Verified". |

## What it is

- **Identity is the signer.** `register_borrower` binds the profile to `gl.message.sender_address`. A structured document counts only if its `wallet` field is that exact address; a text document only if it names it.
- **The lender pins the sources.** A policy lists, per category, the trusted prefixes its documents must come from. Anything else is not fetched and not counted.
- **Hash-bound, append-only evidence.** A borrower can relocate a document (same bytes) or retire one an assessment found stale, never withdraw one.
- **Code decides the numbers and the hard facts.** Integer facts from structured documents; wallet binding, freshness, arithmetic, omitted loans, conflicting exports, overstated claims, injection phrases, hidden text, cross-borrower reuse.
- **Consensus decides the reading.** Document authenticity, contradicted statements, conflicting issuers, liquidation explanations, instructions the marker list missed.
- **Code derives the verdict** from findings, then the score, band, exposure and LTV. A high score never overrides a suspicious, missing, stale, conflicting or unavailable finding.
- **Appeals preserve history.** A reassessment re-reads the appealed assessment's own evidence plus new evidence under the same policy version, as a new record naming what changed.
- **An on-chain adversarial-test engine.** The lender registers attacks and controls against a policy version; anyone runs them through the real pipeline; a rule change is checked by replaying them onto the new version.

## How it works

### For the lender (policy owner)

1. `register_policy(definition_json)`: a strict JSON definition, stored canonically and covered by `definition_hash`.
2. `register_adversarial_case` for the attacks and legitimate cases the rules must handle; anyone calls `run_adversarial_case`.
3. To change the rules, `publish_policy_version`, then `replay_adversarial_case` onto it. Assessments under the old version become `STALE` at once.
4. Read `is_eligible` or `assessment_status` with your own clock.

### For the borrower

1. `register_borrower(declared_purpose)` from the wallet being assessed.
2. Publish each document at a stable https location, then `submit_evidence` with its sha256.
3. `request_credit_assessment(wallet, policy_id)` (the borrower or the lender, subject to the policy's cooldown).
4. Within the appeal window, commit new evidence and `submit_appeal`; then `request_reassessment`.

## Verdicts

| Verdict | Meaning | Exposure / LTV | Eligible |
|---|---|---|---|
| `APPROVED` | evidence sufficient and consistent; score at or above `minimum_score` | band and policy caps, bounded by income | yes, while fresh |
| `REVIEW_REQUIRED` | sufficient evidence; score between `review_score` and `minimum_score` | computed, for a human decision | no |
| `REJECTED` | sufficient evidence; score below `review_score` | 0 | no |
| `SUSPICIOUS` | a hard fact, a registry hit, or a grounded panel finding of manipulation or injection; score capped | 0 | no |
| `CONFLICTING_EVIDENCE` | records or issuers contradict each other | 0 | no |
| `INSUFFICIENT_EVIDENCE` | a required category unmet, or too few counted documents | 0 | no |
| `STALE_EVIDENCE` | a required category met only by documents older than the policy allows | 0 | no |
| `SOURCE_UNAVAILABLE` | an allowed document unreachable, or its bytes changed | 0 | no |
| `INCONCLUSIVE` | a malformed document, an unusable model answer, or an undecided finding | 0 | no |

Freshness (`assessment_status`, `is_eligible`): `RELIABLE`; `STALE` when the validity period passed, a counted document aged past the policy limit, or the policy version is no longer ACTIVE; `BLOCKED` for `SOURCE_UNAVAILABLE`; `UNKNOWN` for a malformed or earlier clock.

## Scoring

Integer arithmetic in `_score`; every component is stored. Full rules in `docs/scoring-policy.md`.

```text
score = clamp(0, 100, base + repaid loans (capped) - defaults - liquidations
                      (less if explained) + income (capped) + history + coverage
                      - leverage penalty)
```

| Score | Band | Demo policy LTV cap | Demo exposure cap |
|---:|---|---:|---:|
| 0-29 | VERY_HIGH | 0 | 0 |
| 30-49 | HIGH | 25% | 500,000 |
| 50-69 | MODERATE | 40% | 1,500,000 |
| 70-84 | LOW | 60% | 3,000,000 |
| 85-100 | VERY_LOW | 75% | 5,000,000 |

Exposure is also capped by the policy maximum and by verified monthly income times `income_exposure_multiple`. Thresholds and caps are policy-configurable.

## Lifecycle

```text
register_policy ------------> v1 ACTIVE --publish_policy_version--> v1 SUPERSEDED, v2 ACTIVE
                                  |                                  (v1 assessments STALE)
register_borrower                 |
submit_evidence x N               v
request_credit_assessment --> consensus round --> CA-000001 (immutable)
                                                     |
                  within appeal_window: submit_appeal (new evidence only)
                                                     |
                  request_reassessment (same version, same + new evidence)
                                                     v
                                          CA-000002 REASSESSMENT, appeal_of CA-000001,
                                          changes: verdict, score, band, reason codes
```

## Contract

`contracts/credencelend.py`, runner `py-genlayer:1jb45aa8...` (pinned), 13 writes, 15 views.

### Write methods

| Method | Who | Does |
|---|---|---|
| `register_policy(definition_json)` | anyone (becomes owner) | version 1 of a policy |
| `publish_policy_version(policy_id, definition_json)` | owner | a successor; the previous version is SUPERSEDED |
| `revoke_policy_version(policy_id, version)` | owner | terminal |
| `register_borrower(declared_purpose)` | the wallet itself | one profile per wallet |
| `submit_evidence(category, url, sha256, issuer_or_protocol, description, claimed_value, currency)` | borrower | `EV-nnnnnn` |
| `relocate_evidence(evidence_id, url)` | borrower | same bytes, new location |
| `retire_evidence(evidence_id)` | borrower | only after an assessment saw it stale |
| `request_credit_assessment(wallet, policy_id)` | borrower or owner | the consensus round |
| `submit_appeal(assessment_id, new_evidence_ids, reason)` | the assessed borrower | once, within the window |
| `request_reassessment(appeal_id)` | borrower or owner | the consensus round; refused if the version was replaced |
| `register_adversarial_case(...)` | owner | a case bound to a policy version |
| `run_adversarial_case(case_id)` | anyone | the consensus round; records pass or fail |
| `replay_adversarial_case(case_id, target_version)` | owner | the case onto another version |

### Read methods

`get_config`, `health_check`, `get_policy`, `definition_hash`, `get_borrower_profile`, `get_evidence`, `get_assessment`, `get_latest_assessment`, `get_assessment_history` (paged), `get_appeal`, `assessment_status`, `is_eligible`, `get_adversarial_case`, `list_adversarial_cases` (paged), `get_stats`. Views never revert on unknown ids and read bounded slices only.

## Verified

| Check | Command | Result |
|---|---|---|
| Direct Mode | `python -m pytest tests/direct -q` | 280 passed |
| Preflight | `python scripts/preflight.py` | 36 checks, 0 failed |
| GenVM validation | `genvm-lint check contracts/credencelend.py --json` | ok, 28 methods, 0 errors (I200 informational) |
| Lint | `ruff check .` | clean |
| Mutation sweep (deployed bytes) | `python scripts/mutation_check.py` | 106 mutations, 106 killed |
| Sample assessment | `python scripts/run_direct_mode.py` | APPROVED, 78/100, LOW band |
| Integration (the deployment) | `CREDENCELEND_LIVE_WRITES=1 pytest tests/integration -v` | 5 passed |
| Live run (the deployment) | `python scripts/live_scenarios.py` | 103 transactions: 5/5 real borrowers, 28/28 adversarial cases, the rule change and 7 refusals |

On the deployment, with real models: a strong borrower APPROVED at 93; a
liquidation REVIEW_REQUIRED at 68 on the records alone and APPROVED at 78
after an appeal whose statement the panel found explanatory, the original
record preserved; an impostor's copied history SUSPICIOUS; all 28 threat-model
cases matching Direct Mode; publishing a stricter policy version making the
earlier approval `STALE` and not eligible at once. 24 of the 28 cases are
decided by code or the registry and are asserted by the run; 4 are
panel-decided and are recorded as observed. `SUBMISSION.md` has the full
tally, and `deploy/live_scenarios_transcript.json` every transaction.

## Repository

```text
contracts/credencelend.py       the contract
tests/direct/                   Direct Mode suite (seven modules, brief section 19)
tests/integration/              StudioNet checks against the canonical deployment
fixtures/                       evidence documents, demo wallets, the case catalogue
scripts/generate_fixtures.py    regenerates fixtures/ byte for byte
scripts/run_direct_mode.py      one readable sample assessment
scripts/preflight.py            repository invariants
scripts/mutation_check.py       mutation kill sweep with an accept-control
scripts/deploy_studionet.py     deploy and verify source parity
scripts/inspect_deployment.py   read-only inspection of a deployment
scripts/live_scenarios.py       the live run on StudioNet
docs/                           architecture, threat model, scoring, evidence, consensus, deployment
```

## Getting started

```bash
python -m pip install -r requirements-test.txt
```

```bash
python scripts/fetch_genvm_bundle.py
```

```bash
python -m pytest tests/direct -q
```

```bash
python scripts/run_direct_mode.py
```

`fetch_genvm_bundle.py` seeds the GenVM runner bundle that `genlayer-test` 0.29.2 cannot fetch on a cold cache. No key or network account is needed for anything above; `docs/deployment.md` covers StudioNet.

## Security

Everything retrieved is untrusted data: code scans for instruction phrases and hidden text before any model is asked, the prompt frames every document and label as the borrower's claim, and no model produces a number. `docs/threat-model.md` walks all thirty brief attacks with their tests.

## Limitations

- A hash proves bytes have not changed since commitment, not that the issuer is genuine; authenticity rests on the lender's trusted prefixes.
- `minimum_evidence_count` counts documents, not independent publishers; independence comes from the required categories the lender pins to different issuers.
- Everything committed is public on-chain. This is not for private financial records.
- The score measures verified evidence against a policy. It is not a guarantee of repayment and does not remove lending risk.
- Panel findings depend on validator models; they are grounded and compared strictly, and an undecided finding keeps the assessment `INCONCLUSIVE`.
- Views take the caller's clock (`as_of`); a view has no clock of its own.

## Not production-ready

No audit; demo issuers are fixtures in this repository; the policy is a demo; StudioNet is a test network.
