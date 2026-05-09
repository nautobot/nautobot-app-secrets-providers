"""Seed a running Vaultwarden container with test accounts and items.

This script registers two accounts (one PBKDF2-SHA256, one Argon2id), creates
personal-vault items in each, creates an organization for the PBKDF2 account,
and adds an org-owned cipher to it. It writes a `fixtures.json` file the
integration test runner reads to know what to retrieve.

It mirrors the *encryption* side of the Bitwarden Vault API, intentionally
re-implementing what `_vaultwarden_client.py` does on the decryption side. Two
implementations of the same crypto under the same roof catches asymmetric bugs
(e.g. swapped enc/mac keys would round-trip here but break against a real
client - or vice versa).

Run via:
    make seed     (recommended - handles uv run + deps)
    OR: uv run --with cryptography --with argon2-cffi --with requests \\
            python seed_vault.py
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymm_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ---------------------------------------------------------------------------
# Crypto primitives (encryption side - mirrors the client's decryption side)
# ---------------------------------------------------------------------------

KDF_PBKDF2 = 0
KDF_ARGON2ID = 1


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand (RFC 5869) with SHA-256.

    Same implementation as the client's `_hkdf_expand` - kept inline rather than
    imported so this file can be reasoned about as a self-contained crypto unit.
    """
    blocks = b""
    previous = b""
    counter = 1
    while len(blocks) < length:
        previous = hmac.new(prk, previous + info + struct.pack("B", counter), hashlib.sha256).digest()
        blocks += previous
        counter += 1
    return blocks[:length]


def derive_master_key(password: str, email: str, kdf: int, iterations: int,
                      memory_kb: Optional[int] = None,
                      parallelism: Optional[int] = None) -> bytes:
    """Derive the 32-byte master key. PBKDF2-SHA256 or Argon2id."""
    salt = email.strip().lower().encode("utf-8")
    pwd = password.encode("utf-8")
    if kdf == KDF_PBKDF2:
        return hashlib.pbkdf2_hmac("sha256", pwd, salt, iterations, dklen=32)
    if kdf == KDF_ARGON2ID:
        from argon2.low_level import Type, hash_secret_raw
        return hash_secret_raw(
            secret=pwd,
            salt=hashlib.sha256(salt).digest(),
            time_cost=iterations,
            memory_cost=memory_kb * 1024,
            parallelism=parallelism,
            hash_len=32,
            type=Type.ID,
        )
    raise ValueError(f"unknown kdf {kdf}")


def derive_auth_hash(master_key: bytes, password: str) -> str:
    """One-iteration PBKDF2 of the master key, salted with the password.

    This is what crosses the wire as `masterPasswordHash`. The master key itself
    never leaves the client.
    """
    raw = hashlib.pbkdf2_hmac("sha256", master_key, password.encode("utf-8"), 1, dklen=32)
    return base64.b64encode(raw).decode("ascii")


def stretch(master_key: bytes) -> tuple[bytes, bytes]:
    """HKDF-Expand stretch: master_key -> (enc_key, mac_key) for AES-CBC + HMAC."""
    return _hkdf_expand(master_key, b"enc", 32), _hkdf_expand(master_key, b"mac", 32)


def aes_cbc_hmac_encrypt(plaintext: bytes, enc_key: bytes, mac_key: bytes) -> str:
    """Produce a Bitwarden CipherString of type 2 (AES-CBC-256 + HMAC-SHA256)."""
    iv = secrets.token_bytes(16)
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)
    encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    mac = hmac.new(mac_key, iv + ct, hashlib.sha256).digest()
    return f"2.{base64.b64encode(iv).decode()}|{base64.b64encode(ct).decode()}|{base64.b64encode(mac).decode()}"


def rsa_oaep_sha1_encrypt(plaintext: bytes, public_key) -> str:
    """RSA-OAEP-SHA1 encrypt and produce a CipherString of type 4.

    SHA-1 here is OAEP padding hash, not for authenticity. This is what real
    Bitwarden servers emit for org keys; we mirror the format.
    """
    ct = public_key.encrypt(
        plaintext,
        asymm_padding.OAEP(
            mgf=asymm_padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303 - OAEP padding
            algorithm=hashes.SHA1(),  # noqa: S303 - OAEP padding
            label=None,
        ),
    )
    return f"4.{base64.b64encode(ct).decode()}"


# ---------------------------------------------------------------------------
# Account + vault data structures
# ---------------------------------------------------------------------------

