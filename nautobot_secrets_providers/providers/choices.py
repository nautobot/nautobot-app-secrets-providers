"""Choices for Thycotic Secret Server Plugin."""
from nautobot.utilities.choices import ChoiceSet


class ThycoticSecretChoices(ChoiceSet):
    """Choices for Thycotic Secret Server Result."""

    SECRET_TOKEN = "token"  # nosec
    SECRET_PASSWORD = "password"  # nosec
    SECRET_USERNAME = "username"  # nosec
    SECRET_URL = "url"  # nosec
    SECRET_NOTES = "notes"  # nosec

    CHOICES = (
        (SECRET_TOKEN, "Token"),
        (SECRET_PASSWORD, "Password"),
        (SECRET_USERNAME, "Username"),
        (SECRET_URL, "URL"),
        (SECRET_NOTES, "Notes"),
    )


class HashicorpKVVersionChoices(ChoiceSet):
    """Choices for Hashicorp KV Version."""

    KV_VERSION_1 = "v1"
    KV_VERSION_2 = "v2"

    CHOICES = (
        (KV_VERSION_1, "V1"),
        (KV_VERSION_2, "V2"),
    )
