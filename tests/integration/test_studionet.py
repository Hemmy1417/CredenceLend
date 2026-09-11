"""StudioNet integration: the canonical deployment in deploy/deployment.json,
checked over the network.

    python -m pytest tests/integration -v
    CREDENCELEND_LIVE_WRITES=1 python -m pytest tests/integration -v

Read-only by default (CI runs it that way, non-blocking): the deployed
source is byte-identical to contracts/credencelend.py, the deployed schema
exposes the public surface, the views answer, and an assessment recorded by
the live run reads back with its recorded verdict. With
CREDENCELEND_LIVE_WRITES=1 one write goes through real consensus: a fresh
ephemeral wallet registers as a borrower (StudioNet is gasless).

genlayer-py is used directly: gltest's ContractFactory cannot bind a
hosted contract from its schema on this SDK generation.
"""

import base64
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECORD = ROOT / "deploy" / "deployment.json"
TRANSCRIPT = ROOT / "deploy" / "live_scenarios_transcript.json"
RPC = "https://studio.genlayer.com/api"

pytestmark = pytest.mark.skipif(not RECORD.exists(), reason="no deployment recorded")
sys.path.insert(0, str(ROOT / "scripts"))


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last = None
    for attempt in range(6):
        try:
            request = urllib.request.Request(RPC, data=body, headers={
                "Content-Type": "application/json", "User-Agent": "credencelend-integration"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except Exception as err:          # noqa: BLE001 - transport errors vary
            last = err
            time.sleep(10 * (attempt + 1))
    raise last


@pytest.fixture(scope="module")
def deployment():
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client():
    import studionet_transport  # noqa: F401
    from genlayer_py import create_client
    from genlayer_py.chains import studionet
    return create_client(chain=studionet)


def test_deployed_source_is_the_committed_file(deployment):
    result = rpc("gen_getContractCode", [deployment["contract_address"]])["result"]
    deployed = result.encode() if result.lstrip().startswith("#") else base64.b64decode(result)
    local = (ROOT / "contracts" / "credencelend.py").read_bytes()
    assert hashlib.sha256(deployed).hexdigest() == hashlib.sha256(local).hexdigest() \
        == deployment["source_sha256"]


def test_deployed_schema_exposes_the_surface(deployment):
    schema = rpc("gen_getContractSchema", [deployment["contract_address"]])["result"]
    methods = set(schema["methods"])
    for name in ("register_policy", "register_borrower", "submit_evidence",
                 "request_credit_assessment", "submit_appeal", "request_reassessment",
                 "run_adversarial_case", "get_assessment", "assessment_status", "is_eligible",
                 "get_latest_assessment", "get_assessment_history", "health_check"):
        assert name in methods, name


def test_views_answer(deployment, client):
    read = lambda fn, a: client.read_contract(  # noqa: E731
        address=deployment["contract_address"], function_name=fn, args=a)
    assert read("health_check", [])["ok"] is True
    assert read("get_config", [])["contract_version"] == "0.1.0"
    assert read("get_assessment", ["CA-999999"])["found"] is False


@pytest.mark.skipif(not TRANSCRIPT.exists(), reason="no live run recorded")
def test_a_recorded_assessment_reads_back(deployment, client):
    transcript = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    if transcript.get("address") != deployment["contract_address"]:
        pytest.skip("the transcript belongs to another deployment")
    recorded = transcript["A"]["bola_records_only"]["observed"]
    record = client.read_contract(address=deployment["contract_address"],
                                  function_name="get_assessment",
                                  args=[recorded["assessment_id"]])
    assert record["verdict"] == recorded["verdict"] and record["score"] == recorded["score"]


@pytest.mark.skipif(os.environ.get("CREDENCELEND_LIVE_WRITES") != "1",
                    reason="writes to the canonical deployment are opt-in")
def test_a_write_through_consensus(deployment):
    import studionet_transport  # noqa: F401
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet
    from genlayer_py.types import TransactionStatus
    account = create_account()
    client = create_client(chain=studionet, account=account)
    tx = client.write_contract(address=deployment["contract_address"],
                               function_name="register_borrower",
                               args=["integration test borrower"], consensus_max_rotations=3)
    receipt = client.wait_for_transaction_receipt(
        transaction_hash=tx, status=TransactionStatus.FINALIZED, interval=5000, retries=240)
    leader = receipt["consensus_data"]["leader_receipt"]
    assert str((leader[0] if isinstance(leader, list) else leader)["execution_result"]) == \
        "SUCCESS"
    profile = client.read_contract(address=deployment["contract_address"],
                                   function_name="get_borrower_profile",
                                   args=[str(account.address).lower()])
    assert profile["found"] and profile["borrower_id"] == str(account.address).lower()
