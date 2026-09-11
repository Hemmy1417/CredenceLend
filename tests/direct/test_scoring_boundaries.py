"""The score, the band, exposure and LTV: integer arithmetic owned by code.
Boundaries are driven through the real contract with policy overrides, and
the pure scoring helpers are exercised directly for the edges a fixture
cannot reach cheaply."""

import json

import pytest

from tests.direct.support import (
    BUNDLES, CASES, as_sender, assess, policy_definition, policy_json, register_policy,
    run_case, submit)


def mallory_under(lend, direct_vm, **overrides) -> dict:
    """The mallory baseline (score 70) under an altered policy."""
    policy_id = register_policy(lend, direct_vm, **overrides)
    return run_case(lend, direct_vm, policy_id, "BASE-MALLORY")


def test_baseline_breakdown_is_complete(lend, direct_vm):
    record = mallory_under(lend, direct_vm)
    parts = {p["component"]: p["points"] for p in record["score_breakdown"]}
    assert parts == {"BASE": 30, "REPAID_LOANS": 10, "DEFAULTS": 0,
                     "UNEXPLAINED_LIQUIDATIONS": 0, "EXPLAINED_LIQUIDATIONS": 0,
                     "INCOME": 12, "HISTORY": 8, "COVERAGE": 10, "LEVERAGE": 0}
    assert sum(parts.values()) == record["score"] == 70
    for name, points in parts.items():
        if points:
            assert "SCORE:%s:%s%d" % (name, "+" if points > 0 else "", points) \
                in record["reason_codes"]


@pytest.mark.parametrize("minimum,review,verdict", [
    (70, 50, "APPROVED"),          # exactly the minimum approves
    (71, 50, "REVIEW_REQUIRED"),   # one below it needs review
    (71, 70, "REVIEW_REQUIRED"),   # exactly the review score is reviewed
    (72, 71, "REJECTED"),          # one below the review score is rejected
    (100, 100, "REJECTED"),
])
def test_threshold_edges(lend, direct_vm, minimum, review, verdict):
    record = mallory_under(lend, direct_vm, minimum_score=minimum, review_score=review)
    assert record["score"] == 70 and record["verdict"] == verdict
    assert record["eligible"] == (verdict == "APPROVED")
    if verdict == "REJECTED":
        assert record["recommended_exposure"] == 0 and record["recommended_ltv_bps"] == 0


@pytest.mark.parametrize("thresholds,band", [
    ([70, 80, 90, 95], "HIGH"),
    ([30, 50, 70, 85], "LOW"),
    ([10, 20, 30, 71], "LOW"),
    ([10, 20, 30, 70], "VERY_LOW"),
    ([71, 80, 90, 95], "VERY_HIGH"),
])
def test_band_edges(lend, direct_vm, thresholds, band):
    record = mallory_under(lend, direct_vm, band_thresholds=thresholds, review_score=0,
                           minimum_score=0)
    assert record["risk_band"] == band


def test_band_function(mod):
    policy = policy_definition()
    expected = {0: 0, 29: 0, 30: 1, 49: 1, 50: 2, 69: 2, 70: 3, 84: 3, 85: 4, 100: 4}
    for score, band in expected.items():
        assert mod._band(policy, score) == band


def test_exposure_is_the_smallest_cap(lend, direct_vm):
    # band LOW cap 3,000,000; policy max 5,000,000; income 300,000 x 6 = 1,800,000
    assert mallory_under(lend, direct_vm)["recommended_exposure"] == 1800000


def test_exposure_policy_maximum_and_ltv_cap(lend, direct_vm):
    record = mallory_under(lend, direct_vm, maximum_exposure=1000000, maximum_ltv_bps=5000)
    assert record["recommended_exposure"] == 1000000
    assert record["recommended_ltv_bps"] == 5000


def test_income_multiple_zero_drops_the_income_cap(lend, direct_vm):
    record = mallory_under(lend, direct_vm, income_exposure_multiple=0)
    assert record["recommended_exposure"] == 3000000


def test_score_is_clamped_to_100(lend, direct_vm):
    weights = dict(policy_definition()["risk_weights"], base=100)
    policy_id = register_policy(lend, direct_vm, risk_weights=weights)
    record = run_case(lend, direct_vm, policy_id, "BASE-ADA")
    assert record["score"] == 100
    assert sum(p["points"] for p in record["score_breakdown"]) > 100


