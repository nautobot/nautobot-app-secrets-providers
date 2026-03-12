"""Password Manager Pro Secrets Provider for Nautobot."""
import os
import requests
from django import forms
from django.conf import settings
from nautobot.extras.secrets import SecretsProvider, exceptions

__all__ = ("PasswordManagerProSecretsProvider",)


class PasswordManagerProSecretsProvider(SecretsProvider):
    """Secrets Provider that retrieves secrets from Password Manager Pro via HTTP GET, using connection config from PLUGINS_CONFIG and token from environment."""

    slug = "password-manager-pro"
    name = "Password Manager Pro Provider"
    description = "Retrieve secrets from Password Manager Pro via HTTP GET (global config)."
    is_available = True

    class ParametersForm(forms.Form):
        """Plain text input for resource and account names."""

        resource_name = forms.CharField(
            label="Resource Name",
            required=True,
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )
        account_name = forms.CharField(
            label="Account Name",
            required=True,
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )

    @classmethod
    def _get_plugin_config(cls, secret):
        """Retrieve plugin config from Nautobot settings."""
        try:
            config = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["password_manager_pro"]
        except KeyError:
            raise exceptions.SecretParametersError(secret, cls, "Password Manager Pro plugin not configured")

        if "base_url" not in config or "token" not in config:
            raise exceptions.SecretParametersError(
                secret, cls, "Password Manager Pro config requires 'base_url' and 'token'"
            )

        return config

    @classmethod
    def _get_resource_account_ids(cls, secret, resource_name, account_name):
        """Helper to get resource and account IDs based on names."""
        config = cls._get_plugin_config(secret)
        url = f"{config['base_url'].rstrip('/')}/restapi/json/v1/resources/getResourceIdAccountId?RESOURCENAME={resource_name}&ACCOUNTNAME={account_name}"
        token = os.getenv(config["token"])
        headers = {"APP_AUTHTOKEN": token}

        try:
            r = requests.get(url, headers=headers, verify=config.get("verify_ssl", True), timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise exceptions.SecretParametersError(secret, cls, f"Failed to fetch resource/account IDs: {exc}") from exc

        try:
            data = r.json()
        except ValueError:
            raise exceptions.SecretParametersError(secret, cls, "Response is not valid JSON")

        operation = data.get("operation", {})
        details = operation.get("Details", {})
        resource_id = details.get("RESOURCEID")
        account_id = details.get("ACCOUNTID")
        if not resource_id or not account_id:
            raise exceptions.SecretParametersError(secret, cls, "Resource or account not found in response")
        return resource_id, account_id

    @classmethod
    def _get_secret_value(cls, secret, resource_id, account_id):
        """Helper to get the secret value based on resource and account IDs."""
        config = cls._get_plugin_config(secret)
        url = f"{config['base_url'].rstrip('/')}/restapi/json/v1/resources/{resource_id}/accounts/{account_id}/password"
        token = os.getenv(config["token"])
        headers = {"APP_AUTHTOKEN": token}

        try:
            r = requests.get(url, headers=headers, verify=config.get("verify_ssl", True), timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise exceptions.SecretParametersError(secret, cls, f"Failed to fetch secret value: {exc}") from exc

        try:
            data = r.json()
        except ValueError:
            raise exceptions.SecretParametersError(secret, cls, "Response is not valid JSON")

        operation = data.get("operation", {})
        details = operation.get("Details", {})
        password = details.get("PASSWORD")
        if password is None or password == "":
            raise exceptions.SecretValueNotFoundError(secret, cls, "Password not found in response")

        return password

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Get the secret value from Password Manager Pro based on resource and account names."""
        parameters = secret.rendered_parameters(obj=obj)
        resource_name = parameters["resource_name"]
        account_name = parameters["account_name"]

        if not resource_name or not account_name:
            raise exceptions.SecretParametersError(secret, cls, "Resource name and account name must be provided")

        resource_id, account_id = cls._get_resource_account_ids(secret, resource_name, account_name)
        return cls._get_secret_value(secret, resource_id, account_id)
