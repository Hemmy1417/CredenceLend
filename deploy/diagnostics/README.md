# Diagnostic deployments

Disposable deployments run before the canonical one, to find which fields
split validators on the panel-decided cases (`scripts/diagnostic_rounds.py`).
Not canonical; nothing here is an evidence of record for the deployment. Each
JSON file holds, per round, the case, the observed verdict and score, the
panel findings, and every node's model, vote and stdout tail.

| Run | Contract commit | Address | Rounds | Finding |
|---|---|---|---|---|
| `run_20260911T090314.json` | c06aac6 | `0xFE2F7183E5E069Eb671bC3f3AC99F195EC89994b` | BASE-ADA, A17, A20, A12, BASE-ADA, A17 | Ada's accurate statement read as a hundredfold understatement (`"amount_minor": 450000` taken as 450,000 USD): SUSPICIOUS 20 unanimously once, no verdict the second time. A12 held by majority with one validator also calling the injected page manipulated. A17 and A20 held. |
| `run_20260911T092020.json` | 4ec5bea | `0xeBfAbEda2D1aD48D844538f9485E9A3c4132419f` | BASE-ADA, A12, BASE-ADA, A20, A17, BASE-ADA | After converting money for the panel: all six rounds finalized as expected (Ada APPROVED 93 three times), each Ada round with one minority validator calling the statement unsupported - one quoting `"liquidated":0`, which supports it. |
| `run_20260911T142733.json` | a261d28 | `0xfA6c9c40f54653CF76907f97ff09e0131cE2857E` | BASE-ADA, A12, BASE-ADA, BASE-ADA | After "only a contradiction counts": four of four rounds finalized as expected with no dissenting vote. |

What changed between runs is in the commit messages of 4ec5bea and a261d28
and in `docs/consensus.md` ("Model diversity").
