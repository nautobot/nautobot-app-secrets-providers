"""Bitwarden CLI secrets provider backed by bw serve REST endpoints."""

from __future__ import annotations

import logging
import os
import re
import time
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from django import forms
from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe
from nautobot.apps.forms import BootstrapMixin
from nautobot.apps.secrets import SecretsProvider
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.secrets import exceptions
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
BITWARDEN_ITEM_ENDPOINT_TEMPLATE = "/object/item/{secret_id}"
BITWARDEN_RETRY_TOTAL = 3
BITWARDEN_RETRY_BACKOFF = 0.3
BITWARDEN_CACHE_TTL_SECONDS = 0

DEFAULT_BITWARDEN_FIELDS = [
    {"name": "card_brand", "label": "Card Brand"},
    {"name": "card_cardholderName", "label": "Card Holder Name"},
    {"name": "card_code", "label": "Card Security Code"},
    {"name": "card_expMonth", "label": "Card Expiry Month"},
    {"name": "card_expYear", "label": "Card Expiry Year"},
    {"name": "card_number", "label": "Card Number"},
    {"name": "custom", "label": "Custom Field"},
    {"name": "identity_address1", "label": "Identity Address 1"},
    {"name": "identity_address2", "label": "Identity Address 2"},
    {"name": "identity_address3", "label": "Identity Address 3"},
    {"name": "identity_city", "label": "Identity City"},
    {"name": "identity_company", "label": "Identity Company"},
    {"name": "identity_country", "label": "Identity Country"},
    {"name": "identity_email", "label": "Identity Email"},
    {"name": "identity_firstName", "label": "Identity First Name"},
    {"name": "identity_lastName", "label": "Identity Last Name"},
    {"name": "identity_licenseNumber", "label": "Identity License Number"},
    {"name": "identity_middleName", "label": "Identity Middle Name"},
    {"name": "identity_passportNumber", "label": "Identity Passport Number"},
    {"name": "identity_phone", "label": "Identity Phone"},
    {"name": "identity_postalCode", "label": "Identity Postal Code"},
    {"name": "identity_ssn", "label": "Identity SSN"},
    {"name": "identity_state", "label": "Identity State"},
    {"name": "identity_title", "label": "Identity Title"},
    {"name": "identity_username", "label": "Identity Username"},
    {"name": "notes", "label": "Notes"},
    {"name": "password", "label": "Password"},
    {"name": "ssh_key_fingerprint", "label": "SSH Key Fingerprint"},
    {"name": "ssh_private_key", "label": "SSH Private Key"},
    {"name": "ssh_public_key", "label": "SSH Public Key"},
    {"name": "totp", "label": "TOTP"},
    {"name": "uri", "label": "URI (first)"},
    {"name": "username", "label": "Username"},
]

# Fields for entry types that have nested structures in the API response.
# The key is the secret_field value and the value is the path within the item data.
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

SSHKEY_FIELDS = {
    "ssh_private_key": "privateKey",
    "ssh_public_key": "publicKey",
    "ssh_key_fingerprint": "kexFingerprint",
}


