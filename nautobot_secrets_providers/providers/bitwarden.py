"""Bitwarden CLI secrets provider backed by bw serve REST endpoints."""

# This provider intentionally includes the Bitwarden widget structure plus provider logic.
# pylint: disable=too-many-lines

from __future__ import annotations

import logging
import os
import re
import time
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from django import forms
from django.conf import settings
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe
from nautobot.apps.forms import BootstrapMixin
from nautobot.apps.secrets import SecretsProvider
from nautobot.core.settings_funcs import is_truthy
from nautobot.extras.secrets import exceptions
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from nautobot_secrets_providers.constants import (
    BITWARDEN_CACHE_TTL_SECONDS,
    BITWARDEN_COMMON_ALLOWED_FIELDS,
    BITWARDEN_ITEM_ENDPOINT_TEMPLATE,
    BITWARDEN_ITEM_TYPE_ALLOWED_FIELDS,
    BITWARDEN_LIST_ITEMS_ENDPOINT,
    BITWARDEN_PARAMETER_KEYS,
    BITWARDEN_RETRY_BACKOFF,
    BITWARDEN_RETRY_TOTAL,
    BITWARDEN_WIDGET_JS_PATH,
    CARD_FIELDS,
    DEFAULT_BITWARDEN_FIELDS,
    IDENTITY_FIELDS,
    LOGIN_FIELDS,
    REQUEST_TIMEOUT,
    SSHKEY_FIELDS,
)

logger = logging.getLogger(__name__)


class BitwardenCustomFieldNameWidget(forms.Select):
    """Select widget for `custom_field_name` with Bitwarden helper controls."""

    def render(self, name, value, attrs=None, renderer=None):
        """Render the input together with buttons and external Bitwarden widget JavaScript."""
        attrs = dict(attrs or {})
        attrs.setdefault("data-initial-custom-field", str(value or "").strip())
        input_html = super().render(name, value, attrs, renderer)
        try:
            item_info_url = reverse("plugins:nautobot_secrets_providers:bitwarden_item_info")
        except NoReverseMatch:
            item_info_url = ""
        try:
            search_url = reverse("plugins:nautobot_secrets_providers:bitwarden_search_items")
        except NoReverseMatch:
            search_url = ""
        wrapper = (
            '<style id="bw-secret-style">'
            ".bw-secret-name { font-weight:600; color:#056d3b; }"
            "#bw-search-items-btn { display: inline-block; margin-left: 0; background-color: #0066cc !important; color: white !important; border-radius: 3px; border: 1px solid #0052a3; cursor: pointer; font-weight: 500; transition: background-color 0.2s; }"
            "#bw-search-items-btn:hover { background-color: #0052a3 !important; }"
            "#bw-search-items-btn:active { background-color: #003d7a !important; }"
            "#bw-search-items-btn:disabled { background-color: #cccccc !important; color: #666 !important; cursor: not-allowed; }"
            "#bw-search-anchor { display: none; margin-top: 8px; width: 100%; max-width: 100%; }"
            "#bw-search-panel { margin-top: 8px; width: min(36rem, 100%); max-width: 100%; padding: 8px; border: 1px solid #d0d0d0; border-radius: 4px; background: rgba(0, 0, 0, 0.02); box-sizing: border-box; }"
            ".bw-search-controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }"
            ".bw-search-input { flex: 1 1 16rem; min-width: 0; }"
            ".bw-search-item { display: block; width: 100%; text-align: left; padding: 6px 8px; margin: 4px 0; border: 1px solid #d6d6d6; background: #fff; border-radius: 4px; cursor: pointer; }"
            ".bw-search-item:hover, .bw-search-item.is-selected { border-color: #2f855a; background: #edf9f1; }"
            ".bw-search-item-name { display: block; font-weight: 600; color: #1f2933; }"
            ".bw-search-item-id { display: block; font-family: monospace; font-size: 12px; color: #5f6b7a; margin-top: 2px; }"
            "@media (max-width: 767px) {"
            "  .bw-search-controls { flex-direction: column; align-items: stretch; }"
            "  #bw-search-panel { width: 100%; }"
            "  #bw-search-run-btn { width: 100%; }"
            "}"
            "@media (prefers-color-scheme: dark) {"
            "  .bw-secret-name { color: #7ee787; text-shadow: 0 1px 0 rgba(0,0,0,0.6); }"
            "  #bw-search-items-btn { background-color: #0077e6 !important; border-color: #0066cc; }"
            "  #bw-search-items-btn:hover { background-color: #0066cc !important; }"
            "  #bw-search-items-btn:active { background-color: #0052a3 !important; }"
            "  #bw-search-panel { background: rgba(255, 255, 255, 0.04); border-color: #444; }"
            "  .bw-search-item { background: #2d2d2d; border-color: #444; }"
            "  .bw-search-item:hover, .bw-search-item.is-selected { background: #214a34; border-color: #2f855a; }"
            "  .bw-search-item-name { color: #dbe7e0; }"
            "  .bw-search-item-id { color: #b8c5bf; }"
            "}"
            "@media (prefers-color-scheme: light) {"
            "  .bw-secret-name { color: #056d3b; }"
            "}"
            "</style>"
            '<div style="margin-top:4px;">'
            '<div id="bw-search-anchor" style="display:none;">'
            '<button type="button" id="bw-search-items-btn" class="btn btn-sm"'
            f' data-item-info-url="{item_info_url}" data-search-url="{search_url}">Find Item UUID</button>'
            '<div id="bw-search-panel" style="display:none;">'
            '<div class="bw-search-controls">'
            '<input type="text" id="bw-search-query" class="form-control bw-search-input" '
            'placeholder="Search Bitwarden items (min 2 chars)">'
            '<button type="button" id="bw-search-run-btn" class="btn btn-sm">Search</button>'
            "</div>"
            '<small id="bw-search-status" class="text-muted">Enter at least 2 characters to search.</small>'
            '<div id="bw-search-results" style="margin-top:6px;"></div>'
            "</div>"
            "</div>"
            '<div id="bw-custom-field-status" class="text-muted"'
            ' style="display:none;margin-top:4px;"></div>'
            "</div>"
        )
        script_url = static(BITWARDEN_WIDGET_JS_PATH)
        return mark_safe(str(input_html) + wrapper + f'<script src="{script_url}"></script>')  # noqa: S308


