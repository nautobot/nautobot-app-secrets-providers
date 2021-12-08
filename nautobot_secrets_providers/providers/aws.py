"""Secrets Provider for AWS Secrets Manager."""

import base64
import json

try:
    import boto3
except ImportError:
    boto3 = None
from botocore.exceptions import ClientError
from django import forms

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider


__all__ = ("AWSSecretsManagerSecretsProvider",)


class AWSSecretsManagerSecretsProvider(SecretsProvider):
    """A secrets provider for AWS Secrets Manager."""

    slug = "aws-secrets-manager"
    name = "AWS Secrets Manager"
    is_available = boto3 is not None

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for AWS Secrets Manager."""

        name = forms.CharField(
            required=True,
            help_text="The name of the AWS Secrets Manager secret",
        )
        region = forms.CharField(
            required=True,
            help_text="The region name of the AWS Secrets Manager secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key of the AWS Secrets Manager secret",
        )

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the secret value by name and region."""
        # Extract the parameters from the Secret.
        parameters = secret.rendered_parameters(obj=obj)

        secret_name = parameters.get("name")
        secret_key = parameters.get("key")
        region_name = parameters.get("region")

        # Create a Secrets Manager client.
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)

        # This is based on sample code to only handle the specific exceptions for the 'GetSecretValue' API.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        # We rethrow the exception by default.
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except ClientError as err:
            if err.response["Error"]["Code"] == "DecryptionFailureException":  # pylint: disable=no-else-raise
                # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "InternalServiceErrorException":
                # An error occurred on the server side.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "InvalidParameterException":
                # You provided an invalid value for a parameter.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretParametersError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "InvalidRequestException":
                # You provided a parameter value that is not valid for the current state of the resource.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "ResourceNotFoundException":
                # We can't find the resource that you asked for.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretValueNotFoundError(secret, cls, str(err))
        else:
            # Decrypts secret using the associated KMS CMK.
            # Depending on whether the secret is a string or binary, one of these fields will be populated.
            if "SecretString" in get_secret_value_response:
                secret_value = get_secret_value_response["SecretString"]
            else:
                # TODO(jathan): Do we care about this? Let's figure out what to do about a binary value?
                secret_value = base64.b64decode(get_secret_value_response["SecretBinary"])  # noqa

        # If we get this far it should be valid JSON.
        data = json.loads(secret_value)

        # Retrieve the value using the key or complain loudly.
        try:
            return data[secret_key]
        except KeyError as err:
            msg = f"The secret value could not be retrieved using key {err}"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
