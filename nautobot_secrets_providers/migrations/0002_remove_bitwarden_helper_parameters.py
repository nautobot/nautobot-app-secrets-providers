"""Remove transient Bitwarden helper fields from stored Secret parameters."""

from django.db import migrations

BITWARDEN_PROVIDER_SLUG = "bitwarden-cli"
TRANSIENT_PARAMETER_KEYS = {
    "fetch-fields-btn",
    "fetch_fields_btn",
    "search-items-btn",
    "search-query",
    "search-run-btn",
    "search_items_btn",
    "search_query",
    "search_run_btn",
}


def remove_transient_bitwarden_helper_parameters(apps, _schema_editor):
    """Delete transient Bitwarden widget helper keys from stored Secret parameters."""
    Secret = apps.get_model("extras", "Secret")

    for secret in Secret.objects.filter(provider=BITWARDEN_PROVIDER_SLUG):
        parameters = secret.parameters
        if not isinstance(parameters, dict):
            continue

        cleaned_parameters = {key: value for key, value in parameters.items() if key not in TRANSIENT_PARAMETER_KEYS}
        if cleaned_parameters == parameters:
            continue

        secret.parameters = cleaned_parameters
        secret.save(update_fields=["parameters"])


class Migration(migrations.Migration):
    """Remove stale Bitwarden helper fields from persisted Secret parameter JSON."""

    dependencies = [
        ("nautobot_secrets_providers", "0001_update_thycotic_delinea_slug"),
        ("extras", "0132_approval_workflow_seed_data"),
    ]

    operations = [
        migrations.RunPython(remove_transient_bitwarden_helper_parameters, migrations.RunPython.noop),
    ]
