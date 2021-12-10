"""Plugin UI views for Secrets Providers."""

from django.views.generic import TemplateView

from nautobot_secrets_providers import secrets


class SecretsProvidersHomeView(TemplateView):
    """Plugin home page for Secrets Providers."""

    template_name = "nautobot_secrets_providers/home.html"

    def get_context_data(self, **kwargs):
        """Inject `secrets_providers` into template context."""
        ctx = super().get_context_data(**kwargs)
        ctx["secrets_providers"] = secrets.secrets_providers
        return ctx
