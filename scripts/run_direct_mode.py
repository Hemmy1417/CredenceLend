#!/usr/bin/env python3
"""Run one sample credit assessment in Direct Mode and print it readably.

    python scripts/run_direct_mode.py            # readable summary
    python scripts/run_direct_mode.py --json     # the full stored record

The sample is fixture case A17: Bola, a borrower with one LendHub
liquidation and a statement explaining it. It runs the real contract in the
official genlayer-test direct runner (via the smoke test that asserts the
same record), with the fixture documents served byte for byte and the panel
answered from fixtures/cases.json. No network, no keys.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST = "tests/direct/test_contract_smoke.py::test_sample_assessment_readable"


def money(minor: int) -> str:
    return "$" + format(minor // 100, ",") + "." + str(minor % 100).zfill(2)


def show(record: dict) -> None:
    print("CredenceLend sample assessment (Direct Mode)")
    print("=" * 60)
    print(f"assessment      {record['assessment_id']}  ({record['kind']})")
    print(f"borrower        {record['borrower_wallet']}")
    print(f"policy          {record['policy_id']} v{record['policy_version']}  "
          f"hash {record['definition_hash'][:16]}...")
    print(f"verdict         {record['verdict']}   eligible: {record['eligible']}")
    print(f"score           {record['score']}/100   band: {record['risk_band']}   "
          f"confidence: {record['confidence']}")
    print(f"exposure        up to {money(record['recommended_exposure'])}   "
          f"LTV up to {record['recommended_ltv_bps'] / 100:.2f}%")
    print(f"appeal until    {record['appeal_deadline']}   valid until {record['valid_until']}")
    print()
    print("score breakdown")
    for part in record["score_breakdown"]:
        print(f"  {part['component']:<26}{part['points']:+d}")
    print()
    print("evidence receipts")
    print(f"  {'id':<4}{'category':<22}{'status':<11}{'fresh':<8}{'auth':<24}{'counted'}")
    for r in record["receipts"]:
        print(f"  {r['evidence_id']:<4}{r['category']:<22}{r['status']:<11}"
              f"{r['freshness_status']:<8}{r['authenticity_status'] + '/' + r['authenticity_by']:<24}"
              f"{r['counted']}")
    print()
    print("findings that decided it")
    for f in record["indicators"]:
        if f["state"] not in ("ABSENT", "NOT_APPLICABLE"):
            quotes = "; ".join(f"{q['evidence_id']}: \"{q['text']}\"" for q in f["quotes"])
            print(f"  {f['id']}: {f['state']} (by {f['by']}) {quotes}")
    print()
    print("reason codes")
    print("  " + ", ".join(record["reason_codes"]))
    print()
    print("summary")
    print("  " + record["reasoning_summary"])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "record.json"
        env = dict(os.environ, CREDENCELEND_SAMPLE_OUT=str(out))
        run = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-p",
                              "no:cacheprovider"], cwd=ROOT, env=env,
                             capture_output=True, text=True)
        if run.returncode != 0 or not out.exists():
            print(run.stdout[-3000:], run.stderr[-3000:])
            print("the sample assessment did not complete")
            return 1
        record = json.loads(out.read_text(encoding="utf-8"))
    if "--json" in sys.argv:
        print(json.dumps(record, indent=2))
    else:
        show(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
