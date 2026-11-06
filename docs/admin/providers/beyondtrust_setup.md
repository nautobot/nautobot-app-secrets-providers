# BeyondTrust Password Safe

Two providers are supported:

- **BeyondTrust Managed Account** — a credentials release request is created for the managed account and the
  credential is returned for that request. Checking the request back in is what triggers password rotation,
  so rotation is a separate step from reading a secret.
- **BeyondTrust Secrets Safe** — a Text or Credential secret is read by folder path and title, or by secret
  ID. Plain lookup and read: no request lifecycle, nothing checked in, nothing rotated. File secrets are not
  supported.

## Prerequisites

Password Safe (BeyondInsight / Password Safe, or Password Safe Cloud) must be reachable from Nautobot.

Authentication supports two paths, and the API registration must be enabled for either:

- **OAuth client** — create an API client in Password Safe and use its `client_id` / `client_secret`.
- **API key** — create an API key and the user it runs as (`run_as`). Keys are only usable with the
  `PS-Auth` header, so a run-as user is required.

The API user needs permission to view the managed system and account, and to create release requests.

## Configuration

Provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "beyondtrust": {
            "base_url": os.getenv("BT_BASE_URL"),  # e.g. https://bt.example.com/BeyondTrust/api/public/v3
            "client_id": os.getenv("BT_CLIENT_ID"),
            "client_secret": os.getenv("BT_CLIENT_SECRET"),
            "verify_ssl": True,
            "timeout": 30,
        },
    },
}
```

Or, for API-key auth:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "beyondtrust": {
            "base_url": os.getenv("BT_BASE_URL"),
            "api_key": os.getenv("BT_API_KEY"),
            "run_as": os.getenv("BT_RUN_AS"),
        },
    },
}
```

## Secret parameters

When creating a Secret with the **BeyondTrust Managed Account** provider:

| Parameter | Required | Notes |
|---|---|---|
| `system_name` | yes | Managed system (asset) name. Supports Jinja2, e.g. `{{ obj.name }}` |
| `account_name` | yes | Managed account name on that system |
| `duration_minutes` | no | Release window in minutes, default `5` |
| `rotate_on_checkin` | no | `true` / `false`, default `true` |
| `reason` | no | Reason recorded on the request |

When creating a Secret with the **BeyondTrust Secrets Safe** provider:

| Parameter | Required | Notes |
|---|---|---|
| `folder_path` | yes* | Secrets Safe folder path, e.g. `IT/Platform`. Supports Jinja2 |
| `title` | yes* | Secret title inside the folder |
| `secret_id` | no | Direct lookup instead of a path and title search |

\* `folder_path` and `title` are required unless `secret_id` is provided.

## Rotation

Reading a secret only releases it. To rotate, check the request back in after the credential has been
used:

```python
from nautobot_secrets_providers.providers import BeyondTrustManagedAccountSecretsProvider as BT

request_id = BT.release(secret)          # returns the request ID
password = BT.get_value_for_secret(secret)
BT.check_in(secret, request_id, reason="job complete")   # rotation happens here
```
