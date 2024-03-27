# Installing the App in Nautobot

Here you will find detailed instructions on how to **install** and **configure** the App within your Nautobot environment.

## Prerequisites

- This app is compatible with Nautobot 1.2.1 and higher.
- Support for Thycotic Secret Server requires Python 3.7 or later.
- Databases supported: PostgreSQL, MySQL

!!! note
    Please check the [dedicated page](compatibility_matrix.md) for a full compatibility matrix and the deprecation policy.

Before you proceed, you must have **at least one** of the dependent libaries installed as detailed below.

Please do not enable this app until you are able to install the dependencies, as it will block Nautobot from starting.

### Dependencies

For this app to operate you must install at least one of the dependent libraries required by the secrets providers.

**You must install the dependencies for at least one of the supported secrets providers or a `RuntimeError` will be raised.**

#### AWS

AWS Secrets Manager and Systems Manager Parameter Store are supported. Both providers require the `boto3` library. This can be easily installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[aws]
```

#### HashiCorp Vault

The HashiCorp Vault provider requires the `hvac` library. This can easily be installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[hashicorp]
```

#### Delinea/Thycotic Secret Server

The Delinea/Thycotic Secret Server provider requires the `python-tss-sdk` library. This can easily be installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[thycotic]
```

### Access Requirements

There are no special access requirements to install the app.

## Install Guide

!!! note
    Apps can be installed from the [Python Package Index](https://pypi.org/) or locally. See the [Nautobot documentation](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/app-install/) for more details. The pip package name for this app is [`nautobot-secrets-providers`](https://pypi.org/project/nautobot-secrets-providers/).

The app is available as a Python package via PyPI and can be installed with `pip`:

```shell
pip install nautobot-secrets-providers
```

To ensure Nautobot's Secrets Providers App is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the `nautobot-secrets-providers` package:

```shell
echo nautobot-secrets-providers >> local_requirements.txt
```

Once installed, the app needs to be enabled in your Nautobot configuration. The following block of code below shows the additional configuration required to be added to your `nautobot_config.py` file:

- Append `"nautobot_secrets_providers"` to the `PLUGINS` list.
- Append the `"nautobot_secrets_providers"` dictionary to the `PLUGINS_CONFIG` dictionary and override any defaults.

```python
# In your nautobot_config.py
PLUGINS = ["nautobot_secrets_providers"]

# PLUGINS_CONFIG = {
#   "nautobot_secrets_providers": {
#     ADD YOUR SETTINGS HERE
#   }
# }
```

Once the Nautobot configuration is updated, run the Post Upgrade command (`nautobot-server post_upgrade`) to run migrations and clear any cache:

```shell
nautobot-server post_upgrade
```

Then restart (if necessary) the Nautobot services which may include:

- Nautobot
- Nautobot Workers
- Nautobot Scheduler

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

## App Configuration

### AWS

#### Authentication

No configuration is needed within Nautobot for this provider to operate. Instead you must provide [AWS credentials in one of the methods supported by the `boto3` library](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#configuring-credentials).

Boto3 credentials can be configured in multiple ways (eight as of this writing) that are mirrored here:

1. Passing credentials as parameters in the `boto.client()` method
2. Passing credentials as parameters when creating a Session object
3. Environment variables
4. Shared credential file (`~/.aws/credentials`)
5. AWS config file (`~/.aws/config`)
6. Assume Role provider
7. Boto2 config file (`/etc/boto.cfg` and `~/.boto`)
8. Instance metadata service on an Amazon EC2 instance that has an IAM role configured.

**The AWS providers only support methods 3-8. Methods 1 and 2 ARE NOT SUPPORTED at this time.**

We highly recommend you defer to using environment variables for your deployment as specified in the credentials documentation linked above. The values specified in the linked documentation should be [set within your `~.bashrc`](https://nautobot.readthedocs.io/en/latest/installation/nautobot/#update-the-nautobot-bashrc) (or similar profile) on your system.

#### Configuration

This is an example based on our recommended deployment pattern in the section above (item 3) that is using [environment variables](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#environment-variables). You will need to set these in the environment prior to starting Nautobot:

```no-highlight
export AWS_ACCESS_KEY_ID=foo      # The access key for your AWS account.
export AWS_SECRET_ACCESS_KEY=bar  # The secret key for your AWS account.
```

Please refer to the [Nautobot documentation on updating your `.bashrc`](https://nautobot.readthedocs.io/en/latest/installation/nautobot/#update-the-nautobot-bashrc) for how to do this for production Nautobot deployments.

### HashiCorp Vault

#### Configuration

You must provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "hashicorp_vault": {
            "url": "http://localhost:8200",
            "auth_method": "token",
            "token": os.getenv("NAUTOBOT_HASHICORP_VAULT_TOKEN"),
        }
    },
}
```

