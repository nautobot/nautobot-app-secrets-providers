# v4.1 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Added support for HashiCorp Vault "Active Directory" and "LDAP" secrets engines.
- Dropped support for Nautobot v3.0.x.

<!-- towncrier release notes start -->

## [v4.1.0 (2026-10-14)](https://github.com/nautobot/nautobot-app-secrets-providers/releases/tag/v4.1.0)

### Added

- [#230](https://github.com/nautobot/nautobot-app-secrets-providers/issues/230) - Added the HashiCorp Vault AD/LDAP secrets provider to retrieve credentials from the Active Directory and LDAP secrets engines.

### Housekeeping

- Rebaked from the cookie `nautobot-app-v3.1.4`.
