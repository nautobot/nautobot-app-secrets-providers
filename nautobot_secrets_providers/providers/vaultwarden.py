"""Secrets Provider for Vaultwarden (Bitwarden-compatible self-hosted servers)."""

import hashlib
import hmac

from django import forms
from django.conf import settings
from django.core.cache import cache as django_cache
from nautobot.core.forms import BootstrapMixin
from nautobot.extras.secrets import SecretsProvider, exceptions

# Soft-import: the cryptography lib is the only hard dep beyond stdlib + requests.
# If it's missing, the provider declares itself unavailable so Nautobot doesn't crash.
try:
    import cryptography  # noqa: F401

    from . import _vaultwarden_client as vw
except ImportError:
    vw = None  # type: ignore[assignment]

__all__ = ("VaultwardenSecretsProvider",)


# Cache key prefix for unwrapped session payloads. The full key includes a hash of
# (server_url, email, master_password) so rotating the master password naturally
# invalidates any cached session - we'll never resurrect old credentials.
_SESSION_CACHE_KEY_PREFIX = "nautobot_secrets_providers:vaultwarden:session"
# Default TTL for the session cache. Bitwarden access tokens default to 1h; we
# stay well clear of the edge to avoid handing out a token that's seconds from
# expiring. Operators can override via `session_cache_seconds` in PLUGINS_CONFIG.
_DEFAULT_SESSION_CACHE_TTL_SECONDS = 30 * 60
# HMAC key prefix used to derive cache keys. The key itself isn't a secret - it
# just needs to make the hash collision-resistant and not reveal credentials in
# the cache backend's key namespace.
_CACHE_KEY_HMAC_PREFIX = b"nautobot-secrets-providers:vaultwarden:cache-key-v1"


def vault_choices():
    """Form-field choices: enumerate configured Vaultwarden servers from PLUGINS_CONFIG.

    Multi-server config style mirrors HashiCorp/1Password providers - if `vaults` is
    present, each key becomes a choice; otherwise we fall back to "default" which uses
    the top-level vaultwarden settings dict.
    """
    plugin_settings = settings.PLUGINS_CONFIG.get("nautobot_secrets_providers", {})
    vaultwarden_settings = plugin_settings.get("vaultwarden", {})
    if "vaults" in vaultwarden_settings:
        return [(key, key.replace("_", " ").title()) for key in vaultwarden_settings["vaults"].keys()]
    return [("default", "Default")]


def field_type_choices():
    """Reserved field names plus 'custom' for user-defined fields on the cipher."""
    return [
        ("password", "Password"),
        ("username", "Username"),
        ("notes", "Notes"),
        ("totp", "TOTP Seed"),
        ("custom", "Custom Field"),
    ]


