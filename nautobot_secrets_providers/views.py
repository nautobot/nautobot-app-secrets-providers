"""Plugin UI views for Secrets Providers."""

from django.views.generic import TemplateView
from nautobot.extras.models import Secret
from nautobot.extras.secrets.exceptions import SecretError

from nautobot_secrets_providers import secrets


class SecretsProvidersHomeView(TemplateView):
    """Plugin home page for Secrets Providers."""

    template_name = "nautobot_secrets_providers/home.html"

    def get_context_data(self, **kwargs):
        """Inject `secrets_providers` into template context."""
        ctx = super().get_context_data(**kwargs)
        ctx["secrets_providers"] = secrets.secrets_providers
        return ctx


def _extra_content_helper(secret):
    """Helper function to inject data into template context."""
    try:
        secret.get_value()  # type: ignore
        check_successfull = "1"
        check_message = "The secret is accessible."
    except SecretError:
        check_successfull = "0"
        check_message = "The secret is not accessible."
    return {
        "check_successfull": check_successfull,
        "check_message": check_message,
    }


# This is a workaround to stay compatible with Nautobot 1.4.x and >= 1.5.x
IS_SECRET_CHECK_TAB_AVAILABLE = True

try:
    # For Nautobot >= 1.5.x
    from nautobot.apps.views import ObjectView  # pylint: disable=ungrouped-imports

    class SecretDetailNautobotSecretProvidersTabCheckView(ObjectView):  # pylint: disable=too-few-public-methods
        """Plugin tab for Secret Detail."""

        queryset = Secret.objects.all()
        template_name = "nautobot_secrets_providers/tab_secret_detail_check.html"

        def get_extra_context(self, request, instance):  # pylint: disable=no-self-use
            """Inject `secrets` into template context."""
            return _extra_content_helper(instance)

except ImportError:
    try:
        # Stay compatible with Nautobot 1.4.x
        from nautobot.core.views import generic  # pylint: disable=ungrouped-imports

        class SecretDetailNautobotSecretProvidersTabCheckView(generic.ObjectView):
            """Plugin tab for Secret Detail."""

            queryset = Secret.objects.all()
            template_name = "nautobot_secrets_providers/tab_secret_detail_check.html"

            def get_extra_context(self, request, instance):
                """Inject `secrets` into template context."""
                return _extra_content_helper(instance)

    except ImportError:
        # No extra tab available. Check function is disabled.
        IS_SECRET_CHECK_TAB_AVAILABLE = False
