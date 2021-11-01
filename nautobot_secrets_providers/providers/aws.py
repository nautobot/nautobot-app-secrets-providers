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
    """
    A secrets provider for AWS Secrets Manager.
    """

    slug = "aws-secrets-manager"
    name = "AWS Secrets Manager"
    is_available = boto3 is not None

    class ParametersForm(BootstrapMixin, forms.Form):
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
    def get_value_for_secret(cls, secret):
        """
        Return the secret value by name and region.
        """

        # Extract the parameters from the Secret.
        secret_name = secret.parameters.get("name")
        secret_key = secret.parameters.get("key")
        region_name = secret.parameters.get("region")

        # Create a Secrets Manager client.
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)

        # This is based on sample code to only handle the specific exceptions for the 'GetSecretValue' API.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        # We rethrow the exception by default.
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "DecryptionFailureException":
                # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InternalServiceErrorException":
                # An error occurred on the server side.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InvalidParameterException":
                # You provided an invalid value for a parameter.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretParametersError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InvalidRequestException":
                # You provided a parameter value that is not valid for the current state of the resource.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "ResourceNotFoundException":
                # We can't find the resource that you asked for.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise exceptions.SecretValueNotFoundError(secret, cls, str(e))
        else:
            # Decrypts secret using the associated KMS CMK.
            # Depending on whether the secret is a string or binary, one of these fields will be populated.
            if "SecretString" in get_secret_value_response:
                secret_value = get_secret_value_response["SecretString"]
            else:
                # FIXME(jathan): Do we care about this? And why is the variable name different?
                decoded_binary_secret = base64.b64decode(get_secret_value_response["SecretBinary"])  # noqa

        # If we get this far it should be valid JSON.
        data = json.loads(secret_value)

        # Retrieve the value using the key or complain loudly.
        try:
            return data[secret_key]
        except KeyError as err:
            msg = f"The secret value could not be retrieved using key {err}"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
