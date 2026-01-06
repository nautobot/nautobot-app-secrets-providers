# Azure Key Vault

## Prerequisites

Ensure that an Azure Service Principal is created and has been configured with access to the targeted Key Vault(s) using the "Key Vault Secrets User" role. More information on how to set up the Service Principal in Azure can be found in the [Azure docs](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide?tabs=azure-cli).

## Authentication

No configuration is needed within Nautobot for this provider to operate. Instead, you must provide Azure Service Principal credentials in one of the [formats supported by the `azure-identity` library](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.environmentcredential?view=azure-python). The credential variables should then be injected into Nautobot's environment via your preferred method. The `creds.example.env` file has examples of the variables from the methods discussed below.

### Service Principal with Secret

The recommended method is to use a [Service Principal with Secret](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python#service-principal-with-secret). This method requires three environment variables to be set within the Nautobot environment:

```python
AZURE_TENANT_ID=''
AZURE_CLIENT_ID=''
AZURE_CLIENT_SECRET=''
```

### Service Principal with Certificate

You can also use a [Service Principal with Certificate](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python#service-principal-with-certificate), which has these environment variables:

```python
AZURE_TENANT_ID=''
AZURE_CLIENT_ID=''
AZURE_CLIENT_CERTIFICATE_PATH=''
AZURE_CLIENT_CERTIFICATE_PASSWORD=''  # Optional
```
