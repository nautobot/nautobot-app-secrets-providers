"""Integration test runner for the Vaultwarden secrets provider.

Reads `fixtures.json` (produced by `seed_vault.py`) and exercises the underlying
`BitwardenClient` against the live Vaultwarden container. Tests four scenarios:

1. Personal-vault item retrieval (PBKDF2 account)
2. Organization-owned item retrieval (RSA-OAEP unwrap path)
3. Argon2id KDF account retrieval
4. Session-cache behaviour (timing-based - second call should be much faster
   because PBKDF2 / Argon2id is skipped)

Why drive the client directly instead of through Nautobot:

The Django/Nautobot integration layer is already covered by mocked unit tests.
The point of this integration test is to validate the wire format and crypto
*against a real Bitwarden-protocol server* - that's what the client does. Bringing
up a full Nautobot stack just for the same crypto validation would be wasteful.

Run via:
    make test     (recommended)
    OR: uv run --with cryptography --with argon2-cffi --with requests \\
            python run_integration.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make the provider's client module importable as a sibling of this dir.
THIS_DIR = Path(__file__).resolve().parent
PROVIDERS_DIR = THIS_DIR.parent.parent / "nautobot_secrets_providers" / "providers"
sys.path.insert(0, str(PROVIDERS_DIR))

import _vaultwarden_client as vw  # noqa: E402

# Pretty-print helpers - keep output structured so failures are easy to read.
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


class TestFailure(Exception):
    """Raised when a scenario assertion fails."""


def assert_equal(actual, expected, label):
    if actual != expected:
        raise TestFailure(f"{label}: expected {expected!r}, got {actual!r}")


def run_test(name, fn):
    print(f"  [{name}] ... ", end="", flush=True)
    start = time.perf_counter()
    try:
        fn()
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"{GREEN}PASS{RESET} ({elapsed_ms:.0f}ms)")
        return True
    except Exception as err:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"{RED}FAIL{RESET} ({elapsed_ms:.0f}ms)")
        print(f"      {err}")
        return False


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

def test_pbkdf2_personal(fixtures):
    """Retrieve every field type from a PBKDF2 account's personal-vault item."""
    pbkdf2 = fixtures["accounts"]["pbkdf2"]
    item = pbkdf2["personal_item"]
    client = vw.BitwardenClient(
        server_url=fixtures["server_url"],
        email=pbkdf2["email"],
        master_password=pbkdf2["master_password"],
    )
    assert_equal(client.get_secret(item["id"], "password"), item["password"], "password by UUID")
    assert_equal(client.get_secret(item["id"], "username"), item["username"], "username by UUID")
    assert_equal(client.get_secret(item["id"], "notes"), item["notes"], "notes by UUID")
    assert_equal(client.get_secret(item["name"], "password"), item["password"], "password by name")
    snmp = item["custom_fields"]["snmp_community"]
    assert_equal(client.get_secret(item["id"], "snmp_community"), snmp, "custom field by UUID")


def test_organization_item(fixtures):
    """Retrieve an org-owned item - exercises the RSA-OAEP + per-org key path."""
    pbkdf2 = fixtures["accounts"]["pbkdf2"]
    org_item = pbkdf2["organization"]["item"]
    client = vw.BitwardenClient(
        server_url=fixtures["server_url"],
        email=pbkdf2["email"],
        master_password=pbkdf2["master_password"],
    )
    assert_equal(client.get_secret(org_item["id"], "password"), org_item["password"], "org password by UUID")
    assert_equal(client.get_secret(org_item["id"], "username"), org_item["username"], "org username by UUID")
    assert_equal(client.get_secret(org_item["name"], "password"), org_item["password"], "org password by name")
    # Sanity: the session must hold a decrypted org key for the org we created.
    org_id = pbkdf2["organization"]["id"].lower()
    if org_id not in client.session.org_keys:
        raise TestFailure(
            f"expected org key {org_id} in session.org_keys, found {list(client.session.org_keys)}"
        )


def test_argon2id_account(fixtures):
    """Same flow but the master key is derived via Argon2id rather than PBKDF2."""
    argon2 = fixtures["accounts"]["argon2id"]
    item = argon2["personal_item"]
    client = vw.BitwardenClient(
        server_url=fixtures["server_url"],
        email=argon2["email"],
        master_password=argon2["master_password"],
    )
    assert_equal(client.get_secret(item["id"], "password"), item["password"], "argon2id password")
    assert_equal(client.get_secret(item["id"], "username"), item["username"], "argon2id username")


def test_session_cache_speedup(fixtures):
    """Manually exercise the session caching pattern.

    The provider class wraps this in Django's cache; here we use the raw
    to_cache_payload / from_cache_payload round-trip to verify that a hydrated
    session skips PBKDF2 entirely.
    """
    pbkdf2 = fixtures["accounts"]["pbkdf2"]
    item = pbkdf2["personal_item"]

    # Cold start - measures full login including PBKDF2.
    cold_client = vw.BitwardenClient(
        server_url=fixtures["server_url"],
        email=pbkdf2["email"],
        master_password=pbkdf2["master_password"],
    )
    cold_start = time.perf_counter()
    cold_client.login()
    cold_login_ms = (time.perf_counter() - cold_start) * 1000

    # Hydrate the cache from the cold session, then run a second client with it.
    payload = cold_client.session.to_cache_payload()
    rehydrated = vw.BitwardenSession.from_cache_payload(payload)
    warm_client = vw.BitwardenClient(
        server_url=fixtures["server_url"],
        email=pbkdf2["email"],
        master_password=pbkdf2["master_password"],
        session=rehydrated,
    )
    warm_start = time.perf_counter()
    warm_value = warm_client.get_secret(item["id"], "password")
    warm_total_ms = (time.perf_counter() - warm_start) * 1000

    assert_equal(warm_value, item["password"], "warm-cache retrieval")

    # Print timings inline so a passing test still shows the speedup.
    print(f"\n      cold login: {cold_login_ms:.0f}ms, warm retrieval (sync only): {warm_total_ms:.0f}ms",
          end="")

    # PBKDF2 with 600k iterations is ~250-500ms; sync is typically <100ms locally.
    # Require at least a 2x speedup to declare "the cache works". This is an
    # intentionally generous threshold - on slow machines PBKDF2 can be very slow,
    # making the speedup ratio much larger.
    if warm_total_ms >= cold_login_ms / 2:
        raise TestFailure(
            f"expected warm retrieval to be at least 2x faster than cold login; "
            f"cold={cold_login_ms:.0f}ms warm={warm_total_ms:.0f}ms"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", default="fixtures.json", type=Path)
    args = parser.parse_args()

    if not args.fixtures.exists():
        print(f"{RED}fixtures file not found: {args.fixtures}{RESET}", file=sys.stderr)
        print(f"{YELLOW}Run `make seed` first.{RESET}", file=sys.stderr)
        return 1

    fixtures = json.loads(args.fixtures.read_text())
    print(f"\nIntegration tests against {fixtures['server_url']}\n")

    scenarios = [
        ("PBKDF2 personal-vault item", lambda: test_pbkdf2_personal(fixtures)),
        ("Organization-owned item",    lambda: test_organization_item(fixtures)),
        ("Argon2id account",           lambda: test_argon2id_account(fixtures)),
        ("Session cache speedup",      lambda: test_session_cache_speedup(fixtures)),
    ]
    results = [run_test(name, fn) for name, fn in scenarios]

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} scenarios passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
