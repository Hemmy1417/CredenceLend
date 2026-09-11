"""Smoke: the public surface end to end on the happy paths - policy,
borrower, evidence, one consensus round, the stored record and every view a
lender reads."""

import json
import os
import pathlib

from tests.direct.support import (
    BUNDLES, CASES, NOW, assert_bounds, finding, policy_definition, receipt,
    register_policy, run_case, submit, wallet, warp)


def test_config_and_health(lend):
    config = lend.get_config()
    assert config["contract_version"] == "0.1.0"
    assert len(config["attack_categories"]) == 32
    assert "SUSPICIOUS" in config["verdicts"]
    assert config["risk_bands"] == ["VERY_HIGH", "HIGH", "MODERATE", "LOW", "VERY_LOW"]
    health = lend.health_check()
    assert health["ok"] is True and health["policies"] == 0


def test_policy_registration_is_canonical_and_hashed(lend, direct_vm):
    policy_id = register_policy(lend, direct_vm)
    assert policy_id == "LP-000001"
    view = lend.get_policy(policy_id, 0)
    assert view["found"] and view["version"] == 1 and view["status"] == "ACTIVE"
    assert view["definition"] == policy_definition()
    assert view["definition_hash"] == lend.definition_hash(policy_id, 1)
    assert len(view["definition_hash"]) == 64
    assert view["owner"] == wallet("lender")


def test_borrower_identity_is_the_signing_wallet(lend, direct_vm, policy_id):
    ids = submit(lend, direct_vm, "ada", BUNDLES["ada"][:1])
    profile = lend.get_borrower_profile(wallet("ada"))
    assert profile["found"]
    assert profile["borrower_id"] == wallet("ada") == profile["wallet_address"]
    assert profile["evidence_ids"] == ids == ["EV-000001"]
    ev = lend.get_evidence(ids[0])
    assert ev["borrower_id"] == wallet("ada")
    assert ev["source_type"] == "ONCHAIN_ACTIVITY"
    assert ev["committed_seq"] == 1 and ev["retired"] is False


def test_strong_borrower_is_approved_with_bounded_terms(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "BASE-ADA")
    assert_bounds(record, CASES["BASE-ADA"])
    assert record["score"] == 93
    assert record["risk_band"] == "VERY_LOW"
    assert record["recommended_ltv_bps"] == 7500
    assert record["recommended_exposure"] == 2700000   # 6 x verified monthly income
    assert record["confidence"] == "HIGH"
    assert record["panel_state"] == "ASSESSED"
    assert record["score_inputs"]["repaid_loans"] == 4
    assert record["score_inputs"]["monthly_income"] == 450000
    assert "SCORE:REPAID_LOANS:+20" in record["reason_codes"]
    assert [r["evidence_id"] for r in record["receipts"] if r["counted"]] == \
        ["E1", "E2", "E3", "E4"]
    statement = receipt(record, "E5")
    assert statement["authenticity_status"] == "CONSISTENT"
    assert statement["counted"] is False          # self-attested never counts
    activity = receipt(record, "E1")
    assert activity["hash_verified"] and activity["trusted"] and activity["counted"]
    assert activity["freshness_status"] == "FRESH"
    assert activity["relevance_status"] == "RELEVANT"
    assert "VERDICT:APPROVED" in record["reason_codes"]
    assert record["reasoning_summary"].startswith("APPROVED: score 93/100")


def test_views_for_a_lender(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "BASE-ADA")
    status = lend.assessment_status(record["assessment_id"], NOW)
    assert status["freshness"] == "RELIABLE"
    assert status["consumable"] is True and status["is_latest"] is True
    assert status["finalized"] is False           # appeal window still open
    assert lend.is_eligible(wallet("ada"), policy_id, NOW) is True
    latest = lend.get_latest_assessment(wallet("ada"), policy_id, NOW)
    assert latest["assessment_id"] == record["assessment_id"]
    history = lend.get_assessment_history(wallet("ada"), policy_id, 0, 10)
    assert history == {"total": 1, "items": [record["assessment_id"]]}
    assert lend.get_assessment("CA-999999") == {"found": False, "assessment_id": "CA-999999"}
    assert lend.is_eligible(wallet("bola"), policy_id, NOW) is False
    after_window = "2026-09-19T12:00:00Z"
    assert lend.assessment_status(record["assessment_id"], after_window)["finalized"] is True


def test_record_digest_and_immutability(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "BASE-ADA")
    body = dict(record)
    del body["found"]
    digest = body.pop("record_digest")
    import hashlib
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode()).hexdigest() == digest


def test_sample_assessment_readable(lend, direct_vm, policy_id):
    """The same run scripts/run_direct_mode.py prints."""
    record = run_case(lend, direct_vm, policy_id, "A17")
    out = os.environ.get("CREDENCELEND_SAMPLE_OUT")
    if out:
        pathlib.Path(out).write_text(json.dumps(record, indent=2), encoding="utf-8")
    assert_bounds(record, CASES["A17"])
    assert finding(record, "LIQUIDATION_EXPLANATION")["state"] == "EXPLAINED"
    assert "LIQUIDATION:EXPLAINED" in record["reason_codes"]
    assert "1 liquidations (1 explained)" in record["reasoning_summary"]


def test_weak_history_with_income_needs_review(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A20")
    assert_bounds(record, CASES["A20"])
    assert record["risk_band"] == "MODERATE"
    assert record["recommended_exposure"] == 1500000
    assert record["recommended_ltv_bps"] == 4000
    assert record["eligible"] is False


def test_multi_source_consistent_borrower(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A19")
    assert_bounds(record, CASES["A19"])
    assert record["recommended_exposure"] == 300000   # thin income caps a strong record
    assert "SCORE:LEVERAGE:-15" in record["reason_codes"]
    assert record["panel_state"] == "SKIPPED"


def test_later_clock_is_used(lend, direct_vm, policy_id):
    warp(direct_vm, "2026-09-12T08:30:00Z")
    record = run_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    assert record["created_at"] == "2026-09-12T08:30:00Z"
    assert record["today"] == "2026-09-12"
    assert record["appeal_deadline"] == "2026-09-19T08:30:00Z"
