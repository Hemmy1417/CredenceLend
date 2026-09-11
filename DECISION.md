# Decision record

Why CredenceLend, why this shape, and why it is a standalone Intelligent
Contract.

## The question it answers

> Given this lending policy, is the evidence this borrower committed from the
> policy's approved sources authentic, current, consistent and sufficient, and
> if so, what bounded score, risk band, exposure and LTV does it support?

## Delete-GenLayer test

Remove consensus and one of two things is left. Either a lender's own backend
reads the borrower's documents with one model and decides alone, and the
borrower cannot challenge a reading no one else performed, nor can a second
lender reuse it without trusting the first. Or a deterministic contract
scores on-chain activity only, which cannot read an employer's attestation,
tell an explained liquidation from a reckless one, or notice a credit page
addressed to its evaluator. What breaks is the part that needs reading: the
authenticity of text evidence, the contradiction between a borrower's claim
and an issuer's record, and whether a liquidation is plausibly explained.
CredenceLend has independent validators each fetch, verify and read the same
bytes and agree finding by finding, and it keeps every number in code.

## Portfolio collision analysis

Earlier builds by the same author that touch credit, and how CredenceLend
differs:

| Build | What it decides | Overlap | Why CredenceLend is not a copy |
|---|---|---|---|
| Kredo | a lending pool: an AI scores a borrower's on-chain footprint and the score sets collateral and APR | credit scoring, lending | Kredo scores a self-declared footprint, holds deposits and prices loans. CredenceLend holds no funds, scores nothing with a model, binds identity to the signer, admits only lender-pinned issuers, and is adversarial about every document. |
| Sentinel | a borrower's history and cited sources justify credit terms | credit, appeals | Sentinel's acceptance letter is the design brief of this contract: "borrowers control both the claimed identity and the sources used to justify credit terms, while validators do not bind the stored appeal evidence". Here identity is the signing wallet, sources are the lender's per-category prefixes, every stored field is consensus-bound, and an appeal re-reads the appealed assessment's own hash-bound evidence without touching the original. |
| Credence | identity verification | the name only | Credence verifies who someone is; CredenceLend assesses what verified evidence supports. |
| InsureShield, Tradera | whether committed documents satisfy a policy; fraud indicators | hash-bound evidence, code facts plus a panel, the adversarial-test engine | The closest ancestry and the reason the evidence model is trusted. InsureShield decides a claim; CredenceLend produces a bounded score, band, exposure and LTV from integer facts, adds identity binding, per-category provenance, freshness against evidence age, a loan registry across borrowers, and reassessment of the same evidence set. |

Reused deliberately, from builds that shipped and were reviewed: the pinned
StudioNet runner, hash verification before any read, "the model returns
findings, code derives the verdict", grounding stored quotes in each
validator's own bytes (S39), the per-finding equivalence rule (S21),
commitment-ordered registries, and the Direct Mode harness with validator
replay. Two InsureShield follow-ups are applied from the start: a quote joining
lines with a newline grounds as fragments, and the contradiction questions are
a partition (a contradiction involving the borrower's statement has exactly one
home).

## Ecosystem collision analysis

The GenLayer material reviewed for this build (the official contract-writing
skills and example contracts, including a prediction market) covers web
oracles, markets and escrow patterns; none of it is a credit-assessment
primitive with an explicit evidence, identity and fail-closed model. This is a
statement about what was reviewed, not a survey of every GenLayer project.
Off-chain credit scoring and on-chain reputation scores are single-authority or
activity-only by construction.

## Alternatives considered

| Idea | For | Against | Score /25 |
|---|---|---|---|
| An AI credit score from a wallet's history | simple interface | a model-produced number cannot be agreed field by field; activity is not capacity; collides with Kredo | 9 |
| A lending pool with AI-set terms | economic substance | holds funds; the brief is a standalone assessment primitive; collides with Kredo | 12 |
| Undercollateralized loans backed by off-chain bank data | real demand | private data cannot be public on-chain | 8 |
| **CredenceLend: evidence-based assessment with adversarial testing** | documents need reading; borrowers are adversarial; the output is reusable by any lender or contract | panel agreement across model families is the hardest risk | **21** |

Scoring: problem reality (5), GenLayer load-bearing (5), reusability (5),
testability of the safety claims (5), collision risk (5).

## Consequences

- A lender can rely on an assessment without trusting whoever requested it:
  the record names the policy version and its hash, every document's hash and
  status, every finding with its deciding layer, and how the score was built.
- The score is only as good as the lender's choice of trusted issuers. The
  contract makes that choice explicit and enforced; it cannot make an issuer
  honest.
- No funds move. A lending contract consumes `is_eligible` or
  `assessment_status` and applies its own terms within the recorded bounds.
