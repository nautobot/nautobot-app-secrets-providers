"""1Password Secrets Provider for Nautobot."""

from asgiref.sync import async_to_sync
from django import forms
from django.conf import settings
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions

try:
    from onepassword.client import Client
except ImportError:
    Client = None

from nautobot_secrets_providers import __version__

__all__ = ("OnePasswordSecretsProvider",)


@async_to_sync
async def get_secret_from_vault(vault, item, field, token, section=None):
    """Get a secret from a 1Password vault.

    Args:
        vault (str): 1Password Vault where the secret is located.
        item (str): 1Password Item where the secret is located.
        field (str): 1Password secret field name.
        token (str): 1Password Service Account token.
        section (str, optional): 1Password Item Section for the secret. Defaults to None.

    Returns:
        (str): Value from the secret.
    """
    client = await Client.authenticate(
        auth=token, integration_name="nautobot-secrets-providers", integration_version=__version__
    )
    reference = f"op://{vault}/{item}/{f'{section}/' if section else ''}{field}"
    return await client.secrets.resolve(reference)


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
            help_text="The field where the secret is located. Defaults to 'password'.",
            initial="password",
        )

    @classmethod
    def get_token(cls, secret, vault):
        """Get the token for a vault."""
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "token" in plugin_settings["one_password"]["vaults"][vault]:
            return plugin_settings["one_password"]["vaults"][vault]["token"]
        try:
            return plugin_settings["one_password"]["token"]
        except KeyError as exc:
            raise exceptions.SecretProviderError(secret, cls, "1Password token is not configured!") from exc

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):  # pylint: disable=too-many-locals
        """Get the value for a secret from 1Password."""
        # This is only required for 1Password therefore not defined in
        # `required_settings` for the app config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "one_password" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "1Password is not configured!")

        parameters = secret.rendered_parameters(obj=obj)
        vault = parameters["vault"]

        return get_secret_from_vault(
            vault=vault,
            item=parameters["item"],
            field=parameters["field"],
            token=cls.get_token(secret, vault=vault),
            section=parameters.get("section", None),
        )
