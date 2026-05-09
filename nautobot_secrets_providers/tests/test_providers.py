"""Unit tests for Secrets Providers."""

import os
from unittest.mock import mock_open, patch

import boto3
import requests_mock
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, tag
from hvac import Client as HVACClient
from moto import mock_secretsmanager, mock_ssm
from nautobot.extras.models import Secret
from nautobot.extras.secrets import exceptions

from nautobot_secrets_providers.providers import (
    AWSSecretsManagerSecretsProvider,
    AWSSystemsManagerParameterStore,
    HashiCorpVaultSecretsProvider,
    OnePasswordSecretsProvider,
    VaultwardenSecretsProvider,
)
from nautobot_secrets_providers.providers import _vaultwarden_client as vw
from nautobot_secrets_providers.providers.choices import HashicorpKVVersionChoices
from nautobot_secrets_providers.providers.hashicorp import vault_choices
from nautobot_secrets_providers.providers.one_password import vault_choices as one_password_vault_choices
from nautobot_secrets_providers.providers.vaultwarden import vault_choices as vaultwarden_vault_choices

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


class _VaultwardenFixture:
    """Helper that builds a synthetic encrypted vault for use in tests.

    We generate a fresh vault (random user symmetric keys, random IVs) on each test
    using the same crypto primitives the production client uses. That keeps tests
    deterministic per-run while exercising the entire encrypt -> wire -> decrypt
    round-trip the provider depends on.
    """

    EMAIL = "test@example.com"
    MASTER_PASSWORD = "correct horse battery staple"  # nosec - test fixture
    KDF_ITERATIONS = 600000  # default for new Bitwarden accounts

    ITEM_UUID = "11111111-2222-3333-4444-555555555555"
    ITEM_NAME = "Datacenter Router"
    ITEM_USERNAME = "admin"
    ITEM_PASSWORD = "DC-router-p@ssw0rd!"  # nosec
    ITEM_NOTES = "Use only via jumphost"
    ITEM_TOTP_SEED = "JBSWY3DPEHPK3PXP"  # nosec
    CUSTOM_FIELD_NAME = "snmp_community"
    CUSTOM_FIELD_VALUE = "private-readwrite"  # nosec

    SECOND_ITEM_UUID = "22222222-3333-4444-5555-666666666666"
    SECOND_ITEM_NAME = "Switch Stack"
    SECOND_ITEM_PASSWORD = "switch-secret"  # nosec

    # Org-owned item (only populated when with_org=True).
    ORG_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ORG_ITEM_UUID = "33333333-4444-5555-6666-777777777777"
    ORG_ITEM_NAME = "Org-Owned Firewall"
    ORG_ITEM_USERNAME = "fw-admin"
    ORG_ITEM_PASSWORD = "fw-secret"  # nosec

    def __init__(self, with_org: bool = False):
        import base64 as _b64
        import hashlib as _hashlib
        import hmac as _hmac
        import os

        from cryptography.hazmat.primitives import hashes as _hashes
        from cryptography.hazmat.primitives import serialization as _serialization
        from cryptography.hazmat.primitives.asymmetric import padding as _asymm_padding
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        self._os = os
        self._hmac = _hmac
        self._hashlib = _hashlib
        self._b64 = _b64
        self._Cipher = Cipher
        self._algorithms = algorithms
        self._modes = modes
        self._rsa = _rsa
        self._serialization = _serialization
        self._asymm_padding = _asymm_padding
        self._hashes = _hashes

        master_key = vw.derive_master_key(
            self.MASTER_PASSWORD, self.EMAIL, vw.KDF_PBKDF2_SHA256, self.KDF_ITERATIONS
        )
        self.master_password_hash = vw.derive_master_password_hash(master_key, self.MASTER_PASSWORD)
        stretched_enc, stretched_mac = vw.stretch_master_key(master_key)

        # Random per-run user symmetric key (32 enc + 32 mac).
        self.user_enc_key = os.urandom(32)
        self.user_mac_key = os.urandom(32)
        protected = self._encrypt(
            self.user_enc_key + self.user_mac_key, stretched_enc, stretched_mac
        )

        # User RSA keypair + encrypted private key. Only meaningful when with_org=True,
        # but we always emit a valid PrivateKey so login() doesn't tolerate-and-skip
        # the path - we want to exercise the full flow even on the personal-only tests.
        private_key = self._rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key_der = private_key.private_bytes(
            encoding=self._serialization.Encoding.DER,
            format=self._serialization.PrivateFormat.PKCS8,
            encryption_algorithm=self._serialization.NoEncryption(),
        )
        self.private_key_der = private_key_der
        self.public_key = private_key.public_key()
        protected_private_key = self._encrypt(private_key_der, self.user_enc_key, self.user_mac_key)

        self.token_response = {
            "access_token": "fake-bearer-token",
            "refresh_token": "fake-refresh-token",
            "expires_in": 3600,
            "Key": protected,
            "PrivateKey": protected_private_key,
            "token_type": "Bearer",
        }

        self.prelogin_response = {
            "kdf": vw.KDF_PBKDF2_SHA256,
            "kdfIterations": self.KDF_ITERATIONS,
            "kdfMemory": None,
            "kdfParallelism": None,
        }

        ciphers = [
            self._build_login_cipher(
                cipher_id=self.ITEM_UUID,
                name=self.ITEM_NAME,
                username=self.ITEM_USERNAME,
                password=self.ITEM_PASSWORD,
                notes=self.ITEM_NOTES,
                totp=self.ITEM_TOTP_SEED,
                custom_fields=[(self.CUSTOM_FIELD_NAME, self.CUSTOM_FIELD_VALUE)],
            ),
            self._build_login_cipher(
                cipher_id=self.SECOND_ITEM_UUID,
                name=self.SECOND_ITEM_NAME,
                username="netadmin",
                password=self.SECOND_ITEM_PASSWORD,
            ),
        ]

        organizations = []
        self.org_enc_key = b""
        self.org_mac_key = b""
        if with_org:
            self.org_enc_key = os.urandom(32)
            self.org_mac_key = os.urandom(32)
            org_symkey_plaintext = self.org_enc_key + self.org_mac_key
            # Type 4 = RSA-OAEP-SHA1, the format real Bitwarden servers emit for org keys.
            wrapped = self.public_key.encrypt(
                org_symkey_plaintext,
                self._asymm_padding.OAEP(
                    mgf=self._asymm_padding.MGF1(algorithm=self._hashes.SHA1()),
                    algorithm=self._hashes.SHA1(),
                    label=None,
                ),
            )
            org_key_cipherstring = f"4.{self._b64.b64encode(wrapped).decode()}"
            organizations.append({"id": self.ORG_ID, "name": "Test Org", "key": org_key_cipherstring})
            ciphers.append(
                self._build_login_cipher(
                    cipher_id=self.ORG_ITEM_UUID,
                    name=self.ORG_ITEM_NAME,
                    username=self.ORG_ITEM_USERNAME,
                    password=self.ORG_ITEM_PASSWORD,
                    organization_id=self.ORG_ID,
                    enc_key=self.org_enc_key,
                    mac_key=self.org_mac_key,
                )
            )

        profile = {"id": "user-uuid", "email": self.EMAIL, "name": "Test"}
        if organizations:
            profile["organizations"] = organizations

        self.sync_response = {
            "object": "sync",
            "profile": profile,
            "ciphers": ciphers,
            "folders": [],
            "collections": [],
        }

    def _encrypt(self, plaintext: bytes, enc_key: bytes, mac_key: bytes) -> str:
        iv = self._os.urandom(16)
        pad_len = 16 - (len(plaintext) % 16)
        padded = plaintext + bytes([pad_len] * pad_len)
        encryptor = self._Cipher(self._algorithms.AES(enc_key), self._modes.CBC(iv)).encryptor()
        ct = encryptor.update(padded) + encryptor.finalize()
        mac = self._hmac.new(mac_key, iv + ct, self._hashlib.sha256).digest()
        return f"2.{self._b64.b64encode(iv).decode()}|{self._b64.b64encode(ct).decode()}|{self._b64.b64encode(mac).decode()}"

    def _enc_str(self, value, enc_key=None, mac_key=None):
        if value is None:
            return None
        return self._encrypt(
            value.encode("utf-8"),
            enc_key if enc_key is not None else self.user_enc_key,
            mac_key if mac_key is not None else self.user_mac_key,
        )

    def _build_login_cipher(self, cipher_id, name, username=None, password=None,
                            notes=None, totp=None, custom_fields=None,
                            organization_id=None, enc_key=None, mac_key=None):
        # When organization_id is set, encrypt the cipher's fields with the org's
        # symmetric key (passed as enc_key/mac_key), not the user's. That mirrors
        # what real Bitwarden does and lets the client exercise the org-key path.
        ek = enc_key if enc_key is not None else self.user_enc_key
        mk = mac_key if mac_key is not None else self.user_mac_key
        return {
            "id": cipher_id,
            "type": vw.CIPHER_ITEM_TYPE_LOGIN,
            "organizationId": organization_id,
            "name": self._enc_str(name, ek, mk),
            "notes": self._enc_str(notes, ek, mk),
            "login": {
                "username": self._enc_str(username, ek, mk),
                "password": self._enc_str(password, ek, mk),
                "totp": self._enc_str(totp, ek, mk),
                "uris": [],
            },
            "fields": [
                {"name": self._enc_str(fname, ek, mk), "value": self._enc_str(fvalue, ek, mk), "type": 0}
                for fname, fvalue in (custom_fields or [])
            ],
        }


