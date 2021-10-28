"""Unit tests for nautobot_secrets_providers Secrets Providers."""

import boto3
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, tag
from moto import mock_secretsmanager

from nautobot.extras.models import Secret
from nautobot_secrets_providers.providers import AWSSecretsManagerSecretsProvider

# Use the proper swappable User model
User = get_user_model()


@tag("unit")
class SecretsProviderTestCase(TestCase):

    provider = None

    def setUp(self):
        """Create a secret for use with testing."""
        # Create the test user and make it a BOSS.
        self.user = User.objects.create(username="testuser", is_superuser=True)

        # Initialize the test client
        self.client = Client()

        # Force login explicitly with the first-available backend
        self.client.force_login(self.user)


class AWSSecretsManagerSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for AWSSecretsManagerSecretsProvider."""

    provider = AWSSecretsManagerSecretsProvider

    def setUp(self):
        super().setUp()

        # The secret we be using.
        self.secret = Secret.objects.create(
            name="hello-aws",
            slug="hello-aws",
            provider="aws-secrets-manager",
            parameters={"name": "hello", "region": "us-east-2", "key": "hello"},
        )

    @mock_secretsmanager
    def test_retrieve_success(self):
        """Retrieve a secret successfully."""
        conn = boto3.client("secretsmanager", region_name="us-east-2")
        conn.create_secret(Name="hello", SecretString='{"hello":"world"}')

        result = self.provider.get_value_for_secret(self.secret)
        self.assertEquals(result, "world")
