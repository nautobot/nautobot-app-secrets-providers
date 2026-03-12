# Password Manager Pro

Requires a minimum of Python3.9

## Prerequisites
Password Manager Pro should be reachable by Nautobot
You must create API token in Password Manager Pro

!!! note
    Available Resources and Accounts would be limited by API token scope"

## Configuration

You must provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "password_manager_pro": {
            "base_url": "https://pmp.example.com:8383",
            "token": "PMP_API_TOKEN",
            "verify_ssl": True,
        },
    },
}
```

- `base_url` - (required) Base URL to access Password Manager Pro
- `token` (required) Env Variable name for API token from Password Manager Pro
- `verify_ssl` (optional) SSL Verification, default is True 