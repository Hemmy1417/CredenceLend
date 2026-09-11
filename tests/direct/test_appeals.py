"""Appeals, reassessment, freshness and history: a result is never mutated,
a reassessment names what changed, and an assessment made under rules that
have since changed is never replayed as current."""

import pytest

from tests.direct.support import (
    BUNDLES, NOW, answer_for, as_sender, assess, item_url, policy_json,
    register_policy, stage, submit, wallet, warp)

STATEMENT = BUNDLES["bola"][4]


def bola_without_statement(lend, direct_vm, policy_id) -> dict:
    """Bola's records alone: a liquidation nobody explained - 68, review."""
    submit(lend, direct_vm, "bola", BUNDLES["bola"][:4])
    record = assess(lend, direct_vm, "bola", policy_id)
    assert record["verdict"] == "REVIEW_REQUIRED" and record["score"] == 68
    return record


def appeal_with_statement(lend, direct_vm, record) -> str:
    new_ids = submit(lend, direct_vm, "bola", [STATEMENT])
    as_sender(direct_vm, "bola")
    return lend.submit_appeal(record["assessment_id"], new_ids,
                              "My statement explains the May liquidation.")


def reassess(lend, direct_vm, appeal_id, answer=None, requester="bola") -> dict:
    stage(direct_vm, answer if answer is not None else answer_for("A17"))
    as_sender(direct_vm, requester)
    return lend.get_assessment(lend.request_reassessment(appeal_id))


