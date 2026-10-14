"""1Password Secrets Provider for Nautobot."""

from django import forms
from django.conf import settings
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions

try:
    from bitwarden_sdk import BitwardenClient, DeviceType, client_settings_from_dict
except ImportError:
    BitwardenClient = None


__all__ = ("BitwardenSecretsProvider",)


class BitwardenSecretsProvider(SecretsProvider):
    """A secrets provider for Bitwarden."""

    slug = "bitwarden"  # type: ignore
    name = "Bitwarden"  # type: ignore
    is_available = BitwardenClient is not None

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for HashiCorp Vault."""

        secret_name = forms.CharField(
            label="Secret Name",
            required=False,
            help_text="The name of the secret in the Bitwarden Secrets Manager",
        )
        secret_id = forms.UUIDField(
            label="Secret ID",
            required=False,
            help_text="The UUID used to select the secret in Bitwarden Secrets Manager.",
        )

    @classmethod
    def retrieve_plugin_settings(cls, secret):
        """Retrieve the configuration from settings.

        Args:
            secret (Secret): Nautobot Secret object.
        """
        try:
            plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["bitwarden"]
        except KeyError as err:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden is not configured") from err

        # Validate settings before returning
        cls.validate_settings(plugin_settings, secret)
        return plugin_settings

    @classmethod
    def validate_settings(cls, plugin_settings, secret):
        """Validate the Bitwarden settings.

        Args:
            plugin_settings (dict): Plugin configuration settings.
            secret (Secret): Nautobot Secret object.
        """
        if not plugin_settings:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden is not configured")

        if "api_url" not in plugin_settings:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden configuration is missing an API URL")

        if "identity_url" not in plugin_settings:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden configuration is missing an Identity URL")

        if "token" not in plugin_settings:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden configuration is missing an access token")

        if "org_id" not in plugin_settings:
            raise exceptions.SecretParametersError(secret, cls, "Bitwarden configuration is missing an organization ID")

    @classmethod
    def get_value_by_id(cls, secret, client, secret_id):
        """Retreive secret from Bitwarden by ID.

        Args:
            secret (Secret): Nautobot Secret object.
            client (BitwardenClient): SDK client.
            secret_id (uuid): UUID of secret in Bitwarden.

        Returns:
            secret_retrieved (str): Value of secret stored in Bitwarden.
        """
        try:
            secret_retrieved = client.secrets().get(secret_id)
            if not secret_retrieved.success:
                raise Exception  # pylint: disable=broad-exception-raised
            return secret_retrieved.data.value
        except Exception as err:  # pylint: disable=broad-exception-raised
            raise exceptions.SecretValueNotFoundError(
                secret,
                cls,
                f"Error retrieving secret from Bitwarden with ID {secret_id}. Verify URLs configured and token permissions.",
            ) from err

    @classmethod
    def get_value_by_name(cls, secret, client, secret_name, org_id):
        """Retreive secret from Bitwarden by name.

        Args:
            secret (Secret): Nautobot Secret object.
            client (BitwardenClient): SDK client.
            secret_name (str): Name of secret in Bitwarden.
            org_id (str): UUID for Organization in Bitwarden.

        Returns:
            secret_retrieved (str): Value of secret stored in Bitwarden.
        """
        try:
            # This pulls all secrets the token has permission to view
            # Currently the SDK only supports pulling individual secrets using the UUID
            # This lets us pull using the common name, then iterate over this list later
            all_secrets = client.secrets().list(org_id)
            if not all_secrets:
                raise Exception  # pylint: disable=broad-exception-raised
        except Exception as err:  # pylint: disable=broad-exception-raised
            raise exceptions.SecretProviderError(
                secret,
                cls,
                "Unable to retrieve secrets in Bitwarden. Verify secret parameters in Nautobot, Bitwarden settings, and token permissions.",
            ) from err

        try:
            # Iterate over list of discovered secrets to find matching key using given secret name
            secrets_retrieved = [x for x in all_secrets.data.data if x.key == secret_name]
            if len(secrets_retrieved) == 0:
                raise IndexError
            if len(secrets_retrieved) > 1:
                raise exceptions.SecretValueNotFoundError(
                    secret,
                    cls,
                    f"Multiple secrets found with identical name '{secret_name}'. Bitwarden secret names should be unique.",
                )
            secret_id = secrets_retrieved[0].id
        except AttributeError as err:
            raise exceptions.SecretValueNotFoundError(
                secret,
                cls,
                "Unable to retrieve secret in Bitwarden. Verify secret parameters in Nautobot, Bitwarden settings, and token permissions.",
            ) from err
        except IndexError as err:
            raise exceptions.SecretValueNotFoundError(
                secret,
                cls,
                f"Unable to load secret {secret_name} from Bitwarden. Verify secret exists, token permissions, and the provided secret name exactly matches the configured name.",
            ) from err

        secret_value = cls.get_value_by_id(secret, client, secret_id)
        try:
            if not secret_value:
                raise exceptions.SecretValueNotFoundError(
                    secret, cls, f"No value configured in Bitwarden for secret {secret_name}"
                )
            return secret_value
        except AttributeError as err:
            raise exceptions.SecretValueNotFoundError(
                secret, cls, f"Unable to load value in Bitwarden for secret {secret_name}"
            ) from err

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):  # pylint: disable=too-many-locals
        """Get the value for a secret from Bitwarden.

        Returns:
            secret_value (str): Secret value retrieved from Bitwarden
        """
        plugin_settings = cls.retrieve_plugin_settings(secret)

        client = BitwardenClient(  # type: ignore
            client_settings_from_dict(
                {
                    "apiUrl": plugin_settings["api_url"],
                    "deviceType": DeviceType.SDK,
                    "identityUrl": plugin_settings["identity_url"],
                    "userAgent": "Python",
                }
            )
        )
        try:
            client.auth().login_access_token(plugin_settings["token"])
        except Exception as err:
            raise exceptions.SecretParametersError(
                secret, cls, "Authentication error using token provided in Nautobot config."
            ) from err

        parameters = secret.rendered_parameters(obj=obj)
        secret_name = parameters.get("secret_name")
        secret_id = parameters.get("secret_id")

        # TODO: Add warning if ID and name don't match what's present in Bitwarden?
        if not secret_name and not secret_id:
            raise exceptions.SecretParametersError(
                secret, cls, "Either secret name or ID must be configured in Nautobot."
            )
        if secret_id:
            return cls.get_value_by_id(secret, client, secret_id)

        org_id = plugin_settings["org_id"]
        return cls.get_value_by_name(secret, client, secret_name, org_id)
