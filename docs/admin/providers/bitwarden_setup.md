# Bitwarden CLI

This provider uses Bitwarden CLI running as an HTTP server endpoint (`bw serve`) to access a VaultWarden/Bitwarden backend. Nautobot interacts with the CLI server endpoint to fetch secret values.

The installation and configuration of the VaultWarden Server and Bitwarden CLI server is outside the scope of this documentation. Please refer to Bitwarden CLI documentation and your VaultWarden/Bitwarden deployment documentation for setup instructions.

## References

- https://bitwarden.com/help/cli/
- https://github.com/dani-garcia/vaultwarden
- https://hub.docker.com/r/vaultwarden/server

## Bitwarden CLI provider

This document describes the Bitwarden CLI Secrets Provider that is compatible with VaultWarden.
The provider fetches secrets from a Bitwarden/VaultWarden vault by talking to a
Bitwarden CLI instance that exposes an HTTP API (for example via `bw serve`).

Contents
- Prerequisites
- Configuration
- Environment variables
- Secret parameters and examples
- Troubleshooting
- Security considerations
- Testing
- Appendix: example creds

## Prerequisites

- Bitwarden CLI (`bw`) available for development tasks (used to run `bw serve`).
- A running VaultWarden or Bitwarden instance with items to be retrieved.
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
            # Optional: request timeout in seconds (default 15)
            "request_timeout": int(os.getenv("BW_CLI_REQUEST_TIMEOUT", "15")),
            # Optional: retry behavior for transient 5xx errors
            "retry_total": int(os.getenv("BW_CLI_RETRY_TOTAL", "3")),
            "retry_backoff": float(os.getenv("BW_CLI_RETRY_BACKOFF", "0.3")),
            # Optional: item endpoint template (must include {secret_id})
            "item_endpoint": os.getenv("BW_CLI_ITEM_ENDPOINT", "/object/item/{secret_id}"),
            # Optional: endpoint used by the UI search picker
            "list_items_endpoint": os.getenv("BW_CLI_LIST_ITEMS_ENDPOINT", "/list/object/items"),
            # Optional: UI lookup cache TTL in seconds (default 0 = disabled)
            "cache_ttl": int(os.getenv("BW_CLI_CACHE_TTL", "0")),
        }
    }
}
```

Settings
- `base_url` (required): URL of the Bitwarden CLI service (e.g. `https://bitwarden-cli.example.com`). If a scheme is omitted, the provider will default to `https://`.
- `username`, `password` (required): credentials used by the provider to authenticate to the CLI service.
- `verify_ssl` (optional, default `True`): when `False`, TLS verification is skipped (use only for development).
- `ca_bundle_path` (optional): path to a PEM bundle trusted by your system for validating the CLI server certificate. The path is expanded and must point to an existing file.
- `request_timeout` (optional, default `15`): HTTP timeout in seconds for Bitwarden API requests.
- `retry_total` and `retry_backoff` (optional, defaults `3` and `0.3`): retry policy used for transient network and HTTP 5xx failures.
- `item_endpoint` (optional, default `/object/item/{secret_id}`): endpoint template used to fetch item payloads.
- `list_items_endpoint` (optional, default `/list/object/items`): endpoint used by the UI item-search picker (`?search=<text>`).
- `cache_ttl` (optional, default `0`): in-memory cache TTL for UI helper lookups (`Fetch Fields` / item-name helper). Set to `0` to disable caching.
- `BITWARDEN_FIELDS` (optional): override the default selectable fields presented in the UI (see code reference).

## Environment variables
You can set provider values with environment variables.
Create or edit `development/creds.env` or your environment with the following variables:

```dotenv
# Enable Bitwarden CLI provider (set to 'true' to enable)
NAUTOBOT_BITWARDEN_CLI_ENABLED=true

# Bitwarden CLI API base URL (full scheme + host)
BW_CLI_URL=https://bitwarden-cli-api.example.com

# Bitwarden CLI API username and password
BW_CLI_USER=your-bitwarden-cli-basic-auth-username@example.com
BW_CLI_PASSWORD=your-bitwarden-cli-basic-auth-password

# Optional: Path to CA bundle for TLS verification (if using self-signed certs)
# BW_CLI_CA_BUNDLE=/etc/ssl/certs/ca-bundle.trust.crt

# Optional: Set to 'false' to disable SSL verification (not recommended)
# BW_CLI_VERIFY_SSL=true

# Optional: Request timeout in seconds (default: 15)
# BW_CLI_REQUEST_TIMEOUT=15

# Optional: Override the item endpoint template (default: /object/item/{secret_id})
# BW_CLI_ITEM_ENDPOINT=/object/item/{secret_id}

# Optional: Override the list endpoint template used by item search (default: /list/object/items)
# BW_CLI_LIST_ITEMS_ENDPOINT=/list/object/items

# Optional: Number of retries for HTTP requests (default: 3)
# BW_CLI_RETRY_TOTAL=3

# Optional: Backoff factor for retries (default: 0.3)
# BW_CLI_RETRY_BACKOFF=0.3

# Optional: Cache TTL for UI field lookups in seconds (default: 0 = disabled)
# BW_CLI_CACHE_TTL=0
```

