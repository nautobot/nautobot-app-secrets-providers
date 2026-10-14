# HashiCorp Vault

## Configuration

You must provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "hashicorp_vault": {
            "url": os.environ.get("HASHICORP_VAULT_URL"),
            "token": os.environ.get("HASHICORP_VAULT_TOKEN"),
        }
    },
}
```

- `url` - (required) The URL to the HashiCorp Vault instance (e.g. `http://localhost:8200`).
- `auth_method` - (optional / defaults to "token") The method used to authenticate against the HashiCorp Vault instance. Either `"approle"`, `"aws"`, `"kubernetes"` or `"token"`.
- `ca_cert` - (optional) Path to a PEM formatted CA certificate to use when verifying the Vault connection.  Can alternatively be set to `False` to ignore SSL verification (not recommended) or `True` to use the system certificates.
- `default_mount_point` - (optional / defaults to "secret") The default mount point of the K/V Version 2 secrets engine within Hashicorp Vault.
- `kv_version` - (optional / defaults to "v2") The version of the KV engine to use, can be `v1` or `v2`
- `k8s_token_path` - (optional) Path to the kubernetes service account token file.  Defaults to "/var/run/secrets/kubernetes.io/serviceaccount/token".
- `token` - (optional) Required when `"auth_method": "token"` or `auth_method` is not supplied. The token for authenticating the client with the HashiCorp Vault instance. As with other sensitive service credentials, we recommend that you provide the `token` value as an environment variable and retrieve it with `{"token": os.getenv("NAUTOBOT_HASHICORP_VAULT_TOKEN")}` rather than hard-coding it in your `nautobot_config.py`.
- `role_name` - (optional) Required when `"auth_method": "kubernetes"`, optional when `"auth_method": "aws"`.  The Vault Kubernetes role or Vault AWS role to assume which the pod's service account has access to.
- `role_id` - (optional) Required when `"auth_method": "approle"`. As with other sensitive service credentials, we recommend that you provide the `role_id` value as an environment variable and retrieve it with `{"role_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_ROLE_ID")}` rather than hard-coding it in your `nautobot_config.py`.
- `secret_id` - (optional) Required when `"auth_method": "approle"`.As with other sensitive service credentials, we recommend that you provide the `secret_id value` as an environment variable and retrieve it with `{"secret_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_SECRET_ID")}` rather than hard-coding it in your `nautobot_config.py`.
- `login_kwargs` - (optional) Additional optional parameters to pass to the login method for [`approle`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.AppRole.login), [`aws`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.Aws.iam_login) and [`kubernetes`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.Kubernetes.login) authentication methods.
- `namespace` - (optional) Namespace to use for the [`X-Vault-Namespace` header](https://github.com/hvac/hvac/blob/main/hvac/adapters.py#L287) on all hvac client requests. Required when the [`Namespaces`](https://developer.hashicorp.com/vault/docs/enterprise/namespaces#usage) feature is enabled in Vault Enterprise.

### Multiple Hashicorp Vaults

+++ 3.1.0

Hashicorp Provider now supports using multiple vaults (configurations). You will be able to choose the vault when creating a secret, For example, you could have one vault using `approle` authentication, and a second vault using `token` authentication in combination with a different default mount point:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "hashicorp_vault": {
            "vaults": {
                "hashicorp_approle": {
                    "url": os.environ.get("HASHICORP_VAULT_URL"),
                    "auth_method": "approle",
                    "role_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_ROLE_ID"),
                    "secret_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_SECRET_ID"),
                },
                "hashicorp_v1_custom_mount": {
                    "url": os.environ.get("HASHICORP_VAULT_URL"),
                    "token": os.environ.get("HASHICORP_VAULT_TOKEN"),
                    "kv_version": "v1",
                    "default_mount_point": "secret_kv",
                },
            }
        }
    },
}
```

![Select Secret Configuration](../../images/light/hashicorp_multiple_vaults.png#only-light)
![Select Secret Configuration](../../images/dark/hashicorp_multiple_vaults.png#only-dark)

!!! note
    If using this option, you should not have any keys except `vaults` under `hashicorp_vault`.

## Active Directory and LDAP Credentials

+++ 4.1.0

The `HashiCorp Vault AD/LDAP` provider retrieves the credentials of directory accounts managed by the [LDAP secrets engine](https://developer.hashicorp.com/vault/docs/secrets/ldap) or the Active Directory secrets engine.

A secret using this provider takes the following parameters:

- `role_name` - (required) The name of the role in Vault.
- `key` - (required) The credential value to retrieve. Either `username`, `password` or `last_password`.
- `vault` - (required) The HashiCorp Vault to retrieve the secret from.
- `mount_point` - (optional / defaults to the engine name) The path where the secrets engine was mounted on.
- `engine` - (required) The secrets engine that manages the credentials. Either `ad` for the Active Directory secrets engine or `ldap` for the LDAP secrets engine.

The provider reads the credentials from the following Vault paths, which the token or role used by Nautobot must be allowed to `read`:

| Engine | Path                                    | Value returned for `password` |
| ------ | --------------------------------------- | ----------------------------- |
| `ad`   | `<mount_point>/creds/<role_name>`       | `current_password`            |
| `ldap` | `<mount_point>/static-cred/<role_name>` | `password`                    |

For example, the following Vault policy allows Nautobot to retrieve the credentials of the `nautobot` role of an Active Directory secrets engine mounted on `ad`:

```hcl
path "ad/creds/nautobot" {
  capabilities = ["read"]
}
```

To use the credentials of an account, for example as device credentials, create one secret with `key` set to `username` and one with `key` set to `password` for the same role, and add both of them to a Secrets Group.

!!! note
    Nautobot retrieves each secret of a Secrets Group separately, so only the static roles of the LDAP secrets engine are supported. Dynamic roles create a new account on every read, and service account check-out requires the account to be checked back in.

!!! warning
    HashiCorp has [deprecated](https://developer.hashicorp.com/vault/docs/updates/deprecation) the Active Directory secrets engine and no longer supports it. The LDAP secrets engine configured with `schema=ad` is its replacement for Active Directory accounts.