- `url` - (required) The URL to the HashiCorp Vault instance (e.g. `http://localhost:8200`).
- `auth_method` - (optional / defaults to "token") The method used to authenticate against the HashiCorp Vault instance. Either `"approle"`, `"aws"`, `"kubernetes"` or `"token"`.  For information on using AWS authentication with vault see the [authentication](#authentication) section above.
- `ca_cert` - (optional) Path to a PEM formatted CA certificate to use when verifying the Vault connection.  Can alternatively be set to `False` to ignore SSL verification (not recommended) or `True` to use the system certificates.
- `default_mount_point` - (optional / defaults to "secret") The default mount point of the K/V Version 2 secrets engine within Hashicorp Vault.
- `kv_version` - (optional / defaults to "v2") The version of the KV engine to use, can be `v1` or `v2`
- `k8s_token_path` - (optional) Path to the kubernetes service account token file.  Defaults to "/var/run/secrets/kubernetes.io/serviceaccount/token".
- `token` - (optional) Required when `"auth_method": "token"` or `auth_method` is not supplied. The token for authenticating the client with the HashiCorp Vault instance. As with other sensitive service credentials, we recommend that you provide the token value as an environment variable and retrieve it with `{"token": os.getenv("NAUTOBOT_HASHICORP_VAULT_TOKEN")}` rather than hard-coding it in your `nautobot_config.py`.
- `role_name` - (optional) Required when `"auth_method": "kubernetes"`, optional when `"auth_method": "aws"`.  The Vault Kubernetes role or Vault AWS role to assume which the pod's service account has access to.
- `role_id` - (optional) Required when `"auth_method": "approle"`. As with other sensitive service credentials, we recommend that you provide the role_id value as an environment variable and retrieve it with `{"role_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_ROLE_ID")}` rather than hard-coding it in your `nautobot_config.py`.
- `secret_id` - (optional) Required when `"auth_method": "approle"`.As with other sensitive service credentials, we recommend that you provide the secret_id value as an environment variable and retrieve it with `{"secret_id": os.getenv("NAUTOBOT_HASHICORP_VAULT_SECRET_ID")}` rather than hard-coding it in your `nautobot_config.py`.
- `login_kwargs` - (optional) Additional optional parameters to pass to the login method for [`approle`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.AppRole.login), [`aws`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.Aws.iam_login) and [`kubernetes`](https://hvac.readthedocs.io/en/stable/source/hvac_api_auth_methods.html#hvac.api.auth_methods.Kubernetes.login) authentication methods.
- `namespace` - (optional) Namespace to use for the [`X-Vault-Namespace` header](https://github.com/hvac/hvac/blob/main/hvac/adapters.py#L287) on all hvac client requests. Required when the [`Namespaces`](https://developer.hashicorp.com/vault/docs/enterprise/namespaces#usage) feature is enabled in Vault Enterprise.
 
### Delinea/Thycotic Secret Server (TSS)

The Delinea/Thycotic Secret Server app includes two providers:

#### Thycotic Secret Server by ID

This provider uses the `Secret ID` to specifiy the secret that is selected. The `Secret ID` is displayed in the browser's URL field if you `Edit` the data in Thycotic Secret Server.

!!! example
    The url is: _https://pw.example.local/SecretServer/app/#/secret/**1234**/general_
    In this example the value for `Secret ID` is **1234**.

#### Thycotic Secret Server by Path

This provider allows to select the secret by folder-path and secret-name. The path delimiter is a '\\'. The `Secret path` is displayed as page header when `Edit` a secret.

!!! example
    The header is: **NET-Automation > Nautobot > My-Secret**
    In this example the value for `Secret path` is **`\NET-Automation\Nautobot\My-Secret`**.

#### Configuration

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "thycotic": {  # https://github.com/thycotic/python-tss-sdk
            "base_url": os.getenv("SECRET_SERVER_BASE_URL", None),
            "ca_bundle_path": os.getenv("REQUESTS_CA_BUNDLE", None),
            "cloud_based": is_truthy(os.getenv("SECRET_SERVER_IS_CLOUD_BASED", "False")),
            "domain": os.getenv("SECRET_SERVER_DOMAIN", None),
            "password": os.getenv("SECRET_SERVER_PASSWORD", None),
            "tenant": os.getenv("SECRET_SERVER_TENANT", None),
            "token": os.getenv("SECRET_SERVER_TOKEN", None),
            "username": os.getenv("SECRET_SERVER_USERNAME", None),
        },
    }
}
```

- `base_url` - (required) The Secret Server base_url. _e.g.'https://pw.example.local/SecretServer'_
- `ca_bundle_path` - (optional) When using self-signed certificates this variable must be set to a file containing the trusted certificates (in .pem format). _e.g. '/etc/ssl/certs/ca-bundle.trust.crt'_.
- `cloud_based` - (optional) Set to "True" if Secret Server Cloud should be used. (Default: "False").
- `domain` - (optional) Required for 'Domain Authorization'
- `password` - (optional) Required for 'Secret Server Cloud', 'Password Authorization', 'Domain Authorization'.
- `tenant` - (optional) Required for 'Domain Authorization'.
- `token` - (optional) Required for 'Access Token Authorization'.
- `username` - (optional) Required for 'Secret Server Cloud', 'Password Authorization', 'Domain Authorization'.
