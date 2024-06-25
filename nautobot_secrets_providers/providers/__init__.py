"""Nautobot Secrets Providers."""

from .aws import AWSSecretsManagerSecretsProvider, AWSSystemsManagerParameterStore
from .azure import AzureKeyVaultSecretsProvider
from .hashicorp import HashiCorpVaultSecretsProvider
from .delinea import DelineaSecretServerSecretsProviderId, DelineaSecretServerSecretsProviderPath

__all__ = (  # type: ignore
    AWSSecretsManagerSecretsProvider,  # pylint: disable=invalid-all-object
    AWSSystemsManagerParameterStore,  # pylint: disable=invalid-all-object
    AzureKeyVaultSecretsProvider,  # pylint: disable=invalid-all-object
    DelineaSecretServerSecretsProviderId,  # pylint: disable=invalid-all-object
    DelineaSecretServerSecretsProviderPath,  # pylint: disable=invalid-all-object
    HashiCorpVaultSecretsProvider,  # pylint: disable=invalid-all-object
)
