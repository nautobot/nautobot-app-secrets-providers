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
            "base_url": os.getenv("PMP_BASE_URL"),
            "token": os.getenv("PMP_API_TOKEN"),
            "verify_ssl": True,
        },
    },
}
```

- `base_url` - (required) Base URL to access Password Manager Pro, e.g. `https://pmp.example.com:8383`
- `token` (required) API token for Password Manager Pro. It is recommended to load it from an environment variable as shown above rather than hard-coding it.
- `verify_ssl` (optional) SSL Verification, default is True 