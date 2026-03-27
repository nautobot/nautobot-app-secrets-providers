"""App UI views for Secrets Providers."""

import uuid

from django.contrib.auth.mixins import LoginRequiredMixin
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


class BitwardenCustomFieldNamesView(LoginRequiredMixin, View):
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

        secret_id = request.GET.get("secret_id", "").strip()
        if not secret_id:
            return JsonResponse({"success": False, "error": "secret_id is required."}, status=400)
        try:
            uuid.UUID(secret_id)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid secret_id format."}, status=400)
        try:
            info = BitwardenCLISecretsProvider.get_item_info(secret_id)
        except ValueError as err:
            return JsonResponse({"success": False, "error": str(err)})
        return JsonResponse({"success": True, "fields": info.get("fields", []), "name": info.get("name", "")})
