# Scoring policy

The score is integer arithmetic in `_score` over facts code read from
structured issuer documents that were counted. No model produces a number.
Every component is stored in the record as `score_breakdown` and as a
`SCORE:<COMPONENT>:<points>` reason code, so the score can be recomputed by
hand from the record.

## Inputs (all from counted documents, policy currency only)

A document is **counted** when it is allowed by the policy, examined (bytes
matched the committed sha256 and parsed), about this wallet, fresh (its
`as_of` no older than `maximum_evidence_age_days` and not in the future), and
not altered. A consistent, wallet-linked text document from an issuer category
is counted toward coverage and the evidence count; the borrower's own
statement never is.

| Input | Read from | Rule |
|---|---|---|
| repaid loans | `REPAYMENT_HISTORY` | distinct `issuer|loan_id` with status REPAID; a loan in two exports counts once |
| defaults | `REPAYMENT_HISTORY` | distinct `issuer|loan_id` with status DEFAULTED |
| liquidations | `REPAYMENT_HISTORY` (LIQUIDATED) and `LIQUIDATION_RECORD` events | distinct loan ids across both; one liquidation reported twice counts once |
| monthly income | `INCOME_STATEMENT` | `total_minor // period_months`; the LARGEST counted statement, never a sum |
| months active | `ONCHAIN_ACTIVITY` | the largest `months_active` |
| collateral, debt | `LENDING_POSITIONS` | sums over counted position documents |
| coverage | all counted documents | required categories met / required categories |

Trading volume is read and recorded but is not an input. A high-volume trader
is not thereby a capable borrower (case A18).

## Formula

With the policy's `risk_weights` `w`:

```text
score = clamp(0, 100,
    w.base
  + min(repaid, w.max_repaid_loans) * w.per_repaid_loan
  - defaults * w.per_default
  - unexplained_liquidations * w.per_unexplained_liquidation
  - explained_liquidations * w.per_explained_liquidation
  + min(w.income_points, monthly_income * w.income_points // w.income_reference_minor)
  + (w.history_points if months >= w.history_months
     else months * w.history_points // w.history_months)
  + w.coverage_points * covered // required          (full points if none required)
  - (w.leverage_penalty if debt * 10000 > collateral * w.leverage_limit_bps else 0))
```

`explained_liquidations` is every liquidation when the panel found
`LIQUIDATION_EXPLANATION = EXPLAINED` with quotes from both an explanation
(the borrower's statement or an attestation) and a liquidation record; zero
otherwise. With no statement or attestation to explain it, code records
`NOT_EXPLAINED` without asking a model.

## The demo policy (`tests/direct/support.py: policy_definition`)

| Weight | Value | | Setting | Value |
|---|---:|---|---|---:|
| base | 30 | | minimum_score | 70 |
| per_repaid_loan | 5 | | review_score | 50 |
| max_repaid_loans | 6 | | minimum_evidence_count | 3 |
| per_default | 25 | | maximum_evidence_age_days | 90 |
| per_unexplained_liquidation | 15 | | required categories | ONCHAIN_ACTIVITY, INCOME_STATEMENT |
| per_explained_liquidation | 5 | | maximum_exposure | 5,000,000 (minor units) |
| income_points | 20 | | maximum_ltv_bps | 7500 |
| income_reference_minor | 500,000 | | income_exposure_multiple | 6 |
| history_points / months | 15 / 24 | | suspicious_score_cap | 20 |
| coverage_points | 10 | | appeal window | 7 days |
| leverage_penalty / limit | 15 / 8000 bps | | validity / cooldown | 30 days / 1 hour |

Worked example, Ada (case BASE-ADA): 30 + 4 x 5 + 0 - 0 + min(20, 450,000 x 20 //
500,000 = 18) + 15 (33 months) + 10 (both required categories) - 0 (debt 40% of
collateral) = **93**.

## Bands, exposure, LTV

`band_thresholds` are four strictly increasing integers; the default
`[30, 50, 70, 85]` gives:

| Score | Band | Band LTV cap | Band exposure cap |
|---:|---|---:|---:|
| 0-29 | VERY_HIGH | 0 | 0 |
| 30-49 | HIGH | 25.00% | 500,000 |
| 50-69 | MODERATE | 40.00% | 1,500,000 |
| 70-84 | LOW | 60.00% | 3,000,000 |
| 85-100 | VERY_LOW | 75.00% | 5,000,000 |

Exposure and LTV are computed only for `APPROVED` and `REVIEW_REQUIRED`:

```text
ltv      = min(band_max_ltv_bps[band], maximum_ltv_bps)
exposure = min(band_max_exposure[band], maximum_exposure,
               monthly_income * income_exposure_multiple   (when both > 0))
```

Every other verdict records zero exposure and zero LTV. Only `APPROVED` is
`eligible`. The best band is never uncapped: the policy maximum and verified
income bound it (case A19: six repaid loans, exposure capped at 300,000 by thin
income).

## Verdict precedence (`_derive`)

| # | Condition | Verdict |
|---:|---|---|
| 1 | a hard fact (code or registry) | SUSPICIOUS, score capped at `suspicious_score_cap` |
| 2 | an allowed source unreachable, or its bytes changed | SOURCE_UNAVAILABLE |
| 3 | an allowed document oversized or unparseable | INCONCLUSIVE |
| 4 | the panel's answer unusable | INCONCLUSIVE |
| 5 | panel: injection or unsupported claim present, or a document shows manipulation | SUSPICIOUS, capped |
| 6 | loan records or documents conflict | CONFLICTING_EVIDENCE |
| 7 | a required category has no evidence | INSUFFICIENT_EVIDENCE |
| 8 | a required category is met only by stale documents | STALE_EVIDENCE |
| 9 | fewer counted documents than the minimum | INSUFFICIENT_EVIDENCE |
| 10 | any finding undecided | INCONCLUSIVE |
| 11 | score below `review_score` | REJECTED |
| 12 | score below `minimum_score` | REVIEW_REQUIRED |
| 13 | otherwise | APPROVED |

A high score never overrides rows 1-10. `suspicious_score_cap` is the brief's
`suspicious_score_floor` under an unambiguous name: it is the ceiling a
suspicious assessment's score is held under.

The score is a policy-relative measure of verified evidence. It is not a
guarantee of repayment and it does not eliminate lending risk.
