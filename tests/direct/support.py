"""Shared scenario data and mock helpers for the Direct Mode suite.

The suite runs the real contract inside the official genlayer-test direct
runner (SDK resolved from the contract's own pinned runner hash). Only the
two external boundaries are mocked, and narrowly:

- web fetches: every file under fixtures/ is served at BASE + its relative
  path, byte for byte (an unmocked URL is unreachable, so the contract
  records the document UNAVAILABLE);
- the one panel prompt, matched on its header, answered with a JSON object.

Nothing in the contract is patched: every verdict in this suite is produced
by the contract's own code from those two inputs. Cases, bundles and panel
answers come from fixtures/cases.json, which scripts/generate_fixtures.py
writes and the live run reuses.
"""

import copy
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = "contracts/credencelend.py"
MODULE = "_contract_credencelend"
FIXTURES = ROOT / "fixtures"

BASE = "https://evidence.example.org/credencelend/"
NOW = "2026-09-11T12:00:00Z"
PANEL_PATTERN = r"(?s)CredenceLend credit evidence panel"

CATALOGUE = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
WALLETS = CATALOGUE["wallets"]
BUNDLES = CATALOGUE["bundles"]
CASES = {c["case_id"]: c for c in CATALOGUE["cases"]}
ISSUERS = ("chainscope", "lendhub", "ledgerline", "attestors", "registry", "creditbureau")
PREFIX_OF = {"ONCHAIN_ACTIVITY": "chainscope", "REPAYMENT_HISTORY": "lendhub",
             "LENDING_POSITIONS": "lendhub", "LIQUIDATION_RECORD": "lendhub",
             "INCOME_STATEMENT": "ledgerline", "ATTESTATION": "attestors",
             "REGISTRY_RECORD": "registry", "CREDIT_REPORT": "creditbureau"}


def file_bytes(rel: str) -> bytes:
    return (FIXTURES / rel).read_bytes()


