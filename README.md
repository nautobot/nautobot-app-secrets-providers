# Nautobot Secrets Providers

A plugin for [Nautobot](https://github.com/nautobot/nautobot) 1.2.0 or higher that bundles Secrets Providers for integrating with popular secrets backends.

## Supported Secrets Backends

This plugin currently supports the following popular secrets backends.

- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [HashiCorp Vault](https://www.vaultproject.io)

## Installation

The plugin is available as a Python package in PyPI and can be installed with pip:

```no-highlight
pip install nautobot-secrets-providers
```

> The plugin is compatible with Nautobot 1.2.0 and higher

To ensure Nautobot Secrets Providers is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the `secrets` package:

```no-highlight
echo nautobot-secrets-providers >> local_requirements.txt
```

Once installed, the plugin needs to be enabled in your `nautobot_config.py`:

```python
# In your nautobot_config.py
PLUGINS = ["nautobot_secrets_providers"]

# PLUGINS_CONFIG = {
#   "nautobot_secrets_providers": {
#      See below for how ot configure Nautobot for each secrets provider!
#   }
# }
```

## Usage

You must install the dependencies for at least one of the supported secrets providers or a `RuntimeError` will be raised.

Do not enable this plugin until you are able to install the depenedncies, as it will block Nautobot from starting.

### AWS Secrets Manager

#### Dependencies

The AWS Secrets Manager provider requires the `boto3` library. This can be easily installed along with the plugin using the following command:

```no-highlight
pip install nautobot-secrets-providers[aws]
```

#### Configuration

No configuration is needed within Nautobot for this provider to operate. Instead you must provide [AWS credentials in one of the methods supported by the `boto3` library](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). 

Boto3 credentials can be configured in multiple ways (eight as of this writing) that are mirrored here:

1. Passing credentials as parameters in the boto.client() method
2. Passing credentials as parameters when creating a Session object
3. Environment variables
4. Shared credential file (~/.aws/credentials)
5. AWS config file (~/.aws/config)
6. Assume Role provider
7. Boto2 config file (/etc/boto.cfg and ~/.boto)
8. Instance metadata service on an Amazon EC2 instance that has an IAM role configured.

**The AWS Secrets Manager provider only supports methods 3-8. Methods 1 and 2 ARE NOT SUPPORTED at this time.**

We highly recommend you defer to using environment variables for your deployment as specified in the credentials documentation linked above.

### HashiCorp Vault

#### Dependencies

The HashiCorp Vault provider requires the `hvac` library. This can easily be installed along with the plugin using the following command:

```no-highlight
pip install nautobot-secrets-providers[hashicorp]
```

#### Configuration

You must provide the following in `PLUGINS_CONFIG` within your `nautobot_config.py`:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "hashicorp_vault": {
            "url": {vault_url},
            "token": {vault_token},
        }
    },
}
```

- `url` - The URL to the HashiCorp Vault instance (e.g. `http://localhost:8200`)
- `token` - The token for authenticating the client with the HashiCorp Vault instance. As with other sensitive service credentials, we recommend that you provide the token value as an environment variable and retrieve it with `{"token": os.getenv("NAUTOBOT_HASHICORP_VAULT_TOKEN")}` rather than hard-coding it in your `nautobot_config.py`.

## Contributing

Pull requests are welcomed and automatically built and tested against multiple version of Python and multiple version of Nautobot through TravisCI.

The project is packaged with a light development environment based on `docker-compose` to help with the local development of the project and to run the tests within TravisCI.

The project is following Network to Code software development guideline and is leveraging:

- Black, Pylint, Bandit and pydocstyle for Python linting and formatting.
- Django unit test to ensure the plugin is working properly.

### Development Environment

The development environment can be used in 2 ways. First, with a local poetry environment if you wish to develop outside of Docker with the caveat of using external services provided by Docker for PostgreSQL and Redis. Second, all services are spun up using Docker and a local mount so you can develop locally, but Nautobot is spun up within the Docker container.

Below is a quick start guide if you're already familiar with the development environment provided, but if you're not familiar, please read the [Getting Started Guide](GETTING_STARTED.md).

#### Invoke

