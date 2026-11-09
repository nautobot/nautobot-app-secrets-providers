"""Secrets Providers for BeyondTrust Password Safe."""

import requests
from django import forms
from django.conf import settings
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions

__all__ = (
    "BeyondTrustPasswordSafeManagedAccountSecretsProvider",
    "BeyondTrustPasswordSafeSecretsSafeSecretsProvider",
)

API_VERSION = "3.2"

# Some on-prem Password Safe versions return a bare numeric code as the response body instead of a
# message. Password Safe Cloud returns the message text directly, so this map is only a fallback.
ERROR_MESSAGES = {
    "4031": "User does not have permission.",
    "4034": "Request is not yet approved.",
    "4091": "Conflicting request exists. A request for this user, system and account already exists.",
}

STATUS_MESSAGES = {
    400: "Validation failure, missing request body, or a value exceeds its maximum length.",
    401: "Not authenticated. The reason is recorded in the BeyondInsight User Audit entry.",
    403: "Access forbidden. User does not have the appropriate role or permission.",
    404: "Object not found where expected.",
    409: "Conflict. The request conflicts with the current state of the resource.",
}

ROTATE_CHOICES = (
    ("true", "Rotate on check-in"),
    ("false", "Do not rotate"),
)


class BeyondTrustPasswordSafeSecretsProvider(SecretsProvider):  # pylint: disable=abstract-method
    """Shared connection and request handling for the BeyondTrust Password Safe providers.

    Connection settings are read from `PLUGINS_CONFIG["nautobot_secrets_providers"]["beyondtrust_password_safe"]`.
    Authentication supports either an OAuth client (client_id/client_secret) or an API key with a
    run-as user (api_key/run_as).
    """

    is_available = True

    @classmethod
    def _get_config(cls, secret):
        """Return the BeyondTrust plugin settings, failing early if they are incomplete."""
        plugin_settings = settings.PLUGINS_CONFIG["nautobot_secrets_providers"]
        config = plugin_settings.get("beyondtrust_password_safe")
        if not config:
            raise exceptions.SecretProviderError(secret, cls, "BeyondTrust is not configured!")

        if not config.get("base_url"):
            raise exceptions.SecretProviderError(secret, cls, "BeyondTrust 'base_url' is required.")

        oauth = config.get("client_id") and config.get("client_secret")
        api_key = config.get("api_key") and config.get("run_as")
        if not oauth and not api_key:
            raise exceptions.SecretProviderError(
                secret,
                cls,
                "BeyondTrust needs either 'client_id' and 'client_secret', or 'api_key' and 'run_as'.",
            )

        return config

    @classmethod
    def _authenticate(cls, secret, config):
        """Build a requests session for the BeyondTrust API.

        Returns the session and whether a server-side session was created, since only the API key
        flow needs sign-in and sign-out. With an OAuth bearer token the token is sent on every
        request and no session is created, which also avoids the idle session that outlives the
        token.
        """
        session = requests.Session()
        session.verify = config.get("verify_ssl", True)
        session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

        if config.get("client_id") and config.get("client_secret"):
            response = cls._request(
                secret,
                config,
                session,
                "POST",
                "/Auth/connect/token",
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "grant_type": "client_credentials",
                },
                content_type="application/x-www-form-urlencoded",
            )
            payload = cls._payload(response)
            token = payload.get("access_token") or payload.get("AccessToken")
            if not token:
                raise exceptions.SecretProviderError(secret, cls, "BeyondTrust did not return an access token.")
            session.headers["Authorization"] = f"Bearer {token}"
            if config.get("run_as"):
                session.headers["RunAs"] = config["run_as"]
            return session, False

        session.headers["Authorization"] = f"PS-Auth key={config['api_key']}; runas={config['run_as']};"
        cls._request(secret, config, session, "POST", "/Auth/SignAppIn")
        return session, True

    @classmethod
    def _sign_out(cls, secret, config, session, session_created):
        """End the session, if one was created. A failed sign-out must not mask a value already read."""
        if not session_created:
            return
        try:
            cls._request(secret, config, session, "POST", "/Auth/Signout")
        except exceptions.SecretProviderError:
            pass

    @classmethod
    def _get_parameters(cls, secret, obj):
        """Return the secret's rendered parameters."""
        return secret.rendered_parameters(obj=obj)

    @classmethod
    def _payload(cls, response):
        """Return the response body, tolerating endpoints that answer with a bare value instead of JSON."""
        try:
            return response.json()
        except ValueError:
            return response.text

    @classmethod
    def _error_message(cls, response):
        """Return the most useful message from a BeyondTrust error response.

        Password Safe returns errors in more than one shape: a bare numeric result code (`4031`) on
        some on-prem versions, a bare JSON string (`"Password Safe Role is required"`), or a JSON
        object (`{"error": "Secret does not exist."}`) on Password Safe Cloud. Map a known numeric
        code to friendlier wording, otherwise surface the API's own text, then fall back to a
        per-status message.
        """
        code = response.text.strip().strip('"')
        if code in ERROR_MESSAGES:
            return ERROR_MESSAGES[code]

        body = cls._payload(response)
        if isinstance(body, dict):
            message = body.get("error") or body.get("Message") or body.get("ErrorMessage") or ""
        elif isinstance(body, str):
            message = body
        else:
            message = ""
        return message.strip() or STATUS_MESSAGES.get(response.status_code) or response.text

    @classmethod
    def _request(  # pylint: disable=too-many-arguments,too-many-locals
        cls,
        secret,
        config,
        session,
        method,
        path,
        data=None,
        params=None,
        content_type="application/json",
        expected_status=(200,),
    ):
        """Make an API call to BeyondTrust, mapping its error codes onto Nautobot secret exceptions."""
        url = f"{config['base_url'].rstrip('/')}{path}"
        timeout = config.get("timeout", 30)
        headers = dict(session.headers)
        if content_type != "application/json":
            headers["Content-Type"] = content_type

        params = dict(params or {})
        params.setdefault("version", API_VERSION)

        try:
            kwargs = {"headers": headers, "timeout": timeout, "params": params}
            if data is not None:
                if content_type == "application/json":
                    kwargs["json"] = data
                else:
                    kwargs["data"] = data
            response = session.request(method, url, **kwargs)
        except requests.RequestException as err:
            raise exceptions.SecretProviderError(secret, cls, f"Could not connect to BeyondTrust: {err}") from err

        if response.status_code not in expected_status:
            raise exceptions.SecretProviderError(
                secret, cls, f"BeyondTrust API error [{response.status_code}]: {cls._error_message(response)}"
            )

        return response


