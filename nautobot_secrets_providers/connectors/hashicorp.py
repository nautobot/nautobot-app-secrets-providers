"""Generic connector for HashiCorp Vault not tied to django."""
from .exceptions import ConnectorError, SecretValueNotFoundError
from os.path import exists

try:
    import boto3
except ImportError:
    boto3 = None

import hvac

AUTH_METHOD_CHOICES = ["approle", "aws", "kubernetes", "token"]
DEFAULT_MOUNT_POINT = hvac.api.secrets_engines.kv_v2.DEFAULT_MOUNT_POINT
K8S_TOKEN_DEFAULT_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # nosec B105


class HashiCorpVaultConnector:
    """A generic connector for HashiCorp Vault."""

    vault_settings = {}
    validated = False
    auth_method = ""
    client = None

    @classmethod
    def __init__(cls, vault_settings):
        """Set some defaults."""
        cls.vault_settings = vault_settings
        cls.auth_method = vault_settings.get("auth_method", "token")
        cls.k8s_token_path = vault_settings.get("k8s_token_path", K8S_TOKEN_DEFAULT_PATH)
        if hvac and not cls.validated:
            cls.validate_vault_settings()

    @classmethod
    def validate_vault_settings(cls):
        """Validate the vault settings."""
        if "url" not in cls.vault_settings:
            raise ConnectorError(cls, "HashiCorp Vault configuration is missing a url")

        if cls.auth_method not in AUTH_METHOD_CHOICES:
            raise ConnectorError(cls, f"HashiCorp Vault Auth Method {cls.auth_method} is invalid!")

        if cls.auth_method == "aws":
            if not boto3:
                raise ConnectorError(cls, "HashiCorp Vault AWS Auth Method requires the boto3 plugin!")
        elif cls.auth_method == "token":
            if "token" not in cls.vault_settings:
                raise ConnectorError(cls, "HashiCorp Vault configuration is missing a token for token authentication!")
        elif cls.auth_method == "kubernetes":
            if "role_name" not in cls.vault_settings:
                raise ConnectorError(
                    cls, "HashiCorp Vault configuration is missing a role name for kubernetes authentication!"
                )
            if not exists(cls.k8s_token_path):
                raise ConnectorError(
                    cls, "HashiCorp Vault configuration is missing a role name for kubernetes authentication!"
                )
        elif cls.auth_method == "approle":
            if "role_id" not in cls.vault_settings or "secret_id" not in cls.vault_settings:
                raise ConnectorError(cls, "HashiCorp Vault configuration is missing a role_id and/or secret_id!")
        cls.validated = True

    @classmethod
    def get_client(cls):
        """Get a hvac client and login."""
        if not cls.validated:
            cls.validate_vault_settings()
        elif cls.client:
            return cls.client

        login_kwargs = cls.vault_settings.get("login_kwargs", {})

        # According to the docs (https://hvac.readthedocs.io/en/stable/source/hvac_v1.html?highlight=verify#hvac.v1.Client.__init__)
        # the client verify parameter is either a boolean or a path to a ca certificate file to verify.  This is non-intuitive
        # so we use a parameter to specify the path to the ca_cert, if not provided we use the default of None
        ca_cert = cls.vault_settings.get("ca_cert", None)

        # Get the client and attempt to retrieve the secret.
        try:
            if cls.auth_method == "token":
                cls.client = hvac.Client(
                    url=cls.vault_settings["url"], token=cls.vault_settings["token"], verify=ca_cert
                )
            else:
                cls.client = hvac.Client(url=cls.vault_settings["url"], verify=ca_cert)
                if cls.auth_method == "approle":
                    cls.client.auth.approle.login(
                        role_id=cls.vault_settings["role_id"],
                        secret_id=cls.vault_settings["secret_id"],
                        **login_kwargs,
                    )
                elif cls.auth_method == "kubernetes":
                    with open(cls.k8s_token_path, "r", encoding="utf-8") as token_file:
                        jwt = token_file.read()
                    cls.client.auth.kubernetes.login(role=cls.vault_settings["role_name"], jwt=jwt, **login_kwargs)
                elif cls.auth_method == "aws":
                    session = boto3.Session()
                    aws_creds = session.get_credentials()
                    cls.client.auth.aws.iam_login(
                        access_key=aws_creds.access_key,
                        secret_key=aws_creds.secret_key,
                        session_token=aws_creds.token,
                        region=session.region_name,
                        role=cls.vault_settings.get("role_name", None),
                        **login_kwargs,
                    )
        except hvac.exceptions.InvalidRequest as err:
            raise ConnectorError(
                cls, f"HashiCorp Vault Login failed (auth_method: {cls.auth_method}). Error: {err}"
            ) from err
        except hvac.exceptions.Forbidden as err:
            raise ConnectorError(
                cls, f"HashiCorp Vault Access Denied (auth_method: {cls.auth_method}). Error: {err}"
            ) from err

        return cls.client

    @classmethod
    def get_kv_value(cls, secret_key, default_value=None, **kwargs):
        """Get a kv key and return the value stored in secret_key."""
        client = cls.get_client()
        try:
            response = client.secrets.kv.read_secret(**kwargs)
        except hvac.exceptions.InvalidPath as err:
            raise ConnectorError(cls, str(err)) from err

        # Retrieve the value using the key or complain loudly.
        try:
            return response["data"]["data"][secret_key]
        except KeyError as err:
            if default_value:
                return default_value
            else:
                msg = f"The secret value could not be retrieved using key {err}"
                raise SecretValueNotFoundError(cls, msg) from err