class BitwardenCLISecretsProvider(SecretsProvider):
    """Secrets provider for Bitwarden CLI `bw serve` API."""

    slug = "bitwarden-cli"
    name = "Bitwarden CLI"
    is_available = True
    _item_info_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def remove_transient_parameter_keys(parameters: dict[str, Any] | None) -> dict[str, Any]:
        """Return only canonical Bitwarden parameters from an input payload."""
        if not isinstance(parameters, dict):
            return {}

        return {key: value for key, value in parameters.items() if key in BITWARDEN_PARAMETER_KEYS}

    @classmethod
    def sanitize_parameters(cls, parameters: dict[str, Any] | None) -> dict[str, Any]:
        """Ensure parameters only contain canonical Bitwarden keys.

        This method provides defensive sanitization to guarantee parameters
        stored in a Secret are clean, regardless of how they were submitted
        (form, API, bulk edit, etc.). Transient UI fields are always removed.

        Args:
            parameters: Raw parameters dict, potentially containing transient keys.

        Returns:
            Dict containing only canonical Bitwarden parameter keys.
        """
        cleaned = cls.remove_transient_parameter_keys(parameters)
        # Ensure all canonical keys are present with safe defaults
        return {
            "secret_id": str(cleaned.get("secret_id", "")).strip(),
            "secret_field": str(cleaned.get("secret_field", "")).strip(),
            "custom_field_name": str(cleaned.get("custom_field_name", "")).strip(),
        }

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
        custom_field_name = forms.ChoiceField(
            required=False,
            help_text="Custom field name when secret_field is 'custom'.",
            choices=(("", "---------"),),
        )

        def __init__(self, *args, **kwargs):
            """Dynamically populate the secret_field choices from plugin settings."""
            super().__init__(*args, **kwargs)
            self.fields["secret_field"].choices = BitwardenCLISecretsProvider.get_field_choices()
            self.fields["custom_field_name"].widget = BitwardenCustomFieldNameWidget()
            self.fields["custom_field_name"].choices = [("", "---------")]

            configured_custom_field_name = ""
            if self.is_bound:
                configured_custom_field_name = str(self.data.get("custom_field_name") or "").strip()
            else:
                configured_custom_field_name = str(self.initial.get("custom_field_name") or "").strip()

            if configured_custom_field_name:
                self.fields["custom_field_name"].choices.append(
                    (configured_custom_field_name, configured_custom_field_name)
                )

        def clean(self):
            """Validate cross-field dependencies for Bitwarden parameters.

            Raises a non-field ValidationError when the combination of
            ``secret_field`` and ``custom_field_name`` is inconsistent.  A
            non-field error is used so this method behaves identically whether
            called via ``form.is_valid()`` (standard Django path) or directly
            as Nautobot's ``Secret.clean()`` does after ``is_valid()``.  On
            both invocations a raised exception is the only reliable signal
            that blocks the model save.

            ``self.data`` is consulted as a fallback for ``cleaned_data`` so
            that validation remains correct when Django has already removed a
            field from ``cleaned_data`` (for example after a prior error).
            This is a standard Django practice for robust cross-field
            validation.
            """
            cleaned_data = super().clean()
            # Fall back to raw submitted data when cleaned_data is incomplete.
            # (Django removes a field from cleaned_data when add_error() is
            # called on it, and Nautobot may call clean() again directly.)
            selected_field = str(cleaned_data.get("secret_field") or self.data.get("secret_field", "")).strip()
            custom_field_name = str(
                cleaned_data.get("custom_field_name") or self.data.get("custom_field_name", "")
            ).strip()

            # If the selected field is the generic `custom` option, require a custom name.
            if selected_field == "custom" and not custom_field_name:  # noqa: S105
                raise forms.ValidationError("Custom field name is required if Secret field is set to 'Custom Field'.")

            # If a custom field name was supplied, the selected field must be
            # 'custom'; any other combination is an invalid configuration.
            if custom_field_name and selected_field != "custom":  # noqa: S105
                raise forms.ValidationError(
                    "'Secret field' must be set to 'Custom Field' when 'Custom field name' is provided."
                )

            # Return only canonical provider keys via sanitization.
            # sanitize_parameters ensures transient UI fields are removed and all canonical
            # keys are present with safe defaults.
            return BitwardenCLISecretsProvider.sanitize_parameters(cleaned_data)

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
    def _get_list_items_endpoint(cls) -> str:
        """Return list endpoint from plugin settings/env/default."""
        endpoint = cls._plugin_settings().get("list_items_endpoint") or os.getenv("BW_CLI_LIST_ITEMS_ENDPOINT")
        if not endpoint:
            return BITWARDEN_LIST_ITEMS_ENDPOINT
        endpoint_str = str(endpoint).strip()
        return endpoint_str or BITWARDEN_LIST_ITEMS_ENDPOINT

    @classmethod
    def _get_retry_settings(cls) -> tuple[int, float]:
        """Return retry count and backoff factor for requests session retries."""
        plugin_settings = cls._plugin_settings()
        retry_total = plugin_settings.get("retry_total")
        if retry_total is None:
            retry_total = os.getenv("BW_CLI_RETRY_TOTAL", str(BITWARDEN_RETRY_TOTAL))
        retry_backoff = plugin_settings.get("retry_backoff")
        if retry_backoff is None:
            retry_backoff = os.getenv("BW_CLI_RETRY_BACKOFF", str(BITWARDEN_RETRY_BACKOFF))

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
    def _build_list_items_url(cls, base_url: str, search_query: str) -> str:
        """Build list-items endpoint URL for the given search query."""
        endpoint_path = cls._get_list_items_endpoint()
        if not endpoint_path.startswith("/"):
            endpoint_path = f"/{endpoint_path}"
        base_endpoint = urljoin(f"{base_url}/", endpoint_path.lstrip("/"))
        return f"{base_endpoint}?{urlencode({'search': search_query})}"

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
    def get_allowed_secret_fields_for_item_type(cls, item_type: int | None) -> list[str]:
        """Return allowed ``secret_field`` values for a Bitwarden item type.

        Item type values follow Bitwarden conventions (for example, 1=Login,
        2=Secure Note, 3=Card, 4=Identity, 5=SSH Key).
        """
        choice_values = [name for name, _label in cls.get_field_choices()]

        if item_type is None:
            return choice_values

        type_specific_fields = BITWARDEN_ITEM_TYPE_ALLOWED_FIELDS.get(item_type)
        allowed = (type_specific_fields | BITWARDEN_COMMON_ALLOWED_FIELDS) if type_specific_fields is not None else None
        if allowed is None:
            return choice_values

        return [value for value in choice_values if value in allowed]

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
                logger.warning(
                    "Bitwarden HTTP error for %s: status=%s",
                    url,
                    response.status_code,
                )
                raise raise_exc(f"Bitwarden CLI returned {response.status_code}: {response.text}") from err
            logger.warning("Bitwarden HTTP error without response body for %s", url)
            raise raise_exc("Bitwarden CLI returned an HTTP error without a response body.") from err
        except requests.exceptions.SSLError as err:
            logger.warning("Bitwarden TLS verification error for %s: %s", url, err)
            raise raise_exc(
                "Unable to verify the Bitwarden CLI TLS certificate. "
                "Set BW_CLI_CA_BUNDLE to a trusted CA bundle path or set BW_CLI_VERIFY_SSL=false for development.",
            ) from err
        except requests.RequestException as err:  # pragma: no cover - network error path
            logger.warning("Bitwarden request exception for %s: %s", url, err)
            raise raise_exc(f"Unable to reach Bitwarden CLI server: {err}") from err
        finally:
            session.close()

        try:
            payload = response.json()
        except ValueError as err:
            logger.warning("Bitwarden JSON decode failed for %s", url)
            raise raise_exc("Bitwarden CLI returned invalid JSON.") from err

        if not payload.get("success"):
            message = payload.get("message") or "Bitwarden CLI reported failure."
            logger.warning("Bitwarden payload failure for %s: %s", url, message)
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
        and ``fields`` (list[str]), plus ``item_type`` and
        ``allowed_secret_fields``. Raises ``ValueError`` on failure with an
        explanatory message suitable for display to the user.
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
        item_type = data.get("type")
        try:
            item_type_value = int(item_type) if item_type is not None else None
        except (TypeError, ValueError):
            item_type_value = None

        result = {
            "name": str(name),
            "fields": field_names,
            "item_type": item_type_value,
            "allowed_secret_fields": cls.get_allowed_secret_fields_for_item_type(item_type_value),
        }

        if ttl_seconds > 0:
            cls._item_info_cache[secret_id] = (time.time() + ttl_seconds, dict(result))

        return result

    @classmethod
    def search_items(cls, search_query: str) -> list[dict[str, Any]]:
        """Search Bitwarden items by text and return lightweight item metadata.

        Args:
            search_query: User-provided search string.

        Returns:
            List of dict entries containing ``id``, ``name``, and ``type``.

        Raises:
            ValueError: If query is too short or request/response validation fails.
        """
        query = str(search_query).strip()
        if len(query) < 2:
            raise ValueError("Search text must be at least 2 characters.")

        normalized_url, auth, verify = cls._get_ui_request_settings()
        url = cls._build_list_items_url(normalized_url, query)
        data = cls._request_item_payload(url, auth, verify, ValueError)

        raw_items: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = data.get("data") or []

        items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not item_id:
                continue
            items.append(
                {
                    "id": str(item_id),
                    "name": str(item.get("name") or ""),
                    "type": item.get("type"),
                }
            )
        return items
