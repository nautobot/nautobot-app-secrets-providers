"""Django urlpatterns declaration for nautobot_secrets_providers plugin."""
from django.urls import path

from nautobot_secrets_providers import views
from .views import IS_SECRET_CHECK_TAB_AVAILABLE


app_name = "nautobot_secrets_providers"

urlpatterns = [
    path("", views.SecretsProvidersHomeView.as_view(), name="home"),
]
if IS_SECRET_CHECK_TAB_AVAILABLE:
    urlpatterns += [
        path(
            "secret/<uuid:pk>/check/",
            views.SecretDetailNautobotSecretProvidersTabCheckView.as_view(),
            name="check_secret_tab",
        ),
    ]
