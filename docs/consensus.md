# Consensus and equivalence

## The nondeterministic calls

Exactly two, both inside one `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`
per round (`_run_round`):

1. `gl.nondet.web.get(url)` for each ALLOWED evidence item (`_fetch_row`). The
   raw bytes are hashed first; a mismatch is recorded `HASH_MISMATCH` and the
   bytes are never read. A fetch that fails is `UNAVAILABLE`, never an error.
2. `gl.nondet.exec_prompt(prompt, response_format="json")`, at most once, only
   when `_plan` finds a question whose answer can still change the verdict
   (`_node_round`). A model call that raises is a `[TRANSIENT]` revert: nothing
   is written.

Everything else, including the score and the verdict, runs after consensus in
deterministic code over the agreed payload.

## Leader

The leader runs `_node_round`: fetch and verify every allowed item, read
structured facts, scan text, plan, ask the panel if needed, ground its answer,
and return the canonical JSON payload: `rows`, `facts`, `linked`, `markers`,
`hidden`, `panel_state`, `panel_reason`, `documents`, `indicators`, bound to the
round by `subject_id`, `definition_hash`, `evidence_commitment` and `today`.

The payload has no score, verdict, band, exposure or LTV field. A leader that
adds one fails the gate (`test_leader_adding_a_score_is_refused`).

## Validator

`_validator_decision` runs the same `_node_round` from its own fetch and its
own model call, then:

1. **Gate.** `_parse_payload(leader_payload, ctx, own_texts)`: exact key sets
   and types; known enums; every row's status consistent with the item's
   admission and its byte count with the fetch cap; facts present exactly for
   examined structured items and well-typed; the code indicators, the panel
   plan and every code-decided finding RECOMPUTED from the leader's rows and
   facts and required to match; every panel finding's evidence ids eligible for
   its question; every quote's words found in THIS validator's verified bytes;
   every PRESENT, MANIPULATION_INDICATED and EXPLAINED finding meeting its quote
   rule.
2. **Compare.** `_first_difference(own, leader)`: panel state and reason; facts,
   wallet links, markers and hidden-text hits; each row's status and byte
   count; each document's and each indicator's state and deciding layer.

Agree only if both pass. A validator prints `[DISAGREE] own vs leader:
<field>` naming the first difference; the chain keeps it in the validator's
stdout.

On a leader error: `[EXPECTED]` / `[EXTERNAL]` errors must reproduce exactly;
`[TRANSIENT]` agrees only if this validator also hits a transient failure;
`[LLM_ERROR]` always disagrees (`_vote_on_leader_error`).

The contract then runs `_parse_payload` once more on the ratified text before
anything is stored.

## Equivalence

`EQUIVALENCE_STATEMENT` in the contract, verbatim in `get_config`:

> A validator ratifies the leader only if, after re-fetching and hash-verifying
> every allowed document itself, the leader payload passes the structural gate
> and every row's status and byte count, every structured fact, the scans, the
> panel state and reason, and the state and deciding layer of every document
> classification, indicator and the liquidation explanation equal its own.

| Must agree (strict) | Normalized away | Never compared |
|---|---|---|
| each row's status and byte count | enum spelling and case in model output | notes (leader prose) |
| every structured fact (integers) | answer envelopes, section lists, quote shapes | which quote a node chose |
| wallet links, markers, hidden-text hits | evidence id spelled `4` or `E4` | model wording |
| panel state and reason | quote whitespace and punctuation (word-level grounding) | timestamps that are not decision inputs |
| each finding's state and layer | | |

Score, band, exposure, LTV, verdict, eligibility and reason codes are computed
by code from the agreed fields, so validators agree on them by construction.
They cannot disagree on eligibility while agreeing on the payload.

## Why strict per finding

The brief asks that disagreement be preserved when it affects authenticity,
sufficiency, band, score range, exposure or eligibility. Every one of those is
downstream of a finding state or a fact, so the rule compares those, one by
one. A validator whose model reads a document as manipulated while the leader's
reads it as consistent disagrees (`test_validators_disagreeing_on_authenticity`);
so does one that is undecided where the leader decided
(`test_validator_undecided_where_the_leader_decided`). An undecided finding
never becomes a positive one: every PRESENT, MANIPULATION_INDICATED and
EXPLAINED answer without grounded quotes is downgraded by each node itself
before comparison (the node prints `[DOWNGRADE]`).

## Forged leaders (tests/direct/test_consensus_equivalence.py)

| Forgery | Stopped by |
|---|---|
| inflated income fact | compare (facts differ from the validator's own bytes) |
| a hidden hard fact | gate (code indicators recomputed) |
| a skipped panel | gate (plan recomputed) |
| a rebound round (other subject, policy hash, evidence set, date) | gate |
| a forged byte count | compare |
| an invented quote | gate (quote not in the validator's bytes) |
| a claimed model failure | compare (panel state) |
| a payload with a score | gate (exact keys) |
| a source served differently to this validator | compare (row status) |

## What the record binds (S21, S28, S39)

Every field of the stored record is either a payload field the validators
compared, a quote each validator grounded in its own verified bytes, or a value
code derived from those. A reassessment never reuses a stored excerpt: it
re-fetches the committed locations, re-verifies the committed hashes and runs
a new consensus round, so the bytes an appeal is judged on are the bytes the
original round committed to, and nothing a leader wrote is inherited. Notes are
the one field of leader prose in the record; no later round reads them and no
verdict depends on them.

## Model diversity

StudioNet validators run different model families. The prompt partitions the
indicator questions so each inconsistency has exactly one home, grounding is
word-level (a quote joining two lines or dropping punctuation still grounds),
and every quote shape a model returns is accepted and then grounded. Findings
are still compared strictly.
