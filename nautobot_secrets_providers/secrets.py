import hvac
from django import forms
from django.conf import settings

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider


class VaultSecretsProvider(SecretsProvider):
    """
    A secrets provider for Hashicorp Vault.
    """

    slug = "hashicorp-vault"
    name = "Hashicorp Vault"

    class ParametersForm(BootstrapMixin, forms.Form):
        path = forms.CharField(
            required=True,
            help_text="The path to the Hashicorp Vault secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key of the Hashicorp Vault secret",
        )

    @classmethod
    def get_value_for_secret(cls, secret):
        """
        Return the value stored under the secret’s key in the secret’s path.
        """
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "vault_url" not in plugin_settings or "vault_token" not in plugin_settings:
            raise ValueError("Hashicorp Vault is not configured!")
        client = hvac.Client(url=plugin_settings["vault_url"], token=plugin_settings["vault_token"])
        vault = client.secrets.kv.read_secret(path=secret.parameters.get("path"))
        return vault["data"]["data"][secret.parameters.get("key")]


secrets_providers = [VaultSecretsProvider]