class VaultwardenSecretsProvider(SecretsProvider):
    """A secrets provider for Vaultwarden (Bitwarden-compatible) servers.

    Authenticates with email + master password against the Bitwarden Vault API
    (/identity/connect/token), syncs the encrypted vault, and decrypts the requested
    field of the requested item locally. The master password never crosses the wire -
    only the PBKDF2/Argon2id-derived auth hash does.

    Personal-vault items and organization-owned items are both supported. For org
    items, the user's PKCS#8 RSA-2048 private key is unwrapped from the token response,
    and each organization's symmetric key is RSA-OAEP-decrypted on sync.

    Sessions (access token, unwrapped user keys, RSA private key, decrypted org keys)
    are cached in Django's cache framework keyed by a hash of the credentials. PBKDF2
    is the dominant per-call cost (~300ms) so the cache typically reduces a request
    to a single sync HTTP round-trip plus local AES decryption.
    """

    slug = "vaultwarden"
    name = "Vaultwarden"
    is_available = vw is not None

    # pylint: disable-next=nb-incorrect-base-class
    class ParametersForm(BootstrapMixin, forms.Form):
        """Per-secret parameters identifying the item and field to retrieve."""

        vault = forms.ChoiceField(
            required=False,
            choices=vault_choices,
            help_text="Configured Vaultwarden server to retrieve the secret from.",
        )
        item = forms.CharField(
            required=True,
            help_text="The item's UUID (preferred - exact, no decryption sweep) or its decrypted name.",
        )
        field_type = forms.ChoiceField(
            required=True,
            choices=field_type_choices,
            initial="password",
            help_text="Which field on the item to retrieve. 'Custom Field' requires a Field Name below.",
        )
        field_name = forms.CharField(
            required=False,
            help_text="Name of the custom field to retrieve. Only used when Field Type is 'Custom Field'.",
        )

    @classmethod
    def _retrieve_vault_settings(cls, secret, vault_name):
        """Look up the per-vault settings dict, falling back to the top-level vaultwarden block."""
        plugin_settings = settings.PLUGINS_CONFIG.get("nautobot_secrets_providers", {})
        vaultwarden_settings = plugin_settings.get("vaultwarden")
        if not vaultwarden_settings:
            raise exceptions.SecretProviderError(secret, cls, "Vaultwarden is not configured in PLUGINS_CONFIG!")

        if "vaults" in vaultwarden_settings:
            try:
                return vaultwarden_settings["vaults"][vault_name]
            except KeyError as err:
                raise exceptions.SecretProviderError(
                    secret, cls, f"Vaultwarden vault {vault_name!r} is not configured!"
                ) from err
        return vaultwarden_settings

    @classmethod
    def _validate_vault_settings(cls, secret, vault_settings):
        """Verify required keys are present and well-typed before we touch the network."""
        for required_key in ("url", "email", "master_password"):
            if not vault_settings.get(required_key):
                raise exceptions.SecretProviderError(
                    secret, cls,
                    f"Vaultwarden configuration is missing required key {required_key!r}",
                )

    @classmethod
    def _build_client(cls, vault_settings, cached_session=None):
        """Construct a BitwardenClient from validated settings.

        If `cached_session` is supplied, it's handed to the client so the next
        call skips login(). The client itself doesn't know or care about Django's
        cache - that's our job up here.
        """
        device_identifier = vault_settings.get("device_identifier")
        if not device_identifier:
            # Tie the device identifier to the server URL + email so a Nautobot instance
            # registers as one device per (server, account) rather than churning per-process.
            seed = f"{vault_settings['url']}|{vault_settings['email']}"
            device_identifier = vw.make_device_identifier(seed)

        return vw.BitwardenClient(
            server_url=vault_settings["url"],
            email=vault_settings["email"],
            master_password=vault_settings["master_password"],
            verify_ssl=vault_settings.get("verify_ssl", True),
            timeout=vault_settings.get("timeout", 30.0),
            device_identifier=device_identifier,
            device_name=vault_settings.get("device_name", vw.DEFAULT_DEVICE_NAME),
            session=cached_session,
        )

    @staticmethod
    def _cache_key_for(vault_settings) -> str:
        """Derive a stable, credential-bound cache key.

        We HMAC-SHA256 the (url, email, master_password) tuple with a fixed
        application key. The result is hex-encoded and prefixed so it's recognizable
        in the cache backend without revealing what produced it.
        """
        material = "\x00".join([
            vault_settings.get("url", ""),
            vault_settings.get("email", ""),
            vault_settings.get("master_password", ""),
        ]).encode("utf-8")
        digest = hmac.new(_CACHE_KEY_HMAC_PREFIX, material, hashlib.sha256).hexdigest()
        return f"{_SESSION_CACHE_KEY_PREFIX}:{digest}"

    @classmethod
    def _load_cached_session(cls, vault_settings):
        """Return a hydrated BitwardenSession from cache, or None on miss/disabled."""
        if not vault_settings.get("cache_session", True):
            return None
        cache_key = cls._cache_key_for(vault_settings)
        payload = django_cache.get(cache_key)
        if not payload:
            return None
        try:
            return vw.BitwardenSession.from_cache_payload(payload)
        except (KeyError, TypeError):
            # Stale or malformed payload (e.g. from a prior version with a different
            # schema). Drop it and re-auth.
            django_cache.delete(cache_key)
            return None

    @classmethod
    def _store_cached_session(cls, vault_settings, session) -> None:
        """Persist a session to the cache. No-op when caching is disabled."""
        if not vault_settings.get("cache_session", True):
            return
        cache_key = cls._cache_key_for(vault_settings)
        ttl = vault_settings.get("session_cache_seconds", _DEFAULT_SESSION_CACHE_TTL_SECONDS)
        django_cache.set(cache_key, session.to_cache_payload(), timeout=ttl)

    @classmethod
    def _invalidate_cached_session(cls, vault_settings) -> None:
        """Delete the cached session - used when the server rejects our access token."""
        cache_key = cls._cache_key_for(vault_settings)
        django_cache.delete(cache_key)

    @classmethod
    def _resolve_field_name(cls, secret, parameters):
        """Translate (field_type, field_name) form fields into the underlying client's field arg."""
        field_type = parameters.get("field_type", "password")
        if field_type == "custom":
            field_name = parameters.get("field_name")
            if not field_name:
                raise exceptions.SecretParametersError(
                    secret, cls,
                    "Field Type 'Custom Field' requires a Field Name to be specified.",
                )
            return field_name
        return field_type

    @classmethod
    def _retrieve(cls, client, item, field_name):
        """Run get_secret() against the (possibly cache-hydrated) client.

        Pulled out so the retry path doesn't duplicate the call site.
        """
        return client.get_secret(item=item, field_name=field_name)

    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """Retrieve and return the decrypted value for the given Nautobot Secret.

        Flow:
            1. Resolve settings + parameters.
            2. Try the cached session, if any.
            3. On a cache miss, run the full login + sync.
            4. On a cached-session 401 (token rejected), invalidate the cache and
               retry exactly once with a fresh login.
        """
        if vw is None:
            raise exceptions.SecretProviderError(
                secret, cls,
                "Vaultwarden provider requires the 'cryptography' library, which is not installed.",
            )

        parameters = secret.rendered_parameters(obj=obj)
        try:
            item = parameters["item"]
        except KeyError as err:
            raise exceptions.SecretParametersError(
                secret, cls, f"Missing required parameter: {err}"
            ) from err

        vault_name = parameters.get("vault") or "default"
        vault_settings = cls._retrieve_vault_settings(secret, vault_name)
        cls._validate_vault_settings(secret, vault_settings)
        field_name = cls._resolve_field_name(secret, parameters)

        cached_session = cls._load_cached_session(vault_settings)
        client = cls._build_client(vault_settings, cached_session=cached_session)

        try:
            if not client.has_session():
                client.login()
            try:
                value = cls._retrieve(client, item, field_name)
            except vw.BitwardenAuthError:
                # Cached token was rejected by the server. Wipe it and retry with a
                # fresh login - exactly once. If that also fails we surface it normally.
                if cached_session is not None:
                    cls._invalidate_cached_session(vault_settings)
                    client.invalidate_session()
                    client.login()
                    value = cls._retrieve(client, item, field_name)
                else:
                    raise
            # Successful retrieval - persist the (possibly fresh) session for next time.
            if client.session is not None:
                cls._store_cached_session(vault_settings, client.session)
            return value
        except vw.BitwardenAuthError as err:
            raise exceptions.SecretProviderError(
                secret, cls, f"Vaultwarden authentication failed: {err}"
            ) from err
        except vw.BitwardenItemNotFoundError as err:
            raise exceptions.SecretValueNotFoundError(secret, cls, str(err)) from err
        except vw.BitwardenFieldNotFoundError as err:
            raise exceptions.SecretValueNotFoundError(secret, cls, str(err)) from err
        except vw.BitwardenCryptoError as err:
            raise exceptions.SecretProviderError(
                secret, cls, f"Vaultwarden decryption error: {err}"
            ) from err
        except vw.BitwardenClientError as err:
            raise exceptions.SecretProviderError(
                secret, cls, f"Vaultwarden client error: {err}"
            ) from err


# Suppress "imported but unused" - hashlib is reserved for upcoming session-cache key derivation.
_ = hashlib
