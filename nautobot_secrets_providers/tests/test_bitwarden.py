"""Unit tests for the Bitwarden Secrets Provider."""

from unittest.mock import patch

from nautobot.extras.models import Secret
from nautobot.extras.secrets import exceptions

from nautobot_secrets_providers.providers import BitwardenSecretsProvider
from nautobot_secrets_providers.tests.test_providers import SecretsProviderTestCase


class BitwardenSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for BitwardenSecretsProvider."""

    provider = BitwardenSecretsProvider

    def setUp(self):
        super().setUp()

        # The secret we be using.
        self.secret1 = Secret.objects.create(
            name="hello-bitwarden-1",
            provider=self.provider.slug,
            parameters={
                "secret_name": "example",
                "secret_id": None,
            },
        )
        self.secret2 = Secret.objects.create(
            name="hello-bitwarden-2",
            provider=self.provider.slug,
            parameters={
                "secret_name": "example_2",
                "secret_id": "8a3cb2bd-8130-5dd8-b0cf-7aa2abe6ded3",
            },
        )
        self.secret3 = Secret.objects.create(
            name="hello-bitwarden-3",
            provider=self.provider.slug,
            parameters={
                "secret_name": None,
                "secret_id": "8a3cb2bd-8130-5dd8-b0cf-7aa2abe6ded3",
            },
        )

        self.plugin_config = {
            "nautobot_secrets_providers": {
                "bitwarden": {
                    "api_url": "url1",
                    "identity_url": "url2",
                    "org_id": "8a3cb2bd-8130-5dd8-b0cf-7aa2abe6ded1",
                    "token": "8a3cb2bd-8130-5dd8-b0cf-7aa2abe6ded2",
                }
            }
        }

    @patch(
        "nautobot_secrets_providers.providers.bitwarden.BitwardenSecretsProvider.get_value_for_secret",
        return_value="world",
    )
    def test_retrieve_success(self, get_value_for_secret):
        """Retrieve a secret successfully."""
        with get_value_for_secret:
            with self.settings(PLUGINS_CONFIG=self.plugin_config):
                response = self.provider.get_value_for_secret(self.secret1)
                self.assertEqual("world", response)
                response2 = self.provider.get_value_for_secret(self.secret2)
                self.assertEqual("world", response2)
                response3 = self.provider.get_value_for_secret(self.secret3)
                self.assertEqual("world", response3)

    def test_valid_settings(self):
        valid_plugins_config = self.plugin_config["nautobot_secrets_providers"]["bitwarden"]

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            self.assertIsNone(self.provider.validate_settings(valid_plugins_config, self.secret1))

    def test_invalid_settings(self):
        invalid_plugins_config = {
            "nautobot_secrets_providers": {
                "bitwarden": {
                    "example": {},
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=invalid_plugins_config):
            with self.assertRaises(exceptions.SecretParametersError):
                self.provider.validate_settings(invalid_plugins_config, self.secret1)