class BeyondTrustPasswordSafeManagedAccountSecretsProvider(BeyondTrustPasswordSafeSecretsProvider):
    """Secrets provider for BeyondTrust Password Safe managed accounts.

    Managed accounts are not read directly. A credentials release request is created for the
    managed account, and the credential is returned for that request. Checking the request back in
    is what triggers password rotation, so `check_in()` is exposed separately for jobs that need
    the rotation to happen once the credential has been used.
    """

    slug = "beyondtrust-password-safe-managed-account"
    name = "BeyondTrust Password Safe - Managed Account"
    description = "Retrieve a managed account credential from BeyondTrust Password Safe through a release request."

    class ParametersForm(BootstrapMixin, forms.Form):
        """Parameters identifying the managed account to release.

        All fields are string-valued so that Jinja2 templating against the context object
        (`{{ obj.name }}`) works, as it does for the other providers in this app.
        """

        system_name = forms.CharField(
            required=True,
            max_length=200,
            help_text="Name of the managed system (asset) holding the account.",
        )
        account_name = forms.CharField(
            required=True,
            max_length=200,
            help_text="Name of the managed account on that system.",
        )
        duration_minutes = forms.CharField(
            required=False,
            initial="5",
            max_length=4,
            help_text="How long the release request stays open, in minutes. Defaults to 5.",
        )
        rotate_on_checkin = forms.ChoiceField(
            required=False,
            choices=ROTATE_CHOICES,
            initial="false",
            help_text=(
                "Ask Password Safe to rotate the password when the request is checked in. "
                "Defaults to false, so a plain read does not rotate."
            ),
        )
        reason = forms.CharField(
            required=False,
            max_length=200,
            help_text="Reason recorded on the release request. Defaults to 'Nautobot secrets provider'.",
        )

    @classmethod
    def release(cls, secret, obj=None):
        """Create a credentials release request for the managed account and return its request ID."""
        config, session, parameters, account, session_created = cls._prepare(secret, obj)
        try:
            return cls._create_request(secret, config, session, account, parameters)
        finally:
            cls._sign_out(secret, config, session, session_created)

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the credential released for the managed account described by the secret's parameters."""
        config, session, parameters, account, session_created = cls._prepare(secret, obj)
        try:
            request_id = cls._create_request(secret, config, session, account, parameters)
            credential = cls._get_credential(secret, config, session, request_id)

            if credential is None:
                raise exceptions.SecretValueNotFoundError(
                    secret,
                    cls,
                    f"No credential available for managed account '{parameters['account_name']}' "
                    f"on system '{parameters['system_name']}'.",
                )
            return credential
        finally:
            cls._sign_out(secret, config, session, session_created)

    @classmethod
    def check_in(cls, secret, request_id, reason=""):
        """Check a release request back in, which triggers password rotation.

        Called separately from `get_value_for_secret()` so that a job can use the credential first
        and then return it, rather than rotating on every read.
        """
        config = cls._get_config(secret)
        session, session_created = cls._authenticate(secret, config)
        try:
            return cls._request(
                secret,
                config,
                session,
                "PUT",
                f"/Requests/{request_id}/Checkin",
                data={"Reason": reason},
                expected_status=(200, 204),
            )
        finally:
            cls._sign_out(secret, config, session, session_created)

    @classmethod
    def _prepare(cls, secret, obj):
        """Resolve config, parameters, an authenticated session and the managed account."""
        config = cls._get_config(secret)
        parameters = cls._get_parameters(secret, obj)
        session, session_created = cls._authenticate(secret, config)
        account = cls._find_account(secret, config, session, parameters["system_name"], parameters["account_name"])
        return config, session, parameters, account, session_created

    @classmethod
    def _get_parameters(cls, secret, obj):
        """Return the secret's rendered parameters, failing early if the account is not identified."""
        parameters = super()._get_parameters(secret, obj)
        if not parameters.get("system_name") or not parameters.get("account_name"):
            raise exceptions.SecretParametersError(
                secret, cls, "The 'system_name' and 'account_name' parameters are required."
            )
        return parameters

    @classmethod
    def _find_account(cls, secret, config, session, system_name, account_name):
        """Return the managed account matching the system and account names."""
        payload = cls._payload(
            cls._request(
                secret,
                config,
                session,
                "GET",
                "/ManagedAccounts",
                params={"systemName": system_name, "accountName": account_name},
            )
        )
        # The filtered endpoint may answer with a single account object or a list of them.
        if isinstance(payload, dict):
            accounts = payload.get("Data") or payload.get("Results") or [payload]
        else:
            accounts = payload
        for account in accounts:
            if account.get("SystemName") == system_name and account.get("AccountName") == account_name:
                return account

        raise exceptions.SecretValueNotFoundError(
            secret, cls, f"Managed account '{account_name}' not found on system '{system_name}'."
        )

    @classmethod
    def _create_request(cls, secret, config, session, account, parameters):
        """Create a credentials release request and return its request ID."""
        duration = parameters.get("duration_minutes") or "5"
        try:
            duration_minutes = int(duration)
        except ValueError as err:
            raise exceptions.SecretParametersError(
                secret, cls, f"'duration_minutes' is not a number: {duration}"
            ) from err

        data = {
            "SystemId": account.get("SystemId"),
            "AccountId": account.get("AccountId"),
            "DurationMinutes": duration_minutes,
            "Reason": parameters.get("reason") or "Nautobot secrets provider",
            "ConflictOption": "reuse",
        }
        if str(parameters.get("rotate_on_checkin", "false")).lower() == "true":
            data["RotateOnCheckin"] = True

        response = cls._request(secret, config, session, "POST", "/requests", data=data, expected_status=(200, 201))
        payload = cls._payload(response)
        request_id = payload.get("RequestID") if isinstance(payload, dict) else payload
        if not request_id:
            raise exceptions.SecretValueNotFoundError(secret, cls, "BeyondTrust did not return a request ID.")
        return request_id

    @classmethod
    def _get_credential(cls, secret, config, session, request_id):
        """Return the credential for an approved release request, as a string.

        Some BeyondTrust responses answer with a bare value rather than a JSON object, so an
        all-digit password arrives as an `int` and a null as `None`. Coerce any non-null value to a
        string so callers always receive text.
        """
        payload = cls._payload(cls._request(secret, config, session, "GET", f"/credentials/{request_id}"))
        if isinstance(payload, dict):
            value = payload.get("Password") or payload.get("Credential")
        else:
            value = payload
        return None if value is None else str(value)


