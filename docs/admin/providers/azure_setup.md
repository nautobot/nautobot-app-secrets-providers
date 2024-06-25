### Azure Key Vault

#### Authentication

No configuration is required within Nautobot for this provider to work. You must provide [Azure Service Principal credentials in one of the formats supported by the azure-identity library](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.environmentcredential?view=azure-python). The credential variables should be injected into Nautobot's environment via your preferred method.

The recommended method is to use a Service Principal with Secret, for which creds.example.env has an example. [More information on how to set up the SP in Azure in the Azure docs](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide?tabs=azure-cli).
