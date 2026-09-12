# Submission

CredenceLend - evidence-based credit assessment for DeFi lending. A
standalone GenLayer Intelligent Contract. Every fact below was produced by a
command or read from the network; where a fact is observational rather than
asserted, it says so.

## Repository

| Item | Value |
|---|---|
| Repository | https://github.com/Hemmy1417/CredenceLend |
| Contract path | `contracts/credencelend.py` |
| Canonical source commit | `a261d286dab42db94ab60d708f9eb3761182d969` (the contract is unchanged in every later commit) |
| Source blob | `7b811e2cdf7868044cd10385f78b1473138d19de` |
| Source sha256 | `f56e600967357e0481a26544533ebd538a78b886cd142a8f3bf8cc7f75640ede` |
| Runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (pinned) |

## Deployment

| Item | Value |
|---|---|
| Network | GenLayer StudioNet, chain id 61999, `https://studio.genlayer.com/api` |
| Contract address | `0x583ae5d8c2b09A1EE7eafb993dea72546372bc99` |
| Explorer | https://explorer-studio.genlayer.com/address/0x583ae5d8c2b09A1EE7eafb993dea72546372bc99 (the Code tab shows the deployed source) |
| Deployment transaction | `0x7f048faa5b43d3b765623ffed1fddf96f585eee28c033a503fb7ccf97670507a` - https://explorer-studio.genlayer.com/tx/0x7f048faa5b43d3b765623ffed1fddf96f585eee28c033a503fb7ccf97670507a |
| Transaction status | `FINALIZED`; leader execution `SUCCESS`; validator votes `AGREE` x5 (read from the receipt) |
| Signer public address | `0x00192512c2f4F40c00840e3E313C8f2204DA8ec6` |
| Source parity | the deployed source read back with `gen_getContractCode` has sha256 `f56e6009...0ede`, identical to the committed file; re-check with `python scripts/deploy_studionet.py --verify` or `tests/integration` |

## Validation and tests (actual results)

| Command | Result |
|---|---|
| `genvm-lint check contracts/credencelend.py --json` | `ok: true`; lint 3 passed; validate ok, 28 methods (15 view, 13 write); 0 errors; 1 informational warning (I200: a newer runner exists - that runner is a different SDK generation the linter itself cannot load) |
| `ruff check .` | clean |
| `python scripts/preflight.py` | 36 checks, 0 failed |
| `python -m pytest tests/direct -q` | 280 collected, 280 passed, 0 failed, 0 skipped, about 75 s; Python 3.12.2, genlayer-test 0.29.2, pickling checks on for every test |
| `python scripts/mutation_check.py` (on the deployed contract bytes) | 106 mutations: 105 killed on the sweep; the one survivor (the case engine recording a pass on the verdict alone) was an untested guard, now pinned by a test and killed on re-run - `deploy/mutation_sweep_a261d28.txt` |
| `python scripts/run_direct_mode.py` | a readable sample assessment: APPROVED, 78/100, LOW band, exposure $24,000.00, with receipts, the liquidation explanation's quotes and every reason code |
| `CREDENCELEND_LIVE_WRITES=1 python -m pytest tests/integration -v` (against the deployment) | 5 passed in 53 s (without the variable, as in CI: the 4 read-only checks) |
| clean clone of `6e857e7` from GitHub, fresh virtualenv from `requirements-test.txt` | ruff clean, preflight 36/0, 280 direct passed, `genvm-lint check` ok, fixtures regenerate byte-exact (49 files), the sample assessment prints, integration 4 passed 1 skipped (the write is opt-in), and `git status --porcelain` empty afterwards - `deploy/clean_clone_record.txt` |
| CI (GitHub Actions, ubuntu) | both jobs green: the required gate (ruff, preflight, runner bundle, Direct Mode, the sample assessment, `genvm-lint check`) and the non-blocking StudioNet integration job |
| `python scripts/live_scenarios.py` (on the deployment) | 103 transactions; Phase A 5/5, Phase B 28/28 cases, Phase C rule change and 7 refusals - all as expected; `deploy/live_scenarios_transcript.json` |

## What the live run shows

