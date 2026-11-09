"""Unit tests for Secrets Providers."""

# pylint: disable=too-many-lines

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
    BeyondTrustPasswordSafeManagedAccountSecretsProvider,
    BeyondTrustPasswordSafeSecretsSafeSecretsProvider,
    HashiCorpVaultLDAPSecretsProvider,
    HashiCorpVaultSecretsProvider,
    OnePasswordSecretsProvider,
    PasswordManagerProSecretsProvider,
)
from nautobot_secrets_providers.providers.choices import (
    HashicorpKVVersionChoices,
    HashicorpLDAPCredentialChoices,
    HashicorpLDAPEngineChoices,
)
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


class HashiCorpVaultLDAPSecretsProviderTestCase(SecretsProviderTestCase):
    """Tests for HashiCorpVaultLDAPSecretsProvider."""

    provider = HashiCorpVaultLDAPSecretsProvider

    mock_ad_response = {
        "data": {
            "current_password": "?@09AZnh4Ub",
            "last_password": "?@09AZSen9TzU",
            "username": "nautobot-svc",
        },
    }

    mock_ldap_response = {
        "data": {
            "dn": "CN=nautobot-svc,OU=Service Accounts,DC=example,DC=com",
            "last_password": "?@09AZKh03hBQ",
            "password": "?@09AZGdnkinw",
            "username": "nautobot-svc",
        },
    }

    def setUp(self):
        super().setUp()

        self.secret = Secret.objects.create(
            name="hello-hashicorp-ad",
            provider=self.provider.slug,
            parameters={
                "engine": HashicorpLDAPEngineChoices.ENGINE_AD,
                "role_name": "nautobot",
                "key": HashicorpLDAPCredentialChoices.CREDENTIAL_CURRENT,
            },
        )
        self.ad_test_path = "http://localhost:8200/v1/ad/creds/nautobot"
        self.ldap_test_path = "http://localhost:8200/v1/ldap/static-cred/nautobot"

    @requests_mock.Mocker()
    def test_retrieve_success(self, requests_mocker):
        """Retrieve each credential value from both secrets engines."""
        requests_mocker.register_uri(method="GET", url=self.ad_test_path, json=self.mock_ad_response)
        requests_mocker.register_uri(method="GET", url=self.ldap_test_path, json=self.mock_ldap_response)
        test_cases = (
            (HashicorpLDAPEngineChoices.ENGINE_AD, self.mock_ad_response["data"], "current_password"),
            (HashicorpLDAPEngineChoices.ENGINE_LDAP, self.mock_ldap_response["data"], "password"),
        )

        for engine, data, password_key in test_cases:
            expected_values = {
                HashicorpLDAPCredentialChoices.CREDENTIAL_USERNAME: data["username"],
                HashicorpLDAPCredentialChoices.CREDENTIAL_CURRENT: data[password_key],
                HashicorpLDAPCredentialChoices.CREDENTIAL_LAST: data["last_password"],
            }
            for key, expected in expected_values.items():
                with self.subTest(engine=engine, key=key):
                    self.secret.parameters.update({"engine": engine, "key": key})
                    self.assertEqual(self.provider.get_value_for_secret(self.secret), expected)

    @requests_mock.Mocker()
    def test_retrieve_mount_point_success(self, requests_mocker):
        """Retrieve a credential successfully using a custom `mount_point`."""
        requests_mocker.register_uri(
            method="GET", url="http://localhost:8200/v1/mymount/creds/nautobot", json=self.mock_ad_response
        )
        self.secret.parameters["mount_point"] = "mymount"

        response = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(self.mock_ad_response["data"]["current_password"], response)

    @requests_mock.Mocker()
    def test_retrieve_configuration_success(self, requests_mocker):
        """Retrieve a credential successfully from the selected vault."""
        requests_mocker.register_uri(
            method="GET", url="http://example.com/v1/ad/creds/nautobot", json=self.mock_ad_response
        )
        self.secret.parameters["vault"] = "example_2"

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
            response = self.provider.get_value_for_secret(self.secret)
        self.assertEqual(self.mock_ad_response["data"]["current_password"], response)

    def test_retrieve_invalid_parameters(self):
        """Try and fail to retrieve a secret with missing or invalid parameters."""
        test_cases = (
            (
                {
                    "engine": HashicorpLDAPEngineChoices.ENGINE_AD,
                    "key": HashicorpLDAPCredentialChoices.CREDENTIAL_CURRENT,
                },
                "The secret parameter could not be retrieved for field 'role_name'",
            ),
            (
                {"engine": "bogus", "role_name": "nautobot", "key": HashicorpLDAPCredentialChoices.CREDENTIAL_CURRENT},
                "HashiCorp Vault secrets engine bogus is invalid!",
            ),
        )

        for parameters, message in test_cases:
            with self.subTest(parameters=parameters):
                self.secret.parameters = parameters
                with self.assertRaises(exceptions.SecretParametersError) as err:
                    self.provider.get_value_for_secret(self.secret)
                self.assertEqual(
                    str(err.exception),
                    f'SecretParametersError: Secret "hello-hashicorp-ad" (provider "HashiCorpVaultLDAPSecretsProvider"): {message}',
                )

    @requests_mock.Mocker()
    def test_retrieve_does_not_exist(self, requests_mocker):
        """Try and fail to retrieve the credentials of a role that doesn't exist."""
        requests_mocker.register_uri(method="GET", url=self.ad_test_path, status_code=404)
        requests_mocker.register_uri(
            method="GET",
            url=self.ldap_test_path,
            status_code=400,
            headers={"Content-Type": "application/json"},
            json={"errors": ["unknown role: nautobot"]},
        )
        test_cases = (
            (HashicorpLDAPEngineChoices.ENGINE_AD, "HashiCorp Vault role nautobot was not found on mount point ad"),
            (HashicorpLDAPEngineChoices.ENGINE_LDAP, f"unknown role: nautobot, on get {self.ldap_test_path}"),
        )

        for engine, message in test_cases:
            with self.subTest(engine=engine):
                self.secret.parameters["engine"] = engine
                with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                    self.provider.get_value_for_secret(self.secret)
                self.assertEqual(
                    str(err.exception),
                    f'SecretValueNotFoundError: Secret "hello-hashicorp-ad" (provider "HashiCorpVaultLDAPSecretsProvider"): {message}',
                )

    @requests_mock.Mocker()
    def test_retrieve_invalid_key(self, requests_mocker):
        """Try and fail to retrieve a credential value that is missing or empty in the response."""
        mock_ad_response = {"data": {"current_password": "?@09AZnh4Ub", "username": "nautobot-svc"}}
        mock_ldap_response = {"data": {"last_password": "", "password": "?@09AZGdnkinw", "username": "nautobot-svc"}}
        requests_mocker.register_uri(method="GET", url=self.ad_test_path, json=mock_ad_response)
        requests_mocker.register_uri(method="GET", url=self.ldap_test_path, json=mock_ldap_response)
        self.secret.parameters["key"] = HashicorpLDAPCredentialChoices.CREDENTIAL_LAST

        for engine in (HashicorpLDAPEngineChoices.ENGINE_AD, HashicorpLDAPEngineChoices.ENGINE_LDAP):
            with self.subTest(engine=engine):
                self.secret.parameters["engine"] = engine
                with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                    self.provider.get_value_for_secret(self.secret)
                self.assertEqual(
                    str(err.exception),
                    'SecretValueNotFoundError: Secret "hello-hashicorp-ad" (provider "HashiCorpVaultLDAPSecretsProvider"): The secret value could not be retrieved using key \'last_password\'',
                )


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


