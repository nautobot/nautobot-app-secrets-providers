"""Choices for Thycotic Secret Server Plugin."""
from nautobot.utilities.choices import ChoiceSet


class ThycoticSecretChoices(ChoiceSet):
    """Choices for Thycotic Secret Server Result."""

    SECRET_PASSWORD = "password"  # nosec
    SECRET_USERNAME = "username"  # nosec
    SECRET_URL = "url"  # nosec
    SECRET_NOTES = "notes"  # nosec

    CHOICES = (
        (SECRET_PASSWORD, "Password"),
        (SECRET_USERNAME, "Username"),
        (SECRET_URL, "URL"),
        (SECRET_NOTES, "Notes"),
    )
