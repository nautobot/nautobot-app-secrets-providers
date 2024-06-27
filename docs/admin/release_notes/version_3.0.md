# v3.0 Release Notes

This document describes all new features and changes in the release `3.0`. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release includes support for the Azure Key Vault secrets provider along with significant refactoring and housekeeping.

## [v3.0.0 (2024-06-27)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v3.0.0)

### Added

- [#64](https://github.com/nautobot/nautobot-app-secrets-providers/issues/64) - Added fallthrough for boto3 error handling to catch errors not explicitly defined.
- [#131](https://github.com/nautobot/nautobot-app-secrets-providers/issues/131) - Added a secrets provider for Azure Key Vault.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Added previous release notes to docs.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Added logos and missing doc sections.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Added `0001_update_thycotic_delinea_slug.py` migration to update any legacy Thycotic secrets.

### Changed

- [#124](https://github.com/nautobot/nautobot-app-secrets-providers/issues/124) - Replaced pydocstyle with ruff.
- [#130](https://github.com/nautobot/nautobot-app-secrets-providers/issues/130) - Removed version from docker-compose files.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Updated `creds.example.env` file with clearer environment variables for providers.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Updated lock file dependencies.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Moved installation guides for specific secrets providers to separate pages.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Renamed any existing references of `Thycotic` to `Delinea`.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Updated app's verbose name to `Secrets Providers`.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Updated screenshots in Nautobot 2.0 UI.

### Removed

- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Removed unnecessary provider config from `nautobot_config.py`.
- [#134](https://github.com/nautobot/nautobot-app-secrets-providers/issues/134) - Removed old references to previous Nautobot versions.

### Housekeeping

- [#8](https://github.com/nautobot/nautobot-app-secrets-providers/issues/8) - Re-baked from the latest template.
