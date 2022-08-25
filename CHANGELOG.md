# Nautobot Secrets Providers Changelog

## v1.2.1 (????)

### Added

- [#42](https://github.com/nautobot/nautobot-plugin-secrets-providers/issues/42) Add support for python-tss-sdk version v1.2

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
