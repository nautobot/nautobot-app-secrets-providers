"""Plugin declaration for nautobot_secrets_providers."""
# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
try:
    from importlib import metadata
except ImportError:
    # Python version < 3.8
    import importlib_metadata as metadata

__version__ = metadata.version(__name__)

from nautobot.extras.plugins import PluginConfig


class NautobotSecretsProvidersConfig(PluginConfig):
    """Plugin configuration for the nautobot_secrets_providers plugin."""

    name = "nautobot_secrets_providers"
    verbose_name = "Secrets Management Extensions"
    version = __version__
    author = "Network to Code, LLC"
    description = "Nautobot App that provides direct integrations with Enterprise secrets management systems. Provides patterns to securely fetch secrets for use by other Nautobot Apps and Nautobot Jobs."
    base_url = "secrets"
    required_settings = []
    min_version = "1.2.0"
    max_version = "1.9999"
    default_settings = {}
    caching_config = {}

    # URL reverse lookup names
    home_view_name = "plugins:nautobot_secrets_providers:home"


config = NautobotSecretsProvidersConfig  # pylint:disable=invalid-name
