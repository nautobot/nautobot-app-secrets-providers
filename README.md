# Nautobot Secrets Providers

<p align="center">
  <img src="https://raw.githubusercontent.com/nautobot/nautobot-plugin-secrets-providers/develop/docs/images/icon-nautobot-secrets-providers.png" class="logo" height="200px">
  <br>
  <a href="https://github.com/nautobot/nautobot-plugin-secrets-providers/actions"><img src="https://github.com/nautobot/nautobot-plugin-secrets-providers/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://docs.nautobot.com/projects/secrets-providers/en/latest"><img src="https://readthedocs.org/projects/nautobot-plugin-secrets-providers/badge/"></a>
  <a href="https://pypi.org/project/nautobot-secrets-providers/"><img src="https://img.shields.io/pypi/v/nautobot-secrets-providers"></a>
  <a href="https://pypi.org/project/nautobot-secrets-providers/"><img src="https://img.shields.io/pypi/dm/nautobot-secrets-providers"></a>
  <br>
  An <a href="https://www.networktocode.com/nautobot/apps/">App</a> for <a href="https://nautobot.com/">Nautobot</a>.
</p>

## Overview

Nautobot Secrets Providers is an App (or plugin) for [Nautobot](https://github.com/nautobot/nautobot) 1.2.0 or higher that bundles Secrets Providers for integrating with popular secrets backends. Nautobot 1.2.0 added support for integrating with retrieving secrets from various secrets providers.

This App publishes secrets providers that are not included within the Nautobot core software package so that it will be easier to maintain and extend support for various secrets providers without waiting on Nautobot software releases.

### Supported Secrets Backends

This App supports the following popular secrets backends:

| Secrets Backend                                              | Supported Secret Types                                       | Supported Authentication Methods                             |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/) | [Other: Key/value pairs](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_create-basic-secret.html) | [AWS credentials](https://docs.aws.amazon.com/general/latest/gr/aws-sec-cred-types.html) (see Usage section below) |
| [HashiCorp Vault](https://www.vaultproject.io)               | [K/V Version 2](https://www.vaultproject.io/docs/secrets/kv/kv-v2) | [Token](https://www.vaultproject.io/docs/auth/token)<br/>[AppRole](https://www.vaultproject.io/docs/auth/approle)<br/>[AWS](https://www.vaultproject.io/docs/auth/aws)<br/>[Kubernetes](https://www.vaultproject.io/docs/auth/kubernetes)         |
| [Delinea/Thycotic Secret Server](https://delinea.com/products/secret-server)               | [Secret Server Cloud](https://github.com/DelineaXPM/python-tss-sdk#secret-server-cloud)<br/>[Secret Server (on-prem)](https://github.com/DelineaXPM/python-tss-sdk#initializing-secretserver)| [Access Token Authorization](https://github.com/DelineaXPM/python-tss-sdk#access-token-authorization)<br/>[Domain Authorization](https://github.com/DelineaXPM/python-tss-sdk#domain-authorization)<br/>[Password Authorization](https://github.com/DelineaXPM/python-tss-sdk#password-authorization)<br/>         |

### Screenshots

More screenshots can be found in the [Using the App](https://docs.nautobot.com/projects/secrets-providers/en/latest/user/app_use_cases/) page in the documentation. Here's a quick overview of some of the plugin's added functionality:

![Screenshot of plugin home page](https://raw.githubusercontent.com/nautobot/nautobot-plugin-secrets-providers/develop/docs/images/screenshot02.png "Plugin Home page")

---

![Screenshot of secret using AWS Secrets Manager](https://raw.githubusercontent.com/nautobot/nautobot-plugin-secrets-providers/develop/docs/images/screenshot03.png "Secret using AWS Secrets Manager")


## Documentation

Full documentation for this App can be found over on the [Nautobot Docs](https://docs.nautobot.com) website:

- [User Guide](https://docs.nautobot.com/projects/secrets-providers/en/latest/user/app_overview/) - Overview, Using the App, Getting Started.
- [Administrator Guide](https://docs.nautobot.com/projects/secrets-providers/en/latest/admin/install/) - How to Install, Configure, Upgrade, or Uninstall the App.
- [Developer Guide](https://docs.nautobot.com/projects/secrets-providers/en/latest/dev/contributing/) - Extending the App, Code Reference, Contribution Guide.
- [Release Notes / Changelog](https://docs.nautobot.com/projects/secrets-providers/en/latest/admin/release_notes/).
- [Frequently Asked Questions](https://docs.nautobot.com/projects/secrets-providers/en/latest/user/faq/).

### Contributing to the Documentation

You can find all the Markdown source for the App documentation under the [`docs`](https://github.com/nautobot/nautobot-plugin-secrets-providers/tree/develop/docs) folder in this repository. For simple edits, a Markdown capable editor is sufficient: clone the repository and edit away.

If you need to view the fully-generated documentation site, you can build it with [MkDocs](https://www.mkdocs.org/). A container hosting the documentation can be started using the `invoke` commands (details in the [Development Environment Guide](https://docs.nautobot.com/projects/secrets-providers/en/latest/dev/dev_environment/#docker-development-environment)) on [http://localhost:8001](http://localhost:8001). Using this container, as your changes to the documentation are saved, they will be automatically rebuilt and any pages currently being viewed will be reloaded in your browser.

Any PRs with fixes or improvements are very welcome!

## Questions

For any questions or comments, please check the [FAQ](https://docs.nautobot.com/projects/secrets-providers/en/latest/user/faq/) first. Feel free to also swing by the [Network to Code Slack](https://networktocode.slack.com/) (channel `#nautobot`), sign up [here](http://slack.networktocode.com/) if you don't have an account.
