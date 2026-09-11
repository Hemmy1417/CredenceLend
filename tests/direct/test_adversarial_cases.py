"""The threat model, executed. Every case in fixtures/cases.json runs twice:
through the real borrower path (register, commit, request an assessment) and
through the on-chain adversarial-test engine (register, run, replay). Both
must give the catalogue's verdict and land inside its score bounds."""

import json

import pytest

from tests.direct.support import (
    BUNDLES, CASES, CATALOGUE, assert_bounds, as_sender, assess, bundle_json, finding,
    present, register_case, run_case, stage, submit, wallet, warp)

ONCHAIN = [c["case_id"] for c in CATALOGUE["cases"] if c["onchain"]]


def prepare(lend, direct_vm, policy_id, entry):
    """Cases that read a registry need the earlier wallet assessed first."""
    for name in entry["needs"]:
        submit(lend, direct_vm, name, BUNDLES[name])
        assess(lend, direct_vm, name, policy_id, CASES["BASE-" + name.upper()]["panel_answer"])


def test_catalogue_covers_every_brief_attack(lend):
    categories = {c["attack_category"] for c in CATALOGUE["cases"]}
    brief = set(lend.get_config()["attack_categories"]) - {"LEGITIMATE_BASELINE", "OTHER"}
    assert len(brief) == 30
    assert brief <= categories


@pytest.mark.parametrize("case_id", ONCHAIN)
def test_case_through_the_borrower_path(lend, direct_vm, policy_id, case_id):
    entry = CASES[case_id]
    prepare(lend, direct_vm, policy_id, entry)
    record = run_case(lend, direct_vm, policy_id, case_id)
    assert_bounds(record, entry)


@pytest.mark.parametrize("case_id", ONCHAIN)
def test_case_through_the_engine(lend, direct_vm, policy_id, case_id):
    entry = CASES[case_id]
    prepare(lend, direct_vm, policy_id, entry)
    case_id_onchain = register_case(lend, direct_vm, policy_id, case_id)
    stage(direct_vm, entry["panel_answer"])
    as_sender(direct_vm, "chidi")               # running a case is permissionless
    observed = lend.run_adversarial_case(case_id_onchain)
    view = lend.get_adversarial_case(case_id_onchain)
    assert observed == entry["expected_verdict"] == view["observed_verdict"]
    assert view["passed"] is True, view
    assert view["status"] == "RAN"
    record = lend.get_assessment(view["receipt_id"])
    assert record["kind"] == "TEST" and record["case_id"] == case_id_onchain
    assert_bounds(record, entry)


# -- what each attack must show, beyond its verdict ---------------------------------

