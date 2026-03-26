# Bitwarden CLI

This provider uses Bitwarden CLI running as an HTTP server endpoint (`bw serve`) to access a VaultWarden/Bitwarden backend. Nautobot interacts with the CLI server endpoint to fetch secret values.

The installation and configuration of the VaultWarden Server and Bitwarden CLI server is outside the scope of this documentation. Please refer to Bitwarden CLI documentation and your VaultWarden/Bitwarden deployment documentation for setup instructions.

## References

- https://bitwarden.com/help/cli/
- https://github.com/dani-garcia/vaultwarden
- https://hub.docker.com/r/vaultwarden/server

## Bitwarden CLI provider

This document describes the Bitwarden CLI provider for Nautobot Secrets Providers.
The provider fetches secrets from a Bitwarden/VaultWarden vault by talking to a
Bitwarden CLI instance that exposes an HTTP API (for example via `bw serve`).

Contents
- Prerequisites
- Quick start (development)
- Configuration
- Environment variables
- Secret parameters and examples
- Troubleshooting
- Security considerations
- Testing
- Appendix: example creds

## Prerequisites

- Bitwarden CLI (`bw`) available for development tasks (used to run `bw serve`).
- A running Bitwarden or VaultWarden instance with items to be retrieved.
- The Nautobot Secrets Providers app installed and enabled in your Nautobot installation.

## Configuration

Add the provider configuration under `PLUGINS_CONFIG` in your `nautobot_config.py`.
Example (production-friendly defaults shown as examples):

```python
PLUGINS = ["nautobot_secrets_providers"]

PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "bitwarden": {
            "base_url": os.getenv("BW_CLI_URL", "https://bitwarden-cli-api.example.com"),
            "username": os.getenv("BW_CLI_USER", ""),
            "password": os.getenv("BW_CLI_PASSWORD", ""),
            # Optional: path to a CA bundle file for TLS verification
            "ca_bundle_path": os.getenv("BW_CLI_CA_BUNDLE", ""),
            # Optional: enable/disable strict TLS validation in code (default True)
            "verify_ssl": is_truthy(os.getenv("BW_CLI_VERIFY_SSL", "True")),
        }
    }
}
```

Settings
- `base_url` (required): URL of the Bitwarden CLI service (e.g. `https://bitwarden-cli.example.com`).
- `username`, `password` (required): credentials used by the provider to authenticate to the CLI service.
- `verify_ssl` (optional, default `True`): when `False`, TLS verification is skipped (use only for development).
- `ca_bundle_path` (optional): path to a PEM bundle trusted by your system for validating the CLI server certificate.
- `BITWARDEN_FIELDS` (optional): override the default selectable fields presented in the UI (see code reference).

## Environment variables

When running the development stack you can set provider values with environment variables.
Create or edit `development/creds.env` or your environment with:

```dotenv
BW_CLI_URL=https://bitwarden-cli.example.com
BW_CLI_USER=example-user
BW_CLI_PASSWORD=example-password
BW_CLI_VERIFY_SSL=true
BW_CLI_CA_BUNDLE=/path/to/ca-bundle.pem
```

## Secret parameters and examples

When creating a Nautobot Secret that uses this provider, set these parameters:

- `secret_id` — the Bitwarden item UUID. Copy it from the Bitwarden web vault URL
  (the path segment after `/items/`) or obtain it with the CLI (`bw list items` / `bw get item <id>`).
- `secret_field` — which logical field to retrieve. Allowed values include:
    - `username`, `password`, `totp`, `uri`, `notes`
    - `custom` (requires `custom_field_name`)
    - `ssh_private_key`, `ssh_public_key`, `ssh_key_fingerprint`
    - `identity_*` and `card_*` mappings (e.g. `identity_firstName`, `card_number`)
    - `fido2Credentials`
- `custom_field_name` — the visible name of a custom field when `secret_field` is `custom`.

Example: fetch a password from an item:

```text
secret_provider: bitwarden
secret_parameters:
  secret_id: 9f8a7b6c-...-abcd1234
  secret_field: password
```

Example: fetch a custom field called `api_key`:

```text
secret_provider: bitwarden
secret_parameters:
  secret_id: 9f8a7b6c-...-abcd1234
  secret_field: custom
  custom_field_name: api_key
```

Notes on locating field names

