"""Secrets Provider for AWS Parameter Store."""
import json

try:  # pylint: disable=R0801
    import boto3
    from botocore.exceptions import ClientError
except (ImportError, ModuleNotFoundError):
    boto3 = None

from django import forms

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider


__all__ = ("AWSSystemsManagerParameterStore",)

# See https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html


class AWSSystemsManagerParameterStore(SecretsProvider):
    """A secrets provider for AWS Parameter Store."""

    slug = "aws-ssm-manager"
    name = "AWS Parameter Store"
    is_available = boto3 is not None

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for AWS Parameter Store."""

        name = forms.CharField(
            required=True,
            help_text="The name of the AWS Parameter Store secret",
        )
        region = forms.CharField(
            required=True,
            help_text="The region name of the AWS Parameter Store secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key name to retrieve from AWS Parameter Store",
        )

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the parameter value by name and region."""
        # Extract the parameters from the Nautobot secret.
        parameters = secret.rendered_parameters(obj=obj)

        # Create a SSM client.
        session = boto3.session.Session()
        client = session.client(service_name="ssm", region_name=parameters.get("region"))
        try:
            get_secret_value_response = client.get_parameter(Name=parameters.get("name"), WithDecryption=True)
        except ClientError as err:
            if err.response["Error"]["Code"] == "InternalServerError":  # pylint: disable=no-else-raise
                raise exceptions.SecretProviderError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "InvalidKeyId":
                raise exceptions.SecretProviderError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "ParameterNotFound":
                raise exceptions.SecretParametersError(secret, cls, str(err))
            elif err.response["Error"]["Code"] == "ParameterVersionNotFound":
                raise exceptions.SecretValueNotFoundError(secret, cls, str(err))
        else:
            try:
                # Fetch the Value field from the parameter which must be a json field.
                data = json.loads(get_secret_value_response["Parameter"]["Value"])
            except ValueError as err:
                msg = "InvalidJson"
                raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
        try:
            # Return the value of the secret key configured in the nautobot secret.
            return data[parameters.get("key")]
        except KeyError as err:
            msg = f"InvalidKeyName {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err
