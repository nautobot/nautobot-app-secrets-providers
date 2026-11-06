# BeyondTrust Password Safe

Two providers are supported:

- **BeyondTrust Managed Account** — a credentials release request is created for the managed account and the
  credential is returned for that request. Checking the request back in is what triggers password rotation,
  so rotation is a separate step from reading a secret.
- **BeyondTrust Secrets Safe** — a Text or Credential secret is read by folder path and title, or by secret
  ID. Plain lookup and read: no request lifecycle, nothing checked in, nothing rotated. File secrets are not
  supported.

## Prerequisites

Password Safe (BeyondInsight / Password Safe on-prem, or Password Safe Cloud / Pathfinder) must be
reachable from Nautobot over HTTPS.

### Base URL

The `base_url` is the API endpoint plus the `/BeyondTrust/api/public/v3` path — **not** the sign-in portal:

- **On-prem:** `https://<your-host>/BeyondTrust/api/public/v3`
- **Cloud / Pathfinder:** the **Base API Endpoint** shown on the API Registration page, for example
  `https://<instance>.ps.beyondtrustcloud.com/BeyondTrust/api/public/v3`. The admin portal
  (`https://app.beyondtrust.io/`) is **not** the API host.

### Authentication

Two paths are supported; the API registration must be enabled for whichever you use:

- **OAuth client** (recommended) — create an **API Access Policy** registration and an **Application**
  user bound to it, then use its `client_id` / `client_secret`. On Cloud the registration requires an
  **IP rule** that allow-lists the caller's public IP (Nautobot's egress address), or authentication
  returns a generic 401.
- **API key** — create an API key and the user it runs as (`run_as`). Keys are only usable with the
  `PS-Auth` header, so a run-as user is required. On Cloud the API-key path enforces MFA by default,
  which automation cannot answer, so prefer the OAuth path.

### Permissions (least privilege)

Grant the API user's group only what each provider needs:

- **Secrets Safe** — **Secrets Safe (Read)** on the target safe or folder. Read is sufficient; the
  provider never writes.
- **Managed accounts** — a Password Safe role that can create release requests on the target system and
  account, and the account must have **"Enable for API Access"** set, or it will not appear in
  `GET /ManagedAccounts`.

## Configuration

Provide a mapping in `PLUGINS_CONFIG` within your `nautobot_config.py`, for example:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "beyondtrust": {
            "base_url": os.getenv("BT_BASE_URL"),  # e.g. https://bt.example.com/BeyondTrust/api/public/v3
            "client_id": os.getenv("BT_CLIENT_ID"),
            "client_secret": os.getenv("BT_CLIENT_SECRET"),
            "verify_ssl": True,
            "timeout": 30,
        },
    },
}
```

Or, for API-key auth:

```python
PLUGINS_CONFIG = {
    "nautobot_secrets_providers": {
        "beyondtrust": {
            "base_url": os.getenv("BT_BASE_URL"),
            "api_key": os.getenv("BT_API_KEY"),
            "run_as": os.getenv("BT_RUN_AS"),
        },
    },
}
```

The `client_secret` / `api_key` is a bootstrap credential — it cannot be fetched from BeyondTrust itself,
so supply it from the environment or your deployment's secret store rather than committing it to
`nautobot_config.py`.

## Secret parameters

When creating a Secret with the **BeyondTrust Managed Account** provider:

| Parameter | Required | Notes |
|---|---|---|
| `system_name` | yes | Managed system (asset) name. Supports Jinja2, e.g. `{{ obj.name }}` |
| `account_name` | yes | Managed account name on that system |
| `duration_minutes` | no | Release window in minutes, default `5` |
| `rotate_on_checkin` | no | `true` / `false`, default `true` |
| `reason` | no | Reason recorded on the request |

When creating a Secret with the **BeyondTrust Secrets Safe** provider:

| Parameter | Required | Notes |
|---|---|---|
| `folder_path` | yes* | Secrets Safe folder path, e.g. `IT/Platform`. Supports Jinja2 |
| `title` | yes* | Secret title inside the folder |
| `secret_id` | no | Direct lookup instead of a path and title search |

\* `folder_path` and `title` are required unless `secret_id` is provided.

## Rotation

A normal read never rotates. Reading a managed-account secret — the **Check Secret** button, or a Secrets
Group lookup from a Job — opens a release request, returns the credential, and lets the request expire.
Nothing is checked in and nothing changes.

Rotation is a separate, opt-in action, because the secrets-provider interface only reads. The managed-account
provider exposes `release()` and `check_in()` so a Job can run the full lifecycle and rotate the password
*after* it has been used:

This app is a provider library and ships no Jobs, so the lifecycle lives in a consumer-side Job (place it
in `JOBS_ROOT`, a Git-repository job source, or an app's `jobs.py`):

```python
from nautobot.apps.jobs import BooleanVar, Job, ObjectVar, register_jobs
from nautobot.dcim.models import Device
from nautobot.extras.choices import SecretsGroupAccessTypeChoices as AT, SecretsGroupSecretTypeChoices as ST
from nautobot.extras.models import SecretsGroupAssociation
from nautobot_secrets_providers.providers import BeyondTrustManagedAccountSecretsProvider as BT


class RotateBeyondTrustManagedAccount(Job):
    """Check out a device's managed-account credential, use it, and check it back in."""

    device = ObjectVar(model=Device)
    rotate = BooleanVar(default=False, description="Rotate on check-in (requires a Resource Broker).")

    class Meta:
        name = "BeyondTrust: Rotate Managed Account"
        has_sensitive_variables = False

    def run(self, device, rotate):
        group = device.secrets_group
        secret = SecretsGroupAssociation.objects.get(
            secrets_group=group, access_type=AT.TYPE_GENERIC, secret_type=ST.TYPE_PASSWORD
        ).secret
        # RotateOnCheckin is set when the request is created, so decide it up front.
        secret.parameters = {**secret.parameters, "rotate_on_checkin": "true" if rotate else "false"}

        request_id = BT.release(secret, obj=device)                                       # open the request
        password = group.get_secret_value(AT.TYPE_GENERIC, ST.TYPE_PASSWORD, obj=device)  # reuses it (ConflictOption: reuse)
        self.logger.info("Retrieved the credential (%d chars) for %s.", len(password), device.name)
        # ...use `password` against the device...
        BT.check_in(secret, request_id, reason="rotation job")                            # check in -> rotate if configured + reachable


register_jobs(RotateBeyondTrustManagedAccount)
```

Passing `obj=device` is what lets a Jinja parameter such as `system_name = {{ obj.name }}` resolve per
device, so one Secret serves many devices.

Rotation on check-in only actually changes the password when **both** hold:

1. the Secret's `rotate_on_checkin` parameter is `true` (sets `RotateOnCheckin` on the request), and
2. Password Safe can reach and manage the target account — a functional account plus connectivity, which on
   Password Safe **Cloud** requires a **Resource Broker**.

If Password Safe cannot reach the device, the check-in still succeeds but the password change fails on the
Password Safe side (visible on the account's change status, not in Nautobot) and the vaulted value is
unchanged.
