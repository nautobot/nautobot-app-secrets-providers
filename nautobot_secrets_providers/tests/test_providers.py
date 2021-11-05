"""Unit tests for Secrets Providers."""

import boto3
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, tag
from moto import mock_secretsmanager
import requests_mock

from nautobot.extras.models import Secret
from nautobot.extras.secrets import exceptions
from nautobot_secrets_providers.providers import AWSSecretsManagerSecretsProvider, HashiCorpVaultSecretsProvider


# Use the proper swappable User model
User = get_user_model()


@tag("unit")
class SecretsProviderTestCase(TestCase):
    """Base test case for Secrets Providers."""

    # Set the provider class here
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
            provider=self.provider.slug,
            parameters={"name": "hello", "region": "us-east-2", "key": "location"},
        )

    @mock_secretsmanager
    def test_retrieve_success(self):
        """Retrieve a secret successfully."""
        conn = boto3.client("secretsmanager", region_name=self.secret.parameters["region"])
        conn.create_secret(Name="hello", SecretString='{"location":"world"}')

        result = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(result, "world")

    @mock_secretsmanager
    def test_retrieve_does_not_exist(self):
        """Try and fail to retrieve a secret that doesn't exist."""
        conn = boto3.client(  # noqa pylint: disable=unused-variable
            "secretsmanager", region_name=self.secret.parameters["region"]
        )

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn("ResourceNotFoundException", exc.message)

    @mock_secretsmanager
    def test_retrieve_does_not_match(self):
        """Try and fail to retrieve the wrong secret."""
        conn = boto3.client("secretsmanager", region_name=self.secret.parameters["region"])
        conn.create_secret(Name="bogus", SecretString='{"location":"world"}')

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn("ResourceNotFoundException", exc.message)

    @mock_secretsmanager
    def test_retrieve_invalid_key(self):
        """Try and fail to retrieve the wrong secret."""
        conn = boto3.client("secretsmanager", region_name=self.secret.parameters["region"])
        conn.create_secret(Name="hello", SecretString='{"fake":"notreal"}')

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn(self.secret.parameters["key"], exc.message)


class HashiCorpVaultSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for HashiCorpVaultSecretsProvider."""

    provider = HashiCorpVaultSecretsProvider

    # Mock API response
    mock_response = {
        "request_id": "4708ebf3-3bce-b30e-0601-b192bf47af17",
        "lease_id": "",
        "renewable": False,
        "lease_duration": 0,
        "data": {
            "data": {
                "location": "world",
            },
            "metadata": {
                "created_time": "2021-10-28T22:43:47.829676011Z",
                "deletion_time": "",
                "destroyed": False,
                "version": 2,
            },
        },
        "wrap_info": None,
        "warnings": None,
        "auth": None,
    }

    def setUp(self):
        super().setUp()

        # The secret we be using.
        self.secret = Secret.objects.create(
            name="hello-hashicorp",
            slug="hello-hashicorp",
            provider=self.provider.slug,
            parameters={"path": "hello", "key": "location"},
        )
        self.test_path = "http://localhost:8200/v1/secret/data/hello"

    @requests_mock.Mocker()
    def test_retrieve_success(self, requests_mocker):
        """Retrieve a secret successfully."""
        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        response = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(self.mock_response["data"]["data"]["location"], response)

    @requests_mock.Mocker()
    def test_retrieve_invalid_parameters(self, requests_mocker):
        """Try and fail to retrieve a secret with incorrect parameters."""
        bogus_secret = Secret.objects.create(
            name="bogus-hashicorp",
            slug="bogus-hashicorp",
            provider=AWSSecretsManagerSecretsProvider,  # Wrong provider
            parameters={"name": "hello", "region": "us-east-2", "key": "hello"},  # Wrong params
        )

        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        with self.assertRaises(exceptions.SecretParametersError) as err:
            self.provider.get_value_for_secret(bogus_secret)

        exc = err.exception
        self.assertIn("path", exc.message)

    @requests_mock.Mocker()
    def test_retrieve_does_not_exist(self, requests_mocker):
        """Try and fail to retrieve a secret that doesn't exist."""
        self.secret.parameters["path"] = "bogus"
        bogus_path = self.test_path.replace("hello", "bogus")
        requests_mocker.register_uri(method="GET", url=bogus_path, status_code=404)

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn("bogus", exc.message)

    @requests_mock.Mocker()
    def test_retrieve_invalid_key(self, requests_mocker):
        """Try and fail to retrieve the wrong secret."""
        self.secret.parameters["key"] = "bogus"
        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn(self.secret.parameters["key"], exc.message)