class BeyondTrustPasswordSafeSecretsSafeSecretsProvider(BeyondTrustPasswordSafeSecretsProvider):
    """Secrets provider for BeyondTrust Secrets Safe.

    Secrets Safe holds stored secrets (Text or Credential), read by folder path and title, or by secret
    ID. This is a plain lookup and read - no request lifecycle, so nothing is checked in and nothing is
    rotated. File secrets are not supported.
    """

    slug = "beyondtrust-password-safe-secrets-safe"
    name = "BeyondTrust Password Safe - Secrets Safe"
    description = (
        "Read a Text or Credential secret from BeyondTrust Secrets Safe by folder path and title, or by secret ID."
    )

    class ParametersForm(BootstrapMixin, forms.Form):
        """Parameters identifying the Secrets Safe secret to read.

        All fields are string-valued so that Jinja2 templating against the context object
        (`{{ obj.name }}`) works, as it does for the other providers in this app.
        """

        folder_path = forms.CharField(
            required=False,
            max_length=200,
            help_text=(
                "Secrets Safe folder path, for example 'IT/Platform'. Matched ignoring surrounding slashes "
                "and case. Required unless 'secret_id' is set."
            ),
        )
        title = forms.CharField(
            required=False,
            max_length=200,
            help_text="Secret title inside the folder. Required unless 'secret_id' is set.",
        )
        secret_id = forms.CharField(
            required=False,
            max_length=36,
            help_text="Secrets Safe secret ID (a UUID), for a direct lookup instead of a path and title search.",
        )

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Return the value of the Secrets Safe secret described by the secret's parameters."""
        config = cls._get_config(secret)
        parameters = cls._get_parameters(secret, obj)
        if not parameters.get("secret_id") and not (parameters.get("folder_path") and parameters.get("title")):
            raise exceptions.SecretParametersError(
                secret, cls, "Provide 'secret_id', or both 'folder_path' and 'title'."
            )

        session, session_created = cls._authenticate(secret, config)
        try:
            entry = cls._find_secret(secret, config, session, parameters)
            return cls._extract_value(secret, entry)
        finally:
            cls._sign_out(secret, config, session, session_created)

    @staticmethod
    def _normalize_folder_path(path):
        """Normalize a Secrets Safe folder path for comparison, ignoring surrounding slashes and case."""
        return (path or "").strip("/").casefold()

    @classmethod
    def _find_secret(cls, secret, config, session, parameters):
        """Return the Secrets Safe entry, by ID or by folder path and title."""
        if parameters.get("secret_id"):
            payload = cls._payload(
                cls._request(secret, config, session, "GET", f"/Secrets-Safe/Secrets/{parameters['secret_id']}")
            )
            if isinstance(payload, dict) and payload.get("Id"):
                return payload
            raise exceptions.SecretValueNotFoundError(
                secret, cls, f"Secrets Safe secret '{parameters['secret_id']}' not found."
            )

        folder_path = cls._normalize_folder_path(parameters["folder_path"])
        title = parameters["title"]
        for entry in cls._list_secrets(secret, config, session, parameters["folder_path"], title):
            if cls._normalize_folder_path(entry.get("FolderPath")) == folder_path and entry.get("Title") == title:
                return entry

        raise exceptions.SecretValueNotFoundError(
            secret, cls, f"Secrets Safe secret '{parameters['title']}' not found in '{parameters['folder_path']}'."
        )

    @classmethod
    def _list_secrets(cls, secret, config, session, folder_path, title):
        """Return the matching secrets, paging past the default limit of 1000.

        `Decrypt` is required for the value to be returned at all - without it the model comes back
        with metadata only and a null `Password` or `Text`.
        """
        page_size = config.get("page_size", 1000)
        offset = 0
        results = []
        while True:
            payload = cls._payload(
                cls._request(
                    secret,
                    config,
                    session,
                    "GET",
                    "/Secrets-Safe/Secrets",
                    params={
                        "Path": folder_path,
                        "Title": title,
                        "Decrypt": "true",
                        "Limit": page_size,
                        "Offset": offset,
                    },
                )
            )
            page = payload.get("Data", []) if isinstance(payload, dict) else payload
            results.extend(page)
            if len(page) < page_size:
                return results
            offset += page_size

    @classmethod
    def _extract_value(cls, secret, entry):
        """Return the secret value, which is held in different fields depending on the secret type."""
        entry_type = entry.get("SecretType")
        if entry_type == "File":
            raise exceptions.SecretParametersError(secret, cls, "File secrets are not supported by this provider.")

        value = entry.get("Password") or entry.get("Text")
        if value:
            return value

        title = entry.get("Title") or entry.get("Id")
        if entry.get("TotpEnabled"):
            raise exceptions.SecretValueNotFoundError(
                secret,
                cls,
                f"Secrets Safe secret '{title}' is TOTP-enabled; its one-time code must be read from the "
                f"'Secrets-Safe/Secrets/{entry.get('Id')}/totp-code' endpoint, which this provider does not use.",
            )
        raise exceptions.SecretValueNotFoundError(secret, cls, f"No value for Secrets Safe secret '{title}'.")