def test_score_is_clamped_to_0(lend, direct_vm):
    weights = dict(policy_definition()["risk_weights"], base=0, per_default=100)
    policy_id = register_policy(lend, direct_vm, risk_weights=weights, review_score=0,
                                minimum_score=0)
    record = run_case(lend, direct_vm, policy_id, "A14")
    assert record["score"] == 0 and record["verdict"] == "CONFLICTING_EVIDENCE"


def test_suspicious_score_is_capped(lend, direct_vm):
    policy_id = register_policy(lend, direct_vm, suspicious_score_cap=5)
    record = run_case(lend, direct_vm, policy_id, "A10")
    assert record["verdict"] == "SUSPICIOUS" and record["score"] == 5
    assert record["risk_band"] == "VERY_HIGH"


def test_history_is_proportional(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A20")    # 4 of 24 months
    parts = {p["component"]: p["points"] for p in record["score_breakdown"]}
    assert parts["HISTORY"] == 2


def test_coverage_is_proportional(lend, direct_vm):
    policy_id = register_policy(lend, direct_vm, required_source_categories=[
        "ONCHAIN_ACTIVITY", "INCOME_STATEMENT", "REPAYMENT_HISTORY", "LIQUIDATION_RECORD"])
    record = run_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    parts = {p["component"]: p["points"] for p in record["score_breakdown"]}
    assert parts["COVERAGE"] == 7             # 3 of 4 required categories
    assert record["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "MISSING:LIQUIDATION_RECORD" in record["reason_codes"]


def test_unexplained_liquidation_costs_more(lend, direct_vm, policy_id):
    answer = CASES["A17"]["panel_answer"]
    answer = dict(answer, explanation={"state": "NOT_EXPLAINED", "quotes": [], "note": ""})
    submit(lend, direct_vm, "bola", BUNDLES["bola"])
    record = assess(lend, direct_vm, "bola", policy_id, answer)
    assert record["score"] == 68 and record["verdict"] == "REVIEW_REQUIRED"
    assert "SCORE:UNEXPLAINED_LIQUIDATIONS:-15" in record["reason_codes"]


def test_liquidation_reported_twice_counts_once(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A17")
    assert record["score_inputs"]["liquidations"] == 1


def test_leverage_exactly_at_the_limit_is_not_penalized(mod):
    ctx = {"policy": policy_definition(), "items": [
        {"evidence_id": "E1", "category": "LENDING_POSITIONS"}]}
    payload = {"facts": [{"evidence_id": "E1", "category": "LENDING_POSITIONS",
                          "issuer": "LendHub", "currency": "USD", "wallet": "0x" + "1" * 40,
                          "as_of": "2026-08-31", "keys": [],
                          "values": {"collateral": 1000000, "debt": 800000}}]}
    _score, parts, _inputs = mod._score(ctx, payload, ["E1"], "NOT_APPLICABLE")
    assert dict((p["component"], p["points"]) for p in parts)["LEVERAGE"] == 0
    payload["facts"][0]["values"]["debt"] = 800001
    _score, parts, _inputs = mod._score(ctx, payload, ["E1"], "NOT_APPLICABLE")
    assert dict((p["component"], p["points"]) for p in parts)["LEVERAGE"] == -15


def test_other_currency_facts_are_not_scored(mod):
    ctx = {"policy": policy_definition(), "items": [
        {"evidence_id": "E1", "category": "INCOME_STATEMENT"}]}
    payload = {"facts": [{"evidence_id": "E1", "category": "INCOME_STATEMENT",
                          "issuer": "Ledgerline", "currency": "EUR", "wallet": "0x" + "1" * 40,
                          "as_of": "2026-08-31", "keys": [],
                          "values": {"period_months": 1, "total": 10 ** 9,
                                     "line_sum": 10 ** 9, "monthly": 10 ** 9}}]}
    _score, _parts, inputs = mod._score(ctx, payload, ["E1"], "NOT_APPLICABLE")
    assert inputs["monthly_income"] == 0


# -- the policy definition gate -----------------------------------------------------

def bad(**changes):
    d = policy_definition()
    d.update(changes)
    return json.dumps(d)


@pytest.mark.parametrize("text,message", [
    ("not json", "not valid JSON"),
    (json.dumps({"name": "x"}), "definition keys must be exactly"),
    (bad(minimum_score=101), "minimum_score must be an integer"),
    (bad(minimum_score=70.5), "minimum_score must be an integer"),
    (bad(minimum_score=True), "minimum_score must be an integer"),
    (bad(review_score=80), "review_score exceeds minimum_score"),
    (bad(maximum_exposure=0), "maximum_exposure"),
    (bad(maximum_exposure=10 ** 16), "maximum_exposure"),
    (bad(maximum_ltv_bps=10001), "maximum_ltv_bps"),
    (bad(currency="usd"), "currency"),
    (bad(band_thresholds=[30, 30, 70, 85]), "band_thresholds"),
    (bad(band_thresholds=[30, 50, 70]), "band_thresholds"),
    (bad(band_max_ltv_bps=[0, 2500, 2000, 6000, 7500]), "band_max_ltv_bps"),
    (bad(band_max_exposure=[0, 1, 2, 3, -4]), "band_max_exposure"),
    (bad(required_source_categories=["BORROWER_STATEMENT"]), "required category"),
    (bad(required_source_categories=["ONCHAIN_ACTIVITY", "ONCHAIN_ACTIVITY"]), "duplicate"),
    (bad(sources=[]), "sources must list"),
    (bad(sources=[{"category": "ONCHAIN_ACTIVITY", "trusted_prefixes": []}]),
     "needs a trusted prefix"),
    (bad(sources=[{"category": "ONCHAIN_ACTIVITY",
                   "trusted_prefixes": ["https://a.example.org/x"]}]), "ending in /"),
    (bad(sources=[{"category": "ONCHAIN_ACTIVITY",
                   "trusted_prefixes": ["http://a.example.org/x/"]}]), "https"),
    (bad(sources=[{"category": "WEBSITE", "trusted_prefixes": []}]), "known categories"),
    (bad(risk_weights={"base": 30}), "risk_weights keys"),
    (bad(risk_weights=dict(policy_definition()["risk_weights"], income_reference_minor=0)),
     "income_reference_minor"),
    (bad(appeal_window_seconds=10), "appeal_window_seconds"),
])
def test_definition_gate(lend, direct_vm, text, message):
    as_sender(direct_vm, "lender")
    with direct_vm.expect_revert(message):
        lend.register_policy(text)


def test_policy_versions_and_owner(lend, direct_vm, policy_id):
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the policy owner can publish"):
        lend.publish_policy_version(policy_id, policy_json())
    with direct_vm.expect_revert("only the policy owner can revoke"):
        lend.revoke_policy_version(policy_id, 1)
    as_sender(direct_vm, "lender")
    assert lend.publish_policy_version(policy_id, policy_json(minimum_score=75)) == 2
    assert lend.get_policy(policy_id, 1)["status"] == "SUPERSEDED"
    assert lend.get_policy(policy_id, 0)["version"] == 2
    assert lend.get_policy(policy_id, 1)["definition_hash"] != \
        lend.get_policy(policy_id, 2)["definition_hash"]
    lend.revoke_policy_version(policy_id, 2)
    with direct_vm.expect_revert("already revoked"):
        lend.revoke_policy_version(policy_id, 2)
    assert lend.get_policy("LP-999999", 0)["found"] is False


def test_repaid_loans_are_capped(lend, direct_vm):
    weights = dict(policy_definition()["risk_weights"], max_repaid_loans=3)
    policy_id = register_policy(lend, direct_vm, risk_weights=weights)
    record = run_case(lend, direct_vm, policy_id, "BASE-ADA")
    assert record["score_inputs"]["repaid_loans"] == 4
    assert "SCORE:REPAID_LOANS:+15" in record["reason_codes"]


def test_a_liquidation_in_two_exports_counts_once(lend, direct_vm, policy_id):
    """The liquidated loan appears in two repayment exports and in the
    liquidation record: one liquidation, keyed by issuer and loan id."""
    items = list(BUNDLES["bola"][:4]) + [dict(
        BUNDLES["bola"][1], path="sources/lendhub/bola-repayments-reexport.json",
        description="LendHub repayment history, second export")]
    submit(lend, direct_vm, "bola", items)
    record = assess(lend, direct_vm, "bola", policy_id)
    assert record["score_inputs"]["liquidations"] == 1
    assert record["score_inputs"]["repaid_loans"] == 3
    assert record["score"] == 68 and record["verdict"] == "REVIEW_REQUIRED"
