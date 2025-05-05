# Using the App

The Nautobot Secrets Provider app is used for integrating secrets into Nautobot and its automated workflows using third-party vendors to safely store and retrieve secrets or other sensitive information.

## General Usage

The overall design philosophy of Nautobot is to not permanently store any passwords or otherwise sensitive information, and to instead leverage existing tools designed specifically for this purpose in order to integrate them into various automations and workflows.

This app enables support for various common vendors and integrates the secret retrieval process seamlessly into Nautobot.

## Supported Vendor Screenshots

### General Config

![Screenshot of installed apps](../images/light/secrets-providers-installed-apps.png#only-light "App landing page")
![Screenshot of installed apps](../images/dark/secrets-providers-installed-apps.png#only-dark "App landing page")

---

![Screenshot of plugin home page](../images/light/secrets-providers-home.png#only-light "App Home page")
![Screenshot of plugin home page](../images/dark/secrets-providers-home.png#only-dark "App Home page")

---

![Screenshot of secret using AWS Secrets Manager](../images/light/aws-secrets-manager-secrets-provider-add.png#only-light "Secret using AWS Secrets Manager")
![Screenshot of secret using AWS Secrets Manager](../images/dark/aws-secrets-manager-secrets-provider-add.png#only-dark "Secret using AWS Secrets Manager")

---

![Screenshot of secret using AWS Systems Manager](../images/light/aws-secrets-manager-systems-provider-add.png#only-light "Secret using AWS Systems Manager")
![Screenshot of secret using AWS Systems Manager](../images/dark/aws-secrets-manager-systems-provider-add.png#only-dark "Secret using AWS Systems Manager")

---

![Screenshot of secret using HashiCorp Vault](../images/light/hashicorp-vault-secrets-provider-add.png#only-light "Secret using HashiCorp Vault")
![Screenshot of secret using HashiCorp Vault](../images/dark/hashicorp-vault-secrets-provider-add.png#only-dark "Secret using HashiCorp Vault")

---

![Screenshot of secret using Delinea Secret Server by ID](../images/light/delinea-id-secrets-provider-add.png#only-light "Secret using Delinea Secret Server by ID")
![Screenshot of secret using Delinea Secret Server by ID](../images/dark/delinea-id-secrets-provider-add.png#only-dark "Secret using Delinea Secret Server by ID")

---

![Screenshot of secret using Delinea Secret Server by Path](../images/light/delinea-path-secrets-provider-add.png#only-light "Secret using Delinea Secret Server by Path")
![Screenshot of secret using Delinea Secret Server by Path](../images/dark/delinea-path-secrets-provider-add.png#only-dark "Secret using Delinea Secret Server by Path")

---

![Screenshot of secret using Azure Key Vault](../images/light/azure-key-vault-secrets-provider-add.png#only-light "Secret using Azure Key Vault")
![Screenshot of secret using Azure Key Vault](../images/dark/azure-key-vault-secrets-provider-add.png#only-dark "Secret using Azure Key Vault")

---

![Screenshot of secret using 1Password](../images/light/1password-vault-secrets-provider-add.png#only-light "Secret using 1Password")
![Screenshot of secret using 1Password](../images/dark/1password-vault-secrets-provider-add.png#only-dark "Secret using 1Password")