**Descriptions:**

- `NAUTOBOT_BITWARDEN_CLI_ENABLED`: Set to `true` to enable the Bitwarden CLI provider.
- `BW_CLI_URL`: URL of the Bitwarden CLI API endpoint (required).
- `BW_CLI_USER`, `BW_CLI_PASSWORD`: Credentials for authenticating to the Bitwarden CLI API (required).
- `BW_CLI_CA_BUNDLE`: Path to a CA bundle file for TLS verification (optional).
- `BW_CLI_VERIFY_SSL`: Set to `false` to disable SSL verification (optional, default: `true`).
- `BW_CLI_REQUEST_TIMEOUT`: HTTP request timeout in seconds (optional, default: `15`).
- `BW_CLI_ITEM_ENDPOINT`: Endpoint template for fetching items (optional, default: `/object/item/{secret_id}`).
- `BW_CLI_LIST_ITEMS_ENDPOINT`: Endpoint used for item search (optional, default: `/list/object/items`).
- `BW_CLI_RETRY_TOTAL`: Number of retries for HTTP requests (optional, default: `3`).
- `BW_CLI_RETRY_BACKOFF`: Backoff factor for retries (optional, default: `0.3`).
- `BW_CLI_CACHE_TTL`: Cache TTL for UI field lookups in seconds (optional, default: `0` = disabled).

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

- The Nautobot UI queries Nautobot app API endpoints for item metadata, search results, and custom field names; the browser does not talk directly to the Bitwarden CLI server.
- Those Bitwarden helper API endpoints require an authenticated Nautobot user with the `extras.view_secret` permission, so direct URL access is blocked for users who cannot view Secrets.

### Item name display

When a valid `secret_id` UUID is present in the Parameters form, a non-blocking API call resolves
the Bitwarden item name and appends it to the `secret_id` field help text, shown in green.
This lookup is read-only and does not modify stored parameters.

### Find Item UUID workflow

Use this workflow when creating or editing a Bitwarden-backed Secret and you do not want to copy
the UUID manually from Bitwarden.

1. Open a Secret create or edit form.
2. Click **Find Item UUID** below the `secret_id` field.
3. In the search panel, enter at least 2 characters from the Bitwarden item name.
4. Press Enter or click **Search**.
5. Select the desired result by pressing Enter or double-clicking the item.
6. Confirm that the selected UUID is copied into `secret_id` and the panel closes.

After selecting an item, the form resolves metadata and updates dependent fields:

- The Bitwarden item name is shown in the `secret_id` help text.
- **Secret Field** options are filtered to values valid for the detected item type.
- **Custom field name** choices are loaded from the item custom fields.

Behavior notes:

- The search is performed through Nautobot internal plugin API endpoints; the browser does not
  call the Bitwarden CLI service directly.
- Only canonical keys are persisted in `parameters`: `secret_id`, `secret_field`, and
  `custom_field_name`.
- On the Secret detail page (read-only), the **Find Item UUID** control is hidden.

If a form is opened with a prefilled `secret_id` (for example, while editing an existing Secret),
the widget initializes immediately, resolves item metadata, and filters **Secret Field** options
to those supported by the detected Bitwarden item type. It also initializes the
**Custom field name** dropdown from the Bitwarden item's custom field names.

When **Secret Field** is not `custom`, the **Custom field name** dropdown is disabled and reset
to an empty selection (`---------`).

When `secret_field` is set to `custom`, `custom_field_name` is required and form validation blocks
save until it is provided. The Bitwarden widget renders the validation message inline under
the **Custom field name** field:
*"Custom field name is required if Secret field is set to 'Custom Field'."*
Supplying a `custom_field_name` while a non-custom secret field is selected is equally invalid.
The Bitwarden widget renders that validation message inline under **Secret Field**:
*"'Secret field' must be set to 'Custom Field' when 'Custom field name' is provided."*
Invalid parameter combinations are rejected during save and are not persisted.

