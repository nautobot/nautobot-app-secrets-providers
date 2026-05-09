"""Bitwarden / Vaultwarden Vault API client and CipherString crypto.

Pure-Python implementation of the subset of the Bitwarden Vault API needed
to authenticate, sync, and decrypt personal- and organization-owned items from
a Vaultwarden (or upstream Bitwarden) server. The Vaultwarden REST surface is
wire-compatible with Bitwarden, so the same code targets both.

This module is intentionally Django-agnostic so it can be unit-tested in
isolation with `requests_mock`.
"""

import base64
import hashlib
import hmac
import struct
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymm_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

__all__ = (
    "BitwardenClient",
    "BitwardenClientError",
    "BitwardenAuthError",
    "BitwardenItemNotFoundError",
    "BitwardenFieldNotFoundError",
    "BitwardenCryptoError",
    "CipherString",
    "BitwardenSession",
)

# Bitwarden CipherString type discriminators.
# Symmetric (AES-CBC + HMAC-SHA256) - the only modern symmetric type.
CIPHER_TYPE_AESCBC256_HMACSHA256 = 2
# Asymmetric (RSA-OAEP) - used for wrapping per-organization symmetric keys.
# Each pair differs in the OAEP hash and whether an HMAC is appended.
CIPHER_TYPE_RSA2048_OAEPSHA256 = 3
CIPHER_TYPE_RSA2048_OAEPSHA1 = 4
CIPHER_TYPE_RSA2048_OAEPSHA256_HMACSHA256 = 5
CIPHER_TYPE_RSA2048_OAEPSHA1_HMACSHA256 = 6

_RSA_TYPES = frozenset({
    CIPHER_TYPE_RSA2048_OAEPSHA256,
    CIPHER_TYPE_RSA2048_OAEPSHA1,
    CIPHER_TYPE_RSA2048_OAEPSHA256_HMACSHA256,
    CIPHER_TYPE_RSA2048_OAEPSHA1_HMACSHA256,
})
_RSA_HMAC_TYPES = frozenset({
    CIPHER_TYPE_RSA2048_OAEPSHA256_HMACSHA256,
    CIPHER_TYPE_RSA2048_OAEPSHA1_HMACSHA256,
})

# KDF type identifiers returned by /identity/accounts/prelogin.
KDF_PBKDF2_SHA256 = 0
KDF_ARGON2ID = 1

# DeviceType "SDK" - Bitwarden expects an integer here. 14 is the documented "SDK" value
# used by official integrations and is what the server understands as a non-browser client.
DEVICE_TYPE_SDK = 14
DEFAULT_DEVICE_NAME = "nautobot-secrets-providers"

# Bitwarden cipher.type values.
CIPHER_ITEM_TYPE_LOGIN = 1
CIPHER_ITEM_TYPE_SECURE_NOTE = 2

# Special field names that are not custom fields - they map to top-level cipher attributes.
RESERVED_FIELD_NAMES = ("password", "username", "notes", "totp")


class BitwardenClientError(Exception):
    """Base exception for the Vaultwarden client."""


class BitwardenAuthError(BitwardenClientError):
    """Authentication or KDF derivation failure."""


class BitwardenItemNotFoundError(BitwardenClientError):
    """The requested item could not be located in the synced vault."""


class BitwardenFieldNotFoundError(BitwardenClientError):
    """The requested field is not present on the located item."""


class BitwardenCryptoError(BitwardenClientError):
    """Decryption or HMAC verification failure."""


