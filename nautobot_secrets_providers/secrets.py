"""
Secrets Providers published by this module.

The providers are conditionally loaded based on whether their dependent libraries are installed.
Please see the README for how to install those.
"""

from nautobot_secrets_providers import providers


# Iterate over included secrets providers and only publish them if their `is_available` flag is True
# (meaning their dependent library is installed).
secrets_providers = []

for provider in providers.__all__:
    # Don't publish multiple times.
    if provider in secrets_providers:
        continue

    if provider.is_available:
        secrets_providers.append(provider)

if not secrets_providers:
    raise RuntimeError("No secrets providers were published! Did you remember install the dependencies?")
