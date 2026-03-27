"""Unit tests for Secrets Providers."""

# Tests in this file are intentionally large; relax the too-many-lines check.
# pylint: disable=C0302

import json
import os
from unittest.mock import mock_open, patch

import boto3
import requests
import requests_mock
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, tag
from django.urls import reverse
from hvac import Client as HVACClient
from moto import mock_secretsmanager, mock_ssm
from nautobot.extras.models import Secret
from nautobot.extras.secrets import exceptions

from nautobot_secrets_providers.providers import (
    AWSSecretsManagerSecretsProvider,
    AWSSystemsManagerParameterStore,
    BitwardenCLISecretsProvider,
    HashiCorpVaultSecretsProvider,
    OnePasswordSecretsProvider,
)
from nautobot_secrets_providers.providers.choices import HashicorpKVVersionChoices
from nautobot_secrets_providers.providers.hashicorp import vault_choices
from nautobot_secrets_providers.providers.one_password import vault_choices as one_password_vault_choices

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
            provider=self.provider.slug,
            parameters={
                "path": "hello",
                "key": "location",
                "kv_version": HashicorpKVVersionChoices.KV_VERSION_2,
            },
        )
        # The secret with a mounting point we be using.
        self.secret_mounting_point = Secret.objects.create(
            name="hello-hashicorp-mntpnt",
            provider=self.provider.slug,
            parameters={
                "path": "hello",
                "key": "location",
                "mount_point": "mymount",
                "kv_version": HashicorpKVVersionChoices.KV_VERSION_2,
            },
        )
        self.test_path = "http://localhost:8200/v1/secret/data/hello"
        self.test_mountpoint_path = "http://localhost:8200/v1/mymount/data/hello"
        self.secret_configuration = Secret.objects.create(
            name="hello-hashicorp-configuration",
            provider=self.provider.slug,
            parameters={
                "path": "hello",
                "key": "location",
                "vault": "example",
            },
        )

    @requests_mock.Mocker()
    def test_v1(self, requests_mocker):
        mock_kv_v1_response = {
            "request_id": "f0185257-af7a-f550-2d9a-ada457a70e17",
            "lease_id": "",
            "renewable": False,
            "lease_duration": 0,
            "data": {
                "location": "world",
            },
            "wrap_info": None,
            "warnings": None,
            "auth": None,
        }
        kv_v1_test_path = "http://localhost:8200/v1/secret/hello"
        kv_v1_test_mountpoint_path = "http://localhost:8200/v1/mymount/hello"
        kv_v1_secret = Secret.objects.create(
            name="hello-hashicorp-v1",
            provider=self.provider.slug,
            parameters={"path": "hello", "key": "location", "kv_version": HashicorpKVVersionChoices.KV_VERSION_1},
        )
        kv_v1_secret_mounting_point = Secret.objects.create(
            name="hello-hashicorp-mntpnt-v1",
            provider=self.provider.slug,
            parameters={
                "path": "hello",
                "key": "location",
                "mount_point": "mymount",
                "kv_version": HashicorpKVVersionChoices.KV_VERSION_1,
            },
        )

        with self.subTest("Test v1 retrieve success"):
            requests_mocker.register_uri(method="GET", url=kv_v1_test_path, json=mock_kv_v1_response)

            response = self.provider.get_value_for_secret(kv_v1_secret)
            self.assertEqual(mock_kv_v1_response["data"]["location"], response)

        with self.subTest("Test v1 retrieve success with mount point set"):
            requests_mocker.register_uri(method="GET", url=kv_v1_test_mountpoint_path, json=mock_kv_v1_response)

            response = self.provider.get_value_for_secret(kv_v1_secret_mounting_point)
            self.assertEqual(mock_kv_v1_response["data"]["location"], response)

    @requests_mock.Mocker()
    def test_v2_fallback(self, requests_mocker):
        """
        Before https://github.com/nautobot/nautobot-app-secrets-providers/pull/53 was merged, the Hashicorp
        provider would only support KV v2 and did not include a way to specify the KV version.
        This test ensures that the provider will still work without the kv_version parameter.
        """
        kv_v2_fallback_secret = Secret.objects.create(
            name="hello-hashicorp-v2-fallback",
            provider=self.provider.slug,
            parameters={"path": "hello", "key": "location"},
        )
        kv_v2_fallback_secret_mounting_point = Secret.objects.create(
            name="hello-hashicorp-mntpnt-v2-fallback",
            provider=self.provider.slug,
            parameters={"path": "hello", "key": "location", "mount_point": "mymount"},
        )

        with self.subTest("Test v2 fallback retrieve success"):
            requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

            response = self.provider.get_value_for_secret(kv_v2_fallback_secret)
            self.assertEqual(self.mock_response["data"]["data"]["location"], response)

        with self.subTest("Test v2 fallback retrieve success with mount point set"):
            requests_mocker.register_uri(method="GET", url=self.test_mountpoint_path, json=self.mock_response)

            response = self.provider.get_value_for_secret(kv_v2_fallback_secret_mounting_point)
            self.assertEqual(self.mock_response["data"]["data"]["location"], response)

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
    def test_retrieve_configuration_success(self, requests_mocker):
        requests_mocker.register_uri(method="GET", url=self.test_path, json=self.mock_response)

        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "vaults": {
                        "example": {"token": "nautobot", "url": "http://localhost:8200"},
                        "example_2": {"token": "nautobot", "url": "http://example.com"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            response = self.provider.get_value_for_secret(self.secret_configuration)
            self.assertEqual(self.mock_response["data"]["data"]["location"], response)

    def test_retrieve_configuration_non_configured_vault(self):
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "vaults": {
                        "example": {"token": "nautobot", "url": "http://localhost:8200"},
                        "example_2": {"token": "nautobot", "url": "http://example.com"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.validate_vault_settings(self.secret, "test")
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault test is not configured!',
        )

    @requests_mock.Mocker()
    def test_retrieve_invalid_parameters(self, requests_mocker):
        """Try and fail to retrieve a secret with incorrect parameters."""
        bogus_secret = Secret.objects.create(
            name="bogus-hashicorp",
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

        # Test with default configuration
        returned_settings = self.provider.validate_vault_settings(self.secret, "default")
        self.assertEqual(returned_settings, settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["hashicorp_vault"])

        # Test with named default configuration
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "vaults": {
                        "default": {"token": "nautobot", "url": "http://localhost:8200"},
                        "example_2": {"token": "nautobot", "url": "http://example.com"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            returned_settings = self.provider.validate_vault_settings(self.secret, "default")
            self.assertEqual(
                returned_settings,
                settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["hashicorp_vault"]["vaults"]["default"],
            )

        # No nautobot_secrets_providers
        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {}}):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.validate_vault_settings(self.secret, "default")
        self.assertEqual(
            str(err.exception),
            'SecretProviderError: Secret "hello-hashicorp" (provider "HashiCorpVaultSecretsProvider"): HashiCorp Vault default is not configured!',
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

    def test_multiple_valid_settings(self):
        # Test with a configuration passed in
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "vaults": {
                        "example": {"token": "nautobot", "url": "http://localhost:8200"},
                        "example_2": {"token": "nautobot", "url": "http://example.com"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            returned_settings = self.provider.validate_vault_settings(self.secret, "example")
            self.assertEqual(
                returned_settings,
                settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["hashicorp_vault"]["vaults"]["example"],
            )
            returned_settings = self.provider.validate_vault_settings(self.secret, "example_2")
            self.assertEqual(
                returned_settings,
                settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["hashicorp_vault"]["vaults"]["example_2"],
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

    def test_vault_choices(self):
        choices = vault_choices()
        self.assertEqual(choices, [("default", "Default")])
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "hashicorp_vault": {
                    "vaults": {
                        "example": {"token": "nautobot", "url": "http://localhost:8200"},
                        "example_2": {"token": "nautobot", "url": "http://example.com"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            choices = vault_choices()
            self.assertEqual(choices, [("example", "Example"), ("example_2", "Example 2")])


class AWSSystemsManagerParameterStoreTestCase(SecretsProviderTestCase):
    """Tests for AWSSystemsManagerParameterStore."""

    provider = AWSSystemsManagerParameterStore

    def setUp(self):
        super().setUp()
        self.secret = Secret.objects.create(
            name="hello-aws-parameterstore",
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
        boto3.client("ssm", region_name=self.secret.parameters["region"])

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


class BitwardenCLISecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for Bitwarden CLI secrets provider."""

    provider = BitwardenCLISecretsProvider

    def setUp(self):
        super().setUp()
        self.secret = Secret.objects.create(
            name="hello-bitwarden",
            provider=self.provider.slug,
            parameters={"secret_id": "f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1", "secret_field": "password"},
        )

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_success(self, requests_mocker):
        """Retrieve a Bitwarden secret successfully."""

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"login": {"password": "secret-value", "username": "admin"}}},
        )

        value = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(value, "secret-value")
        self.assertEqual(len(requests_mocker.request_history), 1)
        self.assertEqual(
            requests_mocker.request_history[0].url,
            "https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
        )

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_custom_field_success(self, requests_mocker):
        """Retrieve a named custom field via `custom` + `custom_field_name`."""

        self.secret.parameters["secret_field"] = "custom"
        self.secret.parameters["custom_field_name"] = "custom_test"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={
                "success": True,
                "data": {
                    "fields": [
                        {"name": "custom_test", "value": "custom-value"},
                    ]
                },
            },
        )

        value = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(value, "custom-value")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_custom_field_prefix_success(self, requests_mocker):
        """Retrieve a named custom field via `custom.<field_name>` syntax."""

        self.secret.parameters["secret_field"] = "custom.custom_test"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={
                "success": True,
                "data": {
                    "fields": [
                        {"name": "custom_test", "value": "custom-value-2"},
                    ]
                },
            },
        )

        value = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(value, "custom-value-2")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_identity_field(self, requests_mocker):
        """Retrieve nested identity field value."""

        self.secret.parameters["secret_field"] = "identity.firstName"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"identity": {"firstName": "Max"}}},
        )

        value = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(value, "Max")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_identity_mapped_field(self, requests_mocker):
        """Retrieve an identity field using the mapped key (e.g. identity_firstName)."""

        self.secret.parameters["secret_field"] = "identity_firstName"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"identity": {"firstName": "Jane"}}},
        )

        value = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(value, "Jane")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_card_mapped_field(self, requests_mocker):
        """Retrieve a card field using the mapped key (e.g. card_number)."""

        self.secret.parameters["secret_field"] = "card_number"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"card": {"number": "4111111111111111"}}},
        )

        value = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(value, "4111111111111111")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_retrieve_login_fido2_field(self, requests_mocker):
        """Retrieve fido2Credentials via the LOGIN_FIELDS mapping."""

        self.secret.parameters["secret_field"] = "fido2Credentials"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"login": {"fido2Credentials": "cred-data"}}},
        )

        value = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(value, "cred-data")

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_http_error(self, requests_mocker):
        """Raise provider error on non-200 responses."""

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=401,
            text="Unauthorized",
        )

        with self.assertRaises(exceptions.SecretProviderError) as err:
            self.provider.get_value_for_secret(self.secret)

        self.assertIn("401", str(err.exception))

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @patch("nautobot_secrets_providers.providers.bitwarden.requests.get")
    def test_ssl_error(self, requests_get):
        """Raise provider error with guidance on TLS verification failures."""

        requests_get.side_effect = requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")

        with self.assertRaises(exceptions.SecretProviderError) as err:
            self.provider.get_value_for_secret(self.secret)

        self.assertIn("BW_CLI_VERIFY_SSL=false", str(err.exception))

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
        },
        clear=True,
    )
    def test_missing_env(self):
        """Ensure missing environment variables error loudly."""

        with self.assertRaises(exceptions.SecretProviderError) as err:
            self.provider.get_value_for_secret(self.secret)

        self.assertIn("BW_CLI_PASSWORD", str(err.exception))

    @patch.dict(
        os.environ,
        {
            "NAUTOBOT_BITWARDEN_CLI_ENABLED": "true",
            "BW_CLI_URL": "https://vaultwarden.example",
            "BW_CLI_USER": "nautobot",
            "BW_CLI_PASSWORD": "secret",
        },
        clear=True,
    )
    @requests_mock.Mocker()
    def test_field_not_found(self, requests_mocker):
        """Raise an error when requested field does not exist."""

        self.secret.parameters["secret_field"] = "card.number"

        requests_mocker.register_uri(
            method="GET",
            url="https://vaultwarden.example/object/item/f1ca57e0-2b9f-4c1a-9b2c-7b61aa1dc1b1",
            status_code=200,
            json={"success": True, "data": {"login": {"password": "x"}}},
        )

        with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
            self.provider.get_value_for_secret(self.secret)

        self.assertIn("card.number", str(err.exception))


class OnePasswordSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for OnePasswordSecretsProvider."""

    provider = OnePasswordSecretsProvider

    def setUp(self):
        super().setUp()

        # The secret we be using.
        self.secret = Secret.objects.create(
            name="hello-onepassword",
            provider=self.provider.slug,
            parameters={
                "vault": "example",
                "item": "location",
                "section": "section",
                "field": "value",
            },
        )
        self.secret2 = Secret.objects.create(
            name="hello-onepassword-2",
            provider=self.provider.slug,
            parameters={
                "vault": "example_2",
                "item": "location",
                "field": "value",
            },
        )

        self.plugin_config = {
            "nautobot_secrets_providers": {
                "one_password": {
                    "vaults": {
                        "example": {"token": "nautobot"},
                        "example_2": {},
                    },
                    "token": "another",
                }
            }
        }

    @patch("nautobot_secrets_providers.providers.one_password.get_secret_from_vault", return_value="world")
    def test_retrieve_success(self, get_secret_from_vault):
        """Retrieve a secret successfully."""
        with get_secret_from_vault:
            with self.settings(PLUGINS_CONFIG=self.plugin_config):
                response = self.provider.get_value_for_secret(self.secret)
                self.assertEqual("world", response)
                response2 = self.provider.get_value_for_secret(self.secret2)
                self.assertEqual("world", response2)

    def test_multiple_valid_settings(self):
        # Test with a configuration passed in
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "one_password": {
                    "vaults": {
                        "example": {"token": "nautobot"},
                        "example_2": {},
                    },
                    "token": "another_token",
                }
            }
        }

        invalid_plugins_config = {
            "nautobot_secrets_providers": {
                "one_password": {
                    "vaults": {
                        "example": {},
                    },
                }
            }
        }

        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            token = self.provider.get_token(self.secret, "example")
            self.assertEqual(
                token,
                settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["one_password"]["vaults"]["example"]["token"],
            )
            token = self.provider.get_token(self.secret, "example_2")
            self.assertEqual(
                token,
                settings.PLUGINS_CONFIG["nautobot_secrets_providers"]["one_password"]["token"],
            )

        with self.settings(PLUGINS_CONFIG=invalid_plugins_config):
            with self.assertRaises(exceptions.SecretProviderError):
                self.provider.get_token(self.secret, "example")

    def test_vault_choices(self):
        multiple_plugins_config = {
            "nautobot_secrets_providers": {
                "one_password": {
                    "vaults": {
                        "Example": {"token": "nautobot"},
                        "Example 2": {"token": "nautobot"},
                    }
                }
            }
        }
        with self.settings(PLUGINS_CONFIG=multiple_plugins_config):
            choices = one_password_vault_choices()
            self.assertEqual(choices, [("Example", "Example"), ("Example 2", "Example 2")])


class BitwardenGetCustomFieldNamesTestCase(SecretsProviderTestCase):
    """Tests for BitwardenCLISecretsProvider.get_custom_field_names()."""

    provider = BitwardenCLISecretsProvider
    ITEM_ID = "bb7b4168-9cb9-45ae-b7d0-20743ab4a3e7"
    BW_ENV = {
        "BW_CLI_URL": "https://vaultwarden.example",
        "BW_CLI_USER": "nautobot",
        "BW_CLI_PASSWORD": "secret",
    }

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_returns_field_names(self, requests_mocker):
        """Returns list of custom field names from the Bitwarden item."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            json={
                "success": True,
                "data": {
                    "fields": [
                        {"name": "custom_test", "value": "val1", "type": 0},
                        {"name": "custom_hidden", "value": "val2", "type": 1},
                    ]
                },
            },
        )
        result = self.provider.get_custom_field_names(self.ITEM_ID)
        self.assertEqual(result, ["custom_test", "custom_hidden"])

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_returns_empty_list_when_no_fields(self, requests_mocker):
        """Returns empty list when item has no custom fields."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            json={"success": True, "data": {"fields": []}},
        )
        result = self.provider.get_custom_field_names(self.ITEM_ID)
        self.assertEqual(result, [])

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_raises_on_http_error(self, requests_mocker):
        """Raises ValueError on non-200 HTTP status."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            status_code=401,
        )
        with self.assertRaises(ValueError) as err:
            self.provider.get_custom_field_names(self.ITEM_ID)
        self.assertIn("401", str(err.exception))

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_raises_on_bitwarden_failure(self, requests_mocker):
        """Raises ValueError when Bitwarden reports success=false."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            json={"success": False, "message": "Item not found."},
        )
        with self.assertRaises(ValueError) as err:
            self.provider.get_custom_field_names(self.ITEM_ID)
        self.assertIn("Item not found", str(err.exception))

    @patch.dict(
        os.environ,
        {"BW_CLI_URL": "https://vaultwarden.example", "BW_CLI_USER": "nautobot"},
        clear=True,
    )
    def test_raises_on_missing_configuration(self):
        """Raises ValueError when required environment variables are missing."""
        with self.assertRaises(ValueError) as err:
            self.provider.get_custom_field_names(self.ITEM_ID)
        self.assertIn("BW_CLI_PASSWORD", str(err.exception))


class BitwardenCustomFieldNamesViewTestCase(SecretsProviderTestCase):
    """Tests for the BitwardenCustomFieldNamesView AJAX endpoint."""

    provider = BitwardenCLISecretsProvider
    ITEM_ID = "bb7b4168-9cb9-45ae-b7d0-20743ab4a3e7"
    BW_ENV = {
        "BW_CLI_URL": "https://vaultwarden.example",
        "BW_CLI_USER": "nautobot",
        "BW_CLI_PASSWORD": "secret",
    }

    @property
    def endpoint_url(self):
        """Return the URL for the custom field names AJAX endpoint."""
        return reverse("plugins:nautobot_secrets_providers:bitwarden_custom_fields")

    def test_unauthenticated_request_redirects(self):
        """Unauthenticated requests are redirected to the login page."""
        from django.test import Client as DjangoClient  # pylint: disable=import-outside-toplevel,reimported

        anon_client = DjangoClient()
        response = anon_client.get(self.endpoint_url, {"secret_id": self.ITEM_ID})
        self.assertIn(response.status_code, [302, 403])

    def test_missing_secret_id_returns_400(self):
        """Missing secret_id query param returns 400 with error JSON."""
        response = self.client.get(self.endpoint_url)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("secret_id", data["error"])

    def test_invalid_uuid_returns_400(self):
        """Non-UUID secret_id returns 400 with error JSON."""
        response = self.client.get(self.endpoint_url, {"secret_id": "not-a-uuid"})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Invalid", data["error"])

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_returns_custom_field_names_on_success(self, requests_mocker):
        """Returns JSON with the list of custom field names on success."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            json={
                "success": True,
                "data": {
                    "fields": [
                        {"name": "api_key", "value": "secret-value", "type": 0},
                        {"name": "token", "value": "another-value", "type": 1},
                    ],
                    "name": "Card Identity",
                },
            },
        )
        response = self.client.get(self.endpoint_url, {"secret_id": self.ITEM_ID})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["fields"], ["api_key", "token"])
        # The AJAX endpoint should also return the item name for UI display
        self.assertEqual(data.get("name"), "Card Identity")

    @patch.dict(os.environ, BW_ENV, clear=True)
    @requests_mock.Mocker()
    def test_bitwarden_error_returns_error_json(self, requests_mocker):
        """Returns success=false JSON when Bitwarden returns an error response."""
        requests_mocker.get(
            f"https://vaultwarden.example/object/item/{self.ITEM_ID}",
            json={"success": False, "message": "Item not found."},
        )
        response = self.client.get(self.endpoint_url, {"secret_id": self.ITEM_ID})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Item not found", data["error"])


class BitwardenParametersFormTestCase(SecretsProviderTestCase):
    """Tests for BitwardenCLISecretsProvider.ParametersForm behavior and widget rendering."""

    provider = BitwardenCLISecretsProvider

    def _form(self, **data):
        """Instantiate a bound ParametersForm with the given field values."""
        return self.provider.ParametersForm(data=data)

    def test_widget_renders_fetch_button(self):
        """The custom_field_name widget renders the Fetch Fields button and AJAX script."""
        form = self.provider.ParametersForm()
        rendered = form.as_p()
        self.assertIn("bw-fetch-fields-btn", rendered)
        self.assertIn("bw-fetch-error", rendered)
        self.assertIn("Fetch Fields from Bitwarden", rendered)

    def test_widget_clears_custom_field_and_shows_warning(self):
        """The widget JS clears `custom_field_name` for non-custom fields and shows a warning."""
        form = self.provider.ParametersForm()
        rendered = form.as_p()
        # Verify the injected script contains the clearing logic and warning class
        self.assertIn("customInput.value = ''", rendered)
        self.assertIn("bw-custom-warning", rendered)
        # Keep the existing placeholder help text present
        self.assertIn("Activate Custom field selection to specify this value", rendered)

    def test_model_full_clean_maps_provider_validation_errors(self):
        """Model full_clean should attach provider form errors to `parameters` and not traceback."""
        # Construct a Secret whose provider ParametersForm will be invalid
        bad_params = {"secret_id": "some-uuid", "secret_field": "custom", "custom_field_name": ""}
        secret = Secret(name="bad-secret", provider=BitwardenCLISecretsProvider.slug, parameters=bad_params)

        with self.assertRaises(ValidationError) as cm:
            secret.full_clean()

        exc = cm.exception
        # The ValidationError may appear as a message_dict entry for 'parameters'
        # or as top-level messages depending on how Django composes errors.
        if hasattr(exc, "message_dict") and "parameters" in exc.message_dict:
            msgs = exc.message_dict["parameters"]
        else:
            msgs = exc.messages

        self.assertTrue(any("Custom field name is required for 'custom'" in m for m in msgs), msgs)

    def test_model_full_clean_handles_custom_name_with_non_custom_selected(self):
        """When a custom_field_name is present but a non-custom secret_field is selected,
        full_clean should raise a ValidationError attached to `parameters` rather than crash.
        """
        bad_params = {"secret_id": "some-uuid", "secret_field": "password", "custom_field_name": "PIN"}
        secret = Secret(name="bad-secret-2", provider=BitwardenCLISecretsProvider.slug, parameters=bad_params)

        with self.assertRaises(ValidationError) as cm:
            secret.full_clean()

        exc = cm.exception
        if hasattr(exc, "message_dict") and "parameters" in exc.message_dict:
            msgs = exc.message_dict["parameters"]
        else:
            msgs = exc.messages

        self.assertTrue(any("Selected field must be a Custom Field" in m for m in msgs), msgs)

    def test_valid_form_with_custom_field(self):
        """Form is valid when secret_field is custom and custom_field_name is provided."""
        form = self._form(secret_id="some-uuid", secret_field="custom", custom_field_name="my_field")
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_form_missing_custom_field_name(self):
        """Form is invalid when secret_field is custom but custom_field_name is empty."""
        form = self._form(secret_id="some-uuid", secret_field="custom", custom_field_name="")
        self.assertFalse(form.is_valid())
        self.assertIn("custom_field_name", form.errors)


@tag("integration")
class SecretAdminEditIntegrationTestCase(SecretsProviderTestCase):
    """Integration test to simulate admin edit POST flow for Secrets."""

    def setUp(self):
        super().setUp()
        # Create an initial secret to edit
        self.secret = Secret.objects.create(
            name="admin-edit-secret",
            provider=BitwardenCLISecretsProvider.slug,
            parameters={"secret_id": "some-uuid", "secret_field": "password", "custom_field_name": ""},
        )

    def test_admin_edit_post_triggers_provider_validation_without_traceback(self):
        """POSTing an update that fails provider validation should not traceback (500).

        This simulates the browser/admin POST to /extras/secrets/<pk>/edit/ with
        parameters that cause the provider ParametersForm to raise a ValidationError
        referencing `custom_field_name`.
        """
        url = reverse("extras:secret_edit", kwargs={"pk": self.secret.pk})

        # Prepare form data similar to what the admin would submit. The JSONField
        # `parameters` is posted as a JSON string.
        new_params = {"secret_id": "some-uuid", "secret_field": "custom", "custom_field_name": ""}
        form_data = {
            "name": self.secret.name,
            "description": self.secret.description,
            "provider": self.secret.provider,
            "parameters": json.dumps(new_params),
            "tags": "",
        }

        response = self.client.post(url, data=form_data, follow=True)

        # Ensure we did not get a server error
        self.assertNotEqual(response.status_code, 500)

        # The provider validation message should be present in the response content
        content = response.content.decode("utf-8", errors="ignore")
        self.assertIn("Custom field name is required", content)

    def test_valid_form_non_custom_secret_field(self):
        """Form is valid when secret_field is not custom, regardless of custom_field_name."""
        form = self._form(secret_id="some-uuid", secret_field="password", custom_field_name="")
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_form_custom_name_but_non_custom_selected(self):
        """Form is invalid when a custom_field_name is provided but a non-custom field is selected."""
        form = self._form(secret_id="some-uuid", secret_field="password", custom_field_name="my_field")
        self.assertFalse(form.is_valid())
        # Validation should report an error on the `secret_field`
        self.assertIn("secret_field", form.errors)
