"""Password Manager Pro Secrets Provider for Nautobot."""

import requests
from django import forms
from django.conf import settings
from django.core.cache import cache
from nautobot.extras.secrets import SecretsProvider, exceptions

__all__ = ("PasswordManagerProSecretsProvider",)


class PasswordManagerProSecretsProvider(SecretsProvider):
    """
    Secrets Provider that retrieves secrets from Password Manager Pro via HTTP GET,
    using connection config from PLUGINS_CONFIG and token from environment.
    """

    slug = "password-manager-pro"
    name = "Password Manager Pro Provider"
    description = "Retrieve secrets from Password Manager Pro via HTTP GET (global config)."
    is_available = True

    class ParametersForm(forms.Form):
        """Required parameters to retrieve a secret from PMP."""

        resource_id = forms.CharField(
            label="Resource",
            required=True,
            widget=forms.Select(
                attrs={
                    "class": "form-control nautobot-select2",
                    "data-placeholder": "Select or type resource...",
                }
            ),
        )

        account_id = forms.CharField(
            label="Account",
            required=True,
            widget=forms.Select(
                attrs={
                    "class": "form-control nautobot-select2",
                    "data-placeholder": "Select or type account...",
                }
            ),
        )

    @classmethod
    def _get_plugin_config(cls, secret):
        """Retrieve PMP plugin config from settings."""
        try:
            config = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["password_manager_pro"]
        except KeyError:
            raise exceptions.SecretParametersError(secret, cls, "Password Manager Pro is not configured")
        if not config.get("base_url") or not config.get("token"):
            raise exceptions.SecretParametersError(secret, cls, "Missing base_url or token in config")
        return config

    @classmethod
    def _get_resources(cls, secret):
        """Return dict of resource_name -> resource_id."""
        config = cls._get_plugin_config(secret)
        url = f"{config['base_url'].rstrip('/')}/restapi/json/v1/resources"
        headers = {"APP_AUTHTOKEN": config["token"]}
        try:
            r = requests.get(url, headers=headers, verify=config.get("verify_ssl", True), timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise exceptions.SecretParametersError(secret, cls, f"Failed to fetch resources: {exc}") from exc

        try:
            data = r.json()
        except ValueError:
            raise exceptions.SecretParametersError(secret, cls, "Response is not valid JSON")

        resources = {}
        operation = data.get("operation", [])
        for detail in operation.get("Details", []):
            try:
                resources[detail["RESOURCE NAME"]] = detail["RESOURCE ID"]
            except KeyError:
                continue
        return resources

    @classmethod
    def _get_accounts(cls, secret, resource_id):
        """Return dict of account_name -> account_id for given resource."""
        config = cls._get_plugin_config(secret)
        url = f"{config['base_url'].rstrip('/')}/restapi/json/v1/resources/{resource_id}/accounts"
        headers = {"APP_AUTHTOKEN": config["token"]}
        try:
            r = requests.get(url, headers=headers, verify=config.get("verify_ssl", True), timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise exceptions.SecretParametersError(secret, cls, f"Failed to fetch accounts: {exc}") from exc

        try:
            data = r.json()
        except ValueError:
            raise exceptions.SecretParametersError(secret, cls, "Response is not valid JSON")

        operation = data.get("operation", [])
        details = operation.get("Details")
        if not details:
            return {}

        accounts = {}
        for acc in details.get("ACCOUNT LIST", []):
            name = acc.get("ACCOUNT NAME")
            acc_id = acc.get("ACCOUNT ID")
            if name and acc_id:
                accounts[name] = acc_id
        return accounts

    @classmethod
    def _get_all_resources_with_accounts(cls, secret):
        """Return nested dict of all resources and their accounts, cached for 5 minutes."""
        cache_key = "pmp_resources_accounts"
        cached = cache.get(cache_key)
        if cached:
            return cached

        all_resources = {}
        for resource_name, resource_id in cls._get_resources(secret).items():
            accounts = cls._get_accounts(secret, resource_id)
            all_resources[resource_name] = {"resource_id": resource_id, "accounts": accounts}

        cache.set(cache_key, all_resources, 300)
        return all_resources

    @classmethod
    def _get_secret_value(cls, secret, resource_id, account_id):
        """Fetch the password for a given resource/account."""
        config = cls._get_plugin_config(secret)
        url = f"{config['base_url'].rstrip('/')}/restapi/json/v1/resources/{resource_id}/accounts/{account_id}/password"
        headers = {"APP_AUTHTOKEN": config["token"]}
        try:
            r = requests.get(url, headers=headers, verify=config.get("verify_ssl", True), timeout=10)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise exceptions.SecretValueNotFoundError(secret, cls, f"Failed to retrieve secret: {exc}") from exc

        try:
            data = r.json()
        except ValueError:
            raise exceptions.SecretValueNotFoundError(secret, cls, "Response is not valid JSON")

        operation = data.get("operation", [])
        password = operation.get("Details", {}).get("PASSWORD")
        if not password:
            raise exceptions.SecretValueNotFoundError(secret, cls, "Password not found in response")
        return password

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Retrieve the secret value based on selected resource and account."""
        params = secret.rendered_parameters(obj=obj)
        resource_id = params.get("resource_id")
        account_id = params.get("account_id")
        if not resource_id or not account_id:
            raise exceptions.SecretParametersError(secret, cls, "Both resource and account must be selected.")
        return cls._get_secret_value(secret, resource_id, account_id)

    @classmethod
    def get_parameter_choices(cls, secret, parameter_name, obj=None, **kwargs):
        """Return choices for resource_id and account_id parameters."""
        all_resources = cls._get_all_resources_with_accounts(secret)

        if parameter_name == "resource_id":
            return [(v["resource_id"], name) for name, v in all_resources.items()]

        if parameter_name == "account_id":
            params = secret.rendered_parameters(obj=obj)
            resource_id = params.get("resource_id")
            if not resource_id:
                return []
            resource_name = next((n for n, v in all_resources.items() if v["resource_id"] == resource_id), None)
            if not resource_name:
                return []
            return [(acc_id, acc_name) for acc_name, acc_id in all_resources[resource_name]["accounts"].items()]

        return []