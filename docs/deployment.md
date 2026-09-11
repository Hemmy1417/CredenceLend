# Deployment

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
