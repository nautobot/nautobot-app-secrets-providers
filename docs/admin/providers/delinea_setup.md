# Delinea/Thycotic Secret Server (TSS)

The Delinea (formerly Thycotic) Secret Server provider includes two secret retrieval methods:

### Delinea Secret Server by ID

This method uses the `Secret ID` to specifiy the secret that is selected. The `Secret ID` is displayed in the browser's URL field if you `Edit` the data in Delinea Secret Server.

> **Example:** for the URL `https://pw.example.local/SecretServer/app/#/secret/1234/general`, the value for `Secret ID` is **1234**.

### Delinea Secret Server by Path

This method allows to select the secret by folder-path and secret-name. The path delimiter is a '\\'. The `Secret path` is displayed as page header when `Edit` a secret.

> **Example:** for the header `NET-Automation > Nautobot > My-Secret`, the value for `Secret path` is **\NET-Automation\Nautobot\My-Secret**.

## Configuration

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "delinea": {
            "base_url": os.getenv("SECRET_SERVER_BASE_URL", None),
            "ca_bundle_path": os.getenv("REQUESTS_CA_BUNDLE", None),
            "cloud_based": is_truthy(os.getenv("SECRET_SERVER_IS_CLOUD_BASED", "False")),
            "domain": os.getenv("SECRET_SERVER_DOMAIN", None),
            "password": os.getenv("SECRET_SERVER_PASSWORD", None),
            "tenant": os.getenv("SECRET_SERVER_TENANT", None),
            "token": os.getenv("SECRET_SERVER_TOKEN", None),
            "username": os.getenv("SECRET_SERVER_USERNAME", None),
        },
    }
}
```

- `base_url` - (required) The Secret Server base_url. _e.g.'https://pw.example.local/SecretServer'_
- `ca_bundle_path` - (optional) When using self-signed certificates, this variable must be set to a file containing the trusted certificates (in .pem format). _e.g. '/etc/ssl/certs/ca-bundle.trust.crt'_.
- `cloud_based` - (optional) Set to "True" if Secret Server Cloud should be used. (Default: "False").
- `domain` - (optional) Required for 'Domain Authorization'
- `password` - (optional) Required for 'Secret Server Cloud', 'Password Authorization', 'Domain Authorization'.
- `tenant` - (optional) Required for 'Domain Authorization'.
- `token` - (optional) Required for 'Access Token Authorization'.
- `username` - (optional) Required for 'Secret Server Cloud', 'Password Authorization', 'Domain Authorization'.