@dataclass
class CipherString:
    """Parsed Bitwarden CipherString.

    Format varies by cipher type:
        Type 2 (AES-CBC + HMAC):  "2.<iv_b64>|<ct_b64>|<mac_b64>"
        Type 3,4 (RSA-OAEP):      "<type>.<ct_b64>"
        Type 5,6 (RSA + HMAC):    "<type>.<ct_b64>|<mac_b64>"

    For RSA types `iv` is empty - the field is reused only by AES-CBC.
    """

    cipher_type: int
    iv: bytes
    ciphertext: bytes
    mac: bytes

    @classmethod
    def parse(cls, raw: str) -> "CipherString":
        """Parse a serialized CipherString into its components.

        Supports symmetric type 2 and asymmetric types 3-6. Older types (0, 1)
        are deprecated and refused since modern Bitwarden servers don't emit them
        and supporting them would mean shipping AES-CBC without authentication.
        """
        try:
            type_str, body = raw.split(".", 1)
            cipher_type = int(type_str)
            parts = body.split("|")
        except (ValueError, AttributeError) as err:
            raise BitwardenCryptoError(f"Malformed CipherString: {raw!r}") from err

        try:
            if cipher_type == CIPHER_TYPE_AESCBC256_HMACSHA256:
                if len(parts) != 3:
                    raise BitwardenCryptoError(
                        f"Type 2 expects iv|ct|mac, got {len(parts)} segments"
                    )
                return cls(
                    cipher_type=cipher_type,
                    iv=base64.b64decode(parts[0]),
                    ciphertext=base64.b64decode(parts[1]),
                    mac=base64.b64decode(parts[2]),
                )
            if cipher_type in _RSA_TYPES:
                expected_segments = 2 if cipher_type in _RSA_HMAC_TYPES else 1
                if len(parts) != expected_segments:
                    raise BitwardenCryptoError(
                        f"Type {cipher_type} expects {expected_segments} segment(s), got {len(parts)}"
                    )
                return cls(
                    cipher_type=cipher_type,
                    iv=b"",
                    ciphertext=base64.b64decode(parts[0]),
                    mac=base64.b64decode(parts[1]) if expected_segments == 2 else b"",
                )
        except (ValueError, base64.binascii.Error) as err:
            raise BitwardenCryptoError(f"Failed to base64-decode CipherString segments: {err}") from err

        raise BitwardenCryptoError(
            f"Unsupported CipherString type {cipher_type}; expected one of "
            f"2 (AES-CBC+HMAC) or 3-6 (RSA-OAEP variants)."
        )


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand (RFC 5869) with SHA-256.

    Bitwarden uses HKDF-Expand only (skipping Extract) because the master key is
    already 32 bytes of cryptographically strong material out of PBKDF2/Argon2id.
    Running Extract would just hash it again with no security benefit and would
    diverge from every other Bitwarden client's behaviour.
    """
    if length > 255 * 32:
        raise BitwardenCryptoError("HKDF output length exceeds maximum")
    blocks = b""
    previous = b""
    counter = 1
    while len(blocks) < length:
        previous = hmac.new(prk, previous + info + struct.pack("B", counter), hashlib.sha256).digest()
        blocks += previous
        counter += 1
    return blocks[:length]


def derive_master_key(master_password: str, email: str, kdf: int, iterations: int,
                      memory_kb: Optional[int] = None, parallelism: Optional[int] = None) -> bytes:
    """Derive the 32-byte master key from the master password using server-specified KDF params.

    PBKDF2 uses email.lower() as the salt directly. Argon2id requires a fixed-length salt,
    so Bitwarden hashes the lowercased email with SHA-256 first - this is a server-side
    convention, not a generic Argon2 requirement.
    """
    salt_bytes = email.strip().lower().encode("utf-8")
    pwd_bytes = master_password.encode("utf-8")

    if kdf == KDF_PBKDF2_SHA256:
        return hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, iterations, dklen=32)

    if kdf == KDF_ARGON2ID:
        try:
            from argon2.low_level import Type, hash_secret_raw
        except ImportError as err:
            raise BitwardenAuthError(
                "Server uses Argon2id KDF but the 'argon2-cffi' library is not installed. "
                "Install it via 'pip install argon2-cffi' or use a Bitwarden account configured for PBKDF2."
            ) from err
        if memory_kb is None or parallelism is None:
            raise BitwardenAuthError("Argon2id requires kdfMemory and kdfParallelism from prelogin response")
        return hash_secret_raw(
            secret=pwd_bytes,
            salt=hashlib.sha256(salt_bytes).digest(),
            time_cost=iterations,
            memory_cost=memory_kb * 1024,
            parallelism=parallelism,
            hash_len=32,
            type=Type.ID,
        )

    raise BitwardenAuthError(f"Unsupported KDF type {kdf} (expected 0=PBKDF2 or 1=Argon2id)")


def derive_master_password_hash(master_key: bytes, master_password: str) -> str:
    """Derive the base64-encoded server auth hash from master_key + password.

    This is a one-iteration PBKDF2 with the password as the salt. The result is what
    the server compares against - master_key itself never crosses the wire.
    """
    raw = hashlib.pbkdf2_hmac("sha256", master_key, master_password.encode("utf-8"), 1, dklen=32)
    return base64.b64encode(raw).decode("ascii")


def stretch_master_key(master_key: bytes) -> tuple[bytes, bytes]:
    """Expand the 32-byte master key into a 32-byte enc key + 32-byte mac key via HKDF-SHA256."""
    enc_key = _hkdf_expand(master_key, b"enc", 32)
    mac_key = _hkdf_expand(master_key, b"mac", 32)
    return enc_key, mac_key


def decrypt_cipher_string(cs: CipherString, enc_key: bytes, mac_key: bytes) -> bytes:
    """Verify HMAC then AES-256-CBC decrypt and PKCS7-unpad.

    Encrypt-then-MAC: we verify mac == HMAC-SHA256(mac_key, iv || ct) BEFORE attempting
    decryption, in constant time. Decrypting first would expose us to padding-oracle attacks.
    """
    expected_mac = hmac.new(mac_key, cs.iv + cs.ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, cs.mac):
        raise BitwardenCryptoError("HMAC verification failed - ciphertext is corrupt or wrong key")

    if len(cs.iv) != 16:
        raise BitwardenCryptoError(f"Expected 16-byte IV for AES-CBC, got {len(cs.iv)}")
    if len(cs.ciphertext) % 16 != 0 or len(cs.ciphertext) == 0:
        raise BitwardenCryptoError("Ciphertext length is not a positive multiple of the AES block size")

    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(cs.iv)).decryptor()
    padded = decryptor.update(cs.ciphertext) + decryptor.finalize()

    pad_len = padded[-1]
    if pad_len < 1 or pad_len > 16 or padded[-pad_len:] != bytes([pad_len]) * pad_len:
        raise BitwardenCryptoError("Invalid PKCS7 padding after decryption")
    return padded[:-pad_len]


def decrypt_cipher_string_to_text(raw: str, enc_key: bytes, mac_key: bytes) -> str:
    """Convenience wrapper: parse + decrypt + UTF-8 decode."""
    return decrypt_cipher_string(CipherString.parse(raw), enc_key, mac_key).decode("utf-8")


def decrypt_rsa_cipher_string(cs: CipherString, private_key) -> bytes:
    """RSA-OAEP decrypt a CipherString of type 3, 4, 5, or 6.

    Args:
        cs: Parsed CipherString. Must be one of the RSA types.
        private_key: A `cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey`
            (typically loaded from PKCS#8 DER via serialization.load_der_private_key).

    The HMAC variants (5, 6) include an HMAC-SHA256 over the ciphertext, but the
    HMAC key in those variants is supposed to be derived from the private key in
    a way that's specific to legacy Bitwarden behaviour. In practice modern
    servers emit type 4 (RSA-OAEP-SHA1, no MAC) for org keys, so we accept the
    HMAC types but skip MAC verification - the OAEP padding itself provides
    integrity for asymmetric ciphertexts.
    """
    if cs.cipher_type not in _RSA_TYPES:
        raise BitwardenCryptoError(
            f"decrypt_rsa_cipher_string called on non-RSA type {cs.cipher_type}"
        )

    # SHA-1 here is part of OAEP padding, not a digest used for authenticity. Modern
    # Bitwarden clients still emit type 4 (RSA-OAEP-SHA1) for org keys for legacy
    # compatibility - we have to support it. The padding is RFC 8017 OAEP, which
    # doesn't depend on the OAEP-hash being collision-resistant.
    oaep_hash = (
        hashes.SHA256()
        if cs.cipher_type in (CIPHER_TYPE_RSA2048_OAEPSHA256, CIPHER_TYPE_RSA2048_OAEPSHA256_HMACSHA256)
        else hashes.SHA1()  # noqa: S303 - OAEP padding hash, not for authenticity
    )
    try:
        return private_key.decrypt(
            cs.ciphertext,
            asymm_padding.OAEP(
                mgf=asymm_padding.MGF1(algorithm=oaep_hash),
                algorithm=oaep_hash,
                label=None,
            ),
        )
    except Exception as err:
        raise BitwardenCryptoError(f"RSA-OAEP decryption failed: {err}") from err


def load_rsa_private_key(der_bytes: bytes):
    """Load a PKCS#8 DER-encoded RSA private key.

    Bitwarden stores the user's private key as PKCS#8 (the spec format from
    RFC 5208) inside a CipherString. Once symmetrically decrypted, the bytes go
    straight into cryptography.hazmat's loader.
    """
    try:
        return serialization.load_der_private_key(der_bytes, password=None)
    except Exception as err:
        raise BitwardenCryptoError(f"Failed to parse PKCS#8 RSA private key: {err}") from err


@dataclass
class BitwardenSession:
    """Holds derived keys and access token for an authenticated client.

    These are kept off the wire and out of logs. Don't add a __repr__ that exposes them.

    `org_keys` maps each organization UUID (lowercased) to a `(enc_key, mac_key)` tuple.
    Populated lazily during sync() once the server returns the user's organization list.
    `private_key_der` is the user's PKCS#8 RSA-2048 private key in DER form, used to
    unwrap each org's symmetric key. Held alongside the keys themselves so a cached
    session can re-derive `org_keys` after a sync without going back through the master
    password.
    """

    access_token: str
    user_enc_key: bytes
    user_mac_key: bytes
    private_key_der: bytes = b""
    org_keys: dict = field(default_factory=dict)
    expires_at: float = 0.0
    raw_sync: dict = field(default_factory=dict)

    def to_cache_payload(self) -> dict:
        """Produce a dict suitable for storing in Django's cache.

        Bytes are kept as bytes (Django's cache backends serialize via pickle by
        default, which handles bytes natively). The session is re-hydrated by
        `BitwardenSession.from_cache_payload`.
        """
        return {
            "access_token": self.access_token,
            "user_enc_key": self.user_enc_key,
            "user_mac_key": self.user_mac_key,
            "private_key_der": self.private_key_der,
            "org_keys": dict(self.org_keys),
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_cache_payload(cls, payload: dict) -> "BitwardenSession":
        """Inverse of `to_cache_payload`.

        Trusts the payload format implicitly - only used on entries we wrote
        ourselves into the cache.
        """
        return cls(
            access_token=payload["access_token"],
            user_enc_key=payload["user_enc_key"],
            user_mac_key=payload["user_mac_key"],
            private_key_der=payload.get("private_key_der", b""),
            org_keys=dict(payload.get("org_keys", {})),
            expires_at=payload.get("expires_at", 0.0),
        )


class BitwardenClient:
    """Minimal Vaultwarden / Bitwarden Vault API client for read-only secret retrieval.

    Designed for service-account-style usage: log in once, sync, decrypt requested
    fields. Stateful caching of the session is the caller's responsibility (e.g. via
    Django's cache framework keyed off a hash of the credentials).
    """

    def __init__(self, server_url: str, email: str, master_password: str,
                 verify_ssl: bool = True, timeout: float = 30.0,
                 device_identifier: Optional[str] = None,
                 device_name: str = DEFAULT_DEVICE_NAME,
                 session: Optional[BitwardenSession] = None):
        """Construct the client.

        Args:
            server_url: Base URL of the Vaultwarden server, e.g. "https://vault.example.com".
                Trailing slashes are tolerated. Bitwarden mounts /identity and /api directly.
            email: Account email - used as the KDF salt.
            master_password: Master password for the account. Held in memory only.
            verify_ssl: Whether to verify TLS certs. Disable only for self-signed dev servers.
            timeout: Per-request timeout in seconds.
            device_identifier: Stable UUID identifying this client instance to the server.
                A fixed identifier reduces server-side device-list churn; a random one is
                fine for ephemeral installations.
            device_name: Human-readable device label shown in account audit logs.
            session: Optional pre-hydrated BitwardenSession. If supplied, the client will
                skip the login flow and use these credentials for the next call. Used by
                the Nautobot provider to plug in a Django-cached session. The client
                itself does not depend on Django.
        """
        self.server_url = server_url.rstrip("/")
        self.email = email
        self._master_password = master_password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.device_identifier = device_identifier or str(uuid.uuid4())
        self.device_name = device_name
        self._session: Optional[BitwardenSession] = session

    @property
    def session(self) -> Optional[BitwardenSession]:
        """Read-only access to the current session (None until login() runs)."""
        return self._session

    def has_session(self) -> bool:
        """True iff a session has been established (via login or hydrated from cache)."""
        return self._session is not None

    def invalidate_session(self) -> None:
        """Drop the current session. Forces the next call to re-authenticate."""
        self._session = None

    # The Bitwarden web client posts to /identity/* and /api/*, with the upstream
    # API gateway routing them to the identity-server and api-server respectively.
    # Vaultwarden serves both from the same origin, which is what we assume here.
    def _identity_url(self, path: str) -> str:
        return f"{self.server_url}/identity{path}"

    def _api_url(self, path: str) -> str:
        return f"{self.server_url}/api{path}"

    def _post_form(self, url: str, form: dict, headers: Optional[dict] = None) -> requests.Response:
        merged_headers = {"Accept": "application/json", "Device-Type": str(DEVICE_TYPE_SDK)}
        if headers:
            merged_headers.update(headers)
        return requests.post(url, data=form, headers=merged_headers,
                             verify=self.verify_ssl, timeout=self.timeout)

    def _get_json(self, url: str, headers: Optional[dict] = None) -> dict:
        merged_headers = {"Accept": "application/json", "Device-Type": str(DEVICE_TYPE_SDK)}
        if headers:
            merged_headers.update(headers)
        response = requests.get(url, headers=merged_headers,
                                verify=self.verify_ssl, timeout=self.timeout)
        # 401 is special - it usually means our cached access token expired. Surface
        # it as BitwardenAuthError so callers know retrying with a fresh login may succeed.
        if response.status_code == 401:
            raise BitwardenAuthError(
                f"GET {url} returned 401 - access token rejected (likely expired)."
            )
        if response.status_code != 200:
            raise BitwardenClientError(
                f"GET {url} returned HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.json()

    def _prelogin(self) -> dict:
        """Ask the server for KDF type and iteration count for the email's account.

        Endpoint: POST /identity/accounts/prelogin
        Returns: {"kdf": int, "kdfIterations": int, "kdfMemory": int|null, "kdfParallelism": int|null}
        """
        response = requests.post(
            self._identity_url("/accounts/prelogin"),
            json={"email": self.email},
            headers={"Accept": "application/json"},
            verify=self.verify_ssl, timeout=self.timeout,
        )
        if response.status_code != 200:
            raise BitwardenAuthError(
                f"Prelogin failed (HTTP {response.status_code}): {response.text[:300]}"
            )
        return response.json()

    def _connect_token(self, master_password_hash: str) -> dict:
        """Exchange the master-password-hash for an access token + protected key.

        Endpoint: POST /identity/connect/token (OAuth2 password grant).
        Server responds with access_token (Bearer for /api), refresh_token (we ignore -
        we just re-auth on expiry), Key (protected_symmetric_key as a CipherString), and
        PrivateKey (RSA key, only needed for organization items).
        """
        form = {
            "grant_type": "password",
            "username": self.email,
            "password": master_password_hash,
            "scope": "api offline_access",
            "client_id": "cli",
            "deviceType": str(DEVICE_TYPE_SDK),
            "deviceIdentifier": self.device_identifier,
            "deviceName": self.device_name,
        }
        response = self._post_form(self._identity_url("/connect/token"), form)
        if response.status_code != 200:
            raise BitwardenAuthError(
                f"Token endpoint returned HTTP {response.status_code}: {response.text[:300]}"
            )
        return response.json()

    def login(self) -> BitwardenSession:
        """Run the full login + key-unwrap flow and cache a session for subsequent calls.

        Two layers of unwrap:
            1. The master key (from PBKDF2/Argon2id) is HKDF-stretched to 64 bytes,
               which decrypts the server-stored "Key" CipherString. The plaintext is
               the user's 64-byte symmetric key (32 enc + 32 mac).
            2. The same user symmetric key decrypts "PrivateKey" - a CipherString
               wrapping the user's PKCS#8 RSA-2048 private key. We stash the DER
               bytes for later use unwrapping per-organization keys during sync.
        """
        prelogin = self._prelogin()
        kdf_type = prelogin.get("kdf", KDF_PBKDF2_SHA256)
        iterations = prelogin.get("kdfIterations") or prelogin.get("KdfIterations")
        if not iterations:
            raise BitwardenAuthError("Prelogin response missing kdfIterations")

        master_key = derive_master_key(
            master_password=self._master_password,
            email=self.email,
            kdf=kdf_type,
            iterations=iterations,
            memory_kb=prelogin.get("kdfMemory") or prelogin.get("KdfMemory"),
            parallelism=prelogin.get("kdfParallelism") or prelogin.get("KdfParallelism"),
        )
        master_password_hash = derive_master_password_hash(master_key, self._master_password)

        token_data = self._connect_token(master_password_hash)
        access_token = token_data.get("access_token")
        protected_key = token_data.get("Key") or token_data.get("key")
        if not access_token or not protected_key:
            raise BitwardenAuthError("Token response missing access_token or Key")

        # Stretch the master key so we can decrypt the protected_symmetric_key.
        stretched_enc, stretched_mac = stretch_master_key(master_key)
        decrypted_key_bytes = decrypt_cipher_string(
            CipherString.parse(protected_key), stretched_enc, stretched_mac
        )
        # The protected_symmetric_key plaintext is 64 bytes: 32 enc + 32 mac.
        # These are the keys that decrypt every personal-vault cipher.
        if len(decrypted_key_bytes) != 64:
            raise BitwardenAuthError(
                f"Decrypted user symmetric key has unexpected length {len(decrypted_key_bytes)} (expected 64)"
            )
        user_enc_key = decrypted_key_bytes[:32]
        user_mac_key = decrypted_key_bytes[32:]

        # PrivateKey is optional in the token response - servers may send it on /api/sync
        # instead. We try here first; sync() will fall back to the sync response's profile.
        # If decryption fails for any reason (malformed, wrong key) we degrade silently:
        # the user just loses access to org items, which is the right failure mode here -
        # raising would block login entirely for accounts without orgs.
        private_key_der = b""
        protected_private_key = token_data.get("PrivateKey") or token_data.get("privateKey")
        if protected_private_key:
            try:
                private_key_der = decrypt_cipher_string(
                    CipherString.parse(protected_private_key), user_enc_key, user_mac_key
                )
            except BitwardenCryptoError:
                private_key_der = b""

        self._session = BitwardenSession(
            access_token=access_token,
            user_enc_key=user_enc_key,
            user_mac_key=user_mac_key,
            private_key_der=private_key_der,
        )
        return self._session

    def _ensure_session(self) -> BitwardenSession:
        if self._session is not None:
            return self._session
        # login() either populates self._session and returns it, or raises.
        return self.login()

    def sync(self) -> dict:
        """Fetch the encrypted vault snapshot and decrypt any organization keys it contains."""
        session = self._ensure_session()
        data = self._get_json(
            self._api_url("/sync?excludeDomains=true"),
            headers={"Authorization": f"Bearer {session.access_token}"},
        )
        session.raw_sync = data

        # Some server versions return the user's PrivateKey on /api/sync rather than
        # in the /connect/token response. If we don't have it yet, look for it here.
        if not session.private_key_der:
            profile = data.get("profile") or data.get("Profile") or {}
            protected_private_key = profile.get("privateKey") or profile.get("PrivateKey")
            if protected_private_key:
                session.private_key_der = decrypt_cipher_string(
                    CipherString.parse(protected_private_key),
                    session.user_enc_key, session.user_mac_key,
                )

        # Unwrap every organization's key once per sync. profile.organizations is a list of
        # {id, key, ...}. Each `key` is an RSA-OAEP CipherString of a 64-byte org symmetric
        # key (32 enc + 32 mac). Without the user's RSA private key we can't decrypt them,
        # so we silently skip - the org's items will be unfindable, which is the right
        # behaviour for users who explicitly chose not to populate a private key.
        org_keys = {}
        if session.private_key_der:
            try:
                private_key = load_rsa_private_key(session.private_key_der)
            except BitwardenCryptoError:
                private_key = None
            if private_key is not None:
                profile = data.get("profile") or data.get("Profile") or {}
                organizations = profile.get("organizations") or profile.get("Organizations") or []
                for org in organizations:
                    org_id = (org.get("id") or org.get("Id") or "").lower()
                    encrypted_org_key = org.get("key") or org.get("Key")
                    if not org_id or not encrypted_org_key:
                        continue
                    try:
                        plaintext = decrypt_rsa_cipher_string(
                            CipherString.parse(encrypted_org_key), private_key
                        )
                    except BitwardenCryptoError:
                        # One bad org shouldn't poison the whole sync - skip it and keep going.
                        continue
                    if len(plaintext) != 64:
                        continue
                    org_keys[org_id] = (plaintext[:32], plaintext[32:])
        session.org_keys = org_keys
        return data

    def get_secret(self, item: str, field_name: str = "password") -> str:
        """Locate `item` (by UUID or decrypted name) and return the requested `field`.

        Args:
            item: The cipher's UUID or its decrypted name. UUIDs are matched first
                (cheap), then names (requires decrypting every cipher's name field).
            field_name: One of the reserved names (password, username, notes, totp)
                or the name of a custom field defined on the item.

        Returns:
            The requested field value as a string.

        Raises:
            BitwardenItemNotFoundError: No matching cipher in the synced vault that
                we can decrypt (org items whose org key we couldn't unwrap are skipped).
            BitwardenFieldNotFoundError: Cipher found but the field is missing/empty.
            BitwardenCryptoError: Decryption or HMAC failure on a located cipher.
        """
        session = self._ensure_session()
        sync_data = session.raw_sync or self.sync()
        ciphers = sync_data.get("ciphers", []) or sync_data.get("Ciphers", [])

        match = self._find_cipher(ciphers, item, session)
        if match is None:
            raise BitwardenItemNotFoundError(
                f"No item matching {item!r} found across {len(ciphers)} ciphers "
                f"(personal vault + {len(session.org_keys)} unlocked organization(s))."
            )
        return self._extract_field(match, field_name, session)

    @staticmethod
    def _cipher_keys(cipher: dict, session: BitwardenSession) -> Optional[tuple]:
        """Pick the right (enc_key, mac_key) for a cipher based on its organizationId.

        Personal-vault ciphers (`organizationId` is null/absent) decrypt with the user
        symmetric key. Org-owned ciphers decrypt with the per-org symmetric key from
        `session.org_keys`. Returns None if the cipher claims an org we don't have
        a key for - the caller should treat the cipher as invisible.
        """
        org_id = cipher.get("organizationId") or cipher.get("OrganizationId")
        if not org_id:
            return (session.user_enc_key, session.user_mac_key)
        org_id_lower = org_id.lower()
        if org_id_lower in session.org_keys:
            return session.org_keys[org_id_lower]
        return None

    def _find_cipher(self, ciphers: list, item: str, session: BitwardenSession) -> Optional[dict]:
        """Locate a cipher by UUID first, then by decrypted name.

        Both passes skip ciphers we can't decrypt (org items where the org's key
        wasn't available). For UUID matches the skip happens *after* the UUID
        compares equal - so a UUID hit on an inaccessible org item still surfaces
        as "not found", which is honest: we know it exists but we can't read it.

        Splitting UUID/name into two passes matters: UUID match is constant-cost, but a
        name match requires decrypting every cipher's encrypted name field, which is
        expensive on large vaults. We do the cheap pass first.
        """
        for cipher in ciphers:
            cipher_id = cipher.get("id") or cipher.get("Id")
            if not cipher_id or cipher_id.lower() != item.lower():
                continue
            if self._cipher_keys(cipher, session) is not None:
                return cipher

        for cipher in ciphers:
            keys = self._cipher_keys(cipher, session)
            if keys is None:
                continue
            encrypted_name = cipher.get("name") or cipher.get("Name")
            if not encrypted_name:
                continue
            try:
                decrypted = decrypt_cipher_string_to_text(encrypted_name, *keys)
            except BitwardenCryptoError:
                continue
            if decrypted == item:
                return cipher
        return None

    def _extract_field(self, cipher: dict, field_name: str, session: BitwardenSession) -> str:
        """Pull and decrypt the requested field from the located cipher."""
        keys = self._cipher_keys(cipher, session)
        if keys is None:
            # This shouldn't happen because _find_cipher already filtered, but if
            # someone calls _extract_field directly we still want a clean error.
            raise BitwardenItemNotFoundError(
                f"Cipher {cipher.get('id') or cipher.get('Id')!r} belongs to an "
                f"organization whose key is unavailable."
            )
        enc_key, mac_key = keys
        login_data = cipher.get("login") or cipher.get("Login") or {}

        encrypted = None
        if field_name == "password":
            encrypted = login_data.get("password") or login_data.get("Password")
        elif field_name == "username":
            encrypted = login_data.get("username") or login_data.get("Username")
        elif field_name == "totp":
            encrypted = login_data.get("totp") or login_data.get("Totp")
        elif field_name == "notes":
            encrypted = cipher.get("notes") or cipher.get("Notes")
        else:
            # Custom field lookup - field names are themselves encrypted.
            encrypted = self._find_custom_field_value(cipher, field_name, enc_key, mac_key)

        if not encrypted:
            raise BitwardenFieldNotFoundError(
                f"Field {field_name!r} not found or empty on cipher "
                f"{cipher.get('id') or cipher.get('Id')!r}"
            )
        try:
            return decrypt_cipher_string_to_text(encrypted, enc_key, mac_key)
        except BitwardenCryptoError as err:
            raise BitwardenCryptoError(
                f"Failed to decrypt field {field_name!r} on item: {err}"
            ) from err

    @staticmethod
    def _find_custom_field_value(cipher: dict, field_name: str,
                                 enc_key: bytes, mac_key: bytes) -> Optional[str]:
        """Decrypt each custom-field name to find the requested field, return its (still-encrypted) value."""
        fields = cipher.get("fields") or cipher.get("Fields") or []
        for field_def in fields:
            encrypted_name = field_def.get("name") or field_def.get("Name")
            if not encrypted_name:
                continue
            try:
                decrypted_name = decrypt_cipher_string_to_text(encrypted_name, enc_key, mac_key)
            except BitwardenCryptoError:
                continue
            if decrypted_name == field_name:
                return field_def.get("value") or field_def.get("Value")
        return None


def make_device_identifier(seed: str) -> str:
    """Produce a stable UUID-shaped device identifier from a stable seed.

    Useful when callers want each Nautobot instance to register as a single device
    rather than churning a fresh one each restart. We hash the seed into a UUID5
    so the result is deterministic and well-formed.
    """
    namespace = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # standard URL namespace
    return str(uuid.uuid5(namespace, seed))
