# 1Password Vault

Requires a minimum of Python3.9

## Configuration

You must provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "one_password": {
            "token": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"),
            "vaults": {
                "MyVault": {
                    "token": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"),
                },
            },
        },
    },
}
```

- `token` - (required) The 1Password Service Account Token to be used when it is not specified by a vault.
- `vaults` (required) Each 1Password Vault that is supported by this app will be listed inside this dictionary.
  - `<vault_name>` (required) The name of the vault needs to be placed as a key inside the `vaults` dictionary.
    - `token` (optional) The 1Password Service Account Token to be used by the above vault.

!!! note
    The Service Account token needs to have access to the Vault that it is configured for. Per 1Password policy "You can't grant a service account access to your built-in Personal, Private, or Employee vault, or your default Shared vault."
