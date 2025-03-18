"""Django urlpatterns declaration for nautobot_secrets_providers app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter

from nautobot_secrets_providers import views

app_name = "nautobot_secrets_providers"
router = NautobotUIViewSetRouter()

# Here is an example of how to register a viewset, you will want to replace views.NautobotSecretsProvidersUIViewSet with your viewset
# router.register("nautobot_secrets_providers", views.NautobotSecretsProvidersUIViewSet)

urlpatterns = [
    path("", views.SecretsProvidersHomeView.as_view(), name="home"),
    path("docs/", RedirectView.as_view(url=static("nautobot_secrets_providers/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
