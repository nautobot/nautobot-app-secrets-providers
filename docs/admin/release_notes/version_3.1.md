# v3.1 Release Notes

This document describes all new features and changes in the release `3.1`. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release adds support for multiple HashiCorp Vault secrets providers.

## [v3.1.1 (2024-08-22)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v3.1.1)

### Dependencies

- [#145](https://github.com/nautobot/nautobot-app-secrets-providers/issues/145) - Updated `boto3` dependency to permit newer releases.

### Housekeeping

- [#144](https://github.com/nautobot/nautobot-app-secrets-providers/issues/144) - Rebaked from the cookie `nautobot-app-v2.3.0`.
- [#147](https://github.com/nautobot/nautobot-app-secrets-providers/pull/147) - Updated documentation dependencies and added a pin for the `griffe` documentation dependency.

## [v3.1.0 (2024-08-01)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v3.1.0)

### Added

- [#67](https://github.com/nautobot/nautobot-app-secrets-providers/issues/67) - Added the ability to choose between multiple vaults (configurations) for HashiCorp.

### Documentation

- [#137](https://github.com/nautobot/nautobot-app-secrets-providers/issues/137) - Updated documentation links for installed apps page.

### Housekeeping

- [#140](https://github.com/nautobot/nautobot-app-secrets-providers/issues/140) - Updated development environment to use `certifi` `2024.7.4`.