@dataclass
class AccountKeys:
    """Everything we derive client-side at registration time."""

    email: str
    password: str
    kdf: int
    iterations: int
    memory_kb: Optional[int]
    parallelism: Optional[int]
    user_enc_key: bytes = b""
    user_mac_key: bytes = b""
    rsa_private_key: object = None
    rsa_public_key: object = None
    auth_hash: str = ""
    protected_user_key: str = ""  # CipherString
    protected_private_key: str = ""  # CipherString
    public_key_b64: str = ""
    access_token: str = ""

    def derive(self) -> None:
        """Generate per-user secrets and pre-compute everything the server expects."""
        master_key = derive_master_key(
            self.password, self.email, self.kdf, self.iterations,
            self.memory_kb, self.parallelism,
        )
        self.auth_hash = derive_auth_hash(master_key, self.password)

        # User symmetric key (random 32+32) - this decrypts every personal cipher.
        self.user_enc_key = secrets.token_bytes(32)
        self.user_mac_key = secrets.token_bytes(32)
        stretched_enc, stretched_mac = stretch(master_key)
        self.protected_user_key = aes_cbc_hmac_encrypt(
            self.user_enc_key + self.user_mac_key, stretched_enc, stretched_mac
        )

        # RSA-2048 keypair - private key is wrapped with the user symmetric key.
        # Public key is sent in the clear (it's a public key, after all).
        self.rsa_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.rsa_public_key = self.rsa_private_key.public_key()
        priv_der = self.rsa_private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.protected_private_key = aes_cbc_hmac_encrypt(
            priv_der, self.user_enc_key, self.user_mac_key
        )
        pub_der = self.rsa_public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_b64 = base64.b64encode(pub_der).decode("ascii")

    def encrypt_str(self, value: str, enc_key: Optional[bytes] = None,
                    mac_key: Optional[bytes] = None) -> str:
        """Encrypt a string with the user (or supplied) symmetric key."""
        ek = enc_key if enc_key is not None else self.user_enc_key
        mk = mac_key if mac_key is not None else self.user_mac_key
        return aes_cbc_hmac_encrypt(value.encode("utf-8"), ek, mk)


@dataclass
class TestVault:
    """The seeded fixture - everything the integration test runner needs to know."""

    server_url: str
    pbkdf2_account: dict = field(default_factory=dict)
    argon2id_account: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HTTP operations against Vaultwarden
# ---------------------------------------------------------------------------

def wait_for_server(base_url: str, timeout_seconds: int = 30) -> None:
    """Poll /alive until the server responds or we time out."""
    deadline = time.time() + timeout_seconds
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/alive", timeout=2)
            if r.status_code == 200:
                return
        except requests.RequestException as err:
            last_err = err
        time.sleep(0.5)
    raise RuntimeError(f"Vaultwarden did not become ready within {timeout_seconds}s: {last_err}")


class VaultAlreadySeededError(RuntimeError):
    """Raised when a registration fails because the account already exists.

    Surfaces a clearly actionable message rather than the raw 400 response so
    `make seed` failures are easy to diagnose.
    """


def register_account(base_url: str, account: AccountKeys, name: str) -> None:
    """Register a fresh account against /identity/accounts/register."""
    payload = {
        "email": account.email,
        "name": name,
        "masterPasswordHash": account.auth_hash,
        "masterPasswordHint": "",
        "key": account.protected_user_key,
        "keys": {
            "publicKey": account.public_key_b64,
            "encryptedPrivateKey": account.protected_private_key,
        },
        "kdf": account.kdf,
        "kdfIterations": account.iterations,
    }
    if account.kdf == KDF_ARGON2ID:
        payload["kdfMemory"] = account.memory_kb
        payload["kdfParallelism"] = account.parallelism

    r = requests.post(
        f"{base_url}/identity/accounts/register",
        json=payload,
        timeout=10,
    )
    if r.status_code in (200, 204):
        return
    # Vaultwarden returns 400 with "user already exists" when re-registering. We
    # detect this and surface the run-clean-then-retry guidance, which is the
    # right human action since the subsequent items would conflict anyway.
    if r.status_code == 400 and "already exists" in r.text:
        raise VaultAlreadySeededError(
            f"Account {account.email} already exists. The vault has been seeded before. "
            f"Run `make clean && make all` to start over from an empty vault."
        )
    raise RuntimeError(f"register failed for {account.email}: HTTP {r.status_code}: {r.text[:300]}")


