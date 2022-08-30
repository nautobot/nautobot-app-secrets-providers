"""Secrets Provider for HashiCorp Vault."""

from django import forms
from django.conf import settings

try:
    import boto3
except ImportError:
    boto3 = None

try:
    import hvac
except ImportError:
    hvac = None

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider

__all__ = ("HashiCorpVaultSecretsProvider",)

K8S_TOKEN_DEFAULT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # nosec B105
AUTH_METHOD_CHOICES = ["approle", "aws", "kubernetes", "token"]


# Default mount point for the HVAC client
try:
    plugins_config = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
    DEFAULT_MOUNT_POINT = plugins_config["hashicorp_vault"]["default_mount_point"]
except KeyError:
    DEFAULT_MOUNT_POINT = "secret"


class HashiCorpVaultSecretsProvider(SecretsProvider):
    """A secrets provider for HashiCorp Vault."""

    slug = "hashicorp-vault"
    name = "HashiCorp Vault"
    is_available = hvac is not None

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for HashiCorp Vault."""

        path = forms.CharField(
            required=True,
            help_text="The path to the HashiCorp Vault secret",
        )
        key = forms.CharField(
            required=True,
            help_text="The key of the HashiCorp Vault secret",
        )
        mount_point = forms.CharField(
            required=False,
            help_text=f"The path where the secret engine was mounted on (Default: <code>{DEFAULT_MOUNT_POINT}</code>)",
            initial=DEFAULT_MOUNT_POINT,
        )

    @classmethod
    def validate_vault_settings(cls, secret=None):
        """Validate the vault settings."""
        # This is only required for HashiCorp Vault therefore not defined in
        # `required_settings` for the plugin config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "hashicorp_vault" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault is not configured!")

        vault_settings = plugin_settings.get("hashicorp_vault", {})
        auth_method = vault_settings.get("auth_method", "token")

        if "url" not in vault_settings:
            raise exceptions.SecretProviderError(secret, cls, "HashiCorp Vault configuration is missing a url")

        if auth_method not in AUTH_METHOD_CHOICES:
            raise exceptions.SecretProviderError(secret, cls, f"HashiCorp Vault Auth Method {auth_method} is invalid!")

        if auth_method == "aws":
            if not boto3:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault AWS Authentication Method requires the boto3 library!"
                )
        elif auth_method == "token":
            if "token" not in vault_settings:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault configuration is missing a token for token authentication!"
                )
        elif auth_method == "kubernetes":
            if "role_name" not in vault_settings:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault configuration is missing a role name for kubernetes authentication!"
                )
        elif auth_method == "approle":
            if "role_id" not in vault_settings or "secret_id" not in vault_settings:
                raise exceptions.SecretProviderError(
                    secret, cls, "HashiCorp Vault configuration is missing a role_id and/or secret_id!"
                )

        return vault_settings

    @classmethod
    def get_client(cls, secret=None):
        """Authenticate and return a hashicorp client."""
        vault_settings = cls.validate_vault_settings(secret)
        auth_method = vault_settings.get("auth_method", "token")

        k8s_token_path = vault_settings.get("k8s_token_path", K8S_TOKEN_DEFAULT_PATH)
        login_kwargs = vault_settings.get("login_kwargs", {})

        # According to the docs (https://hvac.readthedocs.io/en/stable/source/hvac_v1.html?highlight=verify#hvac.v1.Client.__init__)
        # the client verify parameter is either a boolean or a path to a ca certificate file to verify.  This is non-intuitive
        # so we use a parameter to specify the path to the ca_cert, if not provided we use the default of None
        ca_cert = vault_settings.get("ca_cert", None)

        # Get the client and attempt to retrieve the secret.
        try:
            if auth_method == "token":
                client = hvac.Client(url=vault_settings["url"], token=vault_settings["token"], verify=ca_cert)
            else:
                client = hvac.Client(url=vault_settings["url"], verify=ca_cert)
                if auth_method == "approle":
                    client.auth.approle.login(
                        role_id=vault_settings["role_id"],
                        secret_id=vault_settings["secret_id"],
                        **login_kwargs,
                    )
                elif auth_method == "kubernetes":
                    with open(k8s_token_path, "r", encoding="utf-8") as token_file:
                        jwt = token_file.read()
                    client.auth.kubernetes.login(role=vault_settings["role_name"], jwt=jwt, **login_kwargs)
                elif auth_method == "aws":
                    session = boto3.Session()
                    aws_creds = session.get_credentials()
                    client.auth.aws.iam_login(
                        access_key=aws_creds.access_key,
                        secret_key=aws_creds.secret_key,
                        session_token=aws_creds.token,
                        region=session.region_name,
                        role=vault_settings.get("role_name", None),
                        **login_kwargs,
                    )
        except hvac.exceptions.InvalidRequest as err:
            raise exceptions.SecretProviderError(
                secret, cls, f"HashiCorp Vault Login failed (auth_method: {auth_method}). Error: {err}"
            ) from err
        except hvac.exceptions.Forbidden as err:
            raise exceptions.SecretProviderError(
                secret, cls, f"HashiCorp Vault Access Denied (auth_method: {auth_method}). Error: {err}"
            ) from err

        return client

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the value stored under the secret’s key in the secret’s path."""
        # Try to get parameters and error out early.
        parameters = secret.rendered_parameters(obj=obj)
        try:
            secret_path = parameters["path"]
            secret_key = parameters["key"]
            secret_mount_point = parameters.get("mount_point", DEFAULT_MOUNT_POINT)
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err

        client = cls.get_client(secret)

        try:
            response = client.secrets.kv.read_secret(path=secret_path, mount_point=secret_mount_point)
        except hvac.exceptions.InvalidPath as err:
            raise exceptions.SecretValueNotFoundError(secret, cls, str(err)) from err

        # Retrieve the value using the key or complain loudly.
        try:
            return response["data"]["data"][secret_key]
        except KeyError as err:
            msg = f"The secret value could not be retrieved using key {err}"
            raise exceptions.SecretValueNotFoundError(secret, cls, msg) from err
