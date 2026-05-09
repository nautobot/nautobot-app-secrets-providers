# Vaultwarden

Provider for [Vaultwarden](https://github.com/dani-garcia/vaultwarden), the lightweight Bitwarden-compatible server. Also works against the upstream Bitwarden self-hosted server, since the wire protocol is identical.

## How it works

The provider authenticates against the Bitwarden Vault API using your account email and master password. The master password never crosses the wire — it is run through PBKDF2-SHA256 (or Argon2id, depending on your account's KDF setting) locally to produce two keys: an authentication hash that is sent to `/identity/connect/token`, and a decryption key that unwraps the per-user symmetric key returned by the server. All cipher fields are then decrypted locally with that symmetric key.

**Organization items.** The provider also retrieves items owned by organizations you're a member of. The token response includes your PKCS#8 RSA-2048 private key (encrypted with your symmetric key), and `/api/sync` includes each organization's symmetric key wrapped with your RSA public key (RSA-OAEP). The provider unwraps each org's key on sync and selects the right (per-user vs per-org) symmetric key for each cipher based on its `organizationId`.

**Session caching.** Sessions — access token, unwrapped user keys, decrypted RSA private key, decrypted org keys — are cached in Django's cache framework, keyed by an HMAC of `(server_url, email, master_password)`. PBKDF2 (or Argon2id) is the dominant per-call cost (~300ms on a modern CPU); the cache reduces a typical retrieval to a single sync HTTP round-trip plus local AES decryption. Rotating the master password naturally produces a new cache key, so old sessions are never reused. If the cached access token is rejected by the server (HTTP 401), the provider transparently re-authenticates and updates the cache.

## Installation

The provider depends only on the `cryptography` library, which most Nautobot installs already have. Install with the `vaultwarden` extra to be explicit:

```bash
pip install "nautobot-secrets-providers[vaultwarden]"
```

If your Bitwarden account is configured to use Argon2id as the KDF (this is the default for new accounts created on recent server versions), you also need `argon2-cffi`:

```bash
pip install "nautobot-secrets-providers[vaultwarden-argon2]"
```

You can check your account's KDF in the Bitwarden web vault under **Account Settings → Security → Keys → Encryption Key Settings**. PBKDF2-SHA256 with 600,000 iterations is the default and works without Argon2 support.

## Configuration

Add a `vaultwarden` block to `PLUGINS_CONFIG` in `nautobot_config.py`. The provider supports either a single-server configuration:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "vaultwarden": {
            "url": os.environ["VAULTWARDEN_URL"],
            "email": os.environ["VAULTWARDEN_EMAIL"],
            "master_password": os.environ["VAULTWARDEN_MASTER_PASSWORD"],
            "verify_ssl": True,
        },
    },
}
```

…or a multi-server configuration where each `Secret` can pick which Vaultwarden server to query:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "vaultwarden": {
            "vaults": {
                "production": {
                    "url": os.environ["VW_PROD_URL"],
                    "email": os.environ["VW_PROD_EMAIL"],
                    "master_password": os.environ["VW_PROD_MASTER_PASSWORD"],
                },
                "staging": {
                    "url": os.environ["VW_STAGE_URL"],
                    "email": os.environ["VW_STAGE_EMAIL"],
                    "master_password": os.environ["VW_STAGE_MASTER_PASSWORD"],
                    "verify_ssl": False,
                },
            },
        },
    },
}
```

### Settings reference

| Key                     | Required | Default                       | Description                                                                                                                 |
| ----------------------- | -------- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `url`                   | yes      | —                             | Base URL of the Vaultwarden server (`https://vault.example.com`). Trailing slashes are tolerated.                           |
| `email`                 | yes      | —                             | Account email. Also used as the KDF salt — must match the account exactly, including case.                                  |
| `master_password`       | yes      | —                             | Account master password. Held in memory only; never written to the database or sent to the server in clear.                |
| `verify_ssl`            | no       | `True`                        | Set to `False` for self-signed dev servers. Don't disable this in production.                                               |
| `timeout`               | no       | `30.0`                        | Per-request timeout in seconds.                                                                                             |
| `device_name`           | no       | `nautobot-secrets-providers`  | Label shown in the account audit log under **Devices**.                                                                     |
| `device_identifier`     | no       | UUID5 of `url\|email`         | Stable per-instance device identifier. Override only if you want each Nautobot worker to register separately.               |
| `cache_session`         | no       | `True`                        | Cache the unwrapped session (access token + keys) in Django's cache framework. Set to `False` to force a full login per call. |
| `session_cache_seconds` | no       | `1800` (30 min)               | TTL for cached sessions. Bitwarden access tokens default to 1h; the lower TTL stays clear of the expiry edge.               |

