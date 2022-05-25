"""Secrets Provider for HashiCorp Vault."""

from django import forms
from django.conf import settings

try:
    import hvac

    DEFAULT_MOUNT_POINT = hvac.api.secrets_engines.kv_v2.DEFAULT_MOUNT_POINT
except ImportError:
    hvac = None

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider

__all__ = ("HashiCorpVaultSecretsProvider",)


class HashiCorpVaultSecretsProvider(SecretsProvider):
    """A secrets provider for HashiCorp Vault."""

    slug = "hashicorp-vault"
    name = "HashiCorp Vault"
    is_available = hvac is not None

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
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the value stored under the secret’s key in the secret’s path."""
        # This is only required for HashiCorp Vault therefore not defined in
        # `required_settings` for the plugin config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "hashicorp_vault" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault is not configured!")

        vault_settings = plugin_settings["hashicorp_vault"]

        if "url" not in vault_settings:
            raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault configuration is missing a url")

        # Try to get parameters and error out early.
        parameters = secret.rendered_parameters(obj=obj)
        try:
            secret_path = parameters["path"]
            secret_key = parameters["key"]
            secret_mount_point = parameters.get("mount_point", DEFAULT_MOUNT_POINT)
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err

        # default to token authentication
        auth_method = vault_settings.get("auth_method", "token")

        # Get the client and attempt to retrieve the secret.
        if auth_method == "token":
            try:
                client = hvac.Client(url=vault_settings["url"], token=vault_settings["token"])
            except KeyError as err:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault configuration is missing a token"
                ) from err
            except hvac.exceptions.InvalidRequest as err:
                raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault invalid token") from err
        elif auth_method == "approle":
            try:
                client = hvac.Client(url=vault_settings["url"])
                client.auth.approle.login(
                    role_id=vault_settings["role_id"],
                    secret_id=vault_settings["secret_id"],
                )
            except KeyError as err:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault configuration is missing a role_id and/or secret_id"
                ) from err
            except hvac.exceptions.InvalidRequest as err:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault invalid role_id and/or secret_id"
                ) from err
        else:
            raise exceptions.SecretProviderError(
                secret, cls, f'HashiCorp Vault configuration "{auth_method}" is not a valid auth_method'
            )

        try:
            response = client.secrets.kv.read_secret(path=secret_path, mount_point=secret_mount_point)
        except hvac.exceptions.InvalidPath as err:
            raise exceptions.SecretValueNotFoundError(secret, cls, str(err)) from err

        # Retrieve the value using the key or complain loudly.
        try:
            return response["data"]["data"][secret_key]
        except KeyError as err:
            msg = f"The secret value could not be retrieved using key {err}"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
