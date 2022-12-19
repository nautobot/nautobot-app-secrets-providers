"""Extra tabs for the Secret model."""
from django.urls import reverse

DETAILED_TABS_AVAILABLE = True  # Nautobot >= 1.4.0
try:
    from nautobot.apps.ui import TemplateExtension
except ImportError:
    try:
        from nautobot.extras.plugins import PluginTemplateExtension as TemplateExtension
    except ImportError:
        DETAILED_TABS_AVAILABLE = False  # Nautobot < 1.4.0

if DETAILED_TABS_AVAILABLE:
    # Enable Extra Tabs for Nautobot 1.4.0 and above

    class SecretExtraTabs(TemplateExtension):
        """Template extension to add extra tabs to the object detail tabs."""

        model = "extras.secret"

        def detail_tabs(self):
            """Extra tabs to render on a model's detail page.

            You may define extra tabs to render on a model's detail page by utilizing this method.
            Each tab is defined as a dict in a list of dicts.

            For each of the tabs defined:
            - The <title> key's value will become the tab link's title.
            - The <url> key's value is used to render the HTML link for the tab

            These tabs will be visible (in this instance) on the Secret model's detail page as
            set by the SecretExtraTabs.model attribute "extras.secret"
            """
            return [
                {
                    "title": "Check",
                    "url": reverse(
                        "plugins:nautobot_secrets_providers:check_secret_tab", kwargs={"pk": self.context["object"].pk}
                    ),
                },
            ]

    template_extensions = [SecretExtraTabs]
