"""Django urlpatterns declaration for nautobot_secrets_providers plugin."""
from django.urls import path

from nautobot_secrets_providers import views


app_name = "nautobot_secrets_providers"

urlpatterns = [
    path("", views.SecretsProvidersHomeView.as_view(), name="home"),
]