def test_valid_appeal_with_new_evidence(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    appeal_id = appeal_with_statement(lend, direct_vm, original)
    appeal = lend.get_appeal(appeal_id)
    assert appeal["status"] == "OPEN" and appeal["policy_version"] == 1
    assert appeal["additional_evidence_ids"] == ["EV-000005"]
    assert appeal["appellant"] == wallet("bola")
    warp(direct_vm, "2026-09-11T13:00:00Z")
    new = reassess(lend, direct_vm, appeal_id)
    assert new["kind"] == "REASSESSMENT" and new["appeal_of"] == original["assessment_id"]
    assert new["verdict"] == "APPROVED" and new["score"] == 78
    assert new["changes"]["verdict"] == ["REVIEW_REQUIRED", "APPROVED"]
    assert new["changes"]["score"] == [68, 78]
    assert new["changes"]["added_evidence"] == ["EV-000005"]
    assert "LIQUIDATION:EXPLAINED" in new["changes"]["reason_codes_added"]
    assert "LIQUIDATION:NOT_EXPLAINED" in new["changes"]["reason_codes_removed"]
    assert new["policy_version"] == original["policy_version"]
    assert new["definition_hash"] == original["definition_hash"]
    # the original is preserved exactly
    assert lend.get_assessment(original["assessment_id"]) == original
    assert lend.get_appeal(appeal_id)["status"] == "REASSESSED"
    assert lend.get_appeal(appeal_id)["reassessment_id"] == new["assessment_id"]
    old = lend.assessment_status(original["assessment_id"], "2026-09-11T14:00:00Z")
    assert old["superseded_by_reassessment"] and old["finalized"] and not old["is_latest"]
    latest = lend.get_latest_assessment(wallet("bola"), policy_id, "2026-09-11T14:00:00Z")
    assert latest["assessment_id"] == new["assessment_id"] and latest["consumable"]
    history = lend.get_assessment_history(wallet("bola"), policy_id, 0, 10)
    assert history["items"] == [original["assessment_id"], new["assessment_id"]]


def test_reassessment_uses_the_original_bytes(lend, direct_vm, policy_id):
    """Relocating an original document to changed bytes cannot improve a
    reassessment: the hash committed with it is what is checked."""
    original = bola_without_statement(lend, direct_vm, policy_id)
    appeal_id = appeal_with_statement(lend, direct_vm, original)
    record_id = original["evidence"][1]["record_id"]
    as_sender(direct_vm, "bola")
    lend.relocate_evidence(record_id, item_url(BUNDLES["ada"][1]))
    new = reassess(lend, direct_vm, appeal_id)
    assert new["rows"][1]["status"] == "HASH_MISMATCH"
    assert new["verdict"] == "SOURCE_UNAVAILABLE"


def test_reassessment_does_not_bypass_the_allowlist(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    forged = dict(BUNDLES["mallory"][2], path="impostor/mallory-income-forged.json",
                  category="INCOME_STATEMENT")
    new_ids = submit(lend, direct_vm, "bola", [forged])
    as_sender(direct_vm, "bola")
    appeal_id = lend.submit_appeal(original["assessment_id"], new_ids, "More income.")
    new = reassess(lend, direct_vm, appeal_id, answer={})
    assert new["rows"][4]["status"] == "NOT_ALLOWED"
    assert new["score"] == 68 and new["verdict"] == "REVIEW_REQUIRED"


def test_expired_appeal(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    new_ids = submit(lend, direct_vm, "bola", [STATEMENT])
    warp(direct_vm, "2026-09-18T12:00:01Z")                   # window is 7 days
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("appeal window has closed"):
        lend.submit_appeal(original["assessment_id"], new_ids, "late")
    warp(direct_vm, "2026-09-18T12:00:00Z")                   # the last second is in
    assert lend.submit_appeal(original["assessment_id"], new_ids, "just in time")


def test_appeal_rules(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    aid = original["assessment_id"]
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("1 to 4 new evidence items"):
        lend.submit_appeal(aid, [], "nothing")
    with direct_vm.expect_revert("not already assessed"):
        lend.submit_appeal(aid, [original["evidence"][0]["record_id"]], "same again")
    other = submit(lend, direct_vm, "ada", BUNDLES["ada"][:1])
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("borrower's own"):
        lend.submit_appeal(aid, other, "someone else's")
    with direct_vm.expect_revert("borrower's own"):
        lend.submit_appeal(aid, ["EV-999999"], "unknown")
    new_ids = submit(lend, direct_vm, "bola", [STATEMENT])
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("reason is required"):
        lend.submit_appeal(aid, new_ids, "")
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the assessed borrower can appeal"):
        lend.submit_appeal(aid, new_ids, "not mine")
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("unknown assessment_id"):
        lend.submit_appeal("CA-999999", new_ids, "what")
    appeal_id = lend.submit_appeal(aid, new_ids, "the statement")
    with direct_vm.expect_revert("already been appealed"):
        lend.submit_appeal(aid, new_ids, "twice")
    reassess(lend, direct_vm, appeal_id)
    with direct_vm.expect_revert("already been reassessed"):
        lend.request_reassessment(appeal_id)


def test_evidence_committed_before_the_assessment_is_not_new(lend, direct_vm, policy_id):
    """Appealing a reassessment: evidence that already existed when it ran,
    but was left out of the appeal it answered, is not new evidence."""
    original = bola_without_statement(lend, direct_vm, policy_id)
    statement, held_back = submit(lend, direct_vm, "bola", [STATEMENT, BUNDLES["ada"][4]])
    as_sender(direct_vm, "bola")
    appeal_id = lend.submit_appeal(original["assessment_id"], [statement], "statement")
    new = reassess(lend, direct_vm, appeal_id)
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("committed after the assessment"):
        lend.submit_appeal(new["assessment_id"], [held_back], "this one too")


def test_policy_version_mismatch_fails_closed(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    appeal_id = appeal_with_statement(lend, direct_vm, original)
    as_sender(direct_vm, "lender")
    lend.publish_policy_version(policy_id, policy_json(minimum_score=65))
    as_sender(direct_vm, "bola")
    with direct_vm.expect_revert("policy version mismatch"):
        lend.request_reassessment(appeal_id)


def test_only_the_borrower_or_lender_requests_reassessment(lend, direct_vm, policy_id):
    original = bola_without_statement(lend, direct_vm, policy_id)
    appeal_id = appeal_with_statement(lend, direct_vm, original)
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the borrower or the policy owner"):
        lend.request_reassessment(appeal_id)
    new = reassess(lend, direct_vm, appeal_id, requester="lender")
    assert new["verdict"] == "APPROVED"


# -- replay and freshness ------------------------------------------------------------

def test_replay_after_a_policy_change(lend, direct_vm, policy_id):
    record = assess_ada(lend, direct_vm, policy_id)
    assert lend.is_eligible(wallet("ada"), policy_id, NOW) is True
    as_sender(direct_vm, "lender")
    lend.publish_policy_version(policy_id, policy_json(minimum_score=95))
    status = lend.assessment_status(record["assessment_id"], NOW)
    assert status["freshness"] == "STALE" and status["consumable"] is False
    assert lend.is_eligible(wallet("ada"), policy_id, NOW) is False
    # a new assessment runs under the current version
    warp(direct_vm, "2026-09-11T13:00:00Z")
    new = assess(lend, direct_vm, "ada", policy_id, answer_for("BASE-ADA"))
    assert new["policy_version"] == 2 and new["verdict"] == "REVIEW_REQUIRED"


def test_revoked_policy_version_makes_its_assessments_stale(lend, direct_vm, policy_id):
    record = assess_ada(lend, direct_vm, policy_id)
    as_sender(direct_vm, "lender")
    lend.revoke_policy_version(policy_id, 1)
    assert lend.assessment_status(record["assessment_id"], NOW)["freshness"] == "STALE"


def assess_ada(lend, direct_vm, policy_id):
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    return assess(lend, direct_vm, "ada", policy_id, answer_for("BASE-ADA"))


def test_cooldown_and_requesters(lend, direct_vm, policy_id):
    first = assess_ada(lend, direct_vm, policy_id)
    as_sender(direct_vm, "ada")
    with direct_vm.expect_revert("cooldown has not elapsed"):
        lend.request_credit_assessment(wallet("ada"), policy_id)
    warp(direct_vm, "2026-09-11T12:59:59Z")
    with direct_vm.expect_revert("cooldown has not elapsed"):
        lend.request_credit_assessment(wallet("ada"), policy_id)
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the borrower or the policy owner"):
        lend.request_credit_assessment(wallet("ada"), policy_id)
    warp(direct_vm, "2026-09-11T13:00:00Z")
    record = assess(lend, direct_vm, "ada", policy_id, answer_for("BASE-ADA"),
                    requester="lender")
    assert record["verdict"] == "APPROVED"
    # an approval that is no longer the latest is not consumable
    old = lend.assessment_status(first["assessment_id"], "2026-09-11T13:00:00Z")
    assert old["freshness"] == "RELIABLE" and old["is_latest"] is False
    assert old["consumable"] is False


def test_history_is_bounded_and_paged(lend, direct_vm):
    policy_id = register_policy(lend, direct_vm, reassessment_cooldown_seconds=60)
    submit(lend, direct_vm, "mallory", BUNDLES["mallory"])
    for i in range(12):
        warp(direct_vm, "2026-09-11T12:%02d:00Z" % (i * 2))
        assess(lend, direct_vm, "mallory", policy_id)
    warp(direct_vm, "2026-09-11T13:00:00Z")
    stage(direct_vm)
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("history for this borrower and policy is full"):
        lend.request_credit_assessment(wallet("mallory"), policy_id)
    page = lend.get_assessment_history(wallet("mallory"), policy_id, 10, 50)
    assert page["total"] == 12 and len(page["items"]) == 2
    assert lend.get_assessment_history(wallet("mallory"), policy_id, -1, 5)["items"] == []
    assert lend.get_assessment_history(wallet("mallory"), policy_id, 0, 0)["items"] == []


@pytest.mark.parametrize("as_of", ["2026-09-11", "2026-13-01T00:00:00Z", ""])
def test_malformed_clock_is_unknown(lend, direct_vm, policy_id, as_of):
    record = assess_ada(lend, direct_vm, policy_id)
    assert lend.assessment_status(record["assessment_id"], as_of)["freshness"] == "UNKNOWN"
    assert lend.is_eligible(wallet("ada"), policy_id, as_of) is False


def test_test_cases_cannot_be_appealed(lend, direct_vm, policy_id):
    from tests.direct.support import register_case
    case_id = register_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    stage(direct_vm)
    lend.run_adversarial_case(case_id)
    receipt_id = lend.get_adversarial_case(case_id)["receipt_id"]
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("cannot be appealed"):
        lend.submit_appeal(receipt_id, ["EV-000001"], "no")