class PasswordManagerProSecretsProviderTestCase(TestCase):
    """Tests for PasswordManagerProSecretsProvider."""

    provider = PasswordManagerProSecretsProvider

    def setUp(self):
        """Create a secret for use with testing."""
        super().setUp()

        self.secret = Secret.objects.create(
            name="hello-pmp",
            provider=self.provider.slug,
            parameters={
                "resource_name": "server01",
                "account_name": "admin",
            },
        )

        self.plugin_config = {
            "nautobot_secrets_providers": {
                "password_manager_pro": {
                    "base_url": "https://pmp.local",
                    "token": "fake-token",
                    "verify_ssl": False,
                }
            }
        }

    @requests_mock.Mocker()
    def test_retrieve_success(self, mock):
        """Retrieve a secret successfully."""
        mock.get(
            "https://pmp.local/restapi/json/v1/resources/getResourceIdAccountId?RESOURCENAME=server01&ACCOUNTNAME=admin",
            json={"operation": {"Details": {"RESOURCEID": "1001", "ACCOUNTID": "2001"}}},
        )
        mock.get(
            "https://pmp.local/restapi/json/v1/resources/1001/accounts/2001/password",
            json={"operation": {"Details": {"PASSWORD": "world"}}},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            result = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(result, "world")
        for request in mock.request_history:
            self.assertEqual(request.headers["APP_AUTHTOKEN"], "fake-token")

    def test_missing_or_empty_token(self):
        """Raise SecretParametersError if the token is missing, None, or empty."""
        for token in ("MISSING", None, ""):
            with self.subTest(token=token):
                config = {"base_url": "https://pmp.local"}
                if token != "MISSING":
                    config["token"] = token
                with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {"password_manager_pro": config}}):
                    with self.assertRaises(exceptions.SecretParametersError) as err:
                        self.provider.get_value_for_secret(self.secret)
                self.assertIn("requires 'base_url' and 'token'", str(err.exception))

    @requests_mock.Mocker()
    def test_password_not_found(self, mock):
        """Fail to retrieve a secret if password is None."""
        mock.get(
            "https://pmp.local/restapi/json/v1/resources/getResourceIdAccountId?RESOURCENAME=server01&ACCOUNTNAME=admin",
            json={"operation": {"Details": {"RESOURCEID": "1001", "ACCOUNTID": "2001"}}},
        )
        mock.get(
            "https://pmp.local/restapi/json/v1/resources/1001/accounts/2001/password",
            json={"operation": {"Details": {"PASSWORD": None}}},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError):
                self.provider.get_value_for_secret(self.secret)

    @requests_mock.Mocker()
    def test_api_failure(self, mock):
        """Raise SecretParametersError on API failure."""
        mock.get(
            "https://pmp.local/restapi/json/v1/resources/getResourceIdAccountId?RESOURCENAME=server01&ACCOUNTNAME=admin",
            status_code=500,
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretParametersError):
                self.provider.get_value_for_secret(self.secret)

    def test_missing_plugin_config(self):
        """Raise SecretParametersError if plugin config missing."""
        with self.settings(PLUGINS_CONFIG={}):
            with self.assertRaises(exceptions.SecretParametersError):
                self.provider.get_value_for_secret(self.secret)

    def test_missing_parameters(self):
        """Raise SecretParametersError if secret parameters are missing."""
        bad_secret = Secret.objects.create(
            name="bad-secret",
            provider=self.provider.slug,
            parameters={
                "resource_name": "",
                "account_name": "",
            },
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretParametersError) as err:
                self.provider.get_value_for_secret(bad_secret)

        self.assertIn("Resource name and account name must be provided", str(err.exception))