- Use the Bitwarden web UI or `bw get item <id>` to inspect available fields and field labels.
- The Nautobot UI also queries available custom field names (see the provider's view tests for behavior).

## Troubleshooting

- "Bitwarden CLI responded with HTTP <code>": check `BW_CLI_URL`, the `secret_id`, and the CLI server logs.
- TLS failures: confirm `BW_CLI_CA_BUNDLE` points to a valid PEM bundle and `verify_ssl` is `true`.
- Authentication failures: verify `username`/`password` and that the CLI service accepts those credentials.
- Secret not found or field missing: confirm the `secret_id` points to an existing item and that the requested `secret_field` or `custom_field_name` exists on that item.
- Use container logs for debugging:

```bash
docker compose --project-name nautobot-secrets-providers -f development/docker-compose.base.yml -f development/docker-compose.dev.yml logs bitwarden_cli
docker compose --project-name nautobot-secrets-providers -f development/docker-compose.base.yml -f development/docker-compose.dev.yml logs nautobot
```

## Security considerations

- The Bitwarden CLI server (`bw serve`) is intended for local or controlled environments.
- Do NOT expose the CLI server to untrusted networks without strong access controls.
- Prefer running the CLI server on a private management network and fronting it with a reverse proxy or internal API gateway if needed.
- Avoid setting `verify_ssl=false` in production.

## Testing

Relevant tests live in the app test suite:

- `BitwardenCLISecretsProviderTestCase` (`tests/test_providers.py`)
- `BitwardenGetCustomFieldNamesTestCase` (`tests/test_providers.py`)
- `BitwardenCustomFieldNamesViewTestCase` (`tests/test_providers.py`)

Run the provider tests:

```bash
poetry run invoke unittest --label nautobot_secrets_providers.tests.test_providers
```

## Appendix: example `development/creds.env`

```dotenv
# Example development credentials (do NOT commit secrets)
BW_CLI_URL=https://bitwarden-cli.example.com
BW_CLI_USER=
BW_CLI_PASSWORD=
BW_CLI_VERIFY_SSL=true
BW_CLI_CA_BUNDLE=
```

## Appendix: running `bw serve` (development only)

1. Install the Bitwarden CLI (`bw`) locally.
2. Unlock a session interactively (if required) and run:

```bash
bw serve
```

Only use `bw serve` on trusted networks and for development/testing. The CLI server can expose unlocked vault data and must be protected.

## Appendix: Bitwarden CLI Server - Gotchas and Implementation Notes

The Bitwarden CLI (`bw`) is a command-line tool for interacting with Bitwarden vaults. It can be run as an HTTP server endpoint using `bw serve`, which allows Nautobot to fetch secret values from a VaultWarden/Bitwarden backend.

!!!Warning "Bitwarden CLI Server"

    The Bitwarden CLI server is designed for local, unauthenticated access to vault data. It is not intended for remote access or multi-user environments without additional security controls. Use with caution and ensure proper network and access controls are in place.

Use a reverse proxy or other network controls to restrict access to the CLI server if necessary.

e.g. Traefik configuration to add TLS and Basic Auth, for the `bitwarden-cli-api.example.local` hostname:

```yaml
labels:
    - "traefik.enable=true"
    - "traefik.http.routers.bitwarden_cli_api.tls=false"
    - "traefik.http.routers.bitwarden_cli_api.entrypoints=webhttps"
    - "traefik.http.routers.bitwarden_cli_api.rule=Host(`bitwarden-cli-api.example.local`)"
    - "traefik.http.routers.bitwarden_cli_api.service=bitwarden_cli_api_service"
    - "traefik.http.services.bitwarden_cli_api_service.loadbalancer.server.port=8087"
    # Basic auth middleware using htpasswd-style entry provided via env var
    # Ensure BW_CLI_AUTH_STR is exported in the environment used by docker-compose/stack
    - "traefik.http.middlewares.vaultwarden_test_auth.basicauth.users=${BW_CLI_AUTH_STR}"
    - "traefik.http.routers.bitwarden_cli_api.middlewares=vaultwarden_test_auth"
```

### Syncing

Bitwarden CLI server does not automatically reflect changes made in the vault as soon as the vault is **unlocked**. You need to add a `bw sync` command that is periodically refreshing the data.

The example below is a script for a docker swarm service with the ppatlabs/bitwarden-cli:latest image. Add this entrypoint script to refresh the data every 5 minutes:

```bash
#!/bin/sh
set -e

# If the Docker secret file exists, read it and export as BW_HOST
if [ -f /run/secrets/bw_host ]; then
  export BW_HOST="$(cat /run/secrets/bw_host)"
fi

# If the Docker secret file exists, read it and export as BW_PASSWORD
if [ -f /run/secrets/bw_password ]; then
  export BW_PASSWORD="$(cat /run/secrets/bw_password)"
fi

# If the Docker secret file exists, read it and export as BW_USER and BW_USERNAME
if [ -f /run/secrets/bw_user ]; then
  export BW_USER="$(cat /run/secrets/bw_user)"
  export BW_USERNAME="${BW_USER}"
fi

# Background sync loop
(
    sleep 300   # 5 minutes
    while true; do
      /bw sync || echo "bw sync failed"
      sleep 300
    done
) &

# Execute the original image entrypoint with the container CMD as arguments.
# This allows the original entrypoint to do its own setup (bw login, etc.)
# while the env vars exported above are already available.
exec /entrypoint.sh "$@"
```

### Vaultwarden with self-signed certs

To connect to Vaultwarden when it uses a self-signed certificate, choose one of these options:

- **Recommended:** set `NODE_EXTRA_CA_CERTS` to a trusted CA bundle file, for example:  
    `NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt`
- **Development/testing only:** set `BW_CLI_VERIFY_SSL=false` to disable TLS certificate verification.

Avoid disabling SSL verification in production.

### Example Docker Log Output from `bw serve`:

```plaintext
-----------------------------------------------------------------------------------------------
Configuring bitwarden cli to use server: https://vault.example.com...
Could not find dir, "/root/.config/Bitwarden CLI"; creating it instead.
Could not find data file, "/root/.config/Bitwarden CLI/data.json"; creating it instead.
Saved setting `config`.-----------------------------------------------------------------------------------------------
Logging into bitwarden and generating session token...
-----------------------------------------------------------------------------------------------
Unlocking bitwarden...
Vault is unlocked!-----------------------------------------------------------------------------------------------
Running provided CMD: serve --hostname=0.0.0.0 --port=8087...
```
