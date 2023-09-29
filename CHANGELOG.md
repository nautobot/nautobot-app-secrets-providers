# Nautobot Secrets Providers Changelog

## v2.0.1 (2023-09-29)

### Added

- [#113](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/113) Added the missing fix for [issue](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/91) that was not included for v2.0.0

## v2.0.0 (2023-09-23)

### Changed

- [#105](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/106) Updated `nautobot` to `2.0`.

### Removed

- [#105](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/106) Removed `slug` field from `Secret` model. Can be replaced with `name` field or [natural keys](https://docs.nautobot.com/projects/core/en/next/development/apps/migration/model-updates/global/#replace-the-usage-of-slugs-with-composite-keys).

## v1.4.1 (2023-06-07)

### Fixed

- [#91](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/91) Fixed Hashicorp Vault Authentication with AWS Credentials when region is not set.

## v1.4.0 (2023-04-19)

### Added

- [#48](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/48) Add token as secret type choice for Delinea/Thycotic
- [#51](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/51) Add support for AWS Systems Manager Parameter Store
- [#53](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/53) Add support for Hashicorp Key/Value v1 response
- [#66](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/66) Add support for Vault Enterprise Namespace parameter

### Changed

- [#45](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/45) Change references of Thycotic to Delinea
- [#47](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/47) Change version constraint of HVAC module to allow non-major upgrades
- [#56](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/56) Change minimum supported Nautobot version to `1.4.0`
- [#63](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/63) Update plugin description when installed in Nautobot

## v1.3.0 (2022-08-29)

### Added

- [#32](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/32) Add support for skipping certificate validation when connecting to HashiCorp Vault.
- [#34](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/34) Add support for alternate authentication to HashiCorp Vault via AWS and Kubernetes authentication methods.
- [#38](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/38) Add support for Python 3.10.
- [#40](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/40) Add `default_mount_point` config option for HashiCorp Vault.

### Changed

- [#42](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/42) Now requires python-tss-sdk version v1.2 or later

### Fixed

- [#31](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/31) Fixed NameError at startup when installed as `nautobot_secrets_providers[thycotic]`, i.e. without HashiCorp Vault support.
- [#37](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/37) Various fixes and improvements to the development environment.

### Removed

- [#38](https://github.com/nautobot/nautobot-plugin-secrets-providers/pull/38) - Dropped support for end-of-life Python 3.6

## v1.2.0 (2022-05-25)

### Added

- [#8](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/8) Add support for authentication to HashiCorp Vault via AppRole as an alternative to token authentication
- [#23](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/23) Add support for non-default HashiCorp Vault mountpoints

## v1.1.0 (2022-03-10)

### Added

- [#21](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/21) Add Thycotic Secret Server plugin
  **Requires Python 3.7 or greater**

## v1.0.1 (2022-01-06)

### Fixed

- [#17](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/17) Fixed `ModuleNotFoundError` when not installing AWS dependencies

## v1.0.0 (2021-12-22)

This is the initial release of Nautobot Secrets Providers that includes support for basic key-value secrets AWS Secrets Manager and HashiCorp Vault. Please see [README.md](./README.md) for more information.
