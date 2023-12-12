"""Secrets Provider for Keeper."""
import os

# from pathlib import Path
# import base64
# import json

try:
    from keeper_secrets_manager_core import SecretsManager
    from keeper_secrets_manager_core.core import KSMCache
    from keeper_secrets_manager_core.exceptions import KeeperError, KeeperAccessDenied
    from keeper_secrets_manager_core.storage import FileKeyValueStorage  # , InMemoryKeyValueStorage

    # from keeper_secrets_manager_core.utils import get_totp_code
except (ImportError, ModuleNotFoundError):
    keeper = None

from django import forms
from django.conf import settings

# from django.core.exceptions import ValidationError

from nautobot.apps.secrets import exceptions, SecretsProvider
from nautobot.utilities.forms import BootstrapMixin

from .choices import KeeperTypeChoices


__all__ = ("KeeperSecretsProvider",)


try:
    plugins_config = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
    KEEPER_TOKEN = plugins_config["keeper"]["token"]
except KeyError:
    KEEPER_TOKEN = None


class KeeperSecretsProvider(SecretsProvider):
    """A secrets provider for Keeper Secrets Manager."""

    slug = "keeper-secret-manager"
    name = "Keeper Secret Manager"

    class ParametersForm(BootstrapMixin, forms.Form):
        """Parameters for Keeper Secrets Manager."""

        name = forms.CharField(
            label="Secret Name",
            help_text="The secret's name",
            max_length=30,
            min_length=5,
        )
        uid = forms.CharField(
            label="Secret UID",
            help_text="The secret's uid",
            max_length=25,
            min_length=20,
        )
        token = forms.CharField(
            label="Token",
            widget=forms.PasswordInput,
            help_text="The One Time Token",
            max_length=40,
            min_length=20,
            initial=KEEPER_TOKEN,
        )
        """
        https://docs.keeper.io/secrets-manager/secrets-manager/developer-sdk-library
        {
            "hostname": "keepersecurity.com",
            "clientId": "ab2x3z/Acz0QFTiilm8UxIlqNLlNa25KMj=TpOqznwa4Si-h9tY7n3zvFwlXXDoVWkIs3xrMjcLGwgu3ilmq7Q==",
            "privateKey": "MLSHAgABCDEFGyqGSM49AEGCCqGSM49AwEHBG0wawIWALTARgmcnWx/DH+r7cKh4kokasdasdaDbvHmLABstNbqDwaCWhRANCAARjunta9SJdZE/LVXfVb22lpIfK4YMkJEDaFMOAyoBt0BrQ8aEhvrHN5/Z1BgZ/WpDm9dMR7E5ASIQuYUiAw0t9",
            "serverPublicKeyId": "10",
            "appKey": "RzhSIyKxbpjNu045TUrKaNREYIns+Hk9Kn8YtT+CtK0=",
            "appOwnerPublicKey": "Sq1W1OAnTwi8V/Vs/lhsin2sfSoaRfOwwDDBqoP+EO9bsBMWCzQdl9ClauDiKLXGmlmyx2xmSAdH+hlxvBRs6kU="
        }
        """
        config = forms.JSONField(
            label="Config",
            help_text="The JSON configuration",
            max_length=500,
            min_length=70,
        )
        # config = forms.CharField(
        #     required=True,
        #     help_text="The base64 configuration",
        #     max_length=300,
        #     min_length=30,
        # )
        type = forms.ChoiceField(
            label="Type",
            required=True,
            choices=KeeperTypeChoices.CHOICES,
            help_text="The type of information to retrieve from the secret/record",
        )

        """
        Overloaded clean method to check that at least one of the secret's name or uid is provided
        """

        def clean(self):
            cleaned_data = super().clean()
            if not cleaned_data.get("name") and not cleaned_data.get("uid"):
                raise forms.ValidationError("At least the secret's name or uid must be provided")
            if cleaned_data.get("name") and cleaned_data.get("uid"):
                raise forms.ValidationError("Only one of the secret's name or uid must be provided")
            if not cleaned_data.get("token") and not cleaned_data.get("config"):
                raise forms.ValidationError("At least the token or config must be provided")
            return cleaned_data

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the secret value."""
        # Extract the parameters from the Secret.

        parameters = secret.rendered_parameters(obj=obj)

        if keeper is None:
            raise exceptions.SecretProviderError(
                secret, cls, "The Python dependency keeper_secrets_manager_core is not installed"
            )

        try:
            if "name" in parameters:
                secret_name = parameters["name"]
            if "uid" in parameters:
                secret_uid = parameters["uid"]
            token = parameters.get("token", KEEPER_TOKEN)
            if "config" in parameters:
                config = parameters["config"]
            type = parameters.get("type")
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err

        if not KEEPER_TOKEN and not token and not config:
            raise exceptions.SecretProviderError(
                secret, cls, "Nor the Token or config is configured, at least 1 is required!"
            )

        if not secret_name and not secret_uid:
            raise exceptions.SecretProviderError(secret, cls, "At least the secret's name or uid must be provided!")

        # Ensure required parameters are set
        if any([not all([secret_name, secret_uid, token, config, type])]):
            raise exceptions.SecretProviderError(
                secret,
                "Keeper Secret Manager is not configured!",
            )

        try:
            # Create a Secrets Manager client.
            secrets_manager = SecretsManager(
                token=token,
                # config=InMemoryKeyValueStorage(config),
                config=FileKeyValueStorage("config.json"),
                log_level="DEBUG" if os.environ.get("DEBUG", None) else "ERROR",
                custom_post_function=KSMCache.caching_post_function,
            )
        except (KeeperError, KeeperAccessDenied) as err:
            msg = f"Unable to connect to Keeper Secret Manager {err}"
            raise exceptions.SecretProviderError(secret, msg) from err
        except Exception as err:
            msg = f"Unable to connect to Keeper Secret Manager {err}"
            raise exceptions.SecretProviderError(secret, msg) from err

        if secret_uid:
            try:
                secret = secrets_manager.get_secrets(uids=secret_uid)[0]
                # # https://docs.keeper.io/secrets-manager/secrets-manager/about/keeper-notation
                # secret = secrets_manager.get_notation(f'{secret_uid}/field/{type}')[0]
            except Exception as err:
                msg = f"The secret could not be retrieved using uid {err}"
                raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
        elif secret_name:
            try:
                secret = secrets_manager.get_secret_by_title(secret_name)
            except Exception as err:
                msg = f"The secret could not be retrieved using name {err}"
                raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
        else:
            msg = f"At least the secret's name or uid must be provided"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg)

        try:
            my_secret_info = secret.field(type, single=True)
            # api_key = secret.custom_field('API Key', single=True)
            # url = secret.get_standard_field_value('oneTimeCode', True)
            # totp = get_totp_code(url)
            # https://github.com/Keeper-Security/secrets-manager/blob/master/sdk/python/core/keeper_secrets_manager_core/utils.py#L124C24-L124C24:
        except Exception as err:
            msg = f"The secret field could not be retrieved {err}"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err

        return my_secret_info
