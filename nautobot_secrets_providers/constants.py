"""Constants for Bitwarden CLI provider behavior and field mappings."""

REQUEST_TIMEOUT = 15
BITWARDEN_ITEM_ENDPOINT_TEMPLATE = "/object/item/{secret_id}"
BITWARDEN_LIST_ITEMS_ENDPOINT = "/list/object/items"
BITWARDEN_RETRY_TOTAL = 3
BITWARDEN_RETRY_BACKOFF = 0.3
BITWARDEN_CACHE_TTL_SECONDS = 0
BITWARDEN_WIDGET_JS_PATH = "nautobot_secrets_providers/bitwarden_widget.js"

BITWARDEN_PARAMETER_KEYS = {
    "secret_id",
    "secret_field",
    "custom_field_name",
}

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

BITWARDEN_COMMON_ALLOWED_FIELDS = {"notes", "custom"}

BITWARDEN_ITEM_TYPE_ALLOWED_FIELDS = {
    1: set(LOGIN_FIELDS),
    2: set(),
    3: set(CARD_FIELDS),
    4: set(IDENTITY_FIELDS),
    5: set(SSHKEY_FIELDS),
}
