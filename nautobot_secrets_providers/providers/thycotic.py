"""Secrets Provider for Thycotic Secret Server."""
import os
from pathlib import Path

from django import forms
from django.conf import settings

try:
    from thycotic.secrets.server import (
        AccessTokenAuthorizer,
        PasswordGrantAuthorizer,
        DomainPasswordGrantAuthorizer,
        SecretServerCloud,
        SecretServer,
        ServerSecret,
        SecretServerError,
    )

    thycotic_installed = True  # pylint: disable=invalid-name
except ImportError:
    thycotic_installed = False  # pylint: disable=invalid-name

from nautobot.utilities.forms import BootstrapMixin
from nautobot.extras.secrets import exceptions, SecretsProvider


__all__ = (
    "ThycoticSecretServerSecretsProviderId",
    "ThycoticSecretServerSecretsProviderPath",
)


class ThycoticSecretServerSecretsProviderBase(SecretsProvider):
    """A secrets provider for Thycotic Secret Server."""

    is_available = thycotic_installed

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):  # pylint: disable=too-many-locals
        """Return the value stored under the secret’s key in the secret’s path."""
        # This is only required for Thycotic Secret Server therefore not defined in
        # `required_settings` for the plugin config.
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        if "thycotic" not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "Thycotic Secret Server is not configured!")

        # Try to get parameters and error out early.
        parameters = secret.rendered_parameters(obj=obj)
        try:
            if "secret_id" in parameters.keys():
                secret_id = parameters["secret_id"]
            else:
                secret_id = None
            if "secret_path" in parameters.keys():
                secret_path = parameters["secret_path"]
            else:
                secret_path = None
            secret_selected_value = parameters["secret_selected_value"]
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err

        if secret_id is None and secret_path is None:
            msg = "The secret parameter could not be retrieved for field!"
            raise exceptions.SecretParametersError(secret, cls, msg)

        thycotic_settings = plugin_settings["thycotic"]
        is_valid_base_url = "base_url" in thycotic_settings and thycotic_settings["base_url"] != ""
        if not is_valid_base_url:
            raise exceptions.SecretProviderError(secret, cls, "Thycotic Secret Server is not configured!")
        is_valid_domain = "domain" in thycotic_settings and thycotic_settings["domain"] != ""
        is_valid_password = "password" in thycotic_settings and thycotic_settings["password"] != ""
        is_valid_tenant = "tenant" in thycotic_settings and thycotic_settings["tenant"] != ""
        is_valid_token = "token" in thycotic_settings and thycotic_settings["token"] != ""
        is_valid_username = "username" in thycotic_settings and thycotic_settings["username"] != ""
        if_valid_ca_bundle_path = "ca_bundle_path" in thycotic_settings and thycotic_settings["ca_bundle_path"] != ""

        return cls.query_thycotic_secret_server(
            secret=secret,
            base_url=thycotic_settings["base_url"],
            ca_bundle_path=thycotic_settings["ca_bundle_path"] if if_valid_ca_bundle_path else None,
            cloud_based=thycotic_settings["cloud_based"],
            domain=thycotic_settings["domain"] if is_valid_domain else None,
            password=thycotic_settings["password"] if is_valid_password else None,
            secret_id=secret_id,
            secret_path=secret_path,
            secret_selected_value=secret_selected_value,
            tenant=thycotic_settings["tenant"] if is_valid_tenant else None,
            token=thycotic_settings["token"] if is_valid_token else None,
            username=thycotic_settings["username"] if is_valid_username else None,
            caller_class=cls,
        )

    @staticmethod
    def query_thycotic_secret_server(  # pylint: disable=too-many-boolean-expressions,too-many-locals,too-many-branches,too-many-arguments
        secret,
        base_url,
        ca_bundle_path=None,
        cloud_based=None,
        domain=None,
        password=None,
        secret_id=None,
        secret_path=None,
        secret_selected_value=None,
        tenant=None,
        token=None,
        username=None,
        caller_class=None,
    ):
        """Query Thycotic Secret Server."""
        # Ensure required parameters are set
        if (
            token is None and (username is None or password is None)
        ) or (  # pylint: disable=too-many-boolean-expressions
            cloud_based and (tenant is None or username is None or password is None)
        ):
            raise exceptions.SecretProviderError(secret, caller_class, "Thycotic Secret Server is not configured!")

        must_restore_env = False
        original_env = os.getenv("REQUESTS_CA_BUNDLE", "")
        try:
            if ca_bundle_path is not None:
                # Ensure cerificates file exists if ca_bundle_path is defined
                if not Path(ca_bundle_path).exists():
                    raise exceptions.SecretProviderError(
                        secret,
                        caller_class,
                        (
                            "Thycotic Secret Server is not configured properly! "
                            "Trusted certificates file not found: "
                            "Environment variable 'REQUESTS_CA_BUNDLE': "
                            f"{ca_bundle_path}."
                        ),
                    )
                if original_env != ca_bundle_path:
                    os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle_path
                    must_restore_env = True
            # Setup thycotic authorizer
            # Username | Password | Token | Domain | Authorizer
            #   def    |   def    |   *   |   -    | PasswordGrantAuthorizer
            #   def    |   def    |   *   |  def   | DomainPasswordGrantAuthorizer
            #    -     |    -     |  def  |   *    | AccessTokenAuthorizer
            #   def    |    -     |  def  |   *    | AccessTokenAuthorizer
            #    -     |   def    |  def  |   *    | AccessTokenAuthorizer
            if username is not None and password is not None:
                if domain is not None:
                    thy_authorizer = DomainPasswordGrantAuthorizer(
                        base_url=base_url,
                        domain=domain,
                        username=username,
                        password=password,
                    )
                else:
                    thy_authorizer = PasswordGrantAuthorizer(
                        base_url=base_url,
                        username=username,
                        password=password,
                    )
            else:
                thy_authorizer = AccessTokenAuthorizer(token)

            # Get the client.
            if cloud_based:
                thycotic = SecretServerCloud(tenant=tenant, authorizer=thy_authorizer)
            else:
                thycotic = SecretServer(base_url=base_url, authorizer=thy_authorizer)

            # Attempt to retrieve the secret.
            try:
                if secret_id is not None:
                    secret = ServerSecret(**thycotic.get_secret(secret_id))
                else:
                    secret = ServerSecret(**thycotic.get_secret_by_path(secret_path))
            except SecretServerError as err:
                raise exceptions.SecretValueNotFoundError(secret, caller_class, str(err)) from err

            # Attempt to return the selected value.
            try:
                return secret.fields[secret_selected_value].value
            except KeyError as err:
                msg = f"The secret value could not be retrieved using key {err}"
                raise exceptions.SecretValueNotFoundError(secret, caller_class, msg) from err
        finally:
            if must_restore_env:
                os.environ["REQUESTS_CA_BUNDLE"] = original_env