The [PyInvoke](http://www.pyinvoke.org/) library is used to provide some helper commands based on the environment.  There are a few configuration parameters which can be passed to PyInvoke to override the default configuration:

* `nautobot_ver`: the version of Nautobot to use as a base for any built docker containers (default: 1.2.0)
* `project_name`: the default docker compose project name (default: nautobot_secrets_providers)
* `python_ver`: the version of Python to use as a base for any built docker containers (default: 3.6)
* `local`: a boolean flag indicating if invoke tasks should be run on the host or inside the docker containers (default: False, commands will be run in docker containers)
* `compose_dir`: the full path to a directory containing the project compose files
* `compose_files`: a list of compose files applied in order (see [Multiple Compose files](https://docs.docker.com/compose/extends/#multiple-compose-files) for more information)

Using **PyInvoke** these configuration options can be overridden using [several methods](http://docs.pyinvoke.org/en/stable/concepts/configuration.html).  Perhaps the simplest is simply setting an environment variable `INVOKE_NAUTOBOT_SECRETS_PROVIDERS_VARIABLE_NAME` where `VARIABLE_NAME` is the variable you are trying to override.  The only exception is `compose_files`, because it is a list it must be overridden in a yaml file.  There is an example `invoke.yml` (`invoke.example.yml`) in this directory which can be used as a starting point.

#### Local Poetry Development Environment

1. Copy `development/creds.example.env` to `development/creds.env` (This file will be ignored by Git and Docker)
2. Uncomment the `POSTGRES_HOST`, `REDIS_HOST`, and `NAUTOBOT_ROOT` variables in `development/creds.env`
3. Create an `invoke.yml` file with the following contents at the root of the repo (you can also `cp invoke.example.yml invoke.yml` and edit as necessary):

```yaml
---
nautobot_secrets_providers:
  local: true
  compose_files:
    - "docker-compose.requirements.yml"
```

3. Run the following commands:

```shell
poetry shell
poetry install --extras nautobot
export $(cat development/dev.env | xargs)
export $(cat development/creds.env | xargs) 
invoke start && sleep 5
nautobot-server migrate
```

> If you want to develop on the latest develop branch of Nautobot, run the following command: `poetry add --optional git+https://github.com/nautobot/nautobot@develop`. After the `@` symbol must match either a branch or a tag.

4. You can now run nautobot-server commands as you would from the [Nautobot documentation](https://nautobot.readthedocs.io/en/latest/) for example to start the development server:

```shell
nautobot-server runserver 0.0.0.0:8080 --insecure
```

Nautobot server can now be accessed at [http://localhost:8080](http://localhost:8080).

It is typically recommended to launch the Nautobot **runserver** command in a separate shell so you can keep developing and manage the webserver separately.

#### Docker Development Environment

This project is managed by [Python Poetry](https://python-poetry.org/) and has a few requirements to setup your development environment:

1. Install Poetry, see the [Poetry Documentation](https://python-poetry.org/docs/#installation) for your operating system.
2. Install Docker, see the [Docker documentation](https://docs.docker.com/get-docker/) for your operating system.

Once you have Poetry and Docker installed you can run the following commands to install all other development dependencies in an isolated python virtual environment:

```shell
poetry shell
poetry install
invoke start
```

Nautobot server can now be accessed at [http://localhost:8080](http://localhost:8080).

To either stop or destroy the development environment use the following options.

- **invoke stop** - Stop the containers, but keep all underlying systems intact
- **invoke destroy** - Stop and remove all containers, volumes, etc. (This results in data loss due to the volume being deleted)

### CLI Helper Commands

The project is coming with a CLI helper based on [invoke](http://www.pyinvoke.org/) to help setup the development environment. The commands are listed below in 3 categories `dev environment`, `utility` and `testing`.

Each command can be executed with `invoke <command>`. Environment variables `INVOKE_NAUTOBOT_SECRETS_PROVIDERS_PYTHON_VER` and `INVOKE_NAUTOBOT_SECRETS_PROVIDERS_NAUTOBOT_VER` may be specified to override the default versions. Each command also has its own help `invoke <command> --help`

#### Docker dev environment

```no-highlight
  build            Build all docker images.
  debug            Start Nautobot and its dependencies in debug mode.
  destroy          Destroy all containers and volumes.
  restart          Restart Nautobot and its dependencies.
  start            Start Nautobot and its dependencies in detached mode.
  stop             Stop Nautobot and its dependencies.
```

#### Utility

```no-highlight
  cli              Launch a bash shell inside the running Nautobot container.
  create-user      Create a new user in django (default: admin), will prompt for password.
  makemigrations   Run Make Migration in Django.
  nbshell          Launch a nbshell session.
```

#### Testing

```no-highlight
  bandit           Run bandit to validate basic static code security analysis.
  black            Run black to check that Python files adhere to its style standards.
  flake8           This will run flake8 for the specified name and Python version.
  pydocstyle       Run pydocstyle to validate docstring formatting adheres to NTC defined standards.
  pylint           Run pylint code analysis.
  tests            Run all tests for this plugin.
  unittest         Run Django unit tests for the plugin.
```

### Project Documentation

Project documentation is generated by [mkdocs](https://www.mkdocs.org/) from the documentation located in the docs folder.  You can configure [readthedocs.io](https://readthedocs.io/) to point at this folder in your repo.  For development purposes a `docker-compose.docs.yml` is also included.  A container hosting the docs will be started using the invoke commands on [http://localhost:8001](http://localhost:8001), as changes are saved the docs will be automatically reloaded.

### Developing Against Secrets Backends

#### AWS Secrets Manager

This assumes you are logged into the AWS Console. 

- Navigate to AWS Console
- Navigate to AWS Secrets Manager
- Click "Store a new secret"
  - Select “Other type of secrets”
  - Use Secret key/value
  - Enter `hello=world`
  - Use "DefaultEncryptionKey" for now
  - Click "Next"
  - Under "Secret name" fill out `hello`
  - Click "Next"
  - Under "Configure automatic rotation"
    - Leave it as "Disable automatic rotation"
  - On "Store a new secret"
    - Copy the sample code (see below)
  - Click "Store"
- END

##### Install the AWS CLI

Next, install the [AWS CLI](https://aws.amazon.com/cli/).

On MacOS, this can be done using `brew install awscli`:

```
brew install awscli
```

On Linux, you will need to run a `curl` command (This assumes x86. Please see the docs for [AWS CLI on
Linux](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-linux.html) for ARM and other options):

```
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

##### Configure the AWS CLI

After installing the AWS CLI, you will need to configure it for authentication.

You may use an existing AWS access key or create a new one. For these instructions we cover the need to create a new access key that can be used for this.

- Navigate to AWS Console
- Click your username
  - Click "My security credentials"
  - Click "create access key"
- Save your "Access key ID" and "Secret access key" for use when configuring the AWS CLI

Now configure the CLI:

- Run `aws configure`
- Enter your credentials from above
- Choose your region
- Use output format: `json`

Example:

```no-highlight
$ aws configure
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-east-2
Default output format [None]: json
```

Now you are ready to use the sample code to retrieve your secret from AWS Secrets Manager!

##### Sample Code

Make sure that the `boto3` client is installed:

```no-highlight
poetry install --extras aws
```

Next, save this as `aws_secrets.py`:

```python
# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:   
# https://aws.amazon.com/developers/getting-started/python/

import boto3
import base64
from botocore.exceptions import ClientError


def get_secret():

    secret_name = "hello"
    region_name = "us-east-2"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
            
    # Your code goes here. 

# ^ Above was generated by AWS.

# This was added by us so you can run this as a script:
if __name__ == "__main__":
    secret = get_secret()
    print(f"Secret = {secret}")
```

Run it with `python aws_secrets.py`:

```
$ python aws_secrets.py
Secret = {"hello":"world"}.
```

Note that this blob is JSON and will also need to be decoded if you want to extract the value.

#### HashiCorp Vault

Make sure that the `hvac` client is installed:

```no-highlight
poetry install --extras hashicorp
```

##### Start Services with Docker

```no-highlight
invoke start
```

##### Set an alias to work with `vault` 

This will allow you to easily run the CLI command from within the container:

```no-highlight
alias vault="docker exec -it nautobot_secrets_providers_vault_1 vault"
```

Interact with the Vault vi CLI (via `docker exec` into the container from localhost):

```no-highlight
$ vault status
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    1
Threshold       1
Version         1.8.2
Storage Type    inmem
Cluster Name    vault-cluster-35c5d319
Cluster ID      2611f99c-a6de-a883-1fcc-bfffdc0217bc
HA Enabled      false
```

##### Using the Python `hvac` Library

This establishes a client, creates a basic key/value secret (`hello=world`) at the path `hello`, and then retrieves the data from the `hello` key at the secret path `hello`.

> This is equivalent to the command `vault kv get -field hello secret/hello`.

```python
In [1]: import hvac

In [2]: client = hvac.Client(url="http://localhost:8200", token="nautobot")

In [3]: client.secrets.kv.create_or_update_secret(path="hello", secret=dict(hello="world"))
Out[3]:
{'request_id': 'c4709868-c08f-4cb1-ab8c-605c58b82f3f',
 'lease_id': '',
 'renewable': False,
 'lease_duration': 0,
 'data': {'created_time': '2021-09-16T23:21:07.5564132Z',
  'deletion_time': '',
  'destroyed': False,
  'version': 2},
 'wrap_info': None,
 'warnings': None,
 'auth': None}

In [4]: client.secrets.kv.read_secret(path="hello")["data"]["data"]["hello"]
Out[4]: 'world'
```

## Questions

For any questions or comments, please check the [FAQ](FAQ.md) first and feel free to swing by the [Network to Code Slack workspace](https://networktocode.slack.com/) (channel `#networktocode`).
