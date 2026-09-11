#!/usr/bin/env python3
"""Mutation kill check: prove the Direct Mode suite pins each load-bearing
guard, not merely that the code passes today.

For each mutation the contract is copied to a scratch directory with ONE
guard mechanically broken, and the whole Direct Mode suite runs against the
copy. A mutation is KILLED when the suite fails and SURVIVED when it passes
(an unpinned guard). The run starts with an accept-control: the unmodified
copy must pass, or every kill would be vacuous.

Anchors are code TEXT, never line numbers. An anchor that is not found
exactly once is reported as ANCHOR MISSING - the guard moved or was
deleted, which is its own finding. Equivalent mutants (a guard that a second
guard makes unobservable) are not listed; the ones considered and excluded
are named at the bottom of this file with the reason.

Run:  python scripts/mutation_check.py            (full sweep)
      python scripts/mutation_check.py --anchors  (anchor check only)
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = "contracts/credencelend.py"

MUTATIONS = [
    # -- verdict precedence (_derive) ---------------------------------------------------
    ("hard facts no longer SUSPICIOUS",
     "    if any(i in HARD_FACTS for i in present):\n",
     "    if False:\n"),
    ("unreachable or changed source no longer SOURCE_UNAVAILABLE",
     "    elif ROW_UNAVAILABLE in statuses or ROW_HASH_MISMATCH in statuses:\n",
     "    elif False:\n"),
    ("changed bytes no longer SOURCE_UNAVAILABLE",
     "    elif ROW_UNAVAILABLE in statuses or ROW_HASH_MISMATCH in statuses:\n",
     "    elif ROW_UNAVAILABLE in statuses:\n"),
    ("malformed document no longer INCONCLUSIVE",
     "    elif ROW_TOO_LARGE in statuses or ROW_UNPARSEABLE in statuses:\n",
     "    elif False:\n"),
    ("unusable model output no longer INCONCLUSIVE",
     "    elif payload[\"panel_state\"] == PANEL_INVALID:\n",
     "    elif False:\n"),
    ("panel injection or unsupported claim no longer SUSPICIOUS",
     "    elif any(i in PANEL_SUSPICIOUS for i in present) \\\n",
     "    elif False \\\n"),
    ("manipulated document no longer SUSPICIOUS",
     "            or any(s == MANIPULATION for s in doc_state.values()):\n",
     "            or False:\n"),
    ("conflicts no longer CONFLICTING_EVIDENCE",
     "    elif any(i in CONFLICTS for i in present):\n",
     "    elif False:\n"),
    ("missing required category no longer INSUFFICIENT",
     "    elif truly_missing:\n",
     "    elif False:\n"),
    ("stale-only required category no longer STALE_EVIDENCE",
     "    elif only_stale:\n",
     "    elif False:\n"),
    ("minimum evidence count not enforced",
     "    elif len(counted_all) < policy[\"minimum_evidence_count\"]:\n",
     "    elif False:\n"),
    ("minimum evidence count off by one",
     "    elif len(counted_all) < policy[\"minimum_evidence_count\"]:\n",
     "    elif len(counted_all) < policy[\"minimum_evidence_count\"] - 1:\n"),
    ("undecided inputs no longer INCONCLUSIVE",
     "    elif undecided:\n        verdict = \"INCONCLUSIVE\"\n",
     "    elif False:\n        verdict = \"INCONCLUSIVE\"\n"),
    ("an unclear linked document is not undecided",
     "        or any(doc_state[e] == UNCLEAR for e in payload[\"linked\"] if e in doc_state)\n",
     "        or False\n"),
    ("review score off by one",
     "    elif score < policy[\"review_score\"]:\n",
     "    elif score <= policy[\"review_score\"]:\n"),
    ("minimum score off by one",
     "    elif score < policy[\"minimum_score\"]:\n",
     "    elif score <= policy[\"minimum_score\"]:\n"),
    ("suspicious score not capped",
     "        score = min(score, policy[\"suspicious_score_cap\"])\n",
     "        score = score\n"),
    ("exposure offered whatever the verdict",
     "    if verdict in (\"APPROVED\", \"REVIEW_REQUIRED\"):\n",
     "    if True:\n"),
    ("income does not cap exposure",
     "        if inputs[\"monthly_income\"] > 0 and policy[\"income_exposure_multiple\"] > 0:\n",
     "        if False:\n"),
    ("policy LTV maximum ignored",
     "        ltv = min(policy[\"band_max_ltv_bps\"][band], policy[\"maximum_ltv_bps\"])\n",
     "        ltv = policy[\"band_max_ltv_bps\"][band]\n"),
    ("policy exposure maximum ignored",
     "        exposure = min(policy[\"band_max_exposure\"][band], policy[\"maximum_exposure\"])\n",
     "        exposure = policy[\"band_max_exposure\"][band]\n"),
    ("review verdict made eligible",
     "            \"eligible\": verdict == \"APPROVED\", \"confidence\": confidence,\n",
     "            \"eligible\": verdict != \"REJECTED\", \"confidence\": confidence,\n"),
    ("borrower statement counted as evidence",
     "                    and kinds[e] != SELF_ATTESTED]\n",
     "                    and True]\n"),
    # -- the score (_score) ----------------------------------------------------------------
    ("repaid loans not capped",
     "        (\"REPAID_LOANS\", min(len(repaid), w[\"max_repaid_loans\"]) * w[\"per_repaid_loan\"]),\n",
     "        (\"REPAID_LOANS\", len(repaid) * w[\"per_repaid_loan\"]),\n"),
    ("repeated loans counted twice",
     "            if status == \"REPAID\" and ref not in repaid:\n",
     "            if status == \"REPAID\":\n"),
    ("defaults cost nothing",
     "        (\"DEFAULTS\", -len(defaulted) * w[\"per_default\"]),\n",
     "        (\"DEFAULTS\", 0),\n"),
    ("every liquidation treated as explained",
     "    explained = liquidations if explanation == EXPLAINED else 0\n",
     "    explained = liquidations\n"),
    ("income statements summed",
     "            monthly = max(monthly, f[\"values\"][\"monthly\"])\n",
     "            monthly = monthly + f[\"values\"][\"monthly\"]\n"),
    ("income in another currency scored",
     "        if f[\"category\"] == \"INCOME_STATEMENT\" and f[\"currency\"] == currency:\n",
     "        if f[\"category\"] == \"INCOME_STATEMENT\":\n"),
    ("income points not capped",
     "        (\"INCOME\", min(w[\"income_points\"],\n",
     "        (\"INCOME\", max(w[\"income_points\"],\n"),
    ("full history points for any history",
     "        (\"HISTORY\", w[\"history_points\"] if months >= w[\"history_months\"]\n",
     "        (\"HISTORY\", w[\"history_points\"] if months >= 0\n"),
    ("full coverage points for partial coverage",
     "        (\"COVERAGE\", w[\"coverage_points\"] * len(covered) // len(required)\n",
     "        (\"COVERAGE\", w[\"coverage_points\"]\n"),
    ("leverage never penalized",
     "         if debt > 0 and debt * BPS_MAX > collateral * w[\"leverage_limit_bps\"] else 0),\n",
     "         if False else 0),\n"),
    ("leverage penalized at the limit",
     "         if debt > 0 and debt * BPS_MAX > collateral * w[\"leverage_limit_bps\"] else 0),\n",
     "         if debt > 0 and debt * BPS_MAX >= collateral * w[\"leverage_limit_bps\"] else 0),\n"),
    ("score not clamped to 100",
     "    score = max(0, min(100, total))\n",
     "    score = max(0, total)\n"),
    ("score not clamped to 0",
     "    score = max(0, min(100, total))\n",
     "    score = min(100, total)\n"),
    ("a liquidation in two records counted twice",
     "                if status == \"LIQUIDATED\" and ref not in loans:\n",
     "                if status == \"LIQUIDATED\":\n"),
    ("stale documents counted",
     "        if f[\"wallet\"] == ctx[\"wallet\"] and _freshness_of(f, ctx) == \"FRESH\" \\\n",
     "        if f[\"wallet\"] == ctx[\"wallet\"] \\\n"),
    # -- code-decided indicators ---------------------------------------------------------
    ("wallet mismatch not flagged",
     "                              if f[\"wallet\"] != ctx[\"wallet\"]], structured, rows))\n",
     "                              if False], structured, rows))\n"),
    ("income arithmetic not checked",
     "        if (f[\"category\"] == \"INCOME_STATEMENT\" and v[\"line_sum\"] != v[\"total\"]) \\\n",
     "        if (False) \\\n"),
    ("omitted loans not checked",
     "                or (f[\"category\"] == \"REPAYMENT_HISTORY\"\n"
     "                    and v[\"listed\"] != v[\"declared_total\"]):\n",
     "                or (False):\n"),
    ("future-dated document not flagged",
     "                              if f[\"as_of\"] > ctx[\"today\"]], structured, rows))\n",
     "                              if False], structured, rows))\n"),
    ("hidden text not flagged",
     "    out.append(_per_document(\"HIDDEN_TEXT\", list(hidden), allowed, rows))\n",
     "    out.append(_per_document(\"HIDDEN_TEXT\", [], allowed, rows))\n"),
    ("injection markers not flagged",
     "    out.append(_per_document(\"INJECTION_MARKER\", list(markers), allowed, rows))\n",
     "    out.append(_per_document(\"INJECTION_MARKER\", [], allowed, rows))\n"),
    ("overstated claim not flagged",
     "                and item[\"claimed_value\"] > f[\"values\"][CLAIM_FIELD[f[\"category\"]]]:\n",
     "                and False:\n"),
    ("conflicting loan records not flagged",
     "            if ref in seen and seen[ref][0] != rest:\n",
     "            if False:\n"),
    ("absence declared without examining every document",
     "    if not all(e in examined for e in committed):\n",
     "    if False:\n"),
    ("hidden characters not scanned",
     "    if any(ch in body for ch in HIDDEN_CHARACTERS):\n",
     "    if False:\n"),
    ("text documents linked without naming the wallet",
     "        elif _names_wallet(texts[eid], ctx[\"wallet\"]):\n",
     "        elif True:\n"),
    # -- provenance and retrieval ----------------------------------------------------------
    ("unlisted category allowed",
     "    if rule is None:\n        return (False, False, \"\")\n",
     "    if rule is None:\n        return (True, True, \"\")\n"),
    ("any location trusted",
     "        if canonical_url.startswith(canonical_prefix):\n",
     "        if True:\n"),
    ("borrower statements refused",
     "    if category == SELF_ATTESTED:\n        return (True, False, \"\")\n",
     "    if False:\n        return (True, False, \"\")\n"),
    ("not-allowed documents fetched",
     "    if not item[\"allowed\"]:\n        row[\"status\"] = ROW_NOT_ALLOWED\n",
     "    if False:\n        row[\"status\"] = ROW_NOT_ALLOWED\n"),
    ("bytes read without the hash check",
     "    if hashlib.sha256(body).hexdigest() != item[\"sha256\"]:\n",
     "    if False:\n"),
    ("oversized documents read",
     "    if len(body) > FETCH_BYTES_CAP:\n",
     "    if False:\n"),
    ("error responses read",
     "    if status < 200 or status >= 300 or body is None or len(body) == 0:\n",
     "    if body is None or len(body) == 0:\n"),
    ("booleans accepted as integers",
     "    return isinstance(value, int) and not isinstance(value, bool)\n",
     "    return isinstance(value, int)\n"),
    ("credentials in URLs accepted",
     "    if \"@\" in authority:\n",
     "    if False:\n"),
    ("other ports accepted",
     "        if port != \"443\":\n",
     "        if False:\n"),
    ("dot-segments accepted",
     "        if seg in (\".\", \"..\"):\n",
     "        if False:\n"),
    ("IP literal hosts accepted",
     "    if all_numeric or labels[-1].isdigit():\n",
     "    if False:\n"),
    # -- registries ------------------------------------------------------------------------
    ("later commitment flags the first committer",
     "        return seq is None or int(first_seq) < seq\n",
     "        return True\n"),
    ("own documents flagged as reuse",
     "        if first_wallet == ctx[\"wallet\"]:\n            return False\n",
     "        if False:\n            return False\n"),
    ("registry entry overwritten by later committers",
     "        if self.evidence_registry.get(sha256) is None:\n",
     "        if True:\n"),
    ("loans in another wallet's document registered",
     "            if f[\"category\"] != \"REPAYMENT_HISTORY\" or f[\"wallet\"] != ctx[\"wallet\"]:\n",
     "            if f[\"category\"] != \"REPAYMENT_HISTORY\":\n"),
    # -- the panel -------------------------------------------------------------------------
    ("panel convened despite a hard fact",
     "    elif any(f[\"state\"] == PRESENT for f in code_inds\n",
     "    elif False and any(f[\"state\"] == PRESENT for f in code_inds\n"),
    ("panel convened on unexamined evidence",
     "    if any(row_of[e][\"status\"] != ROW_EXAMINED for e in allowed):\n        skip = SKIP_NOT_EXAMINED\n",
     "    if False:\n        skip = SKIP_NOT_EXAMINED\n"),
    ("manipulation accepted without a quote",
     "        if state is None or (state == MANIPULATION and len(quotes) == 0):\n",
     "        if state is None:\n"),
    ("indicator accepted without meeting its quote rule",
     "        if state is None or (state == PRESENT and not satisfied):\n",
     "        if state is None:\n"),
    ("explanation accepted without both sides quoted",
     "        if state is None or (state == EXPLAINED and not satisfied):\n",
     "        if state is None:\n"),
    ("one-document contradiction accepted",
     "    if len(distinct) < min_docs:\n",
     "    if False:\n"),
    ("excluded document accepted in a quote",
     "    if any(kinds[e] in excluded for e in distinct):\n",
     "    if False:\n"),
    ("required document kind not demanded in a quote",
     "    if quote_kinds and not any(kinds[e] in quote_kinds for e in distinct):\n",
     "    if False:\n"),
    ("quote grounding skipped",
     "        position = _find_run(haystack, words, position)\n        if position < 0:\n",
     "        position = 0\n        if position < 0:\n"),
    # -- consensus -------------------------------------------------------------------------
    ("facts and scans not compared",
     "    for key in (\"facts\", \"linked\", \"markers\", \"hidden\"):\n",
     "    for key in ():\n"),
    ("row status and byte count not compared",
     "        if a[\"status\"] != b[\"status\"] or a[\"byte_count\"] != b[\"byte_count\"]:\n",
     "        if False:\n"),
    ("finding states not compared",
     "            if a[\"id\"] != b[\"id\"] or a[\"state\"] != b[\"state\"] or a[\"by\"] != b[\"by\"]:\n",
     "            if False:\n"),
    ("panel state not compared",
     "    if own[\"panel_state\"] != theirs[\"panel_state\"] \\\n",
     "    if False \\\n"),
    ("gate does not re-ground quotes",
     "        if not _quote_grounded(q, eligible, texts):\n",
     "        if False:\n"),
    ("gate does not recompute code indicators",
     "        if indicators[i] != plan[\"code_indicators\"][i]:\n",
     "        if False:\n"),
    ("gate does not recompute the panel decision",
     "    if p[\"panel_reason\"] != plan[\"skip\"]:\n",
     "    if False:\n"),
    ("gate accepts extra or missing payload keys",
     "    if not isinstance(p, dict) or sorted(p.keys()) != sorted(PAYLOAD_KEYS):\n",
     "    if not isinstance(p, dict):\n"),
    ("gate accepts a rebound round",
     "    if p[\"definition_hash\"] != ctx[\"definition_hash\"] \\\n",
     "    if False \\\n"),
    # -- lifecycle and views ---------------------------------------------------------------
    ("assessment under a changed policy stays fresh",
     "        if str(pv.status) != POLICY_ACTIVE:\n            return \"STALE\"\n",
     "        if False:\n            return \"STALE\"\n"),
    ("validity period ignored",
     "        if at > _iso_epoch(record[\"valid_until\"]):\n",
     "        if False:\n"),
    ("evidence age ignored after assessment",
     "                    at // 86400 - _date_days(f[\"as_of\"]) > limit:\n",
     "                    False:\n"),
    ("source-unavailable assessment not BLOCKED",
     "        if record[\"verdict\"] == \"SOURCE_UNAVAILABLE\":\n            return \"BLOCKED\"\n",
     "        if False:\n            return \"BLOCKED\"\n"),
    ("clock before creation not UNKNOWN",
     "        if at is None or at < created:\n",
     "        if at is None:\n"),
    ("superseded approval consumable",
     "            \"consumable\": record[\"eligible\"] and freshness == \"RELIABLE\" and is_latest,\n",
     "            \"consumable\": record[\"eligible\"] and freshness == \"RELIABLE\",\n"),
    ("appeal window not enforced",
     "        if _iso_epoch(now) > _iso_epoch(record[\"appeal_deadline\"]):\n",
     "        if False:\n"),
    ("appeal window off by one",
     "        if _iso_epoch(now) > _iso_epoch(record[\"appeal_deadline\"]):\n",
     "        if _iso_epoch(now) >= _iso_epoch(record[\"appeal_deadline\"]):\n"),
    ("an assessment appealed twice",
     "        if self.appeal_of.get(assessment_id) is not None:\n",
     "        if False:\n"),
    ("old evidence accepted as new",
     "            if int(ev.committed_seq) <= record[\"commitment_seq\"]:\n",
     "            if False:\n"),
    ("reassessment under a replaced policy",
     "        if str(pv.status) != POLICY_ACTIVE:\n            self._fail(\"policy version mismatch",
     "        if False:\n            self._fail(\"policy version mismatch"),
    ("cooldown not enforced",
     "            if _iso_epoch(now) < _iso_epoch(last[\"created_at\"]) \\\n",
     "            if False \\\n"),
    ("anyone may request an assessment",
     "        if sender != wallet and gl.message.sender_address != pv.owner:\n",
     "        if False:\n"),
    ("anyone may publish a policy version",
     "        if gl.message.sender_address != latest.owner:\n",
     "        if False:\n"),
    ("instruction in a declared purpose accepted",
     "    if _injection_hits(purpose) or _hidden_hits(purpose):\n",
     "    if False:\n"),
    ("fresh evidence retired",
     "        if not bool(ev.stale_seen):\n",
     "        if False:\n"),
    ("stale evidence never marked",
     "            if f[\"wallet\"] == ctx[\"wallet\"] and _freshness_of(f, ctx) == \"STALE\":\n",
     "            if False:\n"),
    ("the same document committed twice",
     "            if str(ev.sha256) == sha256:\n",
     "            if False:\n"),
    ("active evidence limit off by one",
     "        if len(active) >= MAX_ACTIVE_EVIDENCE:\n",
     "        if len(active) > MAX_ACTIVE_EVIDENCE:\n"),
    ("a case may run twice",
     "        if str(case.status) != CASE_REGISTERED:\n",
     "        if False:\n"),
    ("case pass ignores the score bounds",
     "            int(case.expected_score_min) <= outcome[\"score\"] <= int(case.expected_score_max)\n",
     "            True\n"),
    ("definition key set not enforced",
     "    if not isinstance(d, dict) or sorted(d.keys()) != sorted(DEFINITION_KEYS):\n",
     "    if not isinstance(d, dict):\n"),
    ("review score above minimum accepted",
     "    if d[\"review_score\"] > d[\"minimum_score\"]:\n",
     "    if False:\n"),
]

# Considered and excluded as equivalent (a second guard makes the first
# unobservable, so no test can tell the mutant from the original):
# - the wallet check in _counted_structured: a document about another wallet
#   is always a WALLET_MISMATCH hard fact, so the verdict is SUSPICIOUS and
#   the score capped whichever documents were counted.
# - the ALTERED check in _counted_structured: an altered document is always
#   a DOCUMENT_ALTERED hard fact, with the same consequence.


def run_suite(workdir: pathlib.Path) -> bool:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/direct", "-q", "-x",
         "-p", "no:cacheprovider", "--no-header"],
        cwd=workdir, capture_output=True, text=True)
    return completed.returncode == 0


def check_anchors(source: str) -> int:
    missing = 0
    for name, old, _new in MUTATIONS:
        hits = source.count(old)
        if hits != 1:
            print(f"ANCHOR MISSING ({hits} hits): {name}")
            missing += 1
    return missing


def main() -> None:
    source = (ROOT / CONTRACT).read_text(encoding="utf-8")
    missing = check_anchors(source)
    print(f"{len(MUTATIONS)} mutations, {missing} anchor problems")
    if "--anchors" in sys.argv:
        sys.exit(0 if missing == 0 else 1)

    scratch = pathlib.Path(tempfile.mkdtemp(prefix="credencelend-mut-"))
    work = scratch / "repo"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "deploy", "artifacts", ".data"))
    target = work / CONTRACT

    print("accept-control: unmodified copy must pass ...", flush=True)
    if not run_suite(work):
        print("CONTROL FAILED: the unmodified suite does not pass; aborting")
        sys.exit(1)
    print("control green\n", flush=True)

    killed = survived = 0
    for name, old, new in MUTATIONS:
        if source.count(old) != 1:
            continue
        target.write_text(source.replace(old, new), encoding="utf-8", newline="\n")
        passed = run_suite(work)
        target.write_text(source, encoding="utf-8", newline="\n")
        if passed:
            print(f"SURVIVED: {name}", flush=True)
            survived += 1
        else:
            print(f"killed:   {name}", flush=True)
            killed += 1
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"\nmutations: {killed} killed, {survived} survived, {missing} anchor missing")
    sys.exit(0 if survived == 0 and missing == 0 else 1)


if __name__ == "__main__":
    main()
