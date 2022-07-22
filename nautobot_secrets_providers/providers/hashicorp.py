"""Secrets Provider for HashiCorp Vault."""

from django import forms
from django.conf import settings

try:
    import boto3
except ImportError:
    boto3 = None

try:
    import hvac

    DEFAULT_MOUNT_POINT = hvac.api.secrets_engines.kv_v2.DEFAULT_MOUNT_POINT
except ImportError:
    hvac = None

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider

from nautobot_secrets_providers.connectors import HashiCorpVaultConnector
from nautobot_secrets_providers.connectors.exceptions import ConnectorError, SecretValueNotFoundError

__all__ = ("HashiCorpVaultSecretsProvider",)

K8S_TOKEN_DEFAULT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # nosec B105
AUTH_METHOD_CHOICES = ["approle", "aws", "kubernetes", "token"]


class HashiCorpVaultSecretsProvider(SecretsProvider):
    """A secrets provider for HashiCorp Vault."""

    slug = "hashicorp-vault"
    name = "HashiCorp Vault"
    is_available = hvac is not None
    connector = None

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for HashiCorp Vault."""

        path = forms.CharField(
            required=True,
            help_text="The path to the HashiCorp Vault secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key of the HashiCorp Vault secret",
        )
        mount_point = forms.CharField(
            required=False,
            help_text=f"The path where the secret engine was mounted on (Default: <code>{DEFAULT_MOUNT_POINT}</code>)",
            initial=DEFAULT_MOUNT_POINT,
        )

    @classmethod
    def validate_vault_settings(cls, secret):
        """Validate the vault settings."""
        # This is only required for HashiCorp Vault therefore not defined in
        # `required_settings` for the plugin config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "hashicorp_vault" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault is not configured!")

        vault_settings = plugin_settings.get("hashicorp_vault")
        if not cls.connector:
            try:
                cls.connector = HashiCorpVaultConnector(vault_settings)
            except ConnectorError as err:
                raise exceptions.SecretProviderError(secret, cls, str(err)) from err

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the value stored under the secret’s key in the secret’s path."""
        # Try to get parameters and error out early.
        parameters = secret.rendered_parameters(obj=obj)
        try:
            secret_path = parameters["path"]
            secret_key = parameters["key"]
            secret_mount_point = parameters.get("mount_point", DEFAULT_MOUNT_POINT)
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err

        if not cls.connector:
            cls.validate_vault_settings(secret)

        try:
            cls.connector.get_kv_value(secret_key=secret_key, path=secret_path, mount_point=secret_mount_point)
        except ConnectorError as err:
            raise exceptions.SecretProviderError(secret, cls, str(err)) from err
        except SecretValueNotFoundError as err:
            raise exceptions.SecretValueNotFoundError(secret, cls, str(err)) from err
