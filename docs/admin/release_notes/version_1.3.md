# v1.3 Release Notes

This document describes all new features and changes in the release `1.3`. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release adds support for Python 3.10, along with other provider enhancements and bug fixes. 

## [v1.3.0 (2022-08-30)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v1.3.0)

### Added

- [#32](https://github.com/nautobot/nautobot-app-secrets-providers/issues/32) - Add support for skipping certificate validation when connecting to HashiCorp Vault.
- [#34](https://github.com/nautobot/nautobot-app-secrets-providers/issues/34) - Add support for alternate authentication to HashiCorp Vault via AWS and Kubernetes authentication methods.
- [#38](https://github.com/nautobot/nautobot-app-secrets-providers/issues/38) - Add support for Python 3.10.
- [#40](https://github.com/nautobot/nautobot-app-secrets-providers/issues/40) - Add `default_mount_point` config option for HashiCorp Vault.

### Changed

- [#42](https://github.com/nautobot/nautobot-app-secrets-providers/issues/42) - Now requires python-tss-sdk version v1.2 or later.

### Fixed

- [#31](https://github.com/nautobot/nautobot-app-secrets-providers/issues/31) - Fixed NameError at startup when installed as `nautobot_secrets_providers[thycotic]`, i.e. without HashiCorp Vault support.
- [#37](https://github.com/nautobot/nautobot-app-secrets-providers/issues/37) - Various fixes and improvements to the development environment.

### Removed

- [#38](https://github.com/nautobot/nautobot-app-secrets-providers/issues/38) - Dropped support for end-of-life Python 3.6