def login(base_url: str, account: AccountKeys) -> None:
    """OAuth password-grant login. Stashes access_token on the account."""
    form = {
        "grant_type": "password",
        "username": account.email,
        "password": account.auth_hash,
        "scope": "api offline_access",
        "client_id": "cli",
        "deviceType": "14",
        "deviceIdentifier": str(uuid.uuid4()),
        "deviceName": "nautobot-secrets-seed",
    }
    r = requests.post(
        f"{base_url}/identity/connect/token",
        data=form,
        headers={"Accept": "application/json"},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login failed for {account.email}: HTTP {r.status_code}: {r.text[:300]}")
    account.access_token = r.json()["access_token"]


def create_login_cipher(base_url: str, account: AccountKeys, *,
                        name: str, username: str, password: str,
                        notes: Optional[str] = None,
                        custom_fields: Optional[list[tuple[str, str]]] = None,
                        organization_id: Optional[str] = None,
                        org_enc_key: Optional[bytes] = None,
                        org_mac_key: Optional[bytes] = None,
                        collection_ids: Optional[list[str]] = None) -> str:
    """POST a Login-type cipher and return its UUID.

    For org-owned items, encrypt fields with the org's symmetric key (org_enc_key,
    org_mac_key) instead of the user's. The server stores the ciphertext as-is;
    only the right key can decrypt it later.
    """
    use_org = organization_id is not None
    ek = org_enc_key if use_org else account.user_enc_key
    mk = org_mac_key if use_org else account.user_mac_key

    cipher = {
        "type": 1,  # Login
        "name": aes_cbc_hmac_encrypt(name.encode("utf-8"), ek, mk),
        "notes": (aes_cbc_hmac_encrypt(notes.encode("utf-8"), ek, mk) if notes else None),
        "favorite": False,
        "organizationId": organization_id,
        "folderId": None,
        "login": {
            "username": aes_cbc_hmac_encrypt(username.encode("utf-8"), ek, mk),
            "password": aes_cbc_hmac_encrypt(password.encode("utf-8"), ek, mk),
            "uris": [],
            "totp": None,
        },
        "fields": [
            {
                "name": aes_cbc_hmac_encrypt(fn.encode("utf-8"), ek, mk),
                "value": aes_cbc_hmac_encrypt(fv.encode("utf-8"), ek, mk),
                "type": 0,
            }
            for fn, fv in (custom_fields or [])
        ],
        "secureNote": None,
        "card": None,
        "identity": None,
    }

    headers = {"Authorization": f"Bearer {account.access_token}"}
    if use_org:
        # Org-owned ciphers go through /api/ciphers/create with the cipher AND
        # the list of collections to assign it to.
        body = {"cipher": cipher, "collectionIds": collection_ids or []}
        r = requests.post(f"{base_url}/api/ciphers/create", json=body, headers=headers, timeout=10)
    else:
        r = requests.post(f"{base_url}/api/ciphers", json=cipher, headers=headers, timeout=10)

    if r.status_code not in (200, 201):
        raise RuntimeError(f"cipher create failed: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["id"]


def create_organization(base_url: str, account: AccountKeys, *,
                        org_name: str) -> tuple[str, str, bytes, bytes]:
    """Create an organization. Returns (org_id, default_collection_id, org_enc_key, org_mac_key).

    Vaultwarden auto-creates a default collection at org-creation time and includes
    its UUID in the response. We need it to assign org-owned ciphers somewhere.
    """
    org_enc_key = secrets.token_bytes(32)
    org_mac_key = secrets.token_bytes(32)
    # The org's symmetric key is wrapped with the user's RSA public key so only
    # the user (and other authorized members, when invited) can read it.
    wrapped_org_key = rsa_oaep_sha1_encrypt(org_enc_key + org_mac_key, account.rsa_public_key)

    # Each org also gets its own RSA keypair (for member-key wrapping).
    org_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    org_pub = org_priv.public_key()
    org_priv_der = org_priv.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    org_pub_der = org_pub.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    org_priv_wrapped = aes_cbc_hmac_encrypt(org_priv_der, org_enc_key, org_mac_key)

    payload = {
        "name": org_name,
        "billingEmail": account.email,
        "key": wrapped_org_key,
        "keys": {
            "publicKey": base64.b64encode(org_pub_der).decode("ascii"),
            "encryptedPrivateKey": org_priv_wrapped,
        },
        "collectionName": aes_cbc_hmac_encrypt(b"Default Collection", org_enc_key, org_mac_key),
        "planType": 0,
    }
    headers = {"Authorization": f"Bearer {account.access_token}"}
    r = requests.post(f"{base_url}/api/organizations", json=payload, headers=headers, timeout=10)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"org create failed: HTTP {r.status_code}: {r.text[:300]}")
    org = r.json()
    org_id = org["id"]

    # Find the default collection by syncing - the org-create response itself doesn't
    # always include the collection list, but /api/sync does.
    sync = requests.get(
        f"{base_url}/api/sync?excludeDomains=true",
        headers=headers, timeout=10,
    ).json()
    collections = sync.get("collections") or sync.get("Collections") or []
    org_collections = [c for c in collections
                       if (c.get("organizationId") or c.get("OrganizationId")) == org_id]
    if not org_collections:
        raise RuntimeError(f"no default collection found for org {org_id}")
    default_collection_id = org_collections[0]["id"]

    return org_id, default_collection_id, org_enc_key, org_mac_key


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def seed(base_url: str, fixtures_path: Path) -> None:
    print(f"[seed] waiting for {base_url}/alive ...")
    wait_for_server(base_url)

    # --- PBKDF2 account (default for compatibility) ---
    pbkdf2 = AccountKeys(
        email="pbkdf2-test@example.com",
        password="pbkdf2-master-password-1",  # nosec - test fixture
        kdf=KDF_PBKDF2,
        iterations=600000,
        memory_kb=None,
        parallelism=None,
    )
    pbkdf2.derive()
    print(f"[seed] registering PBKDF2 account: {pbkdf2.email}")
    register_account(base_url, pbkdf2, name="PBKDF2 Test User")
    login(base_url, pbkdf2)

    pbkdf2_personal_id = create_login_cipher(
        base_url, pbkdf2,
        name="Datacenter Router",
        username="dc-admin",
        password="datacenter-secret-1",  # nosec
        notes="Use only via jumphost",
        custom_fields=[("snmp_community", "private-readwrite")],
    )
    print(f"[seed]   created personal cipher {pbkdf2_personal_id}")

    org_id, collection_id, org_enc, org_mac = create_organization(
        base_url, pbkdf2, org_name="Test Organization",
    )
    print(f"[seed]   created org {org_id} with collection {collection_id}")

    pbkdf2_org_id = create_login_cipher(
        base_url, pbkdf2,
        name="Org-Owned Firewall",
        username="fw-admin",
        password="firewall-secret-99",  # nosec
        organization_id=org_id,
        org_enc_key=org_enc,
        org_mac_key=org_mac,
        collection_ids=[collection_id],
    )
    print(f"[seed]   created org cipher {pbkdf2_org_id}")

    # --- Argon2id account ---
    argon2 = AccountKeys(
        email="argon2id-test@example.com",
        password="argon2id-master-password-2",  # nosec
        kdf=KDF_ARGON2ID,
        iterations=3,
        memory_kb=64,  # 64 MiB
        parallelism=4,
    )
    argon2.derive()
    print(f"[seed] registering Argon2id account: {argon2.email}")
    register_account(base_url, argon2, name="Argon2id Test User")
    login(base_url, argon2)

    argon2_personal_id = create_login_cipher(
        base_url, argon2,
        name="Argon2 Item",
        username="argon2-user",
        password="argon2-secret-3",  # nosec
    )
    print(f"[seed]   created personal cipher {argon2_personal_id}")

    fixtures = {
        "server_url": base_url,
        "accounts": {
            "pbkdf2": {
                "email": pbkdf2.email,
                "master_password": pbkdf2.password,
                "kdf": "pbkdf2",
                "personal_item": {
                    "id": pbkdf2_personal_id,
                    "name": "Datacenter Router",
                    "username": "dc-admin",
                    "password": "datacenter-secret-1",
                    "notes": "Use only via jumphost",
                    "custom_fields": {"snmp_community": "private-readwrite"},
                },
                "organization": {
                    "id": org_id,
                    "name": "Test Organization",
                    "item": {
                        "id": pbkdf2_org_id,
                        "name": "Org-Owned Firewall",
                        "username": "fw-admin",
                        "password": "firewall-secret-99",
                    },
                },
            },
            "argon2id": {
                "email": argon2.email,
                "master_password": argon2.password,
                "kdf": "argon2id",
                "personal_item": {
                    "id": argon2_personal_id,
                    "name": "Argon2 Item",
                    "username": "argon2-user",
                    "password": "argon2-secret-3",
                },
            },
        },
    }
    fixtures_path.write_text(json.dumps(fixtures, indent=2))
    print(f"[seed] wrote {fixtures_path}")
    print("[seed] DONE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=os.environ.get("VAULTWARDEN_DOMAIN", "http://localhost:18080"))
    parser.add_argument("--fixtures", default="fixtures.json", type=Path)
    args = parser.parse_args()
    try:
        seed(args.server, args.fixtures)
    except Exception as err:  # noqa: BLE001
        print(f"[seed] ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
