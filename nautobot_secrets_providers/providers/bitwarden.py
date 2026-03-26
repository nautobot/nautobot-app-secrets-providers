"""Bitwarden CLI secrets provider backed by bw serve REST endpoints."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import requests
import urllib3
from django import forms
from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe
from nautobot.apps.forms import BootstrapMixin
from nautobot.apps.secrets import SecretsProvider
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.secrets import exceptions

REQUEST_TIMEOUT = 15

DEFAULT_BITWARDEN_FIELDS = [
    {"name": "username", "label": "Username"},
    {"name": "password", "label": "Password"},
    {"name": "totp", "label": "TOTP"},
    {"name": "uri", "label": "URI (first)"},
    {"name": "notes", "label": "Notes"},
    {"name": "custom", "label": "Custom Field"},
    {"name": "ssh_private_key", "label": "SSH Private Key"},
    {"name": "ssh_public_key", "label": "SSH Public Key"},
    {"name": "ssh_key_fingerprint", "label": "SSH Key Fingerprint"},
    {"name": "identity_title", "label": "Identity Title"},
    {"name": "identity_firstName", "label": "Identity First Name"},
    {"name": "identity_middleName", "label": "Identity Middle Name"},
    {"name": "identity_lastName", "label": "Identity Last Name"},
    {"name": "identity_address1", "label": "Identity Address 1"},
    {"name": "identity_address2", "label": "Identity Address 2"},
    {"name": "identity_address3", "label": "Identity Address 3"},
    {"name": "identity_city", "label": "Identity City"},
    {"name": "identity_state", "label": "Identity State"},
    {"name": "identity_postalCode", "label": "Identity Postal Code"},
    {"name": "identity_country", "label": "Identity Country"},
    {"name": "identity_company", "label": "Identity Company"},
    {"name": "identity_email", "label": "Identity Email"},
    {"name": "identity_phone", "label": "Identity Phone"},
    {"name": "identity_ssn", "label": "Identity SSN"},
    {"name": "identity_username", "label": "Identity Username"},
    {"name": "identity_passportNumber", "label": "Identity Passport Number"},
    {"name": "identity_licenseNumber", "label": "Identity License Number"},
    {"name": "card_cardholderName", "label": "Card Holder Name"},
    {"name": "card_brand", "label": "Card Brand"},
    {"name": "card_number", "label": "Card Number"},
    {"name": "card_expMonth", "label": "Card Expiry Month"},
    {"name": "card_expYear", "label": "Card Expiry Year"},
    {"name": "card_code", "label": "Card Security Code"},
]

# Fields for entry types that have nested structures in the API response.
# The key is the secret_field value and the value is the path within the item data.
SSHKEY_FIELDS = {
    "ssh_private_key": "privateKey",
    "ssh_public_key": "publicKey",
    "ssh_key_fingerprint": "kexFingerprint",
}

IDENTITY_FIELDS = {
    "identity_title": "title",
    "identity_firstName": "firstName",
    "identity_middleName": "middleName",
    "identity_lastName": "lastName",
    "identity_address1": "address1",
    "identity_address2": "address2",
    "identity_address3": "address3",
    "identity_city": "city",
    "identity_state": "state",
    "identity_postalCode": "postalCode",
    "identity_country": "country",
    "identity_company": "company",
    "identity_email": "email",
    "identity_phone": "phone",
    "identity_ssn": "ssn",
    "identity_username": "username",
    "identity_passportNumber": "passportNumber",
    "identity_licenseNumber": "licenseNumber",
}

CARD_FIELDS = {
    "card_cardholderName": "cardholderName",
    "card_brand": "brand",
    "card_number": "number",
    "card_expMonth": "expMonth",
    "card_expYear": "expYear",
    "card_code": "code",
}

LOGIN_FIELDS = {
    "username": "username",
    "password": "password",
    "fido2Credentials": "fido2Credentials",
    "totp": "totp",
    "uri": "login.uris[0].uri",
}


_BITWARDEN_FETCH_JS = """\
(function () {
    var customInput = document.getElementById('id_custom_field_name');
    if (!customInput) { return; }
    var secretIdInput = document.getElementById('id_secret_id');
    var secretFieldSelect = document.getElementById('id_secret_field');
    var fetchBtn = document.getElementById('bw-fetch-fields-btn');
    var suggestionsDiv = document.getElementById('bw-field-suggestions');
    var fieldList = document.getElementById('bw-field-list');
    var errorDiv = document.getElementById('bw-fetch-error');
    if (!secretIdInput || !secretFieldSelect || !fetchBtn) { return; }
    var fetchUrl = fetchBtn.getAttribute('data-url');
    function setCustomFieldState() {
        var isCustom = secretFieldSelect.value === 'custom';
        customInput.disabled = !isCustom;
        customInput.style.opacity = isCustom ? '1' : '0.5';
        customInput.placeholder = isCustom ? '' : 'Activate Custom field selection to specify this value';
    }
    function setButtonVisibility() {
        var hasId = secretIdInput.value.trim().length > 0;
        fetchBtn.style.display = hasId ? '' : 'none';
        if (!hasId) {
            suggestionsDiv.style.display = 'none';
            errorDiv.style.display = 'none';
        }
    }
    secretFieldSelect.addEventListener('change', setCustomFieldState);
    secretIdInput.addEventListener('input', setButtonVisibility);
    fetchBtn.addEventListener('click', function () {
        var secretId = secretIdInput.value.trim();
        if (!secretId) { return; }
        fetchBtn.disabled = true;
        fetchBtn.textContent = 'Fetching...';
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
        suggestionsDiv.style.display = 'none';
        fetch(fetchUrl + '?secret_id=' + encodeURIComponent(secretId), {
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(function (r) {
            return r.json();
        }).then(function (data) {
            fetchBtn.disabled = false;
            fetchBtn.textContent = 'Fetch Fields from Bitwarden';
            if (data.success && data.fields && data.fields.length > 0) {
                fieldList.innerHTML = '';
                data.fields.forEach(function (fname) {
                    var b = document.createElement('button');
                    b.type = 'button';
                    b.className = 'btn btn-xs btn-default';
                    b.style.cssText = 'margin:2px;';
                    b.textContent = fname;
                    b.addEventListener('click', function () { customInput.value = fname; });
                    fieldList.appendChild(b);
                });
                suggestionsDiv.style.display = '';
            } else if (data.success) {
                errorDiv.textContent = 'No custom fields found on this Bitwarden item.';
                errorDiv.style.display = '';
            } else {
                errorDiv.textContent = data.error || 'Could not fetch Bitwarden custom fields.';
                errorDiv.style.display = '';
            }
        }).catch(function (err) {
            fetchBtn.disabled = false;
            fetchBtn.textContent = 'Fetch Fields from Bitwarden';
            errorDiv.textContent = 'Request failed: ' + err.message;
            errorDiv.style.display = '';
        });
    });
    setCustomFieldState();
    setButtonVisibility();
}());
"""


class BitwardenCustomFieldNameWidget(forms.TextInput):
    """Text input widget for `custom_field_name` with a Bitwarden field-fetch button."""

    def render(self, name, value, attrs=None, renderer=None):
        """Render the input together with the suggestion button and inline JavaScript."""
        input_html = super().render(name, value, attrs, renderer)
        try:
            fetch_url = reverse("plugins:nautobot_secrets_providers:bitwarden_custom_fields")
        except NoReverseMatch:
            fetch_url = ""
        wrapper = (
            '<div style="margin-top:4px;">'
            '<button type="button" id="bw-fetch-fields-btn"'
            ' class="btn btn-default btn-sm" style="display:none;"'
            f' data-url="{fetch_url}">Fetch Fields from Bitwarden</button>'
            '<div id="bw-field-suggestions" style="display:none;margin-top:6px;">'
            '<small class="text-muted">Click a field name to copy it above:</small>'
            '<div id="bw-field-list" style="margin-top:4px;"></div>'
            "</div>"
            '<div id="bw-fetch-error" class="text-danger"'
            ' style="display:none;margin-top:4px;"></div>'
            "</div>"
        )
        return mark_safe(str(input_html) + wrapper + "<script>" + _BITWARDEN_FETCH_JS + "</script>")  # noqa: S308


class BitwardenCLISecretsProvider(SecretsProvider):
    """Secrets provider for Bitwarden CLI `bw serve` API."""

    slug = "bitwarden-cli"
    name = "Bitwarden CLI"
    is_available = True

    # TBD: Remove after pylint-nautobot bump
    # pylint: disable-next=nb-incorrect-base-class
    class ParametersForm(BootstrapMixin, forms.Form):
        """Required parameters for Bitwarden CLI."""

        secret_id = forms.CharField(
            required=True,
            help_text="The Bitwarden item UUID.",
        )
        secret_field = forms.ChoiceField(  # noqa: S105
            required=True,
            help_text="The field name to retrieve.",
        )
        custom_field_name = forms.CharField(
            required=False,
            help_text="Custom field name when secret_field is 'custom'.",
        )

        def __init__(self, *args, **kwargs):
            """Dynamically populate the secret_field choices from plugin settings."""
            super().__init__(*args, **kwargs)
            self.fields["secret_field"].choices = BitwardenCLISecretsProvider.get_field_choices()
            self.fields["custom_field_name"].widget = BitwardenCustomFieldNameWidget()

        def clean(self):
            """Validate that required fields are present based on the selected secret_field."""
            cleaned_data = super().clean()
            secret_field = cleaned_data.get("secret_field")  # noqa: S105
            custom_field_name = cleaned_data.get("custom_field_name")

            if secret_field == "custom" and not custom_field_name:  # noqa: S105
                raise forms.ValidationError({"custom_field_name": "Custom field name is required for 'custom'."})

            return cleaned_data

    @classmethod
    def _require_enabled(cls, secret) -> None:
        """Ensure the Bitwarden CLI provider is enabled.

        Raises a `SecretProviderError` when the provider is disabled. This
        protects secret retrieval paths when the feature is intentionally
        turned off in the environment.
        """
        if not is_truthy(os.getenv("NAUTOBOT_BITWARDEN_CLI_ENABLED", "false")):
            raise exceptions.SecretProviderError(secret, cls, "Bitwarden CLI provider is disabled.")

    @staticmethod
    def _plugin_settings() -> dict[str, Any]:
        """Return provider-specific configuration from `PLUGINS_CONFIG`.

        This helper centralizes reading the plugin configuration so callers can
        obtain configured values or fall back to environment variables.
        """
        plugin_config = settings.PLUGINS_CONFIG.get("nautobot_secrets_providers", {})
        return plugin_config.get("bitwarden", {})

    @classmethod
    def get_field_choices(cls) -> list[tuple[str, str]]:
        """Return selectable Bitwarden field choices for the UI.

        Returns a list of `(value, label)` tuples derived from configured
        `BITWARDEN_FIELDS` or the built-in defaults.
        """
        configured_fields = cls._plugin_settings().get("BITWARDEN_FIELDS", DEFAULT_BITWARDEN_FIELDS)
        choices = []
        for field in configured_fields:
            name = field.get("name")
            label = field.get("label")
            if name and label:
                choices.append((name, label))
        if not choices:
            choices = [(field["name"], field["label"]) for field in DEFAULT_BITWARDEN_FIELDS]
        return choices

    @classmethod
    def _load_env_settings(cls, secret) -> tuple[str, str, str]:
        """Return configured Bitwarden CLI credentials and validate presence.

        Reads `base_url`, `username` and `password` from plugin settings or
        environment variables and raises `SecretProviderError` listing missing
        variables when called in the context of a secret operation.
        """
        base_url, username, password = cls._get_credentials()

        missing = [
            name
            for name, value in [
                ("BW_CLI_URL", base_url),
                ("BW_CLI_USER", username),
                ("BW_CLI_PASSWORD", password),
            ]
            if not value
        ]
        if missing:
            raise exceptions.SecretProviderError(
                secret, cls, f"Missing required environment variable(s): {', '.join(missing)}"
            )

        return str(base_url), str(username), str(password)

    @classmethod
    def _get_credentials(cls) -> tuple[Any, Any, Any]:
        """Return raw credential values from plugin settings or environment.

        This helper returns the configured values or `None`-like values if not
        present. Callers are responsible for validating presence and raising an
        appropriate error type for their context.
        """
        plugin_settings = cls._plugin_settings()
        base_url = plugin_settings.get("base_url") or os.getenv("BW_CLI_URL")
        username = plugin_settings.get("username") or os.getenv("BW_CLI_USER")
        password = plugin_settings.get("password") or os.getenv("BW_CLI_PASSWORD")
        return base_url, username, password

    @classmethod
    def _load_tls_settings(cls):
        """Return TLS verification setting used by `requests`.

        The return value is either a boolean (True/False) or a string path to a
        CA bundle file suitable for passing directly to `requests.get(..., verify=...)`.
        The caller should validate that a provided file path exists and raise an
        appropriate error type for its context.
        """
        plugin_settings = cls._plugin_settings()
        ca_bundle_path = plugin_settings.get("ca_bundle_path") or os.getenv("BW_CLI_CA_BUNDLE")
        if ca_bundle_path:
            return str(ca_bundle_path)

        verify_ssl_setting = plugin_settings.get("verify_ssl")
        if verify_ssl_setting is None:
            verify_ssl_setting = os.getenv("BW_CLI_VERIFY_SSL", "true")
        return is_truthy(verify_ssl_setting)

    @staticmethod
    def _read_parameters(secret, obj=None) -> tuple[str, str, str]:
        """Read and validate parameters from the `Secret` instance.

        Returns a tuple of `(secret_id, secret_field, custom_field_name)` and
        raises `SecretParametersError` when expected parameters are missing.
        """
        parameters = secret.rendered_parameters(obj=obj)
        try:
            secret_id = parameters["secret_id"]
            secret_field = parameters["secret_field"]
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, BitwardenCLISecretsProvider, msg) from err

        custom_field_name = parameters.get("custom_field_name", "")
        return secret_id, secret_field, custom_field_name

    @classmethod
    def _fetch_item(cls, secret, secret_id: str) -> dict[str, Any]:
        """Fetch the raw Bitwarden item JSON from the CLI server.

        Credentials are loaded via `_get_credentials()` so callers do not need
        to pass them explicitly. The method validates the `secret_id` format
        and TLS settings. On network, TLS, or response errors a
        `SecretProviderError` is raised with a user-facing message.
        """
        # Basic validation to avoid path-injection and ensure reasonable format
        if not isinstance(secret_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", secret_id):
            raise exceptions.SecretProviderError(secret, cls, "Invalid secret_id format.")

        base_url, username, password = cls._get_credentials()
        missing = [
            name
            for name, value in [
                ("BW_CLI_URL", base_url),
                ("BW_CLI_USER", username),
                ("BW_CLI_PASSWORD", password),
            ]
            if not value
        ]
        if missing:
            raise exceptions.SecretProviderError(
                secret, cls, f"Missing required Bitwarden configuration: {', '.join(missing)}"
            )

        url = f"{str(base_url).rstrip('/')}/object/item/{secret_id}"
        verify = cls._load_tls_settings()

        # If a CA bundle path is returned, ensure the file exists before use.
        if isinstance(verify, str):
            if not Path(verify).exists():
                raise exceptions.SecretProviderError(secret, cls, f"CA bundle not found at: {verify}")

        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            response = requests.get(url, auth=(str(username), str(password)), timeout=REQUEST_TIMEOUT, verify=verify)
        except requests.exceptions.SSLError as err:
            raise exceptions.SecretProviderError(
                secret,
                cls,
                "Unable to verify the Bitwarden CLI TLS certificate. "
                "Set BW_CLI_CA_BUNDLE to a trusted CA bundle path or set BW_CLI_VERIFY_SSL=false for development.",
            ) from err
        except requests.RequestException as err:  # pragma: no cover - network error path
            raise exceptions.SecretProviderError(secret, cls, f"Unable to reach Bitwarden CLI server: {err}") from err

        if response.status_code != 200:
            raise exceptions.SecretProviderError(
                secret,
                cls,
                f"Bitwarden CLI returned {response.status_code}: {response.text}",
            )

        try:
            payload = response.json()
        except ValueError as err:
            raise exceptions.SecretProviderError(secret, cls, "Bitwarden CLI returned invalid JSON.") from err

        if not payload.get("success"):
            message = payload.get("message") or "Bitwarden CLI reported failure."
            raise exceptions.SecretProviderError(secret, cls, message)

        return payload.get("data") or {}

    @staticmethod
    def _read_nested(data: dict[str, Any], path: str) -> Any:
        """Read a dotted-path from nested dictionaries.

        Returns the nested value or `None` when any intermediate path segment
        does not exist or the structure is not a mapping.
        """
        value: Any = data
        for part in path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _extract_custom_field(cls, secret, data: dict[str, Any], custom_field_name: str) -> str:
        """Return the value for a custom field name from an item.

        Raises `SecretValueNotFoundError` when the named custom field does not
        exist or has no value.
        """
        fields = data.get("fields") or []
        for field in fields:
            if field.get("name") == custom_field_name:
                value = field.get("value")
                if value is None:
                    break
                return str(value)
        raise exceptions.SecretValueNotFoundError(secret, cls, f"Custom field '{custom_field_name}' not found.")

    @classmethod
    def _extract_uri(cls, _secret, data: dict[str, Any]) -> Any:
        """Return the primary URI value from an item's login data.

        Raises `SecretValueNotFoundError` when no URIs are present.
        """
        uris = cls._read_nested(data, "login.uris") or []
        if not uris:
            raise exceptions.SecretValueNotFoundError(_secret, cls, "The Bitwarden item has no URIs.")
        return uris[0].get("uri")

    @classmethod
    def _extract_ssh_field(cls, _secret, data: dict[str, Any], secret_field: str) -> Any:
        """Return SSH key related fields from an item, validating presence."""
        ssh_key = data.get("sshKey")
        if not ssh_key:
            raise exceptions.SecretValueNotFoundError(_secret, cls, "The Bitwarden item has no SSH key data.")
        return ssh_key.get(SSHKEY_FIELDS[secret_field])

    @classmethod
    def _extract_login_field(cls, _secret, data: dict[str, Any], secret_field: str) -> Any:
        """Return a mapped login field (username/password/totp/uri)."""
        return cls._read_nested(data, f"login.{LOGIN_FIELDS[secret_field]}")

    @classmethod
    def _extract_identity_field(cls, _secret, data: dict[str, Any], secret_field: str) -> Any:
        """Return a mapped identity attribute from an item, validating presence."""
        identity = data.get("identity")
        if not identity:
            raise exceptions.SecretValueNotFoundError(_secret, cls, "The Bitwarden item has no identity data.")
        return identity.get(IDENTITY_FIELDS[secret_field])

    @classmethod
    def _extract_card_field(cls, _secret, data: dict[str, Any], secret_field: str) -> Any:
        """Return a mapped card attribute from an item, validating presence."""
        card = data.get("card")
        if not card:
            raise exceptions.SecretValueNotFoundError(_secret, cls, "The Bitwarden item has no card data.")
        return card.get(CARD_FIELDS[secret_field])

    @classmethod
    def _extract_generic(cls, _secret, data: dict[str, Any], secret_field: str) -> Any:
        """Return either a dotted-path nested value or a top-level field value."""
        if "." in secret_field:
            return cls._read_nested(data, secret_field)
        return data.get(secret_field)

    @classmethod
    def _extract_field(cls, secret, data: dict[str, Any], secret_field: str, custom_field_name: str) -> str:  # noqa: S105
        """Return the requested value from item data for a logical field.

        Delegates detailed extraction to smaller helpers to keep branching low
        in this dispatching function. Raises `SecretValueNotFoundError` when
        the target value cannot be located.
        """
        if secret_field == "custom":  # noqa: S105
            return cls._extract_custom_field(secret, data, custom_field_name)

        if secret_field.startswith("custom."):  # noqa: S105
            return cls._extract_custom_field(secret, data, secret_field.split("custom.", maxsplit=1)[1])

        if secret_field == "notes":  # noqa: S105
            value = data.get("notes")
        elif secret_field == "uri":  # noqa: S105
            value = cls._extract_uri(secret, data)
        elif secret_field in SSHKEY_FIELDS:
            value = cls._extract_ssh_field(secret, data, secret_field)
        elif secret_field in LOGIN_FIELDS:
            value = cls._extract_login_field(secret, data, secret_field)
        elif secret_field in IDENTITY_FIELDS:
            value = cls._extract_identity_field(secret, data, secret_field)
        elif secret_field in CARD_FIELDS:
            value = cls._extract_card_field(secret, data, secret_field)
        else:
            value = cls._extract_generic(secret, data, secret_field)

        if value is None:
            raise exceptions.SecretValueNotFoundError(
                secret, cls, f"The field '{secret_field}' is not set on the Bitwarden item."
            )

        return str(value)

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Retrieve and return the configured secret value for a Nautobot Secret.

        This is the primary entry point used by Nautobot when resolving a
        Secret's value. It validates the provider is enabled, reads required
        parameters from the Secret instance, fetches the Bitwarden item and
        extracts the requested field.
        """
        _ = kwargs
        cls._require_enabled(secret)
        secret_id, secret_field, custom_field_name = cls._read_parameters(secret, obj=obj)
        item_data = cls._fetch_item(secret, secret_id)
        return cls._extract_field(secret, item_data, secret_field, custom_field_name)

    @classmethod
    def get_custom_field_names(cls, secret_id: str) -> list[str]:
        """Return custom field names for the provided Bitwarden item ID.

        This helper is intended for UI usage (e.g. to populate suggestions) and
        raises `ValueError` with a clear, user-facing message on failure.
        """
        base_url, username, password = cls._get_credentials()

        missing = [
            name
            for name, value in [
                ("BW_CLI_URL", base_url),
                ("BW_CLI_USER", username),
                ("BW_CLI_PASSWORD", password),
            ]
            if not value
        ]
        if missing:
            raise ValueError(f"Missing Bitwarden configuration: {', '.join(missing)}")

        # Very small safety check for the provided secret ID to reduce risk of
        # accidental path traversal in downstream services.
        if not isinstance(secret_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", secret_id):
            raise ValueError("Invalid secret_id format.")

        url = f"{str(base_url).rstrip('/')}/object/item/{secret_id}"
        verify = cls._load_tls_settings()

        # If a CA bundle path is provided, ensure the file exists before use.
        if isinstance(verify, str) and not Path(verify).exists():
            raise ValueError(f"CA bundle not found at: {verify}")

        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            response = requests.get(url, auth=(str(username), str(password)), timeout=REQUEST_TIMEOUT, verify=verify)
        except requests.RequestException as err:
            raise ValueError(f"Unable to reach Bitwarden CLI server: {err}") from err
        if response.status_code != 200:
            raise ValueError(
                f"Bitwarden CLI responded with HTTP {response.status_code}; verify item ID, wait for bw server to sync, and check server logs for details."
            )
        try:
            payload = response.json()
        except ValueError as err:
            raise ValueError("Bitwarden CLI returned invalid JSON.") from err
        if not payload.get("success"):
            message = payload.get("message") or "Bitwarden CLI reported failure."
            raise ValueError(message)
        data = payload.get("data") or {}
        fields = data.get("fields") or []
        return [item["name"] for item in fields if item.get("name")]
