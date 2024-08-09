"""Choices for Secrets Providers App."""

from nautobot.core.choices import ChoiceSet


class DelineaSecretChoices(ChoiceSet):
    """Choices for Delinea Secret Server Result."""

    SECRET_TOKEN = "token"  # noqa: S105
    SECRET_PASSWORD = "password"  # noqa: S105
    SECRET_USERNAME = "username"  # noqa: S105
    SECRET_URL = "url"  # noqa: S105
    SECRET_NOTES = "notes"  # noqa: S105

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