## Troubleshooting

- "Bitwarden CLI responded with HTTP <code>": check `BW_CLI_URL`, the `secret_id`, and the CLI server logs.
- TLS failures: confirm `BW_CLI_CA_BUNDLE` points to a valid PEM bundle file and `verify_ssl` is `true`.
- Authentication failures: verify `username`/`password` and that the CLI service accepts those credentials.
- Secret not found or field missing: confirm the `secret_id` points to an existing item and that the requested `secret_field` or `custom_field_name` exists on that item.
- HTTP 403 from the internal Bitwarden helper URLs: confirm the logged-in user has the `extras.view_secret` permission before calling the item-info, search, or custom-fields endpoints directly.
- Invalid JSON responses: ensure the reverse proxy/service in front of Bitwarden is returning valid JSON payloads for item endpoints.
- Use container logs for debugging:

```bash
invoke logs --tail 100
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
      - "traefik.http.routers.bitwarden_cli_api.tls=true"
      - "traefik.http.routers.bitwarden_cli_api.tls.certresolver=step-ca"
      - "traefik.http.routers.bitwarden_cli_api.entrypoints=webhttps"
      - "traefik.http.routers.bitwarden_cli_api.rule=Host(`bitwarden-cli-api.example.local`)"
      - "traefik.http.routers.bitwarden_cli_api.service=bitwarden_cli_api_service"
      - "traefik.http.services.bitwarden_cli_api_service.loadbalancer.server.port=8087"
      - "traefik.http.services.bitwarden_cli_api_service.loadbalancer.server.scheme=http"
      - "traefik.http.middlewares.bitwarden_cli_auth.basicauth.users=${BW_CLI_AUTH_STR}"
      - "traefik.http.routers.bitwarden_cli_api.middlewares=bitwarden_cli_auth"
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


### Example Docker Stack Service Definition

```yaml
---

# File: .bitwarden-cli/docker-compose.bitwarden_cli-stack.yml

services:
  bitwarden-cli:
    image: ppatlabs/bitwarden-cli:latest
    networks:
      - t3_proxy  # Overlay network used for Traefik
    restart: unless-stopped
    environment:
      - BW_SESSIONFILE=/data/bw_session.json
      - NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
    volumes:
      - bw_cli_data:/data
      - "/etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro"
    entrypoint: ["/usr/local/bin/bitwarden-entrypoint.sh"]
    command: ["serve", "--hostname=0.0.0.0", "--port=8087"]
    configs:
      - source: bitwarden_cli_entrypoint
        target: /usr/local/bin/bitwarden-entrypoint.sh
        mode: 0755
    secrets:
      - bw_host
      - bw_user
      - bw_password
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
        delay: 20s
        max_attempts: 6
        window: 20s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.bitwarden_cli_api.tls=true"
      - "traefik.http.routers.bitwarden_cli_api.tls.certresolver=step-ca"
      - "traefik.http.routers.bitwarden_cli_api.entrypoints=webhttps"
      - "traefik.http.routers.bitwarden_cli_api.rule=Host(`bitwarden-cli-api.example.local`)"
      - "traefik.http.routers.bitwarden_cli_api.service=bitwarden_cli_api_service"
      - "traefik.http.services.bitwarden_cli_api_service.loadbalancer.server.port=8087"
      - "traefik.http.services.bitwarden_cli_api_service.loadbalancer.server.scheme=http"
      - "traefik.http.middlewares.bitwarden_cli_auth.basicauth.users=${BW_CLI_AUTH_STR}"
      - "traefik.http.routers.bitwarden_cli_api.middlewares=bitwarden_cli_auth"


volumes:
  bw_cli_data:
    driver: local

networks:
  t3_proxy:       # type overlay for swarm
    external: true
    name: t3_proxy

configs:
  bitwarden_cli_entrypoint:
    external: true
    name: bitwarden_cli_entrypoint

secrets:
  bw_user:
    external: true
    name: $SECRET_VAULTWARDEN_BW_USER  # Secret name to allow rolling updates
  bw_password:
    external: true
    name: $SECRET_VAULTWARDEN_BW_PASSWORD
  bw_host:
    external: true
    name: $SECRET_VAULTWARDEN_BW_HOST
```




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
