"""Choices for Thycotic Secret Server Plugin."""

from nautobot.core.choices import ChoiceSet


class ThycoticSecretChoices(ChoiceSet):
    """Choices for Thycotic Secret Server Result."""

    SECRET_TOKEN = "token"  # nosec
    SECRET_PASSWORD = "password"  # nosec
    SECRET_USERNAME = "username"  # nosec
    SECRET_URL = "url"  # nosec
    SECRET_NOTES = "notes"  # nosec
    SECRET_PASSWORD1 = "password-1"  # nosec
    SECRET_PASSWORD2 = "password-2"  # nosec

    CHOICES = (
        (SECRET_TOKEN, "Token"),
        (SECRET_PASSWORD, "Password"),
        (SECRET_USERNAME, "Username"),
        (SECRET_URL, "URL"),
        (SECRET_NOTES, "Notes"),
        (SECRET_PASSWORD1, "Password 1"),
        (SECRET_PASSWORD2, "Password 2"),
    )


class HashicorpKVVersionChoices(ChoiceSet):
    """Choices for Hashicorp KV Version."""

    KV_VERSION_1 = "v1"
    KV_VERSION_2 = "v2"

    CHOICES = (
        (KV_VERSION_1, "V1"),
        (KV_VERSION_2, "V2"),
    )
