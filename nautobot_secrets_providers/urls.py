"""Django urlpatterns declaration for nautobot_secrets_providers app."""

from django.urls import path
from django.templatetags.static import static
from django.views.generic import RedirectView

from nautobot_secrets_providers import views


app_name = "nautobot_secrets_providers"

urlpatterns = [
    path("", views.SecretsProvidersHomeView.as_view(), name="home"),
    path("docs/", RedirectView.as_view(url=static("nautobot_secrets_providers/docs/index.html")), name="docs"),
]
