"""Signal handlers for nautobot_secrets_providers app."""

from django.db.models.signals import pre_save
from django.dispatch import receiver
from nautobot.extras.models import Secret


@receiver(pre_save, sender=Secret)
def sanitize_bitwarden_secret_parameters(sender, instance, raw=False, using=None, update_fields=None, **kwargs):  # pylint: disable=unused-argument
    """Automatically sanitize Bitwarden Secret parameters before save.

    This signal handler ensures that all Bitwarden secret parameters are cleaned
    whenever a Secret is saved, regardless of the code path (form, API, bulk edit, etc.).
    Transient UI fields are always removed and canonical keys are preserved.

    Args:
        sender: The model class.
        instance: The Secret instance being saved.
        raw: Whether this is a raw save (direct database).
        using: The database being used.
        update_fields: Specific fields being updated.
        **kwargs: Additional keyword arguments.
    """
    # Import lazily to avoid import cycles during app initialization.
    from nautobot_secrets_providers.providers.bitwarden import (  # pylint: disable=import-outside-toplevel
        BitwardenCLISecretsProvider,
    )

    # Only sanitize if this is a Bitwarden provider secret
    if instance.provider != BitwardenCLISecretsProvider.slug:
        return

    # Only sanitize actual parameters dicts, skip raw saves
    if raw or not isinstance(instance.parameters, dict):
        return

    # Sanitize the parameters to remove transient UI fields
    instance.parameters = BitwardenCLISecretsProvider.sanitize_parameters(instance.parameters)