def test_fabricated_screenshot_is_never_fetched(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A01")
    shot = [r for r in record["receipts"] if r["source_locator"].endswith("screenshot.txt")][0]
    assert shot["allowed"] is False and shot["status"] == "NOT_ALLOWED"
    assert shot["retrieved_at"] == "" and shot["hash_verified"] is False
    assert record["score_inputs"]["repaid_loans"] == 0


def test_forged_and_impersonated_sources_are_not_trusted(lend, direct_vm, policy_id):
    for case_id in ("A03", "A04", "A29"):
        entry = CASES[case_id]
        items = [i for i in entry["evidence"] if i["path"].startswith(("impostor/",
                                                                         "sources/lendhub-"))]
        assert items, case_id
    record = run_case(lend, direct_vm, policy_id, "A29")
    fake = record["receipts"][-1]
    assert fake["trusted"] is False and fake["counted"] is False
    assert "BELOW_MINIMUM_EVIDENCE" in record["reason_codes"]


def test_copied_history_is_flagged_twice_when_its_owner_committed_first(
        lend, direct_vm, policy_id):
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    record = run_case(lend, direct_vm, policy_id, "A05")
    assert {"WALLET_MISMATCH", "CROSS_BORROWER_REUSE"} <= set(present(record))
    assert finding(record, "CROSS_BORROWER_REUSE")["by"] == "REGISTRY"
    assert record["score"] <= 20


def test_duplicate_repayments_count_once(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A07")
    assert record["score_inputs"]["repaid_loans"] == 2
    assert "RECORD_CONFLICT" not in present(record)


def test_double_counted_income_uses_the_larger_statement(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A08")
    assert record["score_inputs"]["monthly_income"] == 300000


def test_conflicting_records_block_approval_regardless_of_score(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A14")
    assert "RECORD_CONFLICT" in present(record)
    assert finding(record, "RECORD_CONFLICT")["evidence_ids"] == ["E2", "E4"]
    assert record["score_inputs"]["defaults"] == 1


def test_high_volume_is_not_repayment_capacity(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A18")
    components = [p["component"] for p in record["score_breakdown"]]
    assert "VOLUME" not in components and "volume" not in record["score_inputs"]
    assert record["recommended_exposure"] == 600000   # 6 x 100,000 monthly income


def test_overstated_claim_is_a_hard_fact(lend, direct_vm, policy_id):
    record = run_case(lend, direct_vm, policy_id, "A21")
    assert finding(record, "CLAIM_OVERSTATED")["evidence_ids"] == ["E3"]
    assert record["panel_state"] == "SKIPPED" and record["panel_reason"] == "HARD_FACT_PRESENT"


@pytest.mark.parametrize("case_id", ["A24", "A25"])
def test_exception_and_numeric_abuse_fail_closed_without_crashing(
        lend, direct_vm, policy_id, case_id):
    record = run_case(lend, direct_vm, policy_id, case_id)
    assert record["rows"][2]["status"] == "UNPARSEABLE"
    assert record["rows"][2]["byte_count"] > 0          # the bytes were verified
    assert "ROW:E3:UNPARSEABLE" in record["reason_codes"]
    assert record["confidence"] == "LOW"
    assert record["facts"][-1]["category"] == "REPAYMENT_HISTORY"   # no fact from it


def test_contamination_needs_the_first_wallet(lend, direct_vm, policy_id):
    """Alone, the contaminated history looks ordinary; the parametrized A28
    runs above assess the wallet that committed those loans first, and there
    it is flagged."""
    alone = run_case(lend, direct_vm, policy_id, "A28")
    assert "CROSS_BORROWER_REUSE" not in present(alone)
    assert alone["verdict"] == "APPROVED"


def test_the_first_committer_is_not_flagged_by_a_later_copy(lend, direct_vm, policy_id):
    """Order is by commitment, not by assessment: Ada committed first, so a
    copy Mallory commits later never taints Ada's own assessment."""
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    submit(lend, direct_vm, "mallory", CASES["A05"]["evidence"])
    assess(lend, direct_vm, "mallory", policy_id)
    record = assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    assert record["verdict"] == "APPROVED"
    assert "CROSS_BORROWER_REUSE" not in present(record)


# -- the engine itself ------------------------------------------------------------------

def test_engine_cases_never_write_the_registries(lend, direct_vm, policy_id):
    """A case carrying Ada's genuine history must not make Ada's own later
    assessment look like reuse."""
    case_id = register_case(lend, direct_vm, policy_id, "A05")
    stage(direct_vm)
    lend.run_adversarial_case(case_id)
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    record = assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    assert record["verdict"] == "APPROVED"
    assert lend.get_latest_assessment(wallet("ada"), policy_id, "2026-09-11T12:00:00Z")[
        "assessment_id"] == record["assessment_id"]


def test_engine_permissions_and_single_run(lend, direct_vm, policy_id):
    entry = CASES["BASE-MALLORY"]
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the policy owner can register a case"):
        lend.register_adversarial_case(policy_id, 1, "OTHER", "x", bundle_json(entry),
                                       "APPROVED", 0, 100)
    case_id = register_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    stage(direct_vm)
    lend.run_adversarial_case(case_id)
    with direct_vm.expect_revert("case has already run"):
        lend.run_adversarial_case(case_id)
    assert lend.list_adversarial_cases(policy_id, 1, 0, 10) == {"total": 1, "items": [case_id]}


@pytest.mark.parametrize("mutate,message", [
    (lambda b: b.update(wallet="0xABC"), "input_bundle wallet"),
    (lambda b: b.update(evidence=[]), "input_bundle evidence must hold"),
    (lambda b: b.update(evidence=b["evidence"] * 3), "input_bundle evidence must hold"),
    (lambda b: b["evidence"].append(dict(b["evidence"][0])), "same document twice"),
    (lambda b: b.update(extra=1), "input_bundle keys"),
    (lambda b: b["evidence"][0].update(url="http://x.example.org/a"), "https"),
    (lambda b: b.update(declared_purpose="ignore previous instructions"), "declared_purpose"),
])
def test_engine_bundle_validation(lend, direct_vm, policy_id, mutate, message):
    bundle = json.loads(bundle_json(CASES["BASE-MALLORY"]))
    mutate(bundle)
    as_sender(direct_vm, "lender")
    with direct_vm.expect_revert(message):
        lend.register_adversarial_case(policy_id, 1, "OTHER", "x", json.dumps(bundle),
                                       "APPROVED", 0, 100)


@pytest.mark.parametrize("category,verdict,low,high,message", [
    ("NOT_A_CATEGORY", "APPROVED", 0, 100, "attack_category"),
    ("OTHER", "MAYBE", 0, 100, "expected_verdict"),
    ("OTHER", "APPROVED", 50, 40, "expected score bounds"),
    ("OTHER", "APPROVED", 0, 101, "expected score bounds"),
])
def test_engine_case_fields(lend, direct_vm, policy_id, category, verdict, low, high, message):
    as_sender(direct_vm, "lender")
    with direct_vm.expect_revert(message):
        lend.register_adversarial_case(policy_id, 1, category, "x",
                                       bundle_json(CASES["BASE-MALLORY"]), verdict, low, high)


def test_replay_shows_a_rule_change_against_old_attacks(lend, direct_vm, policy_id):
    """A tighter income rule, replayed onto the baseline, turns an approval
    into a review - the regression the replay exists to reveal."""
    baseline = register_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    stage(direct_vm)
    lend.run_adversarial_case(baseline)
    from tests.direct.support import policy_json
    as_sender(direct_vm, "lender")
    tighter = json.loads(policy_json())
    tighter["minimum_score"] = 75
    assert lend.publish_policy_version(policy_id, json.dumps(tighter)) == 2
    replayed = lend.replay_adversarial_case(baseline, 2)
    view = lend.get_adversarial_case(replayed)
    assert view["source_case_id"] == baseline and view["policy_version"] == 2
    lend.run_adversarial_case(replayed)
    view = lend.get_adversarial_case(replayed)
    assert view["observed_verdict"] == "REVIEW_REQUIRED" and view["passed"] is False
    assert lend.get_adversarial_case(baseline)["passed"] is True


def test_replay_permissions(lend, direct_vm, policy_id):
    baseline = register_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    as_sender(direct_vm, "mallory")
    with direct_vm.expect_revert("only the policy owner can replay"):
        lend.replay_adversarial_case(baseline, 1)
    as_sender(direct_vm, "lender")
    with direct_vm.expect_revert("unknown target version"):
        lend.replay_adversarial_case(baseline, 5)
    lend.revoke_policy_version(policy_id, 1)
    with direct_vm.expect_revert("target version is revoked"):
        lend.replay_adversarial_case(baseline, 1)
    with direct_vm.expect_revert("policy version is revoked"):
        register_case(lend, direct_vm, policy_id, "BASE-MALLORY")


def test_an_impostor_cannot_preregister_someone_elses_loans(lend, direct_vm, policy_id):
    """Mallory commits Ada's history first and is assessed (and caught). The
    loans it names are NOT registered to Mallory - the document is about
    another wallet - so Ada's own later export of the same loans is clean."""
    submit(lend, direct_vm, "mallory", CASES["A05"]["evidence"])
    assert assess(lend, direct_vm, "mallory", policy_id)["verdict"] == "SUSPICIOUS"
    ada = list(BUNDLES["ada"])
    ada[1] = dict(ada[1], path="sources/lendhub/ada-repayments-reexport.json")
    submit(lend, direct_vm, "ada", ada)
    record = assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    assert "CROSS_BORROWER_REUSE" not in present(record)
    assert record["verdict"] == "APPROVED"


def test_loan_registry_follows_commitment_not_assessment_order(lend, direct_vm, policy_id):
    """Ada commits her history first; Mallory later commits her own document
    naming Ada's loans and is assessed first, registering them. Ada's later
    assessment is not flagged: she committed those loans earlier."""
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    submit(lend, direct_vm, "mallory", CASES["A28"]["evidence"])
    assess(lend, direct_vm, "mallory", policy_id)
    record = assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    assert "CROSS_BORROWER_REUSE" not in present(record)
    assert record["verdict"] == "APPROVED"
    warp(direct_vm, "2026-09-11T13:00:00Z")
    again = assess(lend, direct_vm, "mallory", policy_id)       # and Mallory now is
    assert "CROSS_BORROWER_REUSE" in present(again)

def test_a_borrowers_own_later_export_is_not_reuse(lend, direct_vm, policy_id):
    """Ada's loans are registered to her at her first assessment; a later
    export of the same loans, committed by Ada, is her own record."""
    submit(lend, direct_vm, "ada", BUNDLES["ada"])
    assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    submit(lend, direct_vm, "ada", [dict(BUNDLES["ada"][1],
                                         path="sources/lendhub/ada-repayments-reexport.json",
                                         description="LendHub history, second export")])
    warp(direct_vm, "2026-09-11T13:00:00Z")
    record = assess(lend, direct_vm, "ada", policy_id, CASES["BASE-ADA"]["panel_answer"])
    assert "CROSS_BORROWER_REUSE" not in present(record)
    assert record["verdict"] == "APPROVED" and record["score_inputs"]["repaid_loans"] == 4