class BeyondTrustPasswordSafeManagedAccountSecretsProviderTestCase(TestCase):
    """Tests for BeyondTrustPasswordSafeManagedAccountSecretsProvider."""

    provider = BeyondTrustPasswordSafeManagedAccountSecretsProvider
    base_url = "https://beyondtrust.local/BeyondTrust/api/public/v3"

    def setUp(self):
        """Create a secret for use with testing."""
        super().setUp()

        self.secret = Secret.objects.create(
            name="core-switch-account",
            provider=self.provider.slug,
            parameters={
                "system_name": "sw01.sitea",
                "account_name": "network_admin",
            },
        )

        self.plugin_config = {
            "nautobot_secrets_providers": {
                "beyondtrust_password_safe": {
                    "base_url": self.base_url,
                    "client_id": "fake-client-id",
                    "client_secret": "fake-client-secret",
                    "verify_ssl": False,
                }
            }
        }

    @staticmethod
    def _mock_auth(mock, base_url):
        """Register the OAuth token endpoint and sign-out.

        With a bearer token the token is sent on every request, so no session is created and there
        is no sign-in call.
        """
        mock.post(f"{base_url}/Auth/connect/token", json={"access_token": "fake-token", "expires_in": 3600})
        mock.post(f"{base_url}/Auth/Signout", status_code=204)

    @staticmethod
    def _mock_account(mock, base_url):
        """Register the managed account lookup."""
        mock.get(
            f"{base_url}/ManagedAccounts",
            json=[
                {"SystemId": 100, "AccountId": 200, "SystemName": "sw01.sitea", "AccountName": "network_admin"},
                {"SystemId": 101, "AccountId": 201, "SystemName": "sw02.siteb", "AccountName": "network_admin"},
            ],
        )

    @requests_mock.Mocker()
    def test_retrieve_success(self, mock):
        """Create a release request and return the credential for it."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            result = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(result, "s3cret-password")
        token_request = mock.request_history[0]
        self.assertEqual(token_request.headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertIn("grant_type=client_credentials", token_request.text)
        self.assertEqual(mock.request_history[1].headers["Authorization"], "Bearer fake-token")

    @requests_mock.Mocker()
    def test_release_request_payload(self, mock):
        """The release request carries the resolved IDs, duration and rotation flag."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        secret = Secret.objects.create(
            name="core-switch-account-rotate",
            provider=self.provider.slug,
            parameters={
                "system_name": "sw01.sitea",
                "account_name": "network_admin",
                "duration_minutes": "15",
                "rotate_on_checkin": "true",
                "reason": "planned maintenance",
            },
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            self.provider.get_value_for_secret(secret)

        release = [call for call in mock.request_history if call.path.endswith("/requests")][0]
        self.assertEqual(
            release.json(),
            {
                "SystemId": 100,
                "AccountId": 200,
                "DurationMinutes": 15,
                "Reason": "planned maintenance",
                "ConflictOption": "reuse",
                "RotateOnCheckin": True,
            },
        )

    @requests_mock.Mocker()
    def test_release_request_payload_default_no_rotation(self, mock):
        """A read with no rotate_on_checkin parameter does not ask Password Safe to rotate."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            self.provider.get_value_for_secret(self.secret)

        release = [call for call in mock.request_history if call.path.endswith("/requests")][0]
        self.assertNotIn("RotateOnCheckin", release.json())

    @requests_mock.Mocker()
    def test_managed_account_lookup_uses_server_side_filter(self, mock):
        """The managed-account lookup filters by system and account name on the server."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            self.provider.get_value_for_secret(self.secret)

        lookup = [call for call in mock.request_history if "managedaccounts" in call.url.lower()][0]
        self.assertEqual(lookup.qs["systemname"], ["sw01.sitea"])
        self.assertEqual(lookup.qs["accountname"], ["network_admin"])

    @requests_mock.Mocker()
    def test_managed_account_single_object_response(self, mock):
        """A filtered lookup that returns a single account object instead of a list is handled."""
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/ManagedAccounts",
            json={"SystemId": 100, "AccountId": 200, "SystemName": "sw01.sitea", "AccountName": "network_admin"},
        )
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            result = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(result, "s3cret-password")

    @requests_mock.Mocker()
    def test_api_key_auth(self, mock):
        """An API key with a run-as user authenticates without an OAuth token and signs out afterwards."""
        config = {"beyondtrust_password_safe": {"base_url": self.base_url, "api_key": "fake-key", "run_as": "nautobot_svc"}}
        mock.post(f"{self.base_url}/Auth/SignAppIn", json={"UserId": 1})
        mock.post(f"{self.base_url}/Auth/Signout", status_code=204)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": config}):
            result = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(result, "s3cret-password")
        self.assertEqual(mock.request_history[0].headers["Authorization"], "PS-Auth key=fake-key; runas=nautobot_svc;")
        self.assertTrue(mock.request_history[0].url.endswith("/Auth/SignAppIn"))
        self.assertTrue(mock.request_history[-1].url.endswith("/Auth/Signout"))

    @requests_mock.Mocker()
    def test_oauth_run_as_header(self, mock):
        """OAuth impersonation uses a RunAs header, not the authorization header."""
        config = {
            "beyondtrust_password_safe": {
                "base_url": self.base_url,
                "client_id": "fake-client-id",
                "client_secret": "fake-client-secret",
                "run_as": "nautobot_svc",
            }
        }
        mock.post(f"{self.base_url}/Auth/connect/token", json={"access_token": "fake-token", "expires_in": 3600})
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", json="s3cret-password")

        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": config}):
            self.provider.get_value_for_secret(self.secret)

        urls = [call.url for call in mock.request_history]
        self.assertNotIn(f"{self.base_url}/Auth/SignAppIn", urls)
        self.assertEqual(mock.request_history[1].headers["RunAs"], "nautobot_svc")

    @requests_mock.Mocker()
    def test_check_in_triggers_rotation(self, mock):
        """Checking a request back in is a separate call, so rotation happens after the credential is used."""
        self._mock_auth(mock, self.base_url)
        # Password Safe returns 204 No Content on a successful check-in.
        mock.put(f"{self.base_url}/Requests/4211/Checkin", status_code=204)

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            self.provider.check_in(self.secret, 4211, reason="done")

        check_in = [call for call in mock.request_history if call.method == "PUT"][0]
        self.assertEqual(check_in.json(), {"Reason": "done"})

    def test_missing_config(self):
        """Raise SecretProviderError if BeyondTrust is not configured."""
        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {}}):
            with self.assertRaises(exceptions.SecretProviderError):
                self.provider.get_value_for_secret(self.secret)

    def test_missing_credentials(self):
        """Raise SecretProviderError if neither an OAuth client nor an API key is configured."""
        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {"beyondtrust_password_safe": {"base_url": self.base_url}}}):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_value_for_secret(self.secret)

        self.assertIn("client_id", str(err.exception))

    @requests_mock.Mocker()
    def test_account_not_found(self, mock):
        """Raise SecretValueNotFoundError when the system/account pair does not exist."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)

        secret = Secret.objects.create(
            name="unknown-account",
            provider=self.provider.slug,
            parameters={"system_name": "sw99.sitez", "account_name": "network_admin"},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                self.provider.get_value_for_secret(secret)

        self.assertIn("sw99.sitez", str(err.exception))

    @requests_mock.Mocker()
    def test_unapproved_request(self, mock):
        """Map BeyondTrust error code 4034 onto a provider error."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)
        mock.get(f"{self.base_url}/credentials/4211", text="4034", status_code=400)

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_value_for_secret(self.secret)

        self.assertIn("not yet approved", str(err.exception))

    @requests_mock.Mocker()
    def test_release_returns_request_id(self, mock):
        """release() returns the request ID so a job can check it in after using the credential."""
        self._mock_auth(mock, self.base_url)
        self._mock_account(mock, self.base_url)
        mock.post(f"{self.base_url}/requests", json=4211, status_code=201)

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            request_id = self.provider.release(self.secret)

        self.assertEqual(request_id, 4211)


