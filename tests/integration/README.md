# Vaultwarden Integration Tests

End-to-end tests for the Vaultwarden secrets provider that run the actual `BitwardenClient` against a real Vaultwarden server in Docker.

The unit tests under `nautobot_secrets_providers/tests/test_providers.py` use `requests_mock` and synthetic fixtures, which is fast and reliable but can hide bugs where our self-consistent crypto matches the test fixtures but not what real Vaultwarden produces. These integration tests close that gap by hitting an actual server: registration goes through, login is verified by the server's PBKDF2 check, and decryption is verified against ciphertext the server itself never saw in plaintext.

## Quick start

```sh
cd tests/integration
make all
```

That runs `up` → `seed` → `test`:

| Target  | Effect                                                                                  |
|---------|-----------------------------------------------------------------------------------------|
| `up`    | Starts the Vaultwarden container, waits for `/alive` to return 200                      |
| `seed`  | Registers two accounts (PBKDF2 + Argon2id), creates personal items, creates an org     |
| `test`  | Runs the four integration scenarios against the seeded vault                            |
| `down`  | Stops the container (preserves `vw-data/` so seed is cached for next `up`)             |
| `clean` | Stops the container AND wipes `vw-data/` + `fixtures.json` (full reset)                 |
| `logs`  | Tails container logs                                                                    |
| `status`| `docker compose ps`                                                                     |

## What the four scenarios verify

1. **PBKDF2 personal-vault item.** Retrieves password, username, notes, custom field, and by-name lookup against an account with the default KDF (PBKDF2-SHA256, 600k iterations).
2. **Organization-owned item.** Validates the full asymmetric path: AES-decrypt PrivateKey → load PKCS#8 RSA-2048 → RSA-OAEP-SHA1 unwrap of org symmetric key → AES-decrypt org cipher fields.
3. **Argon2id account.** Same flow on an account configured for Argon2id (the newer-Vaultwarden default), validating the `argon2-cffi` code path.
4. **Session cache speedup.** Times a cold login (full PBKDF2) vs. a warm retrieval (using a hydrated session via `to_cache_payload` / `from_cache_payload`), asserting the warm path is at least 2x faster. Confirms the cache wiring eliminates the dominant PBKDF2 cost.

## Why drive `BitwardenClient` directly instead of through Nautobot

The Django/Nautobot integration layer is already covered by mocked unit tests. The integration tests' purpose is to validate the wire format and crypto against a real Bitwarden-protocol server. Bringing up the full Nautobot stack just for the same crypto validation would add infrastructure overhead without adding signal — the `BitwardenClient` is what does all the protocol-sensitive work.

## File layout

```
tests/integration/
├── Makefile              # up / seed / test / down / clean
├── README.md             # you are here
├── docker-compose.yml    # Vaultwarden container
├── .env.example          # copy to .env to override port/domain
├── .gitignore            # excludes vw-data, fixtures.json, .env
├── seed_vault.py         # registers accounts, creates items via the public API
├── run_integration.py    # the four test scenarios
├── vw-data/              # SQLite DB + state, mounted by the container (gitignored)
└── fixtures.json         # account credentials + item UUIDs (gitignored)
```

## Reproducibility

The Vaultwarden image tag is pinned in `docker-compose.yml`. The test data is fully reproducible from `seed_vault.py` — running `make clean && make all` from any clean checkout of this branch will produce the same set of test items (UUIDs change per run since they're server-generated, but field names/values are stable and surface in `fixtures.json`).

## When to update what

| Symptom                                              | Likely fix                                               |
|------------------------------------------------------|----------------------------------------------------------|
| `make up` fails with image-not-found                 | Bump `image:` tag in `docker-compose.yml`                |
| Seed fails on `/identity/accounts/register`           | Server may have changed registration payload — diff against the `bw` CLI source |
| Test fails on a real server but passes locally       | Run with `--verbose` flag and check the `requests_mock` fixtures match server output |
| Argon2id test fails with import error                | `uv run --with argon2-cffi` should handle this — check uv is on PATH |

## Troubleshooting

If `make up` says Vaultwarden is up but `/alive` doesn't respond:
```sh
docker compose logs vaultwarden | tail -50
```
Common causes: port collision (override via `VAULTWARDEN_PORT` in `.env`), or stale state from a previous run mismatched against the current image (run `make clean`).

If the cache speedup test fails with timing too close to cold:

- Check that PBKDF2 iterations are still 600000 in `seed_vault.py`. Lower iterations make cold faster and erode the speedup ratio.
- Loaded test machines or VMs with throttled CPU can produce variable timings; rerun a few times.
