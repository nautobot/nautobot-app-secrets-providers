"""Unit tests for Secrets Providers."""
import os
from unittest.mock import patch, mock_open

import boto3
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, tag
from hvac import Client as HVACClient
from moto import mock_secretsmanager, mock_ssm
import requests_mock

from nautobot.extras.models import Secret
from nautobot.extras.secrets import exceptions
from nautobot_secrets_providers.providers import (
    AWSSecretsManagerSecretsProvider,
    HashiCorpVaultSecretsProvider,
    AWSSystemsManagerParameterStore,
)


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

    aws_auth_env_vars = {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
    }

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

    mock_kubernetes_auth_response = {
        "auth": {
            "client_token": "38fe9691-e623-7238-f618-c94d4e7bc674",
            "accessor": "78e87a38-84ed-2692-538f-ca8b9f400ab3",
            "policies": "default",
            "metadata": {
                "role": "some_role",
                "service_account_name": "vault-auth",
                "service_account_namespace": "default",
                "service_account_secret_name": "vault-auth-token-pd21c",
                "service_account_uid": "aa9aa8ff-98d0-11e7-9bb7-0800276d99bf",
            },
            "lease_duration": 2764800,
            "renewable": True,
        },
    }

    mock_aws_auth_response = {
        "auth": {
            "renewable": True,
            "lease_duration": 1800000,
            "metadata": {
                "role_tag_max_ttl": "0",
                "instance_id": "i-de0f1344",
                "ami_id": "ami-fce36983",
                "role": "dev-role",
                "auth_type": "ec2",
            },
            "policies": ["default", "dev"],
            "accessor": "20b89871-e6f2-1160-fb29-31c2f6d4645e",
            "client_token": "c9368254-3f21-aded-8a6f-7c818e81b17a",
        }
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
        # The secret with a mounting point we be using.
        self.secret_mounting_point = Secret.objects.create(
            name="hello-hashicorp-mntpnt",
            slug="hello-hashicorp-mntpnt",
            provider=self.provider.slug,
            parameters={"path": "hello", "key": "location", "mount_point": "mymount"},
        )
        self.test_path = "http://localhost:8200/v1/secret/data/hello"
        self.test_mountpoint_path = "http://localhost:8200/v1/mymount/data/hello"

    @requests_mock.Mocker()
    def test_retrieve_success(self, requests_mocker):
        """Retrieve a secret successfully."""
        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        response = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(self.mock_response["data"]["data"]["location"], response)

    @requests_mock.Mocker()
    def test_retrieve_mount_point_success(self, requests_mocker):
        """Retrieve a secret successfully using a custom `mount_point`."""
        requests_mocker.register_uri(method="GET", url=self.test_mountpoint_path, json=self.mock_response)

        response = self.provider.get_value_for_secret(self.secret_mounting_point)
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
        self.assertEqual(
            str(err.exception),
            'SecretParametersError: Secret "bogus-hashicorp" (provider "HashiCorpVaultSecretsProvider"): The secret parameter could not be retrieved for field \'path\'',
        )

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
        self.assertEqual(
            str(err.exception),
            'SecretValueNotFoundError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): , on get http://localhost:8200/v1/secret/data/bogus',
        )

        exc = err.exception
        self.assertIn("bogus", exc.message)

    @requests_mock.Mocker()
    def test_retrieve_invalid_key(self, requests_mocker):
        """Try and fail to retrieve the wrong secret."""
        self.secret.parameters["key"] = "bogus"
        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretValueNotFoundError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): The secret value could not be retrieved using key \'bogus\'',
        )

        exc = err.exception
        self.assertIn(self.secret.parameters["key"], exc.message)

    @requests_mock.Mocker()
    @patch("builtins.open", new_callable=mock_open, read_data="data")
    def test_get_client_k8s(self, requests_mocker, mock_file):
        """Test Kubernetes Authentication."""
        vault_url = "http://localhost:8200"
        k8s_token_path = "/some/file/path"  # nosec B105
        new_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "url": vault_url,
                    "auth_method": "kubernetes",
                    "k8s_token_path": k8s_token_path,
                },
            },
        }

        # Test without specifying a role_name
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a role name for kubernetes authentication!',
        )

        # Test with various response codes (https://www.vaultproject.io/api-docs#http-status-codes)
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["role_name"] = "some_role"
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            # Test Valid Response
            requests_mocker.register_uri(
                method="POST",
                url=f"{vault_url}/v1/auth/kubernetes/login",
                status_code=200,
                json=self.mock_kubernetes_auth_response,
            )
            hvac_client = self.provider.get_client(self.secret)
            self.assertIsInstance(hvac_client, HVACClient)

            # Test Invalid Credentials
            requests_mocker.register_uri(method="POST", url=f"{vault_url}/v1/auth/kubernetes/login", status_code=403)
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
            self.assertEqual(
                str(err.exception),
                'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault Access Denied (auth_method: kubernetes). Error: , on post http://localhost:8200/v1/auth/kubernetes/login',
            )

            # Test Invalid Request
            requests_mocker.register_uri(method="POST", url=f"{vault_url}/v1/auth/kubernetes/login", status_code=400)
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
            self.assertEqual(
                str(err.exception),
                'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault Login failed (auth_method: kubernetes). Error: , on post http://localhost:8200/v1/auth/kubernetes/login',
            )

        mock_file.assert_called_with(k8s_token_path, "r", encoding="utf-8")

    def test_valid_settings(self):
        """Test configuration validation."""
        returned_settings = self.provider.validate_vault_settings(self.secret)
        self.assertEqual(returned_settings, settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["hashicorp_vault"])

        # No nautobot_secrets_providers
        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {}}):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.validate_vault_settings(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault is not configured!',
        )

        vault_url = "http://localhost:8200"
        new_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "token": "nautobot",
                }
            }
        }

        # No url
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.validate_vault_settings(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a url',
        )

        # invalid auth_method
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["url"] = vault_url
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["auth_method"] = "invalid"
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault Auth Method invalid is invalid!',
        )

        # auth_method token but no token provided
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["auth_method"] = "token"
        del new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["token"]
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a token for token authentication!',
        )

        # auth_method kubernetes but no role_name
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["auth_method"] = "kubernetes"
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a role name for kubernetes authentication!',
        )

        # auth_method approle but no secret_id
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["auth_method"] = "approle"
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["role_id"] = "asdf"
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a role_id and/or secret_id!',
        )

        # auth_method approle but no role_id
        del new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["role_id"]
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["auth_method"] = "approle"
        new_plugins_config["nautobot_secrets_providers"]["hashicorp_vault"]["secret_id"] = "asdf"  # nosec B105
        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault configuration is missing a role_id and/or secret_id!',
        )

    @patch.dict(os.environ, aws_auth_env_vars)
    @requests_mock.Mocker()
    def test_get_client_aws(self, requests_mocker):
        """Test AWS Authentication."""
        vault_url = "http://localhost:8200"
        new_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "url": vault_url,
                    "auth_method": "aws",
                },
            },
        }

        with self.settings(PLUGINS_CONFIG=new_plugins_config):
            # Test Valid Response
            requests_mocker.register_uri(
                method="POST",
                url=f"{vault_url}/v1/auth/aws/login",
                status_code=200,
                json=self.mock_kubernetes_auth_response,
            )
            hvac_client = self.provider.get_client(self.secret)
            self.assertIsInstance(hvac_client, HVACClient)

            # Test Invalid Credentials
            requests_mocker.register_uri(method="POST", url=f"{vault_url}/v1/auth/aws/login", status_code=403)
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
            self.assertEqual(
                str(err.exception),
                'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault Access Denied (auth_method: aws). Error: , on post http://localhost:8200/v1/auth/aws/login',
            )

            # Test Invalid Request
            requests_mocker.register_uri(method="POST", url=f"{vault_url}/v1/auth/aws/login", status_code=400)
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_client(self.secret)
            self.assertEqual(
                str(err.exception),
                'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault Login failed (auth_method: aws). Error: , on post http://localhost:8200/v1/auth/aws/login',
            )


