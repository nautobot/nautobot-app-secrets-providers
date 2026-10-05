# Nautobot Secrets Providers Package

::: nautobot_secrets_providers.providers
    options:
        show_submodules: True

## Bitwarden Provider Notes

- Widget JavaScript lives in the Django static asset path `nautobot_secrets_providers/static/nautobot_secrets_providers/bitwarden_widget.js` and is loaded via a script `src` from the form widget renderer.
- The Bitwarden form widget JavaScript is organized around a small internal API wrapper that only calls Nautobot app endpoints for item info, search results, and custom-field names.
- Those Bitwarden helper endpoints are protected with the `extras.view_secret` permission so authenticated users still need Secret view access when calling them directly.
- Secret Field choices are initialized from provider choices and then filtered at runtime by Bitwarden item type metadata returned from the dedicated item-info endpoint.
- Request error handling in the provider logs request failures with URL and status context while avoiding credential output.
- Request sessions are created per request with retry configuration and are always closed after each request path (success and error).