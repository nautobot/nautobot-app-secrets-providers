"""Secrets Provider for Azure Key Vault."""

try:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    azure_available = True  # pylint: disable=invalid-name
except ImportError:
    azure_available = False  # pylint: disable=invalid-name

from django import forms
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider

__all__ = ("AzureKeyVaultSecretsProvider",)


class AzureKeyVaultSecretsProvider(SecretsProvider):
    """A secrets provider for Azure Key Vault."""

    slug = "azure-key-vault"
    name = "Azure Key Vault"
    is_available = azure_available

    # pylint: disable-next=nb-incorrect-base-class
    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for Azure Key Vault."""

        vault_url = forms.CharField(
            required=True,
            help_text="The URL of the Azure Key Vault",
        )
        secret_name = forms.CharField(
            required=True,
            help_text="The name of the secret in the Azure Key Vault",
        )

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the secret value by name from Azure Key Vault."""
        # Extract the parameters from the Secret.
        parameters = secret.rendered_parameters(obj=obj)
        vault_url = parameters.get("vault_url")
        secret_name = parameters.get("secret_name")

        # Authenticate with Azure Key Vault using default credentials.
        # This assumes that environment variables for Azure authentication are set.
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        try:
            # Retrieve the secret from Azure Key Vault.
            response = client.get_secret(secret_name)
        except Exception as err:
            # Handle exceptions from the Azure SDK.
            raise exceptions.SecretProviderError(secret, cls, str(err))

        # The value is in the 'value' attribute of the response.
        secret_value = response.value

        # Return the secret value.
        return secret_value
