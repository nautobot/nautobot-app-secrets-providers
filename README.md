# Nautobot's Secrets Providers App

<p align="center">
  <a href="https://github.com/nautobot/nautobot-app-secrets-providers/actions"><img src="https://github.com/nautobot/nautobot-app-secrets-providers/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://docs.nautobot.com/projects/secrets-providers/en/latest/"><img src="https://readthedocs.org/projects/nautobot-plugin-secrets-providers/badge/"></a>
  <a href="https://pypi.org/project/nautobot-secrets-providers/"><img src="https://img.shields.io/pypi/v/nautobot-secrets-providers"></a>
  <a href="https://pypi.org/project/nautobot-secrets-providers/"><img src="https://img.shields.io/pypi/dm/nautobot-secrets-providers"></a>
  <br>
  An <a href="https://www.networktocode.com/nautobot/apps/">App</a> for <a href="https://nautobot.com/">Nautobot</a>.
</p>

Nautobot Secrets Providers is an app for [Nautobot](https://github.com/nautobot/nautobot) 1.2.1 or higher that bundles Secrets Providers for integrating with popular secrets backends. Nautobot 1.2.0 added support for integrating with retrieving secrets from various secrets providers.

This app publishes secrets providers that are not included in the Nautobot core software package so that it will be easier to maintain and extend support for various secrets providers without waiting on Nautobot software releases.

## Supported Secrets Backends

This app supports the following popular secrets backends:

| Secrets Backend                                              | Supported Secret Types                                       | Supported Authentication Methods                             |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/) | [Other: Key/value pairs](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_create-basic-secret.html) | [AWS credentials](https://docs.aws.amazon.com/general/latest/gr/aws-sec-cred-types.html) (see Usage section below) |
| [AWS Systems Manager Parameter Store](https://aws.amazon.com/secrets-manager/) | [Other: Key/value pairs](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) | [AWS credentials](https://docs.aws.amazon.com/general/latest/gr/aws-sec-cred-types.html) (see Usage section below) |
| [HashiCorp Vault](https://www.vaultproject.io)               | [K/V Version 2](https://www.vaultproject.io/docs/secrets/kv/kv-v2)<br/>[K/V Version 1](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v1) | [Token](https://www.vaultproject.io/docs/auth/token)<br/>[AppRole](https://www.vaultproject.io/docs/auth/approle)<br/>[AWS](https://www.vaultproject.io/docs/auth/aws)<br/>[Kubernetes](https://www.vaultproject.io/docs/auth/kubernetes)         |
| [Delinea/Thycotic Secret Server](https://delinea.com/products/secret-server)               | [Secret Server Cloud](https://github.com/DelineaXPM/python-tss-sdk#secret-server-cloud)<br/>[Secret Server (on-prem)](https://github.com/DelineaXPM/python-tss-sdk#initializing-secretserver)| [Access Token Authorization](https://github.com/DelineaXPM/python-tss-sdk#access-token-authorization)<br/>[Domain Authorization](https://github.com/DelineaXPM/python-tss-sdk#domain-authorization)<br/>[Password Authorization](https://github.com/DelineaXPM/python-tss-sdk#password-authorization)<br/>         |
| [Keeper Secret Manager](https://docs.keeper.io/secrets-manager/secrets-manager/quick-start-guide)               | [Other: Key/value pairs](https://docs.keeper.io/secrets-manager/secrets-manager/developer-sdk-library/python-sdk#retrieve-secrets)| [One Time Access Token](https://docs.keeper.io/secrets-manager/secrets-manager/about/one-time-token)        |

## Screenshots

![Screenshot of installed apps](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot01.png "App landing page")

---

![Screenshot of app home page](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot02.png "App Home page")

---

![Screenshot of secret using AWS Secrets Manager](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot03.png "Secret using AWS Secrets Manager")

---

![Screenshot of secret using HashiCorp Vault](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot04.png "Secret using HashiCorp Vault")

---

![Screenshot of secret using Delinea/Thycotic Secret Server by ID](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot05.png "Secret using Thycotic Secret Server by ID")

---

![Screenshot of secret using Delinea/Thycotic Secret Server by Path](https://raw.githubusercontent.com/nautobot/nautobot-app-secrets-providers/develop/docs/images/screenshot06.png "Secret using Thycotic Secret Server by Path")

## Installation

See the [installation documentation](https://docs.nautobot.com/projects/secrets-providers/en/latest/admin/install/) for detailed instructions on installing the Nautobot Secrets Providers app.

### Keeper Secret Manager

The Keeper Secret Manager plugin includes two providers:

- **`Keeper by UID`**

    This provider uses the `UID` to specify the secret that is retrieved. The `UID` is displayed in the `Record Info`.

    - Example:

        The url is: _https://keepersecurity.com/vault/#detail/OuiSc5IkgxEBnbnSyVJ5UA_

        In this example the value for `UID` is **OuiSc5IkgxEBnbnSyVJ5UA**.

- **`Keeper by Name/Title`**

    This provider allows to select the secret by name/title.

    - Example:

        The url is _https://keepersecurity.com/vault/#search/XXX-SW-XXX-F0_

        In this example the value for `Title` is **XXX-SW-XXX-F0**.

#### Configuration

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "keeper": {  # https://github.com/Keeper-Security/secrets-manager/tree/master/sdk/python
            "token": os.getenv("KEEPER_TOKEN", None),
        },
    }
}
```
- `name` - (optional with uid) The secret name/title. _e.g.'XXX-SW-XXX-F0'_
- `uid` - (optional with name) The secret uid. _e.g.'OuiSc5IkgxEBnbnSyVJ5UA'_
- `token` - (optional with config) The Keeper Secret Manager token. _e.g.'1234'_
- `config` - (optional with token) The Keeper Secret Manager config. _e.g.'JSON'_
- `type` - (required) The info type to retrieve from the secret (ENUM CHOICE `password` / `username`). _e.g.'password'_

Either one of `uid` or `name` must be specified. If `token` is not specified, it will use JSON config specified either in the form or in config file instead. If none of them are specified, it will fail to connect to Keeper Secret Manager.

## Contributing

Pull requests are welcomed and automatically built and tested against multiple version of Python and multiple version of Nautobot through GitHub Actions.

The project is packaged with a light development environment based on `docker-compose` to help with the local development of the project and to run the tests within GitHub Actions.

The project is following Network to Code software development guidelines and is leveraging:

- Black, Pylint, Bandit and pydocstyle for Python linting and formatting.
- Django unit test to ensure the app is working properly.

### Development Environment

For information on setting up a local development environment, see the [documentation](https://docs.nautobot.com/projects/secrets-providers/en/latest/dev/dev_environment/).

## Questions

For any questions or comments, please check the [FAQ](FAQ.md) first and feel free to swing by the [Network to Code Slack workspace](https://networktocode.slack.com/) (channel `#networktocode`).