## Creating a secret

When creating a `Secret` in Nautobot with this provider, you'll be asked for:

- **Vault** — Which configured server to use (only relevant when `vaults:` is configured).
- **Item** — Either the cipher's UUID (preferred — exact, no decryption sweep) or its decrypted name. UUIDs can be copied from the Bitwarden web vault: **Edit Item → Item ID** at the bottom.
- **Field Type** — One of:
    - `Password` — the item's password (most common).
    - `Username` — the item's username.
    - `Notes` — the item's notes field.
    - `TOTP Seed` — the raw TOTP secret. Use Nautobot Jobs to generate the rolling code.
    - `Custom Field` — a user-defined field on the item.
- **Field Name** — Required only when **Field Type** is `Custom Field`. Match the field name exactly.

## Organization items

For an organization-owned item, set the **Item** parameter to either:

- The cipher's UUID (preferred) — works identically to personal items.
- The cipher's decrypted name — the provider searches both your personal vault and every organization whose key it could unwrap, decrypting names with the appropriate per-org key.

If you encounter "not found" errors for items you know exist:

1. Confirm the account has access to the organization (check it appears in the web vault).
2. Confirm the `cryptography` library is recent enough to support RSA-OAEP. The provider uses RSA-OAEP-SHA1 by default (this is what Bitwarden's server emits — RFC 8017 OAEP padding, not for authenticity), and falls back to RSA-OAEP-SHA256 if the server uses it.
3. Check the org's enrollment status in Bitwarden — newly accepted invites may take a sync cycle to propagate keys.

## Validating your setup

If retrieval misbehaves and you want to rule out a server-side or network issue, the repo ships a self-contained reference Vaultwarden stack under `tests/integration/`. It builds a known-good vault from scratch (PBKDF2 + Argon2id accounts, a personal item, an org-owned item) and verifies all four retrieval paths against it. Run from a checkout of this app's source:

```no-highlight
cd tests/integration
make all
```

If `make all` passes but your production retrieval fails, the issue is environmental rather than a bug in the provider — common culprits in that order are:

1. **Nautobot can't reach the Vaultwarden URL.** Test with `curl -v {your-vault-url}/alive` from inside the Nautobot container (`invoke cli` to get a shell). A 200 response is what you want.
2. **The configured email or master password is wrong.** Vaultwarden uses email as the KDF salt — even a case difference makes the auth hash mismatch. The server returns HTTP 400 with `invalid_grant` in this case.
3. **The configured `verify_ssl` doesn't match your TLS setup.** Self-signed servers need `verify_ssl: False`; valid certs need `verify_ssl: True` (the default). Mismatches surface as `requests.exceptions.SSLError`.
4. **Cached session has stale state.** Set `cache_session: False` temporarily; if retrieval starts working, the cache had a stale entry. The provider auto-invalidates on HTTP 401, but bumping `session_cache_seconds` lower or restarting the cache backend always works as a manual reset.

See `tests/integration/README.md` for more on how the reference stack is built and what each scenario validates.

## Security notes

- The master password is loaded from `PLUGINS_CONFIG` at request time. Keep it in the environment, not in `nautobot_config.py` itself, and use a tool like `direnv` or a secrets-management init system (systemd `EnvironmentFile`, Docker secrets, etc.) to scope it to the Nautobot process.
- The cached session contains your unwrapped user symmetric key, RSA private key, and decrypted org keys — sensitive material. The cache backend (Redis by default in Nautobot) lives within the same trust boundary as `nautobot_config.py` itself. If you don't trust the cache backend with these, set `cache_session: False` and accept the per-call PBKDF2 overhead.
- The provider deliberately does not support API-key auth (`grant_type=client_credentials`). API keys remove the need to ship the master password but still require it for decryption — they don't provide meaningful additional security in this context, only complexity.
- If you rotate your master password, update `PLUGINS_CONFIG` and restart Nautobot. The new password produces a different cache key, so the old session won't be reused — but the old cached payload will sit in cache until its TTL expires unless your cache backend is restarted too.
- HMAC verification is performed in constant time (`hmac.compare_digest`) before AES decryption is attempted, so the provider is not vulnerable to padding-oracle attacks against malformed CipherStrings.
