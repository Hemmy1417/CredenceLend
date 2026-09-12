"""Consensus: the validator reproduces the round from its own fetch and its
own model call, gates the leader's payload against its own verified bytes,
and compares every decision field. These tests hand the captured validator
forged leader results (direct_vm.run_validator) and change the validator's
world through the mocks."""

import copy

from tests.direct.support import (
    BUNDLES, answer_for, captured_payload, item_url, mock_panel, run_case, serve_all,
    serve_bytes, stage, wallet)


def validate(direct_vm, mod, payload) -> bool:
    text = payload if isinstance(payload, str) else mod._canonical(payload)
    return direct_vm.run_validator(leader_result=text)


def ada_round(lend, direct_vm, policy_id):
    return run_case(lend, direct_vm, policy_id, "BASE-ADA")


def subject(payload, subject_id):
    for f in payload["indicators"] + payload["documents"]:
        if f["id"] == subject_id:
            return f
    raise KeyError(subject_id)


def test_payload_carries_no_score_verdict_or_exposure(mod):
    for key in ("score", "verdict", "risk_band", "recommended_exposure",
                "recommended_ltv_bps", "eligible"):
        assert key not in mod.PAYLOAD_KEYS


def test_honest_leader_is_ratified(lend, direct_vm, policy_id):
    ada_round(lend, direct_vm, policy_id)
    assert direct_vm.run_validator() is True


