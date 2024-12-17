"""Secrets Provider for CyberArk Secret Server."""

import os
from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

try:
    from pyaim import CLIPasswordSDK
    cyberark_installed = True
except ImportError:
    cyberark_installed = False

from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions


class CyberArkCLIPasswordSDKSecretsProvider(SecretsProvider):
    """A secrets provider for CyberArk CLIPasswordSDK."""

    is_available = cyberark_installed
    slug = "cyberark-cli-password-sdk"
    name = "CyberArk CLI Password SDK"

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required paramters for CyberArk CLI Password SDK"""

        app_id = forms.CharField(
            required=True,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's App Id",
            empty_value=None,
        )
        safe = forms.CharField(
            required=True,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Safe",
            empty_value=None,
        )
        object = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Object. Must pass this or username",
            empty_value=None,
        )
        useranme = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Useranme. Must pass this or object",
            empty_value=None,
        )
        output = forms.CharField(
            required=True,
            max_length=300,
            min_length=3,
            help_text=r"Enter the desired output field (Ex: PassProps.Username)",
            empty_value=None,
        )
        folder = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Folder",
            empty_value=None,
        )
        address = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Address",
            empty_value=None,
        )
        database = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Database",
            empty_value=None,
        )
        policyid = forms.IntegerField(
            required=False,
            max_value=30000,
            min_value=0,
            help_text=r"Enter the secret's Policy ID",
        )
        reason = forms.CharField(
            required=False,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's Access Reason",
            empty_value=None,
        )
        query_format = forms.IntegerField(
            required=False,
            max_value=300,
            min_value=0,
            help_text=r"Enter the secret's Query Format",
        )
        connport = forms.IntegerField(
            required=False,
            max_value=65535,
            min_value=1,
            help_text=r"Enter the secret's Connection Port",
        )
        #sendhash = forms.BooleanField(
        #    required=False,
        #    help_text=r"Whether to send Hash",
        #)
        delimeter = forms.CharField(
            required=False,
            max_length=1,
            min_length=1,
            help_text=r"Enter the secret's output Delimiter",
            empty_value=None,
        )
        #dual_accounts = forms.BooleanField(
        #    required=False,
        #    help_text=r"Whether to Dual Accounts",
        #)

        def clean(self):
            clean_data = super().clean()
            object = clean_data.get("object")
            username = clean_data.get("username")
            if not object and not username:
                raise ValidationError("One of 'object' or 'username' must be provided")
            elif object and username:
                raise ValidationError("Only one of 'object' and 'username' may be provided")

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):  # pylint: disable=too-many-locals
        """Return the value stored under the secret's key in the secret's path."""
        # This is only required for Delinea Secret Server therefore not defined in
        # `required_settings` for the app config.
        cyberark_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"].get("cyberark")
        if not cyberark_settings:
            raise exceptions.SecretProviderError(secret, cls, "CyberArk Secrets Provider is not configured!")
        cyberark_sdk_executable_path = cyberark_settings.get("sdk_executable_path")
        if not cyberark_sdk_executable_path:
            raise exceptions.SecretProviderError(secret, cls, "CyberArk Secrets Provider is not configured with cyberark_sdk_executable_path!")
        if not Path(cyberark_sdk_executable_path).exists():
            raise exceptions.SecretProviderError(
                secret,
                cls,
                (
                    "CyberArk Secrets Provider is not configured properly! "
                    "The CLI SDK executable file not found: "
                    f"{cyberark_sdk_executable_path}."
                ),
            )

        parameters = secret.rendered_parameters(obj=obj)
        secret_kwargs = {key: value for key, value in parameters.items() if value is not None}
        try:
            aimcp = CLIPasswordSDK(cyberark_sdk_executable_path)
            response = aimcp.GetPassword(**secret_kwargs)
        except Exception as err:
            msg = f"The secret parameter could not be retrieved {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err
        
        if len(response) == 1:
            return response[parameters["output"]]
        return response