class ThycoticSecretServerSecretsProviderId(ThycoticSecretServerSecretsProviderBase):
    """A secrets provider for Thycotic Secret Server."""

    slug = "thycotic-tss-id"  # type: ignore
    name = "Thycotic Secret Server by ID"  # type: ignore

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for Thycotic Secret Server."""

        secret_id = forms.IntegerField(
            required=True,
            min_value=1,
            help_text="The secret-id used to select the entry in Thycotic Secret Server.",
        )
        secret_selected_value = forms.ChoiceField(
            label="Return value",
            required=True,
            choices=(
                ("password", "Password"),
                ("username", "Username"),
                ("url", "URL"),
                ("notes", "Notes"),
            ),
            help_text="Select which value to return.",
        )


class ThycoticSecretServerSecretsProviderPath(ThycoticSecretServerSecretsProviderBase):
    """A secrets provider for Thycotic Secret Server."""

    slug = "thycotic-tss-path"  # type: ignore
    name = "Thycotic Secret Server by Path"  # type: ignore

    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for Thycotic Secret Server."""

        secret_path = forms.CharField(
            required=True,
            max_length=300,
            min_length=3,
            help_text=r"Enter the secret's path (e.g. \FolderPath\Secret Name).",
        )
        secret_selected_value = forms.ChoiceField(
            label="Return value",
            required=True,
            choices=(
                ("password", "Password"),
                ("username", "Username"),
                ("url", "URL"),
                ("notes", "Notes"),
            ),
            help_text="Select which value to return.",
        )