class BeyondTrustPasswordSafeSecretsSafeSecretsProviderTestCase(TestCase):
    """Tests for BeyondTrustPasswordSafeSecretsSafeSecretsProvider."""

    provider = BeyondTrustPasswordSafeSecretsSafeSecretsProvider
    base_url = "https://beyondtrust.local/BeyondTrust/api/public/v3"

    def setUp(self):
        """Create a secret for use with testing."""
        super().setUp()

        self.secret = Secret.objects.create(
            name="gitlab-service-account",
            provider=self.provider.slug,
            parameters={"folder_path": "IT/Platform", "title": "GitLab Service Account"},
        )

        self.plugin_config = {
            "nautobot_secrets_providers": {
                "beyondtrust_password_safe": {
                    "base_url": self.base_url,
                    "client_id": "fake-client-id",
                    "client_secret": "fake-client-secret",
                    "verify_ssl": False,
                }
            }
        }

    @staticmethod
    def _mock_auth(mock, base_url):
        """Register the OAuth token endpoint and sign-out. No session, so no sign-in call."""
        mock.post(f"{base_url}/Auth/connect/token", json={"access_token": "fake-token", "expires_in": 3600})
        mock.post(f"{base_url}/Auth/Signout", status_code=204)

    @staticmethod
    def _entry(**overrides):
        """A Secrets Safe entry in the documented `SecretsSafeSecretModel` shape."""
        entry = {
            "Id": "1b1b1b1b-1b1b-1b1b-1b1b-1b1b1b1b1b1b",
            "Title": "GitLab Service Account",
            "Folder": "Platform",
            "FolderId": "2c2c2c2c-2c2c-2c2c-2c2c-2c2c2c2c2c2c",
            "FolderPath": "IT/Platform",
            "SecretType": "Text",
            "Text": "glpat-fake-token",
            "Password": None,
            "Username": None,
            "TotpEnabled": False,
        }
        entry.update(overrides)
        return entry

    @staticmethod
    def _search(entries, total=None):
        """Wrap entries in the real Secrets Safe search envelope: `{"TotalCount", "Data"}`."""
        return {"TotalCount": len(entries) if total is None else total, "Data": list(entries)}

    @requests_mock.Mocker()
    def test_retrieve_success(self, mock):
        """Read a Secrets Safe secret by folder path and title."""
        self._mock_auth(mock, self.base_url)
        mock.get(f"{self.base_url}/Secrets-Safe/Secrets", json=self._search([self._entry()]))

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            result = self.provider.get_value_for_secret(self.secret)

        self.assertEqual(result, "glpat-fake-token")
        # requests_mock lowercases the path and query, so assert on the url.
        search = [call for call in mock.request_history if call.url.split("?")[0].endswith("/Secrets-Safe/Secrets")][0]
        for fragment in ("Path=IT%2FPlatform", "Title=GitLab+Service+Account", "Decrypt=true", "version=3.2"):
            self.assertIn(fragment, search.url)

    @requests_mock.Mocker()
    def test_retrieve_by_secret_id(self, mock):
        """A secret ID is a UUID and a direct lookup, with no path and title search."""
        secret_id = "3d3d3d3d-3d3d-3d3d-3d3d-3d3d3d3d3d3d"
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets/{secret_id}",
            json=self._entry(
                Id=secret_id,
                Title="Panorama API Key",
                SecretType="Credential",
                Password="panorama-fake-key",
                Text=None,
                Username="api",
            ),
        )

        secret = Secret.objects.create(
            name="panorama-key",
            provider=self.provider.slug,
            parameters={"secret_id": secret_id},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            result = self.provider.get_value_for_secret(secret)

        self.assertEqual(result, "panorama-fake-key")

    @requests_mock.Mocker()
    def test_value_missing_without_decrypt(self, mock):
        """The documented model returns metadata only unless Decrypt is set, so a null value is an error."""
        self._mock_auth(mock, self.base_url)
        mock.get(f"{self.base_url}/Secrets-Safe/Secrets", json=self._search([self._entry(Text=None)]))

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                self.provider.get_value_for_secret(self.secret)

        self.assertIn("No value", str(err.exception))

    @requests_mock.Mocker()
    def test_totp_secret_is_not_resolved(self, mock):
        """A TOTP-enabled secret has no stored value; its code comes from a separate endpoint."""
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets",
            json=self._search(
                [self._entry(Title="Break Glass", SecretType="Credential", Password=None, Text=None, TotpEnabled=True)]
            ),
        )

        secret = Secret.objects.create(
            name="break-glass",
            provider=self.provider.slug,
            parameters={"folder_path": "IT/Platform", "title": "Break Glass"},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                self.provider.get_value_for_secret(secret)

        self.assertIn("totp-code", str(err.exception))

    @requests_mock.Mocker()
    def test_pagination_walks_past_the_limit(self, mock):
        """Results are paged with Offset until a short page comes back."""
        config = dict(self.plugin_config["nautobot_secrets_providers"]["beyondtrust_password_safe"])
        config["page_size"] = 2
        self._mock_auth(mock, self.base_url)

        target = self._entry(
            Title="Meraki Dashboard API Key", SecretType="Credential", Password="meraki-fake-key", Text=None
        )
        query = "Path=IT%2FPlatform&Title=Meraki+Dashboard+API+Key&Decrypt=true&Limit=2&Offset={offset}&version=3.2"
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets?{query.format(offset=0)}",
            json=self._search([self._entry(Title="Other"), self._entry(Title="Another")], total=3),
        )
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets?{query.format(offset=2)}",
            json=self._search([target], total=3),
        )

        secret = Secret.objects.create(
            name="meraki-key",
            provider=self.provider.slug,
            parameters={"folder_path": "IT/Platform", "title": "Meraki Dashboard API Key"},
        )

        with self.settings(PLUGINS_CONFIG={"nautobot_secrets_providers": {"beyondtrust_password_safe": config}}):
            result = self.provider.get_value_for_secret(secret)

        self.assertEqual(result, "meraki-fake-key")
        offsets = [
            call.url.split("Offset=")[1].split("&")[0]
            for call in mock.request_history
            if call.url.split("?")[0].endswith("/Secrets-Safe/Secrets")
        ]
        self.assertEqual(offsets, ["0", "2"])

    @requests_mock.Mocker()
    def test_permission_denied(self, mock):
        """Surface the API's own 403 message, which Password Safe Cloud returns as a bare JSON string."""
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets",
            json="Permission exception: One of these permissions are required: SecretsSafe.Read, WorkforcePasswords.Read",
            status_code=403,
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_value_for_secret(self.secret)

        self.assertIn("permissions are required", str(err.exception))

    @requests_mock.Mocker()
    def test_secret_id_not_found(self, mock):
        """A by-id lookup of a missing secret returns a 404 object body, which is surfaced."""
        secret_id = "4e4e4e4e-4e4e-4e4e-4e4e-4e4e4e4e4e4e"
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets/{secret_id}",
            json={"error": "Secret does not exist."},
            status_code=404,
        )

        secret = Secret.objects.create(
            name="missing-by-id",
            provider=self.provider.slug,
            parameters={"secret_id": secret_id},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretProviderError) as err:
                self.provider.get_value_for_secret(secret)

        self.assertIn("Secret does not exist", str(err.exception))

    @requests_mock.Mocker()
    def test_secret_not_found(self, mock):
        """Raise SecretValueNotFoundError when the path and title do not match a secret."""
        self._mock_auth(mock, self.base_url)
        mock.get(f"{self.base_url}/Secrets-Safe/Secrets", json=self._search([]))

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretValueNotFoundError) as err:
                self.provider.get_value_for_secret(self.secret)

        self.assertIn("GitLab Service Account", str(err.exception))

    def test_missing_parameters(self):
        """Raise SecretParametersError when neither an ID nor a path and title are given."""
        secret = Secret.objects.create(name="no-params", provider=self.provider.slug, parameters={})

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretParametersError) as err:
                self.provider.get_value_for_secret(secret)

        self.assertIn("secret_id", str(err.exception))

    @requests_mock.Mocker()
    def test_file_secret_not_supported(self, mock):
        """File secrets are out of scope and fail with a clear message."""
        self._mock_auth(mock, self.base_url)
        mock.get(
            f"{self.base_url}/Secrets-Safe/Secrets",
            json=self._search(
                [
                    self._entry(
                        Title="Report Builder File",
                        SecretType="File",
                        Text=None,
                        FileName="report.zip",
                        FileHash="abc123",
                    )
                ]
            ),
        )

        secret = Secret.objects.create(
            name="report-file",
            provider=self.provider.slug,
            parameters={"folder_path": "IT/Platform", "title": "Report Builder File"},
        )

        with self.settings(PLUGINS_CONFIG=self.plugin_config):
            with self.assertRaises(exceptions.SecretParametersError) as err:
                self.provider.get_value_for_secret(secret)

        self.assertIn("File secrets", str(err.exception))