- **Real borrowers (Phase A).** A strong borrower APPROVED at 93 with exposure
  bounded by verified income; a thin-history borrower with a verified salary
  REVIEW_REQUIRED at 62; a borrower with a liquidation REVIEW_REQUIRED at 68 on
  the records alone, then APPROVED at 78 after appealing with a statement the
  panel found explained the liquidation - the original record preserved, its
  digest unchanged (asserted); an impostor committing another wallet's genuine
  history SUSPICIOUS, flagged both `WALLET_MISMATCH` and `CROSS_BORROWER_REUSE`.
- **The threat model (Phase B).** All 28 on-chain cases held: every verdict and
  every score matched what Direct Mode produces. 24 were decided by code or the
  registry and are asserted; 4 are panel-decided (the Ada baseline, the subtle
  injection, the explained liquidation, the employer attestation) and are
  recorded - this is what real models answered on this run, not a guarantee they
  always will.
- **Rule change (Phase C).** Publishing v2 made the v1 approval `STALE` and not
  eligible at once. The legitimate baseline replayed onto v2 became
  REVIEW_REQUIRED - the false positive the replay exists to reveal - while the
  copied-history attack stayed SUSPICIOUS.
- **Refusals.** Seven, each `FINALIZED` with leader execution `ERROR`: a stranger
  publishing a policy version, requesting someone else's assessment, registering
  twice, committing the same document twice, an instruction inside a declared
  purpose, a reassessment under a replaced policy version, and an appeal after
  its window closed.

## What three disposable deployments found first

Before the canonical deployment, three throwaway deployments ran the
panel-decided cases (`deploy/diagnostics/`). Two real defects surfaced there and
nowhere else:

- Every validator read `"amount_minor": 450000` as 450,000 USD rather than
  4,500.00 USD, and judged an accurate borrower statement a hundredfold
  understatement: the strong borrower came out SUSPICIOUS at 20 in one round and
  with no verdict at all in the next. Code now converts every money fact for the
  panel, and the prompt defines minor units.
- Model families disagreed on whether a page carrying an injected instruction
  was also "manipulated", and on whether a claim the records do not mention is
  "unsupported". The prompt now gives each problem exactly one home.

After both fixes the last diagnostic run finalized four of four rounds with no
dissenting vote.

## Known limitations

- A hash proves a document has not changed since commitment, not that its issuer
  is genuine. Authenticity rests on the lender's trusted source prefixes.
- `minimum_evidence_count` counts documents, not independent publishers.
  Independence comes from the required categories, which the lender pins to
  different issuers; the contract does not compare registrable domains.
- URL admission is defence in depth; runtime egress controls are the real SSRF
  boundary.
- Everything a borrower commits is public on-chain; not for private records.
- The score measures verified evidence against a policy. It is not a guarantee
  of repayment and does not remove lending risk.
- Panel findings depend on validator models. They are grounded in each
  validator's own bytes and compared finding by finding, and an undecided
  finding leaves the assessment `INCONCLUSIVE` rather than approved.
- A borrower's statement can be found `UNCLEAR` by the panel, which also leaves
  the assessment `INCONCLUSIVE`; that is deliberate, and it is a fail-closed
  outcome a lender must route to review.
- Freshness views take the caller's clock (`as_of`); a view has no clock of its
  own.
- genlayer-test 0.29.2 needs two documented test-harness shims (Windows temp
  file unlinking; mid-test clock changes reaching `gl.message_raw`); both live in
  `tests/direct`, neither touches the contract.
- The first canonical deployment, `0x25FEDE0811b95697A333633b611B67f8A250eE66`,
  was superseded after its live run: the run's own setup had one borrower appeal
  with another borrower's document, which registered those bytes to the wrong
  wallet and made a later case fail as cross-borrower reuse. The contract was
  right; the state was spoiled by the script. Same bytes, clean deployment,
  repeated run - `docs/deployment.md`.

## Documents

`README.md`, `DECISION.md`, `docs/architecture.md`, `docs/threat-model.md`,
`docs/scoring-policy.md`, `docs/evidence-policy.md`, `docs/consensus.md`,
`docs/deployment.md`.
