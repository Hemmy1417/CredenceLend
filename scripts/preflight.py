#!/usr/bin/env python3
"""Preflight: fast structural checks that need no network and no GenVM.

Run before the Direct Mode suite and the linter (CI does). Every check is
named; the script prints PASS/FAIL per check and exits non-zero on any
failure. It proves repository invariants, not contract behaviour.

  python scripts/preflight.py
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
import sys
import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "credencelend.py"
FIXTURES = ROOT / "fixtures"
RUNNER = "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"
FETCH_BYTES_CAP = 8000
VERDICTS = ("APPROVED", "REVIEW_REQUIRED", "SUSPICIOUS", "INSUFFICIENT_EVIDENCE",
            "STALE_EVIDENCE", "CONFLICTING_EVIDENCE", "SOURCE_UNAVAILABLE", "REJECTED",
            "INCONCLUSIVE")

# Brief section 11: attacks covered only in Direct Mode (the rest are cases in
# fixtures/cases.json, run through both the borrower path and the engine).
DIRECT_ONLY = {
    "UNSUPPORTED_LEADER_SCORE": "test_leader_inflating_a_fact_is_refused",
    "UNSUPPORTED_VALIDATOR_SCORE": "test_validator_undecided_where_the_leader_decided",
    "AUTHENTICITY_DISAGREEMENT": "test_validators_disagreeing_on_authenticity",
    "POLICY_REPLAY": "test_replay_after_a_policy_change",
    "LATE_APPEAL": "test_expired_appeal",
}

# Brief section 19: every named Direct Mode path and the test that covers it.
BRIEF_TESTS = {
    "verified repayment history": "test_strong_borrower_is_approved_with_bounded_terms",
    "multiple consistent sources": "test_multi_source_consistent_borrower",
    "current income, limited history": "test_weak_history_with_income_needs_review",
    "legitimate unusual activity explained": "test_sample_assessment_readable",
    "appeal with valid new evidence": "test_valid_appeal_with_new_evidence",
    "missing evidence": "test_missing_evidence",
    "stale evidence": "test_retirement_only_after_an_assessment_saw_it_stale",
    "conflicting evidence": "test_conflicting_records_block_approval_regardless_of_score",
    "forged document": "test_forged_and_impersonated_sources_are_not_trusted",
    "wrong wallet": "test_wrong_wallet",
    "duplicate evidence": "test_duplicate_evidence_is_refused",
    "source unavailable": "test_source_unavailable",
    "inactive policy": "test_inactive_policy",
    "malformed numeric input": "test_exception_and_numeric_abuse_fail_closed_without_crashing",
    "expired appeal": "test_expired_appeal",
    "policy version mismatch": "test_policy_version_mismatch_fails_closed",
    "unsupported source category": "test_unsupported_source_category_is_not_fetched",
    "prompt injection in document text": "test_code_catches_explicit_injection_without_a_model",
    "prompt injection in webpage content": "test_subtle_injection_is_named_by_the_panel_with_a_quote",
    "leader proposes a high score": "test_leader_inflating_a_fact_is_refused",
    "validator proposes an out-of-range score": "test_payload_carries_no_score_verdict_or_exposure",
    "validators disagree on fraud": "test_validators_disagreeing_on_authenticity",
    "evidence reused for another borrower": "test_copied_history_is_flagged_twice_when_its_owner_committed_first",
    "source content changes between retrievals": "test_source_divergence_between_nodes",
    "manipulated screenshot metadata": "test_screenshot_metadata_contradiction_is_an_unsupported_claim",
    "fake official source": "test_forged_and_impersonated_sources_are_not_trusted",
    "legitimate borrower flagged by a simplistic rule": "test_the_first_committer_is_not_flagged_by_a_later_copy",
}

RESULTS = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else "  -> " + detail))


def words(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.casefold())


def contract_checks():
    raw = CONTRACT.read_bytes()
    lines = raw.decode("utf-8").split("\n")
    check("contract has no CR bytes", b"\r" not in raw)
    check("contract is ASCII", all(b < 128 for b in raw),
          "non-ASCII bytes break the linter and hosted schema encoding")
    check("line 1 is the version comment", lines[0] == "# v0.1.0", lines[0])
    check("line 2 pins the runner", lines[1] == '# { "Depends": "' + RUNNER + '" }', lines[1])
    check("line 3 is blank (Depends block is load-bearing)", lines[2] == "")
    text = raw.decode("utf-8")
    for alias in ("py-genlayer:test", "py-genlayer:latest"):
        check("no runner alias " + alias, alias not in text)
    version = re.search(r'^CONTRACT_VERSION = "([^"]+)"', text, re.M)
    check("CONTRACT_VERSION matches the header",
          version is not None and "# v" + version.group(1) == lines[0])
    check("exactly one gl.Contract", len(re.findall(r"^class \w+\(gl\.Contract\):", text, re.M)) == 1)
    check("no payout or transfer logic",
          "emit_transfer" not in text and "gl.get_contract_at" not in text)
    floats = [t.string for t in tokenize.generate_tokens(io.StringIO(text).readline)
              if (t.type == tokenize.NUMBER and re.search(r"[.eEjJ]", t.string))
              or (t.type == tokenize.NAME and t.string == "float")]
    check("no float literal or float() in the contract (integer arithmetic only)",
          not floats, ", ".join(floats))
    check("no filesystem, clock or randomness in the contract",
          not re.search(r"\bopen\(|\bimport (os|time|random|datetime|requests)\b", text))


def secret_checks():
    pattern = re.compile(r"0x[0-9a-fA-F]{64}")
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts \
                or ".data" in path.parts:
            continue
        if path.suffix.lower() not in (".py", ".md", ".json", ".yml", ".yaml", ".txt",
                                       ".toml", ".cfg", ".ini", ".html", ".example", ""):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in content.splitlines():
            if pattern.search(line) and "private" in line.lower():
                offenders.append(str(path.relative_to(ROOT)))
                break
    check("no private keys in the tree", not offenders, ", ".join(offenders))
    env_files = [p.name for p in ROOT.glob(".env*") if p.is_file() and p.name != ".env.example"]
    check("no .env files in the tree (only .env.example)", not env_files, ", ".join(env_files))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    check(".env.example carries no values",
          all(line.strip().endswith("=") for line in example.splitlines()
              if line.strip() and not line.startswith("#")))
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check(".data/ and .env are gitignored", ".data/" in ignore and ".env" in ignore)
    config = (ROOT / "gltest.config.yaml").read_text(encoding="utf-8")
    check("gltest config carries no interpolated secrets", "${" not in config)
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").strip().splitlines()
    check("fixtures are byte-exact in git (-text, last rule)",
          attributes[-1].strip() == "fixtures/** -text")


def fixture_checks():
    sys.path.insert(0, str(ROOT / "scripts"))
    import generate_fixtures
    built = generate_fixtures.build()
    differ = [p for p, data in built.items()
              if not (FIXTURES / p).exists() or (FIXTURES / p).read_bytes() != data]
    check("fixtures regenerate byte-exact from scripts/generate_fixtures.py",
          not differ, ", ".join(differ))
    on_disk = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*") if p.is_file()}
    extra = sorted(on_disk - set(built))
    check("no fixture file outside the generator", not extra, ", ".join(extra))

    catalogue = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    cases = catalogue["cases"]
    ids = [c["case_id"] for c in cases]
    check("case ids are unique", len(ids) == len(set(ids)))
    keys = ("case_id", "attack_category", "wallet", "evidence", "expected_verdict",
            "expected_score_min", "expected_score_max", "notes", "decided_by",
            "panel_answer", "onchain", "needs")
    missing = [c["case_id"] for c in cases if any(k not in c for k in keys)]
    check("every case names input, verdict, score bounds and deciding layer",
          not missing, ", ".join(missing))
    bad = [c["case_id"] for c in cases if c["expected_verdict"] not in VERDICTS
           or not 0 <= c["expected_score_min"] <= c["expected_score_max"] <= 100]
    check("every case expects a known verdict and valid bounds", not bad, ", ".join(bad))
    panel_needed = [c["case_id"] for c in cases
                    if c["decided_by"] == "PANEL" and c["onchain"] and not c["panel_answer"]]
    check("every panel-decided case carries its recorded panel answer",
          not panel_needed, ", ".join(panel_needed))

    tests = "\n".join(p.read_text(encoding="utf-8")
                      for p in (ROOT / "tests" / "direct").glob("*.py"))
    referenced = set()
    for c in cases:
        for e in c["evidence"]:
            referenced.add(e.get("sha_of", e["path"]))
            if "sha256" not in e:
                referenced.add(e["path"])
    for bundle in catalogue["bundles"].values():
        referenced.update(e["path"] for e in bundle)
    unused = sorted(p for p in on_disk if p not in referenced and p not in (
        "cases.json", "wallets.json") and p not in tests)
    check("every evidence document is used by a case or a test", not unused, ", ".join(unused))
    unpublished = [e["path"] for c in cases for e in c["evidence"]
                   if "sha256" in e and (FIXTURES / e["path"]).exists()]
    check("unreachable locations are never published", not unpublished, ", ".join(unpublished))

    docs = [p for p in FIXTURES.rglob("*") if p.is_file()
            and p.name not in ("cases.json", "wallets.json")]
    big = [p.name for p in docs if p.stat().st_size > FETCH_BYTES_CAP]
    check("every evidence document fits the fetch cap", not big, ", ".join(big))
    cr = [p.name for p in docs if b"\r" in p.read_bytes()]
    check("evidence documents are LF-only (hashes survive checkouts)", not cr, ", ".join(cr))

    ungrounded = []
    for c in cases:
        answer = c["panel_answer"] or {}
        files = {"E" + str(i + 1): e["path"] for i, e in enumerate(c["evidence"])}
        entries = list((answer.get("documents") or {}).values()) + \
            list((answer.get("indicators") or {}).values()) + \
            ([answer["explanation"]] if answer.get("explanation") else [])
        for entry in entries:
            for q in entry.get("quotes", []):
                source = words((FIXTURES / files[q["evidence_id"]]).read_text(encoding="utf-8"))
                needle = words(q["text"])
                if not any(source[i:i + len(needle)] == needle for i in range(len(source))):
                    ungrounded.append(c["case_id"] + " " + q["evidence_id"])
    check("every recorded panel quote is verbatim in its document",
          not ungrounded, "; ".join(ungrounded))


def coverage_checks():
    tests = "\n".join(p.read_text(encoding="utf-8")
                      for p in (ROOT / "tests" / "direct").glob("test_*.py"))
    catalogue = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    onchain = {c["attack_category"] for c in catalogue["cases"] if c["onchain"]}
    contract = CONTRACT.read_text(encoding="utf-8")
    brief = re.search(r"ATTACK_CATEGORIES = \((.*?)\)\n", contract, re.S).group(1)
    brief = [a for a in re.findall(r'"([A-Z_]+)"', brief)
             if a not in ("LEGITIMATE_BASELINE", "OTHER")]
    check("the contract lists the brief's 30 attack categories", len(brief) == 30)
    uncovered = [a for a in brief if a not in onchain
                 and "def " + DIRECT_ONLY.get(a, "-") + "(" not in tests]
    check("every attack category is a case or a named Direct Mode test",
          not uncovered, ", ".join(uncovered))
    missing = [path for path, fn in BRIEF_TESTS.items() if "def " + fn + "(" not in tests]
    check("every brief section 19 path has a named test", not missing, ", ".join(missing))
    names = ("test_contract_smoke.py", "test_scoring_boundaries.py",
             "test_evidence_validation.py", "test_prompt_injection.py",
             "test_adversarial_cases.py", "test_consensus_equivalence.py", "test_appeals.py")
    absent = [n for n in names if not (ROOT / "tests" / "direct" / n).exists()]
    check("the brief's seven test modules exist", not absent, ", ".join(absent))


def address_checks():
    record = ROOT / "deploy" / "deployment.json"
    if not record.exists():
        check("deployment record (skipped: not deployed yet)", True)
        return
    deployment = json.loads(record.read_text(encoding="utf-8"))
    canonical = deployment["contract_address"].lower()
    allowed = {canonical} | {a.lower() for a in deployment.get("other_addresses", {}).values()}
    wallets = json.loads((FIXTURES / "wallets.json").read_text(encoding="utf-8"))
    allowed |= {a.lower() for a in wallets.values()}
    stray = []
    docs = [ROOT / "README.md", ROOT / "SUBMISSION.md", ROOT / "DECISION.md"] + \
        list((ROOT / "docs").glob("*.md"))
    for path in docs:
        if not path.exists():
            continue
        for address in re.findall(r"0x[0-9a-fA-F]{40}(?![0-9a-fA-F])",
                                  path.read_text(encoding="utf-8")):
            if address.lower() not in allowed:
                stray.append(f"{path.name}:{address}")
    placeholders = [p.name for p in docs if p.exists() and re.search(
        r"LIVE_SUMMARY|TO_BE_FILLED|TODO", p.read_text(encoding="utf-8"))]
    check("no unfilled placeholders in the docs", not placeholders, ", ".join(placeholders))
    check("docs name only the recorded addresses (one canonical deployment)",
          not stray, ", ".join(sorted(set(stray))))
    source = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    check("deployment record names the current contract bytes",
          deployment.get("source_sha256") == source,
          f"record {deployment.get('source_sha256')} vs tree {source}")


def main():
    contract_checks()
    secret_checks()
    fixture_checks()
    coverage_checks()
    address_checks()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS)} checks, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
