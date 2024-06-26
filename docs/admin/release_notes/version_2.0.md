# v2.0 Release Notes

This document describes all new features and changes in the release `2.0`. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

This release updates Secrets Provider to be compatible with Nautobot v2.0.

## [v2.0.1 (2023-09-29)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v2.0.1)

### Added

- [#113](https://github.com/nautobot/nautobot-app-secrets-providers/issues/113) - Added the missing fix for [issue](https://github.com/nautobot/nautobot-app-secrets-providers/issues/91) that was not included for v2.0.0.

## [v2.0.0 (2023-09-29)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v2.0.0)

### Changed

- [#105](https://github.com/nautobot/nautobot-app-secrets-providers/pull/106) Updated `nautobot` to `2.0`.
- [#111](https://github.com/nautobot/nautobot-app-secrets-providers/issues/111) - Migrate app to Nautobot v2.0 compatible.

### Fixed

- [#92](https://github.com/nautobot/nautobot-app-secrets-providers/issues/92) - Fixed null AWS region.

### Removed

- [#105](https://github.com/nautobot/nautobot-app-secrets-providers/pull/106) - Removed `slug` field from `Secret` model. Can be replaced with `name` field or [natural keys](https://docs.nautobot.com/projects/core/en/next/development/apps/migration/model-updates/global/#replace-the-usage-of-slugs-with-composite-keys).
