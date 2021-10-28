import base64

import boto3
from botocore.exceptions import ClientError
from django import forms
from django.conf import settings

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider
from nautobot.extras.secrets.exceptions import SecretProviderError


__all__ = ("AWSSecretsManagerSecretsProvider",)


class AWSSecretsManagerSecretsProvider(SecretsProvider):
    """
    A secrets provider for AWS Secrets Manager.
    """

    slug = "aws-secrets-manager"
    name = "AWS Secrets Manager"

    class ParametersForm(BootstrapMixin, forms.Form):
        secret_name = forms.CharField(
            required=True,
            help_text="The name of the AWS Secrets Manager secret",
        )
        region_name = forms.CharField(
            required=True,
            help_text="The region name of the AWS Secrets Manager secret",
        )

    @classmethod
    def get_value_for_secret(cls, secret):
        """
        Return the secret value by name and region.
        """

        secret_name = secret.parameters.get("secret_name")
        region_name = secret.parameters.get("region_name")

        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)

        # This is based on sample code to only handle the specific exceptions for the 'GetSecretValue' API.
        # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        # We rethrow the exception by default.
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except ClientError as e:
            raise SecretProviderError(secret, cls, str(e)) from e
            # TODO(jathan): Decide if we care about this level of granularity in
            # error-handling provided by the AWS sample code?
            """
            if e.response["Error"]["Code"] == "DecryptionFailureException":
                # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InternalServiceErrorException":
                # An error occurred on the server side.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InvalidParameterException":
                # You provided an invalid value for a parameter.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "InvalidRequestException":
                # You provided a parameter value that is not valid for the current state of the resource.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise SecretProviderError(secret, cls, str(e))
            elif e.response["Error"]["Code"] == "ResourceNotFoundException":
                # We can't find the resource that you asked for.
                # Deal with the exception here, and/or rethrow at your discretion.
                raise SecretProviderError(secret, cls, str(e))
            """
        else:
            # Decrypts secret using the associated KMS CMK.
            # Depending on whether the secret is a string or binary, one of these fields will be populated.
            if "SecretString" in get_secret_value_response:
                secret_value = get_secret_value_response["SecretString"]
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response["SecretBinary"])

        return secret_value


secrets_providers = [AWSSecretsManagerSecretsProvider]