def sha256_hex(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def wallet(name: str) -> str:
    return WALLETS[name]


def addr(name: str) -> bytes:
    return bytes.fromhex(WALLETS[name][2:])


def policy_definition(base: str = BASE, **overrides) -> dict:
    """The canonical demo policy every scenario is judged under."""
    definition = {
        "name": "CredenceLend demo policy - USDC working-capital line",
        "currency": "USD",
        "minimum_score": 70,
        "review_score": 50,
        "maximum_exposure": 5000000,
        "maximum_ltv_bps": 7500,
        "minimum_evidence_count": 3,
        "maximum_evidence_age_days": 90,
        "required_source_categories": ["ONCHAIN_ACTIVITY", "INCOME_STATEMENT"],
        "sources": [{"category": c, "trusted_prefixes": [base + "sources/" + PREFIX_OF[c] + "/"]}
                    for c in PREFIX_OF] + [{"category": "BORROWER_STATEMENT",
                                            "trusted_prefixes": []}],
        "risk_weights": {
            "base": 30, "per_repaid_loan": 5, "max_repaid_loans": 6, "per_default": 25,
            "per_unexplained_liquidation": 15, "per_explained_liquidation": 5,
            "income_points": 20, "income_reference_minor": 500000,
            "history_points": 15, "history_months": 24, "coverage_points": 10,
            "leverage_penalty": 15, "leverage_limit_bps": 8000,
        },
        "band_thresholds": [30, 50, 70, 85],
        "band_max_ltv_bps": [0, 2500, 4000, 6000, 7500],
        "band_max_exposure": [0, 500000, 1500000, 3000000, 5000000],
        "income_exposure_multiple": 6,
        "suspicious_score_cap": 20,
        "appeal_window_seconds": 7 * 86400,
        "assessment_validity_seconds": 30 * 86400,
        "reassessment_cooldown_seconds": 3600,
    }
    for key, value in overrides.items():
        definition[key] = value
    return definition


def policy_json(base: str = BASE, **overrides) -> str:
    return json.dumps(policy_definition(base, **overrides))


def item_sha(item: dict) -> str:
    if "sha256" in item:
        return item["sha256"]
    return sha256_hex(file_bytes(item.get("sha_of", item["path"])))


def item_url(item: dict, base: str = BASE) -> str:
    return base + item["path"]


def serve_all(direct_vm, base: str = BASE, skip=()):
    """Serve every fixture file at base + relative path (exact bytes)."""
    for path in sorted(FIXTURES.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(FIXTURES).as_posix()
        if rel in skip:
            continue
        direct_vm.mock_web("^" + re.escape(base + rel) + "$", {
            "method": "GET",
            "response": {"status": 200, "headers": {}, "body": path.read_bytes()}})


def serve_bytes(direct_vm, url: str, body: bytes, status: int = 200):
    direct_vm.mock_web("^" + re.escape(url) + "$", {
        "method": "GET", "response": {"status": status, "headers": {}, "body": body}})


def mock_panel(direct_vm, answer):
    direct_vm.mock_llm(PANEL_PATTERN, answer if isinstance(answer, str) else json.dumps(answer))


def stage(direct_vm, answer=None, base: str = BASE, skip=()):
    """Reset mocks: the web mocks first registered win, so overrides go in
    before serve_all (see serve_override)."""
    direct_vm.clear_mocks()
    serve_all(direct_vm, base, skip)
    if answer is not None:
        mock_panel(direct_vm, answer)


def as_sender(direct_vm, name: str):
    direct_vm.sender = addr(name)


def register_policy(contract, direct_vm, base: str = BASE, **overrides) -> str:
    as_sender(direct_vm, "lender")
    return contract.register_policy(policy_json(base, **overrides))


def submit(contract, direct_vm, name: str, items: list, base: str = BASE) -> list:
    """Register the wallet if needed and commit every item; returns ids."""
    as_sender(direct_vm, name)
    if not contract.get_borrower_profile(wallet(name))["found"]:
        contract.register_borrower("working capital for " + name)
    ids = []
    for it in items:
        ids.append(contract.submit_evidence(
            it["category"], item_url(it, base), item_sha(it), it["issuer"],
            it["description"], it["claimed_value"], it["currency"]))
    return ids


def assess(contract, direct_vm, name: str, policy_id: str, answer=None,
           requester: str = None) -> dict:
    stage(direct_vm, answer)
    as_sender(direct_vm, requester or name)
    assessment_id = contract.request_credit_assessment(wallet(name), policy_id)
    return contract.get_assessment(assessment_id)


def run_case(contract, direct_vm, policy_id: str, case_id: str) -> dict:
    """A case through the real borrower path: register, commit, assess."""
    entry = CASES[case_id]
    submit(contract, direct_vm, entry["wallet"], entry["evidence"])
    return assess(contract, direct_vm, entry["wallet"], policy_id, entry["panel_answer"])


def bundle_json(entry: dict, base: str = BASE) -> str:
    return json.dumps({
        "wallet": wallet(entry["wallet"]), "declared_purpose": entry["declared_purpose"],
        "evidence": [{"category": it["category"], "url": item_url(it, base),
                      "sha256": item_sha(it), "issuer": it["issuer"],
                      "description": it["description"], "claimed_value": it["claimed_value"],
                      "currency": it["currency"]} for it in entry["evidence"]]})


def register_case(contract, direct_vm, policy_id: str, case_id: str, version: int = 1) -> str:
    entry = CASES[case_id]
    as_sender(direct_vm, "lender")
    return contract.register_adversarial_case(
        policy_id, version, entry["attack_category"], entry["notes"], bundle_json(entry),
        entry["expected_verdict"], entry["expected_score_min"], entry["expected_score_max"])


def finding(record: dict, subject_id: str) -> dict:
    for f in record["indicators"] + record["documents"]:
        if f["id"] == subject_id:
            return f
    raise KeyError(subject_id)


def present(record: dict) -> list:
    return [f["id"] for f in record["indicators"] if f["state"] == "PRESENT"]


def receipt(record: dict, evidence_id: str) -> dict:
    for r in record["receipts"]:
        if r["evidence_id"] == evidence_id:
            return r
    raise KeyError(evidence_id)


def assert_bounds(record: dict, entry: dict):
    assert record["verdict"] == entry["expected_verdict"], (record["verdict"],
                                                            record["reason_codes"])
    assert entry["expected_score_min"] <= record["score"] <= entry["expected_score_max"], \
        (record["score"], record["score_breakdown"])
    if record["verdict"] not in ("APPROVED", "REVIEW_REQUIRED"):
        assert record["recommended_exposure"] == 0
        assert record["recommended_ltv_bps"] == 0
    assert record["eligible"] == (record["verdict"] == "APPROVED")
    assert "VERDICT:" + record["verdict"] in record["reason_codes"]


def captured_payload(direct_vm) -> dict:
    """The leader's canonical payload captured from the last round."""
    result, _leader_fn, _validator_fn = direct_vm._captured_validators[-1]
    return json.loads(result)


def answer_for(case_id: str) -> dict:
    return copy.deepcopy(CASES[case_id]["panel_answer"])


def warp(direct_vm, timestamp: str):
    """Move the transaction clock. genlayer-test 0.29.2's warp() updates the
    VM's datetime but its message refresh copies only sender/origin into the
    SDK's cached gl.message_raw, so a warp after deploy never reaches
    contract code. Set both; this touches the test clock only."""
    direct_vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp
