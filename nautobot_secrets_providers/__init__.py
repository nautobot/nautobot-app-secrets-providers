"""App declaration for nautobot_secrets_providers."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class NautobotSecretsProvidersConfig(NautobotAppConfig):
    """App configuration for the nautobot_secrets_providers app."""

    name = "nautobot_secrets_providers"
    verbose_name = "Nautobot's Secrets Providers App"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot's Secrets Providers App."
    base_url = "secrets-providers"
    required_settings = []
    min_version = "2.0.0"
    max_version = "2.9999"
    default_settings = {}
    caching_config = {}


config = NautobotSecretsProvidersConfig  # pylint:disable=invalid-name
