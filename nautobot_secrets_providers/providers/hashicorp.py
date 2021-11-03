from django import forms
from django.conf import settings

try:
    import hvac
except ImportError:
    hvac = None

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider
from nautobot.extras.secrets.exceptions import SecretProviderError


__all__ = ("HashiCorpVaultSecretsProvider",)


class HashiCorpVaultSecretsProvider(SecretsProvider):
    """
    A secrets provider for HashiCorp Vault.
    """

    slug = "hashicorp-vault"
    name = "HashiCorp Vault"
    is_available = hvac is not None

    class ParametersForm(BootstrapMixin, forms.Form):
        path = forms.CharField(
            required=True,
            help_text="The path to the HashiCorp Vault secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key of the HashiCorp Vault secret",
        )

    @classmethod
    def get_value_for_secret(cls, secret):
        """
        Return the value stored under the secret’s key in the secret’s path.
        """
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "hashicorp_vault" not in plugin_settings:
            raise SecretProviderError(secret, cls, "HashiCorp Vault is not configured!")

        plugin_settings = plugin_settings["hashicorp_vault"]
        if "url" not in plugin_settings or "token" not in plugin_settings:
            raise SecretProviderError(secret, cls, "HashiCorp Vault is not configured!")

        client = hvac.Client(url=plugin_settings["url"], token=plugin_settings["token"])
        vault = client.secrets.kv.read_secret(path=secret.parameters.get("path"))
        return vault["data"]["data"][secret.parameters.get("key")]
