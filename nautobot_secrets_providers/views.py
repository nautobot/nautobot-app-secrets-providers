"""App UI views for Secrets Providers."""

import uuid
from typing import cast

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView


class SecretsProvidersHomeView(LoginRequiredMixin, TemplateView):
    """App home page for Secrets Providers."""

    template_name = "nautobot_secrets_providers/home.html"

    def get_context_data(self, **kwargs):
        """Inject `secrets_providers` into template context."""
        from nautobot_secrets_providers import secrets  # pylint: disable=import-outside-toplevel

        ctx = super().get_context_data(**kwargs)
        ctx["secrets_providers"] = secrets.secrets_providers
        ctx["title"] = "Secrets Providers Home"
        return ctx


def _validate_bitwarden_secret_id(secret_id: str) -> tuple[str | None, JsonResponse | None]:
    """Validate and normalize a Bitwarden item UUID from a query parameter."""
    normalized_secret_id = secret_id.strip()
    if not normalized_secret_id:
        return None, JsonResponse({"success": False, "error": "secret_id is required."}, status=400)
    try:
        uuid.UUID(normalized_secret_id)
    except ValueError:
        return None, JsonResponse({"success": False, "error": "Invalid secret_id format."}, status=400)
    return normalized_secret_id, None


class BitwardenSecretPermissionRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Require Secret view access before allowing Bitwarden helper API calls."""

    permission_required = "extras.view_secret"


class BitwardenItemInfoView(BitwardenSecretPermissionRequiredMixin, View):
    """AJAX endpoint that returns item metadata for a given Bitwarden item ID."""

    def get(self, request, *args, **kwargs):
        """Return item metadata used by the Bitwarden widget."""
        from nautobot_secrets_providers.providers.bitwarden import (  # pylint: disable=import-outside-toplevel
            BitwardenCLISecretsProvider,
        )

        secret_id, error_response = _validate_bitwarden_secret_id(request.GET.get("secret_id", ""))
        if error_response is not None:
            return error_response
        secret_id = cast(str, secret_id)

        try:
            info = BitwardenCLISecretsProvider.get_item_info(secret_id)
        except ValueError as err:
            return JsonResponse({"success": False, "error": str(err)})

        return JsonResponse(
            {
                "success": True,
                "name": info.get("name", ""),
                "fields": info.get("fields", []),
                "item_type": info.get("item_type"),
                "allowed_secret_fields": info.get("allowed_secret_fields", []),
            }
        )


class BitwardenCustomFieldNamesView(BitwardenSecretPermissionRequiredMixin, View):
    """AJAX endpoint that returns the custom field names for a given Bitwarden item ID.

    Used by the ParametersForm to populate field name suggestions without requiring
    the user to know the exact names in advance.
    Only performs a Bitwarden API call when the user explicitly clicks the form button.
    """

    def get(self, request, *args, **kwargs):
        """Return JSON list of custom field names from the given Bitwarden item."""
        from nautobot_secrets_providers.providers.bitwarden import (  # pylint: disable=import-outside-toplevel
            BitwardenCLISecretsProvider,
        )

        secret_id, error_response = _validate_bitwarden_secret_id(request.GET.get("secret_id", ""))
        if error_response is not None:
            return error_response
        secret_id = cast(str, secret_id)
        try:
            info = BitwardenCLISecretsProvider.get_item_info(secret_id)
        except ValueError as err:
            return JsonResponse({"success": False, "error": str(err)})
        return JsonResponse({"success": True, "fields": info.get("fields", [])})


class BitwardenItemSearchView(BitwardenSecretPermissionRequiredMixin, View):
    """AJAX endpoint to search Bitwarden items and return IDs and names."""

    def get(self, request, *args, **kwargs):
        """Return JSON search results for Bitwarden item lookup by text."""
        from nautobot_secrets_providers.providers.bitwarden import (  # pylint: disable=import-outside-toplevel
            BitwardenCLISecretsProvider,
        )

        search_text = request.GET.get("search", "").strip()
        if len(search_text) < 2:
            return JsonResponse(
                {"success": False, "error": "Search text must be at least 2 characters."},
                status=400,
            )

        try:
            items = BitwardenCLISecretsProvider.search_items(search_text)
        except ValueError as err:
            return JsonResponse({"success": False, "error": str(err)})

        return JsonResponse({"success": True, "items": items})
