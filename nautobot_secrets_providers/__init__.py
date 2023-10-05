"""Plugin declaration for nautobot_secrets_providers."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

__version__ = metadata.version(__name__)

from nautobot.extras.plugins import NautobotAppConfig


class NautobotSecretsProvidersConfig(NautobotAppConfig):
    """Plugin configuration for the nautobot_secrets_providers plugin."""

    name = "nautobot_secrets_providers"
    verbose_name = "Nautobot's Secrets Providers Plugin"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot's Secrets Providers Plugin."
    base_url = "secrets-providers"
    required_settings = []
    min_version = "1.4.0"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}


config = NautobotSecretsProvidersConfig  # pylint:disable=invalid-name