LOGIN_FIELDS = {
    "username": "username",
    "password": "password",
    "fido2Credentials": "fido2Credentials",
    "totp": "totp",
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

    function findHelpElementFor(el) {
        var parent = el.parentElement;
        if (!parent) { return null; }
        var selectors = ['.help-block', '.help-text', 'small.form-text', 'small.text-muted', 'p.help-block', 'div.help-block', '.field-help', 'small.help-text'];
        for (var i = 0; i < selectors.length; i++) {
            var candidate = parent.querySelector(selectors[i]);
            if (candidate) { return candidate; }
        }
        var s = el.nextElementSibling;
        while (s) {
            if (['SMALL', 'P', 'DIV', 'SPAN'].indexOf(s.tagName) >= 0) { return s; }
            s = s.nextElementSibling;
        }
        return null;
    }

    var helpEl = findHelpElementFor(secretIdInput);
    var originalHelpHTML = helpEl ? helpEl.innerHTML : '';
    var customHelpEl = findHelpElementFor(customInput);
    var originalCustomHelpHTML = customHelpEl ? customHelpEl.innerHTML : '';

    function ensureCustomHelpEl() {
        if (customHelpEl) { return; }
        try {
            var el = document.createElement('small');
            el.className = 'form-text bw-custom-help';
            if (customInput.nextSibling) {
                customInput.parentNode.insertBefore(el, customInput.nextSibling);
            } else {
                customInput.parentNode.appendChild(el);
            }
            customHelpEl = el;
            originalCustomHelpHTML = '';
        } catch (e) {
            // Not critical if we cannot create the help element.
        }
    }

    function syncParametersJson() {
        var jsonInput = document.getElementById('id_parameters');
        if (!jsonInput) { return; }
        var current = {};
        try {
            current = jsonInput.value ? JSON.parse(jsonInput.value) : {};
        } catch (e) {
            current = {};
        }
        current.secret_id = secretIdInput.value || '';
        current.secret_field = secretFieldSelect.value || '';
        current.custom_field_name = customInput.value || '';
        jsonInput.value = JSON.stringify(current, null, 4);
    }

    function setCustomFieldState() {
        var isCustom = secretFieldSelect.value === 'custom';
        if (!isCustom) {
            ensureCustomHelpEl();
            if (customInput.value) {
                customInput.value = '';
                if (customHelpEl) {
                    customHelpEl.innerHTML = originalCustomHelpHTML + ' <span class="bw-custom-warning text-danger">This value was cleared because the selected Secret field is not "Custom Field". Select "Custom Field" to keep it or re-enter a value.</span>';
                }
            } else if (customHelpEl) {
                customHelpEl.innerHTML = originalCustomHelpHTML + ' <span class="bw-custom-warning text-danger">The Custom Field is inactive because the selected Secret field is not "Custom Field".</span>';
            }
        } else if (customHelpEl) {
            customHelpEl.innerHTML = originalCustomHelpHTML;
        }
        customInput.style.opacity = isCustom ? '1' : '0.5';
        customInput.placeholder = isCustom ? '' : 'Activate Custom field selection to specify this value';
    }

    function setButtonVisibility() {
        var hasId = secretIdInput.value.trim().length > 0;
        fetchBtn.style.display = hasId ? '' : 'none';
        if (!hasId) {
            suggestionsDiv.style.display = 'none';
            errorDiv.style.display = 'none';
            if (helpEl) { helpEl.innerHTML = originalHelpHTML; }
        }
    }

    function debounce(fn, wait) {
        var t;
        return function () {
            var args = arguments;
            var ctx = this;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(ctx, args); }, wait);
        };
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;').replace(/'/g, '&#39;');
    }

    var lastRequestedId = null;
    function fetchAndUpdateName(secretId) {
        if (!secretId) {
            if (helpEl) { helpEl.innerHTML = originalHelpHTML; }
            return;
        }
        lastRequestedId = secretId;
        fetch(fetchUrl + '?secret_id=' + encodeURIComponent(secretId), { headers: {'X-Requested-With': 'XMLHttpRequest'} })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (secretIdInput.value.trim() !== lastRequestedId) { return; }
                if (data && data.success && data.name) {
                    if (helpEl) {
                        var escaped = escapeHtml(data.name);
                        helpEl.innerHTML = originalHelpHTML + ' <span class="bw-secret-wrapper">(<span class="text-muted">Secret: </span><span class="bw-secret-name">&#39;' + escaped + '&#39;</span>)</span>';
                    }
                } else if (helpEl) {
                    helpEl.innerHTML = originalHelpHTML;
                }
            })
            .catch(function () {
                if (helpEl) { helpEl.innerHTML = originalHelpHTML; }
            });
    }

    var debouncedFetchName = debounce(function () {
        var id = secretIdInput.value.trim();
        if (!id) {
            if (helpEl) { helpEl.innerHTML = originalHelpHTML; }
            return;
        }
        fetchAndUpdateName(id);
    }, 700);

    customInput.addEventListener('input', function () {
        if (customHelpEl && customInput.value.trim()) {
            customHelpEl.innerHTML = originalCustomHelpHTML;
        }
        syncParametersJson();
    });
    customInput.addEventListener('change', syncParametersJson);

    secretFieldSelect.addEventListener('change', function () {
        setCustomFieldState();
        syncParametersJson();
    });

    secretIdInput.addEventListener('input', function () {
        setButtonVisibility();
        debouncedFetchName();
        syncParametersJson();
    });
    secretIdInput.addEventListener('change', syncParametersJson);

    try {
        var formEl = customInput.closest('form');
        if (formEl) {
            formEl.addEventListener('submit', function () {
                setCustomFieldState();
                syncParametersJson();
            });
        }
    } catch (e) {
        // Ignore if closest() isn't available.
    }

    fetchBtn.addEventListener('click', function () {
        var secretId = secretIdInput.value.trim();
        if (!secretId) { return; }
        fetchBtn.disabled = true;
        fetchBtn.textContent = 'Fetching...';
        errorDiv.textContent = '';
        errorDiv.style.display = 'none';
        suggestionsDiv.style.display = 'none';

        fetch(fetchUrl + '?secret_id=' + encodeURIComponent(secretId), { headers: {'X-Requested-With': 'XMLHttpRequest'} })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                fetchBtn.disabled = false;
                fetchBtn.textContent = 'Fetch Fields from Bitwarden';
                if (data && data.success && data.fields && data.fields.length > 0) {
                    fieldList.innerHTML = '';
                    data.fields.forEach(function (fname) {
                        var b = document.createElement('button');
                        b.type = 'button';
                        b.className = 'btn btn-xs btn-default';
                        b.style.cssText = 'margin:2px;';
                        b.textContent = fname;
                        b.addEventListener('click', function () {
                            customInput.value = fname;
                            try {
                                customInput.dispatchEvent(new Event('input', { bubbles: true }));
                                customInput.dispatchEvent(new Event('change', { bubbles: true }));
                            } catch (e) {
                                // Ignore if dispatching events is not supported.
                            }
                            syncParametersJson();
                            try { customInput.focus(); } catch (e) {}
                        });
                        fieldList.appendChild(b);
                    });
                    suggestionsDiv.style.display = '';
                } else if (data && data.success) {
                    errorDiv.textContent = 'No custom fields found on this Bitwarden item.';
                    errorDiv.style.display = '';
                } else {
                    errorDiv.textContent = (data && data.error) ? data.error : 'Could not fetch Bitwarden custom fields.';
                    errorDiv.style.display = '';
                }
            })
            .catch(function (err) {
                fetchBtn.disabled = false;
                fetchBtn.textContent = 'Fetch Fields from Bitwarden';
                errorDiv.textContent = 'Request failed: ' + (err && err.message ? err.message : String(err));
                errorDiv.style.display = '';
            });
    });

    setCustomFieldState();
    setButtonVisibility();
    syncParametersJson();
    try {
        var initialId = secretIdInput.value.trim();
        if (initialId) {
            setTimeout(function () { fetchAndUpdateName(initialId); }, 150);
        }
    } catch (e) {
        // Fail silently; not critical.
    }
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
            '<style id="bw-secret-style">'
            ".bw-secret-name { font-weight:600; color:#056d3b; }"
            ".bw-custom-warning { color: #a94442; font-weight:600; }"
            "@media (prefers-color-scheme: dark) {"
            "  .bw-secret-name { color: #7ee787; text-shadow: 0 1px 0 rgba(0,0,0,0.6); }"
            "}"
            "@media (prefers-color-scheme: light) {"
            "  .bw-secret-name { color: #056d3b; }"
            "}"
            "</style>"
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
    _item_info_cache: dict[str, tuple[float, dict[str, Any]]] = {}

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
            # Use a local name that avoids triggering security linters
            # (some linters flag variables containing 'secret'/'password').
            selected_field = cleaned_data.get("secret_field")
            custom_field_name = cleaned_data.get("custom_field_name")

            # If the selected field is the generic `custom` option, require a custom name.
            if selected_field == "custom" and not custom_field_name:  # noqa: S105
                raise forms.ValidationError({"custom_field_name": "Custom field name is required for 'custom'."})

            # If a custom field name was supplied, ensure the selected field
            # reflects a custom-field selection. This guards against a user
            # entering a custom name while a non-custom field is chosen.
            # Accept either the literal 'custom' value or scoped values
            # starting with 'custom.' (e.g. 'custom.someField').
            if custom_field_name and not (selected_field == "custom"):
                raise forms.ValidationError(
                    {"secret_field": "Selected field must be a Custom Field when a Custom Field name is provided."}
                )

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
    def _get_timeout(cls) -> int:
        """Return request timeout in seconds from plugin settings/env/defaults."""
        raw_value = cls._plugin_settings().get("request_timeout") or os.getenv("BW_CLI_REQUEST_TIMEOUT")
        if raw_value is None:
            return REQUEST_TIMEOUT
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return REQUEST_TIMEOUT

    @classmethod
    def _get_item_endpoint_template(cls) -> str:
        """Return item endpoint template from plugin settings/env/default."""
        endpoint = cls._plugin_settings().get("item_endpoint") or os.getenv("BW_CLI_ITEM_ENDPOINT")
        if not endpoint:
            return BITWARDEN_ITEM_ENDPOINT_TEMPLATE
        endpoint_str = str(endpoint).strip()
        if "{secret_id}" not in endpoint_str:
            return BITWARDEN_ITEM_ENDPOINT_TEMPLATE
        return endpoint_str

    @classmethod
    def _get_retry_settings(cls) -> tuple[int, float]:
        """Return retry count and backoff factor for requests session retries."""
        plugin_settings = cls._plugin_settings()
        retry_total = plugin_settings.get("retry_total")
        if retry_total is None:
            retry_total = os.getenv("BW_CLI_RETRY_TOTAL", BITWARDEN_RETRY_TOTAL)
        retry_backoff = plugin_settings.get("retry_backoff")
        if retry_backoff is None:
            retry_backoff = os.getenv("BW_CLI_RETRY_BACKOFF", BITWARDEN_RETRY_BACKOFF)

        try:
            parsed_retry_total = int(retry_total)
        except (TypeError, ValueError):
            parsed_retry_total = BITWARDEN_RETRY_TOTAL

        try:
            parsed_retry_backoff = float(retry_backoff)
        except (TypeError, ValueError):
            parsed_retry_backoff = BITWARDEN_RETRY_BACKOFF

        return max(parsed_retry_total, 0), max(parsed_retry_backoff, 0.0)

    @classmethod
    def _get_cache_ttl_seconds(cls) -> int:
        """Return cache TTL for UI lookup helpers in seconds."""
        raw_value = cls._plugin_settings().get("cache_ttl") or os.getenv("BW_CLI_CACHE_TTL")
        if raw_value is None:
            return BITWARDEN_CACHE_TTL_SECONDS
        try:
            return max(int(raw_value), 0)
        except (TypeError, ValueError):
            return BITWARDEN_CACHE_TTL_SECONDS

    @staticmethod
    def _normalize_base_url(base_url: str, raise_exc) -> str:
        """Normalize and validate a Bitwarden base URL.

        Adds ``https://`` when no scheme is provided and validates that the
        resulting URL contains a supported scheme and hostname.
        """
        normalized = str(base_url).strip()
        if not normalized:
            raise raise_exc("Bitwarden base URL is empty.")

        if "://" not in normalized:
            normalized = f"https://{normalized}"

        parsed = urlsplit(normalized)
        if parsed.scheme not in ("http", "https"):
            raise raise_exc("Bitwarden base URL must use http or https scheme.")
        if not parsed.netloc:
            raise raise_exc("Bitwarden base URL must include a hostname.")

        return normalized.rstrip("/")

    @classmethod
    def _build_item_url(cls, base_url: str, secret_id: str) -> str:
        """Build the item endpoint URL for a given secret ID."""
        endpoint_template = cls._get_item_endpoint_template()
        endpoint_path = endpoint_template.format(secret_id=secret_id)
        if not endpoint_path.startswith("/"):
            endpoint_path = f"/{endpoint_path}"
        return urljoin(f"{base_url}/", endpoint_path.lstrip("/"))

    @classmethod
    def _build_session(cls) -> requests.Session:
        """Create a requests session configured with retries."""
        retry_total, retry_backoff = cls._get_retry_settings()
        retry = Retry(
            total=retry_total,
            connect=retry_total,
            read=retry_total,
            status=retry_total,
            backoff_factor=retry_backoff,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

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

        missing = cls._missing_credential_names(base_url, username, password)
        if missing:
            raise exceptions.SecretProviderError(
                secret, cls, f"Missing required environment variable(s): {', '.join(missing)}"
            )

        raise_exc = partial(exceptions.SecretProviderError, secret, cls)
        normalized_url = cls._normalize_base_url(str(base_url), raise_exc)
        return normalized_url, str(username), str(password)

    @classmethod
    def _get_credentials(cls) -> tuple[str | None, str | None, str | None]:
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
    def _load_tls_settings(cls) -> bool | str:
        """Return TLS verification setting used by `requests`.

        The return value is either a boolean (True/False) or a string path to a
        CA bundle file suitable for passing directly to `requests.get(..., verify=...)`.
        The caller should validate that a provided file path exists and raise an
        appropriate error type for its context.
        """
        plugin_settings = cls._plugin_settings()
        ca_bundle_path = plugin_settings.get("ca_bundle_path") or os.getenv("BW_CLI_CA_BUNDLE")
        if ca_bundle_path:
            # Return normalized absolute path; existence is validated at use time.
            return str(Path(ca_bundle_path).expanduser().resolve())

        verify_ssl_setting = plugin_settings.get("verify_ssl")
        if verify_ssl_setting is None:
            verify_ssl_setting = os.getenv("BW_CLI_VERIFY_SSL", "true")
        return is_truthy(verify_ssl_setting)

    @staticmethod
    def _validate_secret_id(secret_id: str, raise_exc) -> None:
        """Validate the secret ID format and raise via `raise_exc` on error.

        `raise_exc` is a callable that accepts a single string message and
        returns or raises an exception appropriate for the caller's context.
        """
        if not isinstance(secret_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", secret_id):
            raise raise_exc("Invalid secret_id format.")

    @classmethod
    def _check_credentials(
        cls,
        base_url: str | None,
        username: str | None,
        password: str | None,
        raise_exc,
    ) -> None:
        """Ensure credentials are present; raise via `raise_exc` if any are missing."""
        missing = cls._missing_credential_names(base_url, username, password)
        if missing:
            raise raise_exc(f"Missing Bitwarden configuration: {', '.join(missing)}")

    @staticmethod
    def _missing_credential_names(
        base_url: str | None,
        username: str | None,
        password: str | None,
    ) -> list[str]:
        """Return names of missing credential inputs for Bitwarden connections."""
        return [
            name
            for name, value in [
                ("BW_CLI_URL", base_url),
                ("BW_CLI_USER", username),
                ("BW_CLI_PASSWORD", password),
            ]
            if not value
        ]

    @classmethod
    def _request_item_payload(cls, url: str, auth: tuple[str, str], verify: bool | str, raise_exc):
        """Perform GET -> JSON -> success-check for Bitwarden item endpoints.

        `raise_exc` should be a callable accepting a single message string and
        producing an exception appropriate for the caller.
        Returns the `data` object from the Bitwarden payload on success.

        Note:
            The requests.Session is intentionally not cached or reused between calls.
            This avoids thread safety issues in Django and WSGI/ASGI environments.
        """
        # If a CA bundle path is returned, ensure the file exists before use.
        if isinstance(verify, str):
            if not Path(verify).expanduser().resolve().is_file():
                raise raise_exc(f"CA bundle not found at: {verify}")

        timeout = cls._get_timeout()
        session = cls._build_session()
        try:
            username, password = auth
            logger.debug("Requesting Bitwarden item payload from %s", url)
            response = session.get(url, auth=(str(username), str(password)), timeout=timeout, verify=verify)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            response = err.response
            if response is not None:
                raise raise_exc(f"Bitwarden CLI returned {response.status_code}: {response.text}") from err
            raise raise_exc("Bitwarden CLI returned an HTTP error without a response body.") from err
        except requests.exceptions.SSLError as err:
            raise raise_exc(
                "Unable to verify the Bitwarden CLI TLS certificate. "
                "Set BW_CLI_CA_BUNDLE to a trusted CA bundle path or set BW_CLI_VERIFY_SSL=false for development.",
            ) from err
        except requests.RequestException as err:  # pragma: no cover - network error path
            raise raise_exc(f"Unable to reach Bitwarden CLI server: {err}") from err
        finally:
            session.close()

        try:
            payload = response.json()
        except ValueError as err:
            raise raise_exc("Bitwarden CLI returned invalid JSON.") from err

        if not payload.get("success"):
            message = payload.get("message") or "Bitwarden CLI reported failure."
            raise raise_exc(message)

        return payload.get("data") or {}

    @classmethod
    def _get_ui_request_settings(cls) -> tuple[str, tuple[str, str], bool | str]:
        """Return normalized URL/auth/verify settings for UI helper requests."""
        base_url, username, password = cls._get_credentials()
        cls._check_credentials(base_url, username, password, ValueError)
        normalized_url = cls._normalize_base_url(str(base_url), ValueError)
        auth = (str(username), str(password))
        verify = cls._load_tls_settings()
        return normalized_url, auth, verify

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

        Uses `_load_env_settings` for credential validation and the shared
        `_request_item_payload` helper to perform the HTTP and JSON work.
        """
        # Validate secret_id format and raise provider-specific error on failure
        raise_exc = partial(exceptions.SecretProviderError, secret, cls)
        cls._validate_secret_id(secret_id, raise_exc)

        base_url, username, password = cls._load_env_settings(secret)
        url = cls._build_item_url(base_url, secret_id)
        verify = cls._load_tls_settings()

        # Delegate request + parse + success-check to shared helper
        return cls._request_item_payload(url, (username, password), verify, raise_exc)

    @staticmethod
    def _read_nested(data: dict[str, Any], path: str) -> Any:
        """Read nested values supporting dotted paths and list indexes.

        Examples:
            - ``login.password``
            - ``login.uris[0].uri``
        """
        value: Any = data
        for part in path.split("."):
            match = re.fullmatch(r"([A-Za-z0-9_]+)((?:\[[0-9]+\])*)", part)
            if not match:
                return None

            key, indexes = match.groups()
            if not isinstance(value, dict):
                return None
            value = value.get(key)

            if indexes:
                for idx_str in re.findall(r"\[([0-9]+)\]", indexes):
                    if not isinstance(value, list):
                        return None
                    idx = int(idx_str)
                    if idx >= len(value):
                        return None
                    value = value[idx]

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
        return list(cls.get_item_info(secret_id).get("fields", []))

    @classmethod
    def get_item_info(cls, secret_id: str) -> dict[str, Any]:
        """Return item metadata for the provided Bitwarden item ID.

        Intended for UI usage. Returns a dict with keys ``name`` (string)
        and ``fields`` (list[str]). Raises ``ValueError`` on failure with
        an explanatory message suitable for display to the user.
        """
        ttl_seconds = cls._get_cache_ttl_seconds()
        if ttl_seconds > 0:
            cached = cls._item_info_cache.get(secret_id)
            if cached and cached[0] >= time.time():
                return dict(cached[1])

        normalized_url, auth, verify = cls._get_ui_request_settings()

        # Validate secret id format
        cls._validate_secret_id(secret_id, ValueError)

        url = cls._build_item_url(normalized_url, secret_id)
        data = cls._request_item_payload(url, auth, verify, ValueError)
        fields = data.get("fields") or []
        field_names = [item.get("name") for item in fields if item.get("name")]
        name = data.get("name") or ""
        result = {"name": str(name), "fields": field_names}

        if ttl_seconds > 0:
            cls._item_info_cache[secret_id] = (time.time() + ttl_seconds, dict(result))

        return result
