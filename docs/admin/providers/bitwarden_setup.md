# Bitwarden Secrets Manager

Requires a minimum of Python3.9

## Prerequisites

You must create a Machine Account for the Bitwarden Project(s) you are trying to access. You can follow the [Machine Accounts](https://bitwarden.com/help/machine-accounts/) to assist with creating the Machine Account.

!!! note
    The Machine Account token needs to have access to the Project that it is configured for.

## Configuration

You must provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "bitwarden": {
            "api_url": os.getenv("BITWARDEN_API_URL"),
            "identity_url": os.getenv("BITWARDEN_IDENTITY_URL"),
            "org_id": os.getenv("BITWARDEN_ORG_ID"),
            "token": os.getenv("BITWARDEN_ACCESS_TOKEN"),
        },
    },
}
```

- `api_url` - (required) The Bitwarden API URL.
- `identity_url` - (required) The Identity URL to use when authenticating to the Bitwarden API.
- `org_id` - (required) The Organization ID found in Bitwarden.
- `token` - (required) The Bitwarden Machine Account Token to be used.

### API Endpoints

Additional details can be found in the [Bitwarden Public API](https://bitwarden.com/help/public-api/) guide.

#### Base URL

For cloud-hosted, `https://api.bitwarden.com` or `https://api.bitwarden.eu`.

For self-hosted, `https://your.domain.com/api`.

#### Identity endpoints

For cloud-hosted, `https://identity.bitwarden.com` or `https://identity.bitwarden.eu`.

> **Note:** The documentation differs on the above endpoint and shows `https://identity.bitwarden.com/connect/token`, however the above works with Nautobot. If you get authentication errors, you may need to try a different Identity endpoint.

For self-hosted, `https://your.domain.com/identity/connect/token`.
