# Nautobot Secrets Providers App

This document provides an overview of the App including critical information and important considerations when applying it to your Nautobot environment.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

Nautobot Secrets Providers is an app for [Nautobot](https://github.com/nautobot/nautobot) 1.2.1 or higher that bundles Secrets Providers for integrating with popular secrets backends. Nautobot 1.2.0 added support for integrating with retrieving secrets from various secrets providers.

This app publishes secrets providers that are not included in the Nautobot core software package so that it will be easier to maintain and extend support for various secrets providers without waiting on Nautobot software releases.

### Supported Secrets Backends

This app supports the following popular secrets backends:

| Secrets Backend                                              | Supported Secret Types                                       | Supported Authentication Methods                             |
| ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/) | [Other: Key/value pairs](https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_create-basic-secret.html) | [AWS credentials](https://docs.aws.amazon.com/general/latest/gr/aws-sec-cred-types.html) (see Usage section below) |
| [AWS Systems Manager Parameter Store](https://aws.amazon.com/secrets-manager/) | [Other: Key/value pairs](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html) | [AWS credentials](https://docs.aws.amazon.com/general/latest/gr/aws-sec-cred-types.html) (see Usage section below) |
| [HashiCorp Vault](https://www.vaultproject.io)               | [K/V Version 2](https://www.vaultproject.io/docs/secrets/kv/kv-v2)<br/>[K/V Version 1](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v1) | [Token](https://www.vaultproject.io/docs/auth/token)<br/>[AppRole](https://www.vaultproject.io/docs/auth/approle)<br/>[AWS](https://www.vaultproject.io/docs/auth/aws)<br/>[Kubernetes](https://www.vaultproject.io/docs/auth/kubernetes)         |
| [Delinea/Thycotic Secret Server](https://delinea.com/products/secret-server)               | [Secret Server Cloud](https://github.com/DelineaXPM/python-tss-sdk#secret-server-cloud)<br/>[Secret Server (on-prem)](https://github.com/DelineaXPM/python-tss-sdk#initializing-secretserver)| [Access Token Authorization](https://github.com/DelineaXPM/python-tss-sdk#access-token-authorization)<br/>[Domain Authorization](https://github.com/DelineaXPM/python-tss-sdk#domain-authorization)<br/>[Password Authorization](https://github.com/DelineaXPM/python-tss-sdk#password-authorization)<br/>         |

## Audience (User Personas) - Who should use this App?

- Anyone who needs to retrieve secrets from Hashicorp Vault, AWS, or Delinea/Thycotic and use them in Nautobot

## Authors and Maintainers

- Nautobot Core Team

## Nautobot Features Used

- Secrets Providers
