# Installing the App in Nautobot

Here you will find detailed instructions on how to **install** and **configure** the App within your Nautobot environment.

## Prerequisites

- This app is compatible with Nautobot 2.0.0 and higher.
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

#### Azure Key Vault

The Azure Key Vault provider requires the `azure-identity` and `azure-keyvault-secrets` libraries. This can be easily installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[azure]
```

#### Delinea/Thycotic Secret Server

The Delinea/Thycotic Secret Server provider requires the `python-tss-sdk` library. This can easily be installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[thycotic]
```

#### HashiCorp Vault

The HashiCorp Vault provider requires the `hvac` library. This can easily be installed along with the app using the following command:

```no-highlight
pip install nautobot-secrets-providers[hashicorp]
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

View configuration details for specific secrets providers on their dedicated pages [here](./providers/index.md).
