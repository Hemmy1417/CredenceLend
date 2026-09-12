# Deployment

## The deployment of record

| Item | Value |
|---|---|
| Contract | `0x583ae5d8c2b09A1EE7eafb993dea72546372bc99` |
| Explorer | https://explorer-studio.genlayer.com/address/0x583ae5d8c2b09A1EE7eafb993dea72546372bc99 (the Code tab shows the deployed source) |
| Deploy transaction | `0x7f048faa5b43d3b765623ffed1fddf96f585eee28c033a503fb7ccf97670507a` |
| Status | `FINALIZED`, leader execution `SUCCESS`, validator votes `AGREE` x5 |
| Source | `contracts/credencelend.py` at commit `a261d28`, blob `7b811e2`, sha256 `f56e6009...0ede` |
| Source parity | the source read back with `gen_getContractCode` has the same sha256 (`python scripts/deploy_studionet.py --verify`) |
| Signer | `0x00192512c2f4F40c00840e3E313C8f2204DA8ec6` |

`deploy/deployment.json` is the machine-readable record and also lists the
addresses that are NOT deployments of record: three disposable diagnostic
deployments (`deploy/diagnostics/`), and a first canonical deployment,
`0x25FEDE0811b95697A333633b611B67f8A250eE66`, superseded before its live run
finished. The contract bytes are identical in both; what differed was the
live run's own setup, which had one borrower appeal with another borrower's
document. That registered those bytes to the wrong wallet, so a later case
was flagged as cross-borrower reuse - the contract behaving exactly as
designed, on state the run itself had spoiled. The script now has each
borrower appeal with their own document, and the run was repeated from a
clean deployment.

## Network and assumptions

| Item | Value |
|---|---|
| Network | GenLayer StudioNet, chain id 61999 |
| RPC | `https://studio.genlayer.com/api` |
| Explorer | `https://explorer-studio.genlayer.com` (`/address/<address>` has a Code tab with the deployed source; `/tx/<hash>`) |
| Runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`, pinned in the contract header |
| Gas | StudioNet is gasless; a signer needs no funds |
| Rate limits | per IP: 60 requests a minute, 1000 an hour. `scripts/studionet_transport.py` retries transport failures and rate-limit answers only - never a contract revert |

## Keys and environment

No private key is read from the environment and none is committed.

| File (gitignored) | Created by | Holds |
|---|---|---|
| `.data/deployer.json` | `scripts/deploy_studionet.py` on first run | the deployer key |
| `.data/demo_wallets.json` | `scripts/generate_fixtures.py` when `fixtures/wallets.json` does not exist | the lender and five demo borrower keys; their public addresses are in `fixtures/wallets.json` |
| `.data/live_accounts.json` | `scripts/live_scenarios.py` | one ephemeral "stranger" key |

`.env.example` lists the only two optional settings (`CREDENCELEND_LIVE_WRITES`,
`GENVM_VERSION`), both empty.

## Build

There is no build step: GenVM runs the Python source. The gates before a
canonical deployment are:

```bash
python scripts/preflight.py
```

```bash
python -m pytest tests/direct -q
```

```bash
genvm-lint check contracts/credencelend.py --json
```

```bash
python scripts/mutation_check.py
```

## Deploy

The contract must be committed and unmodified; the script refuses otherwise,
so the deployment corresponds to an identifiable commit.

```bash
python scripts/deploy_studionet.py
```

It signs with `.data/deployer.json`, waits for `FINALIZED`, requires the
leader's execution result to be `SUCCESS` (lifecycle status alone is not
execution success), reads the deployed source back with `gen_getContractCode`,
compares its sha256 with the committed file, and writes
`deploy/deployment.json`: address, deploy transaction, votes, source commit,
blob, both hashes and `byte_identical`.

## After deployment

Source parity, schema, health and version, read-only and keyless:

```bash
python scripts/deploy_studionet.py --verify
```

```bash
python scripts/inspect_deployment.py
```

A sample assessment through the GenLayer CLI (`genlayer network set studionet`
first). The evidence URLs must be publicly reachable and serve exactly the
committed bytes; `scripts/live_scenarios.py` does the whole flow with the
fixtures pinned at a commit on `raw.githubusercontent.com`:

```bash
python scripts/live_scenarios.py <address> --raw-base https://raw.githubusercontent.com/<owner>/<repo>/<commit>/fixtures/
```

Inspect a stored result:

```bash
genlayer call <address> get_assessment --args CA-000001
```

```bash
genlayer call <address> assessment_status --args CA-000001 2026-09-12T00:00:00Z
```

## Reset and teardown

A deployed contract cannot be deleted and its records are immutable by
design. To start clean, deploy a fresh instance (a new address) and point
`deploy/deployment.json` at it; move the previous address to
`other_addresses` with the reason. Deleting `.data/` rotates every local key;
`fixtures/wallets.json` must then be deleted too and the fixtures regenerated,
because the documents name the demo wallets.
