from django.views.generic import TemplateView

from nautobot_secrets_providers import secrets


class SecretsProvidersHomeView(TemplateView):
    template_name = "nautobot_secrets_providers/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["secrets_providers"] = secrets.secrets_providers
        return ctx


class SecretsProvidersConfigView(TemplateView):
    template_name = "nautobot_secrets_providers/config.html"