class AWSSystemsManagerParameterStoreTestCase(SecretsProviderTestCase):
    """Tests for AWSSystemsManagerParameterStore."""

    provider = AWSSystemsManagerParameterStore

    def setUp(self):
        super().setUp()
        self.secret = Secret.objects.create(
            name="hello-aws-parameterstore",
            slug="hello-aws-parameterstore",
            provider=self.provider.slug,
            parameters={"name": "hello", "region": "eu-west-3", "key": "location"},
        )

    @mock_ssm
    def test_retrieve_success(self):
        """Retrieve a secret successfully."""
        conn = boto3.client("ssm", region_name=self.secret.parameters["region"])
        conn.put_parameter(Name="hello", Type="SecureString", Value='{"location":"world"}')
        result = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(result, "world")

    @mock_ssm
    def test_retrieve_does_not_exist(self):
        """Try and fail to retrieve a secret that doesn't exist."""
        conn = boto3.client("ssm", region_name=self.secret.parameters["region"])  # noqa pylint: disable=unused-variable

        with self.assertRaises(exceptions.SecretParametersError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn("ParameterNotFound", exc.message)

    @mock_ssm
    def test_retrieve_invalid_key(self):
        """Try and fail to retrieve a secret from an existing parameter but an invalid key."""
        conn = boto3.client("ssm", region_name=self.secret.parameters["region"])
        conn.put_parameter(Name="hello", Type="SecureString", Value='{"position":"world"}')
        # Try to fetch the secret with key as locatio
        with self.assertRaises(exceptions.SecretParametersError) as err:
            self.provider.get_value_for_secret(self.secret)
        exc = err.exception
        self.assertIn(f"InvalidKeyName '{self.secret.parameters['key']}'", exc.message)

    @mock_ssm
    def test_retrieve_non_valid_json(self):
        conn = boto3.client("ssm", region_name=self.secret.parameters["region"])
        conn.put_parameter(Name="hello", Type="SecureString", Value="Non Valid JSON")

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        exc = err.exception
        self.assertIn("InvalidJson", exc.message)

    @mock_ssm
    def test_retrieve_invalid_version(self):
        """Try and fail to retrieve a parameter while specifying an invalid version|label."""
        conn = boto3.client("ssm", region_name=self.secret.parameters["region"])
        conn.put_parameter(Name="hello", Type="SecureString", Value='{"location":"world"}')
        # add a non existing version to the Nautobot secret name and try to fetch it
        self.secret.parameters["name"] += ":2"
        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)
        exc = err.exception
        self.assertIn("ParameterVersionNotFound", exc.message)