@tag("unit")
class VaultwardenSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for VaultwardenSecretsProvider."""

    provider = VaultwardenSecretsProvider

    SERVER_URL = "https://vault.example.com"

    def setUp(self):
        super().setUp()
        self.fixture = _VaultwardenFixture()

        self.plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "url": self.SERVER_URL,
                    "email": self.fixture.EMAIL,
                    "master_password": self.fixture.MASTER_PASSWORD,
                    "verify_ssl": True,
                },
            },
        }

        self.secret_password = Secret.objects.create(
            name="vaultwarden-password",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "password",
            },
        )
        self.secret_username = Secret.objects.create(
            name="vaultwarden-username",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "username",
            },
        )
        self.secret_notes = Secret.objects.create(
            name="vaultwarden-notes",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "notes",
            },
        )
        self.secret_totp = Secret.objects.create(
            name="vaultwarden-totp",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "totp",
            },
        )
        self.secret_custom_field = Secret.objects.create(
            name="vaultwarden-custom",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "custom",
                "field_name": self.fixture.CUSTOM_FIELD_NAME,
            },
        )
        self.secret_by_name = Secret.objects.create(
            name="vaultwarden-by-name",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_NAME,
                "field_type": "password",
            },
        )

    def _register_endpoints(self, mocker, prelogin=None, token=None, sync=None):
        """Wire up the three endpoints the client touches.

        Pulled out as a helper so individual tests can override one endpoint
        (e.g. return 401 for bad-credentials tests) while keeping the others happy.
        """
        mocker.register_uri(
            method="POST",
            url=f"{self.SERVER_URL}/identity/accounts/prelogin",
            json=prelogin if prelogin is not None else self.fixture.prelogin_response,
        )
        mocker.register_uri(
            method="POST",
            url=f"{self.SERVER_URL}/identity/connect/token",
            json=token if token is not None else self.fixture.token_response,
        )
        mocker.register_uri(
            method="GET",
            url=f"{self.SERVER_URL}/api/sync?excludeDomains=true",
            json=sync if sync is not None else self.fixture.sync_response,
            complete_qs=True,
        )

    @requests_mock.Mocker()
    def test_retrieve_password_by_uuid(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_password)
        self.assertEqual(result, self.fixture.ITEM_PASSWORD)

    @requests_mock.Mocker()
    def test_retrieve_username_by_uuid(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_username)
        self.assertEqual(result, self.fixture.ITEM_USERNAME)

    @requests_mock.Mocker()
    def test_retrieve_notes(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_notes)
        self.assertEqual(result, self.fixture.ITEM_NOTES)

    @requests_mock.Mocker()
    def test_retrieve_totp(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_totp)
        self.assertEqual(result, self.fixture.ITEM_TOTP_SEED)

    @requests_mock.Mocker()
    def test_retrieve_custom_field(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_custom_field)
        self.assertEqual(result, self.fixture.CUSTOM_FIELD_VALUE)

    @requests_mock.Mocker()
    def test_retrieve_by_decrypted_name(self, mocker):
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            result = self.provider.get_value_for_secret(self.secret_by_name)
        self.assertEqual(result, self.fixture.ITEM_PASSWORD)

    @requests_mock.Mocker()
    def test_unknown_item_raises_value_not_found(self, mocker):
        self._register_endpoints(mocker)
        bad_secret = Secret.objects.create(
            name="vaultwarden-bad-item",
            provider=self.provider.slug,
            parameters={"item": "no-such-item", "field_type": "password"},
        )
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError):
                self.provider.get_value_for_secret(bad_secret)

    @requests_mock.Mocker()
    def test_missing_field_raises_value_not_found(self, mocker):
        self._register_endpoints(mocker)
        bad_secret = Secret.objects.create(
            name="vaultwarden-bad-field",
            provider=self.provider.slug,
            parameters={
                "item": self.fixture.ITEM_UUID,
                "field_type": "custom",
                "field_name": "nonexistent_field",
            },
        )
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError):
                self.provider.get_value_for_secret(bad_secret)

    @requests_mock.Mocker()
    def test_custom_field_without_name_raises_parameters_error(self, mocker):
        self._register_endpoints(mocker)
        bad_secret = Secret.objects.create(
            name="vaultwarden-no-field-name",
            provider=self.provider.slug,
            parameters={"item": self.fixture.ITEM_UUID, "field_type": "custom"},
        )
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            with self.assertRaises(exceptions.SecretParametersError):
                self.provider.get_value_for_secret(bad_secret)

    @requests_mock.Mocker()
    def test_auth_failure_raises_provider_error(self, mocker):
        # Server rejects the master_password_hash with 400 (Bitwarden's invalid_grant code).
        mocker.register_uri(
            method="POST",
            url=f"{self.SERVER_URL}/identity/accounts/prelogin",
            json=self.fixture.prelogin_response,
        )
        mocker.register_uri(
            method="POST",
            url=f"{self.SERVER_URL}/identity/connect/token",
            json={"error": "invalid_grant"},
            status_code=400,
        )
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            with self.assertRaises(exceptions.SecretProviderError):
                self.provider.get_value_for_secret(self.secret_password)

    def test_no_settings_raises_provider_error(self):
        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {}}):
            with self.assertRaises(exceptions.SecretProviderError):
                self.provider.get_value_for_secret(self.secret_password)

    def test_missing_required_settings_raises_provider_error(self):
        incomplete_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {"url": self.SERVER_URL},  # missing email + master_password
            },
        }
        with self.settings(PLUGINS_CONFIG=incomplete_config):
            with self.assertRaises(exceptions.SecretProviderError):
                self.provider.get_value_for_secret(self.secret_password)

    @requests_mock.Mocker()
    def test_organization_item_retrieved(self, mocker):
        """End-to-end org-key path: PrivateKey -> RSA-OAEP unwrap -> org symmetric key -> decrypt cipher."""
        org_fixture = _VaultwardenFixture(with_org=True)
        self._register_endpoints(
            mocker,
            prelogin=org_fixture.prelogin_response,
            token=org_fixture.token_response,
            sync=org_fixture.sync_response,
        )
        # Use the org fixture's URL/email/master_password so its derived keys match.
        plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "url": self.SERVER_URL,
                    "email": org_fixture.EMAIL,
                    "master_password": org_fixture.MASTER_PASSWORD,
                    "cache_session": False,
                },
            },
        }
        org_secret = Secret.objects.create(
            name="vaultwarden-org-item",
            provider=self.provider.slug,
            parameters={"item": org_fixture.ORG_ITEM_UUID, "field_type": "password"},
        )
        with self.settings(PLUGINS_CONFIG=plugins_config):
            value = self.provider.get_value_for_secret(org_secret)
        self.assertEqual(value, org_fixture.ORG_ITEM_PASSWORD)

    @requests_mock.Mocker()
    def test_organization_item_by_name(self, mocker):
        """Name-based lookup must search org-owned items too, decrypting names with the org key."""
        org_fixture = _VaultwardenFixture(with_org=True)
        self._register_endpoints(
            mocker,
            prelogin=org_fixture.prelogin_response,
            token=org_fixture.token_response,
            sync=org_fixture.sync_response,
        )
        plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "url": self.SERVER_URL,
                    "email": org_fixture.EMAIL,
                    "master_password": org_fixture.MASTER_PASSWORD,
                    "cache_session": False,
                },
            },
        }
        org_secret = Secret.objects.create(
            name="vaultwarden-org-by-name",
            provider=self.provider.slug,
            parameters={"item": org_fixture.ORG_ITEM_NAME, "field_type": "username"},
        )
        with self.settings(PLUGINS_CONFIG=plugins_config):
            value = self.provider.get_value_for_secret(org_secret)
        self.assertEqual(value, org_fixture.ORG_ITEM_USERNAME)

    @requests_mock.Mocker()
    def test_organization_item_unavailable_when_no_private_key(self, mocker):
        """If PrivateKey is missing/malformed, org items become unfindable (clean 'not found')."""
        org_fixture = _VaultwardenFixture(with_org=True)
        # Strip PrivateKey so login() leaves session.private_key_der empty -> no org keys.
        broken_token = {**org_fixture.token_response}
        broken_token.pop("PrivateKey", None)
        self._register_endpoints(
            mocker,
            prelogin=org_fixture.prelogin_response,
            token=broken_token,
            sync=org_fixture.sync_response,
        )
        plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "url": self.SERVER_URL,
                    "email": org_fixture.EMAIL,
                    "master_password": org_fixture.MASTER_PASSWORD,
                    "cache_session": False,
                },
            },
        }
        org_secret = Secret.objects.create(
            name="vaultwarden-org-no-private-key",
            provider=self.provider.slug,
            parameters={"item": org_fixture.ORG_ITEM_UUID, "field_type": "password"},
        )
        with self.settings(PLUGINS_CONFIG=plugins_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError):
                self.provider.get_value_for_secret(org_secret)

    def test_vault_choices_default(self):
        with self.settings(PLUGINS_CONFIG=self.plugins_config):
            choices = vaultwarden_vault_choices()
            self.assertEqual(choices, [("default", "Default")])

    def test_vault_choices_multi(self):
        multi_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "vaults": {
                        "production": {"url": "https://vault.prod.example", "email": "x", "master_password": "y"},
                        "staging": {"url": "https://vault.stage.example", "email": "x", "master_password": "y"},
                    },
                },
            },
        }
        with self.settings(PLUGINS_CONFIG=multi_config):
            choices = vaultwarden_vault_choices()
            self.assertEqual(sorted(choices), [("production", "Production"), ("staging", "Staging")])

    def test_cipher_string_parser_rejects_unknown_type(self):
        # Type 1 (deprecated AES-CBC, no MAC) - we explicitly refuse these.
        with self.assertRaises(vw.BitwardenCryptoError):
            vw.CipherString.parse("1.iv|ct")

    def test_cipher_string_parser_rejects_malformed(self):
        with self.assertRaises(vw.BitwardenCryptoError):
            vw.CipherString.parse("not a cipherstring")

    def test_hmac_tampering_detected(self):
        # Encrypt then flip a byte in the ciphertext - decrypt must fail HMAC, not produce garbage.
        plaintext = b"hello world"
        enc_key = b"\x00" * 32
        mac_key = b"\x01" * 32
        cs_str = self.fixture._encrypt(plaintext, enc_key, mac_key)
        cs = vw.CipherString.parse(cs_str)
        tampered = vw.CipherString(
            cipher_type=cs.cipher_type,
            iv=cs.iv,
            ciphertext=bytes([cs.ciphertext[0] ^ 0xFF]) + cs.ciphertext[1:],
            mac=cs.mac,
        )
        with self.assertRaises(vw.BitwardenCryptoError):
            vw.decrypt_cipher_string(tampered, enc_key, mac_key)

    def test_cipher_string_parses_rsa_types(self):
        """Type 3-6 parsers should round-trip without raising.

        We don't decrypt here - just verify the parser accepts the right shapes.
        """
        # Type 3 (RSA-OAEP-SHA256, no MAC): single ciphertext segment.
        cs3 = vw.CipherString.parse("3.YWJjZA==")
        self.assertEqual(cs3.cipher_type, 3)
        self.assertEqual(cs3.mac, b"")

        # Type 4 (RSA-OAEP-SHA1, no MAC).
        cs4 = vw.CipherString.parse("4.YWJjZA==")
        self.assertEqual(cs4.cipher_type, 4)

        # Type 5 (RSA-OAEP-SHA256 + HMAC): ct|mac.
        cs5 = vw.CipherString.parse("5.YWJjZA==|ZGVmZw==")
        self.assertEqual(cs5.cipher_type, 5)
        self.assertNotEqual(cs5.mac, b"")

        # Type 6 (RSA-OAEP-SHA1 + HMAC).
        cs6 = vw.CipherString.parse("6.YWJjZA==|ZGVmZw==")
        self.assertEqual(cs6.cipher_type, 6)


@tag("unit")
class VaultwardenSessionCacheTestCase(VaultwardenSecretsProviderTestCase):
    """Cache hit / miss / invalidate tests for the Vaultwarden provider.

    Inherits the base setUp (fixture + secrets) and overrides the cache to LocMemCache
    so we don't need a Redis instance for these checks.
    """

    LOCMEM_CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "vaultwarden-test-cache",
        },
    }

    def setUp(self):
        super().setUp()
        # Make sure each test starts from a cold cache - LocMemCache is process-global.
        from django.core.cache import cache as _cache
        _cache.clear()

    @requests_mock.Mocker()
    def test_cache_skips_login_on_second_call(self, mocker):
        """Second call with the same credentials should not re-do prelogin or token exchange."""
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config, CACHES=self.LOCMEM_CACHES):
            # First call populates the cache.
            self.provider.get_value_for_secret(self.secret_password)
            requests_before = len(mocker.request_history)
            # Second call should be cache-hot.
            self.provider.get_value_for_secret(self.secret_password)
            requests_after = len(mocker.request_history)

        # Difference between the two should be exactly 1 (only the /api/sync GET fires
        # on the cached call - prelogin and token are skipped).
        new_requests = mocker.request_history[requests_before:requests_after]
        self.assertEqual(len(new_requests), 1, f"expected 1 new request on cache hit, got {len(new_requests)}")
        self.assertIn("/api/sync", new_requests[0].url)

    @requests_mock.Mocker()
    def test_cache_disabled_does_full_login_each_time(self, mocker):
        """With cache_session=False, every call should re-do the full login flow."""
        self._register_endpoints(mocker)
        plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {**self.plugins_config["nautobot_secrets_providers"]["vaultwarden"],
                                "cache_session": False},
            },
        }
        with self.settings(PLUGINS_CONFIG=plugins_config, CACHES=self.LOCMEM_CACHES):
            self.provider.get_value_for_secret(self.secret_password)
            requests_before = len(mocker.request_history)
            self.provider.get_value_for_secret(self.secret_password)
            new_requests = mocker.request_history[requests_before:]

        # Three new requests: prelogin + token + sync.
        self.assertEqual(len(new_requests), 3)

    @requests_mock.Mocker()
    def test_cache_invalidated_on_401(self, mocker):
        """If a cached access token gets a 401, the provider should re-login transparently and succeed."""
        # First: normal flow, populates the cache.
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config, CACHES=self.LOCMEM_CACHES):
            self.provider.get_value_for_secret(self.secret_password)

        # Second: register sync to return 401 *once*, then 200 the second time.
        # We use response_list so the first match returns 401 and subsequent matches return 200.
        sync_url = f"{self.SERVER_URL}/api/sync?excludeDomains=true"
        mocker.register_uri(
            "GET", sync_url, complete_qs=True,
            response_list=[
                {"status_code": 401, "json": {"error": "invalid_token"}},
                {"json": self.fixture.sync_response, "status_code": 200},
            ],
        )
        # Re-register prelogin + token so the retry path can re-authenticate.
        mocker.register_uri("POST", f"{self.SERVER_URL}/identity/accounts/prelogin",
                            json=self.fixture.prelogin_response)
        mocker.register_uri("POST", f"{self.SERVER_URL}/identity/connect/token",
                            json=self.fixture.token_response)

        with self.settings(PLUGINS_CONFIG=self.plugins_config, CACHES=self.LOCMEM_CACHES):
            value = self.provider.get_value_for_secret(self.secret_password)
        self.assertEqual(value, self.fixture.ITEM_PASSWORD)

    @requests_mock.Mocker()
    def test_rotated_master_password_invalidates_cache_naturally(self, mocker):
        """Changing the master_password produces a different cache key, so an old session
        for the old password is never reused."""
        self._register_endpoints(mocker)
        with self.settings(PLUGINS_CONFIG=self.plugins_config, CACHES=self.LOCMEM_CACHES):
            self.provider.get_value_for_secret(self.secret_password)

        # Now switch the master_password in settings - this should be a cache miss.
        # Build a fresh fixture under the new password so the mock crypto matches.
        new_fixture = _VaultwardenFixture()
        new_password = "new-rotated-password"  # nosec
        # Re-derive the fixture's responses with the new password by faking it: the
        # crypto path doesn't actually use the password to encrypt anything (the AES
        # keys are random), only to derive the auth hash. So we can swap the password
        # in PLUGINS_CONFIG; the server-side mocks don't validate it either.
        plugins_config = {
            "nautobot_secrets_providers": {
                "vaultwarden": {
                    "url": self.SERVER_URL,
                    "email": new_fixture.EMAIL,
                    "master_password": new_password,
                },
            },
        }
        # New fixture means new prelogin/token/sync responses.
        self._register_endpoints(
            mocker,
            prelogin=new_fixture.prelogin_response,
            token=new_fixture.token_response,
            sync=new_fixture.sync_response,
        )
        secret = Secret.objects.create(
            name="vaultwarden-rotated",
            provider=self.provider.slug,
            parameters={"item": new_fixture.ITEM_UUID, "field_type": "password"},
        )
        requests_before = len(mocker.request_history)
        with self.settings(PLUGINS_CONFIG=plugins_config, CACHES=self.LOCMEM_CACHES):
            value = self.provider.get_value_for_secret(secret)
        self.assertEqual(value, new_fixture.ITEM_PASSWORD)
        # Should have done a full login (prelogin + token + sync = 3 new requests).
        new_requests = mocker.request_history[requests_before:]
        self.assertEqual(len(new_requests), 3)