def test_prose_is_not_compared(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    subject(payload, "E5")["note"] = "a different sentence entirely"
    assert validate(direct_vm, mod, payload) is True


def test_leader_inflating_a_fact_is_refused(lend, direct_vm, mod, policy_id):
    """A leader proposing a favorable score has only one route: change the
    facts code scores. The validator read its own bytes."""
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    income = [f for f in payload["facts"] if f["category"] == "INCOME_STATEMENT"][0]
    income["values"].update(total=13500000, line_sum=13500000, monthly=4500000)
    assert validate(direct_vm, mod, payload) is False


def test_leader_adding_a_score_is_refused(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    payload["score"] = 100
    assert validate(direct_vm, mod, payload) is False


def test_leader_hiding_a_hard_fact_is_refused(lend, direct_vm, mod, policy_id):
    run_case(lend, direct_vm, policy_id, "A05")
    payload = captured_payload(direct_vm)
    f = subject(payload, "WALLET_MISMATCH")
    assert f["state"] == "PRESENT"
    f.update(state="ABSENT", evidence_ids=[])
    assert validate(direct_vm, mod, payload) is False
    payload = captured_payload(direct_vm)
    payload["facts"][2]["wallet"] = wallet("mallory")   # and rewriting the fact itself
    assert validate(direct_vm, mod, payload) is False


def test_leader_skipping_the_panel_is_refused(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    payload["panel_state"] = "SKIPPED"
    payload["panel_reason"] = "NOTHING_TO_ASSESS"
    assert validate(direct_vm, mod, payload) is False


def test_leader_rebinding_the_round_is_refused(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    for key, value in (("subject_id", "CA-000999"), ("definition_hash", "0" * 64),
                       ("evidence_commitment", "1" * 64), ("today", "2027-01-01")):
        payload = captured_payload(direct_vm)
        payload[key] = value
        assert validate(direct_vm, mod, payload) is False, key


def test_forged_byte_count_is_refused(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    payload["rows"][0]["byte_count"] = payload["rows"][0]["byte_count"] + 1
    assert validate(direct_vm, mod, payload) is False


def test_invented_quote_is_refused(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    subject(payload, "E5").update(state="MANIPULATION_INDICATED", quotes=[
        {"evidence_id": "E5", "text": "this statement was forged by the borrower"}])
    assert validate(direct_vm, mod, payload) is False


def test_source_divergence_between_nodes(lend, direct_vm, policy_id):
    """The leader verified the bytes; this validator is served different
    bytes at the same location. It records HASH_MISMATCH and disagrees."""
    ada_round(lend, direct_vm, policy_id)
    direct_vm.clear_mocks()
    serve_bytes(direct_vm, item_url(BUNDLES["ada"][3]), b'{"changed": true}')
    serve_all(direct_vm)
    mock_panel(direct_vm, answer_for("BASE-ADA"))
    assert direct_vm.run_validator() is False


def test_source_unreachable_for_this_validator(lend, direct_vm, policy_id):
    ada_round(lend, direct_vm, policy_id)
    stage(direct_vm, answer_for("BASE-ADA"), skip=(BUNDLES["ada"][1]["path"],))
    assert direct_vm.run_validator() is False


def test_validators_disagreeing_on_authenticity(lend, direct_vm, policy_id):
    ada_round(lend, direct_vm, policy_id)
    answer = answer_for("BASE-ADA")
    answer["documents"]["E5"] = {"state": "MANIPULATION_INDICATED", "quotes": [
        {"evidence_id": "E5", "text": "repaid each loan in full"}], "note": "doubt"}
    stage(direct_vm, answer)
    assert direct_vm.run_validator() is False


def test_validator_undecided_where_the_leader_decided(lend, direct_vm, policy_id):
    ada_round(lend, direct_vm, policy_id)
    answer = answer_for("BASE-ADA")
    answer["indicators"]["UNSUPPORTED_CLAIM"] = {"state": "UNDETERMINED"}
    stage(direct_vm, answer)
    assert direct_vm.run_validator() is False


def test_leader_claiming_the_model_failed(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    payload["panel_state"] = "MODEL_OUTPUT_INVALID"
    payload["documents"][4] = mod._finding("E5", "UNCLEAR", "PANEL")
    for i, f in enumerate(payload["indicators"]):
        if f["by"] == "PANEL":
            payload["indicators"][i] = mod._finding(f["id"], "UNDETERMINED", "PANEL")
    assert validate(direct_vm, mod, payload) is False       # this validator's model answered
    stage(direct_vm, {"nonsense": True})
    assert validate(direct_vm, mod, payload) is True        # both really failed


def test_leader_errors(lend, direct_vm, policy_id):
    ada_round(lend, direct_vm, policy_id)
    assert direct_vm.run_validator(
        leader_error=Exception("[TRANSIENT] the model call failed")) is False
    assert direct_vm.run_validator(leader_error=Exception("[LLM_ERROR] garbage")) is False
    stage(direct_vm)                                          # model unreachable here too
    assert direct_vm.run_validator(
        leader_error=Exception("[TRANSIENT] the model call failed")) is True
    assert direct_vm.run_validator(leader_error=Exception("[LLM_ERROR] garbage")) is False


def test_vote_table_pure(mod, genlayer_vm):
    def raising(text):
        def run():
            raise genlayer_vm.UserError(text)
        return run

    E = genlayer_vm.UserError
    assert mod._vote_on_leader_error(E("[EXPECTED] x"), raising("[EXPECTED] x")) is True
    assert mod._vote_on_leader_error(E("[EXPECTED] x"), raising("[EXPECTED] y")) is False
    assert mod._vote_on_leader_error(E("[EXPECTED] x"), lambda: None) is False
    assert mod._vote_on_leader_error(E("[TRANSIENT] a"), raising("[TRANSIENT] b")) is True
    assert mod._vote_on_leader_error(E("[TRANSIENT] a"), raising("[EXPECTED] b")) is False
    assert mod._vote_on_leader_error(E("[LLM_ERROR] a"), raising("[LLM_ERROR] a")) is False
    assert mod._vote_on_leader_error("not an error", lambda: None) is False

    def boom():
        raise ValueError("not a user error")
    assert mod._vote_on_leader_error(E("[EXPECTED] x"), boom) is False


def test_gate_is_strict_about_shape(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    honest = captured_payload(direct_vm)
    forgeries = []
    p = copy.deepcopy(honest)
    p["rows"][0]["status"] = "FETCHED"
    forgeries.append(p)
    p = copy.deepcopy(honest)
    p["facts"][0]["values"]["months_active"] = 33.0
    forgeries.append(p)
    p = copy.deepcopy(honest)
    p["facts"][0]["values"]["months_active"] = True
    forgeries.append(p)
    p = copy.deepcopy(honest)
    p["linked"] = []
    forgeries.append(p)
    p = copy.deepcopy(honest)
    p["indicators"] = p["indicators"][:-1]
    forgeries.append(p)
    p = copy.deepcopy(honest)
    subject(p, "E5")["by"] = "CODE"
    forgeries.append(p)
    p = copy.deepcopy(honest)
    subject(p, "E5")["note"] = "line\nbreak"
    forgeries.append(p)
    for forged in forgeries:
        assert validate(direct_vm, mod, forged) is False
    assert validate(direct_vm, mod, "not json") is False
    assert validate(direct_vm, mod, honest) is True


def test_code_only_round_is_ratified_and_forgeable_nowhere(lend, direct_vm, mod, policy_id):
    """A round the panel never sees still goes through the validator: the
    code-decided fields are recomputed and compared."""
    record = run_case(lend, direct_vm, policy_id, "BASE-MALLORY")
    assert record["panel_state"] == "SKIPPED"
    assert direct_vm.run_validator() is True
    payload = captured_payload(direct_vm)
    payload["facts"][1]["keys"] = payload["facts"][1]["keys"][:1]   # hide a loan
    assert validate(direct_vm, mod, payload) is False


def test_leader_invalid_against_an_all_undecided_validator(lend, direct_vm, mod, policy_id):
    """The same findings, but the leader says its model failed while this
    validator's model answered (undecided on everything): panel_state alone
    differs, and it is compared."""
    ada_round(lend, direct_vm, policy_id)
    payload = captured_payload(direct_vm)
    payload["panel_state"] = "MODEL_OUTPUT_INVALID"
    payload["documents"][4] = mod._finding("E5", "UNCLEAR", "PANEL")
    for i, f in enumerate(payload["indicators"]):
        if f["by"] == "PANEL":
            payload["indicators"][i] = mod._finding(f["id"], "UNDETERMINED", "PANEL")
    stage(direct_vm, {"documents": {"E5": {"state": "UNCLEAR"}},
                      "indicators": {"INSTRUCTION_INJECTION": {"state": "UNDETERMINED"},
                                     "UNSUPPORTED_CLAIM": {"state": "UNDETERMINED"}}})
    assert validate(direct_vm, mod, payload) is False


def captured_ctx(direct_vm) -> dict:
    """The plain round context the contract closed over."""
    _result, leader_fn, _validator_fn = direct_vm._captured_validators[-1]
    for cell in leader_fn.__closure__ or ():
        value = cell.cell_contents
        if isinstance(value, dict) and "subject_id" in value:
            return value
    raise AssertionError("round context not found")


def test_the_gate_alone_refuses_forgeries(lend, direct_vm, mod, policy_id):
    """_parse_payload runs again on the ratified text before anything is
    stored. Without any validator's own round it still recomputes every
    code-decided field."""
    run_case(lend, direct_vm, policy_id, "A05")
    ctx = captured_ctx(direct_vm)
    honest = captured_payload(direct_vm)
    assert mod._parse_payload(mod._canonical(honest), ctx, None) is not None
    forged = copy.deepcopy(honest)
    subject(forged, "WALLET_MISMATCH").update(state="ABSENT", evidence_ids=[])
    assert mod._parse_payload(mod._canonical(forged), ctx, None) is None
    forged = copy.deepcopy(honest)
    forged["panel_reason"] = ""
    forged["panel_state"] = "ASSESSED"
    assert mod._parse_payload(mod._canonical(forged), ctx, None) is None
    forged = copy.deepcopy(honest)
    forged["markers"] = ["E3"]
    assert mod._parse_payload(mod._canonical(forged), ctx, None) is None
    forged = copy.deepcopy(honest)
    forged["rows"][0]["status"] = "TOO_LARGE"
    assert mod._parse_payload(mod._canonical(forged), ctx, None) is None


def test_the_gate_alone_refuses_panel_forgeries(lend, direct_vm, mod, policy_id):
    ada_round(lend, direct_vm, policy_id)
    ctx = captured_ctx(direct_vm)
    honest = captured_payload(direct_vm)
    texts = mod._node_round(ctx)[1]
    assert mod._parse_payload(mod._canonical(honest), ctx, texts) is not None
    for change in (
            {"state": "MANIPULATION_INDICATED", "quotes": []},
            {"state": "FORGED"},
            {"evidence_ids": ["E1", "E5"]},
            {"quotes": [{"evidence_id": "E5", "text": "never said anywhere at all"}],
             "evidence_ids": ["E5"]}):
        forged = copy.deepcopy(honest)
        subject(forged, "E5").update(change)
        assert mod._parse_payload(mod._canonical(forged), ctx, texts) is None, change
    forged = copy.deepcopy(honest)
    subject(forged, "UNSUPPORTED_CLAIM").update(
        state="PRESENT", evidence_ids=["E5"],
        quotes=[{"evidence_id": "E5", "text": "repaid each loan in full"}])
    assert mod._parse_payload(mod._canonical(forged), ctx, texts) is None   # one side only


def test_the_gate_alone_refuses_forgeries_on_an_answered_round(lend, direct_vm, mod, policy_id):
    """When the panel ANSWERED, the recomputed code indicators and the
    recomputed panel decision are the only things standing between a leader
    and a rewritten record: a skipped round is caught by its own equality
    check, so it cannot stand in for this one."""
    ada_round(lend, direct_vm, policy_id)
    ctx = captured_ctx(direct_vm)
    honest = captured_payload(direct_vm)
    texts = mod._node_round(ctx)[1]
    assert mod._parse_payload(mod._canonical(honest), ctx, texts) is not None
    assert honest["panel_state"] == "ASSESSED" and honest["panel_reason"] == ""

    forged = copy.deepcopy(honest)
    subject(forged, "WALLET_MISMATCH").update(state="PRESENT", evidence_ids=["E1"])
    assert mod._parse_payload(mod._canonical(forged), ctx, texts) is None

    forged = copy.deepcopy(honest)
    subject(forged, "CLAIM_OVERSTATED")["state"] = "UNDETERMINED"
    assert mod._parse_payload(mod._canonical(forged), ctx, texts) is None

    forged = copy.deepcopy(honest)
    forged["panel_reason"] = "HARD_FACT_PRESENT"
    assert mod._parse_payload(mod._canonical(forged), ctx, texts) is None
