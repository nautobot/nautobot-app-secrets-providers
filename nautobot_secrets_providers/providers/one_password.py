import asyncio
import os
from django import forms
from django.conf import settings
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions
try:
    from onepassword.client import Client
except ImportError:
    Client = None


async def get_secret_from_vault(vault, item, field, token, section=None):
    pass

def vault_choices():
    """Generate Choices for vault form field.

    Build a form option for each key in vaults.
    """
    plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
    return [(key, key) for key in plugin_settings["one_password"]["vaults"].keys()]


class OnePasswordSecretsProvider(SecretsProvider):
    """A secrets provider for 1Password."""

    slug = "one-password"
    name = "1Password Vault"
    is_available = Client is not None

    # TBD: Remove after pylint-nautobot bump
    # pylint: disable-next=nb-incorrect-base-class
    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for HashiCorp Vault."""

        vault = forms.ChoiceField(
            required=True,
            choices=vault_choices,
            help_text="1Password Vault to retrieve the secret from.",
        )
        item = forms.CharField(
            required=True,
            help_text="The item in 1Password.",
        )
        section = forms.CharField(
            required=False,
            help_text="The section where the field is a part of.",
        )
        field = forms.CharField(
            required=True,
            help_text="The field where the secret is located.",
        )

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):  # pylint: disable=too-many-locals

        # This is only required for 1Password therefore not defined in
        # `required_settings` for the app config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "1password" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "1Password is not configured!")
        
        asyncio.run(get_secret_from_vault())