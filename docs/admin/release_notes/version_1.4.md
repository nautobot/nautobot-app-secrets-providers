# v1.4 Release Notes

This document describes all new features and changes in the release `1.4`. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release adds additional enhancements for the Delinea/Thycotic, AWS, and HashiCorp providers. 

## [v1.4.1 (2023-06-08)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v1.4.1)

### Fixed

- [#91](https://github.com/nautobot/nautobot-app-secrets-providers/issues/91) - Fixed Hashicorp Vault Authentication with AWS Credentials when region is not set.

## [v1.4.0 (2023-04-19)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v1.4.0)

### Added

- [#48](https://github.com/nautobot/nautobot-app-secrets-providers/issues/48) - Add token as secret type choice for Delinea/Thycotic.
- [#51](https://github.com/nautobot/nautobot-app-secrets-providers/issues/51) - Add support for AWS Systems Manager Parameter Store.
- [#53](https://github.com/nautobot/nautobot-app-secrets-providers/issues/53) - Add support for Hashicorp Key/Value v1 response.
- [#66](https://github.com/nautobot/nautobot-app-secrets-providers/issues/66) - Add support for Vault Enterprise Namespace parameter.

### Changed

- [#45](https://github.com/nautobot/nautobot-app-secrets-providers/issues/45) - Change references of Thycotic to Delinea.
- [#47](https://github.com/nautobot/nautobot-app-secrets-providers/issues/47) - Change version constraint of HVAC module to allow non-major upgrades.
- [#56](https://github.com/nautobot/nautobot-app-secrets-providers/issues/56) - Change minimum supported Nautobot version to 1.4.0.
- [#63](https://github.com/nautobot/nautobot-app-secrets-providers/issues/63) - Update plugin description when installed in Nautobot.
