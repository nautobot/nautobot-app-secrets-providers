import socket
from email.policy import default

from django import forms
from django.conf import settings

try:
    import requests
except ImportError:
    requests = None

from nautobot.extras.secrets import SecretsProvider, exceptions
from nautobot.core.forms import BootstrapMixin

__all__ = ("CyberARKSecretsProvider")

class CyberARKSecretsProvider(SecretsProvider):
    """
    A secrets provider for CyberARK AIM.
    """
    
    slug = "cyberark"
    name = "CyberARK"
    is_available = requests is None
    
    class ParametersForm(BootstrapMixin, forms.Form):
        """
        Required parameters for CyberARK.
        """
        
        object = forms.CharField(
            required = False,
            help_text = "Object to requestin CyberARK (not required if username is given)"
        )
        username = forms.CharField(
            required = True if object.empty_value else False,
            help_text = "Username to request in CyberARK (not required if objects is given)"
        )
        object.required = True if username.empty_value else False
    
    @classmethod
    def get_value_for_secret(cls, secret, obj=None, **kwargs):
        """
        Return the value stored under the

        Args:
            secret (_type_): _description_
            obj (_type_, optional): _description_. Defaults to None.
        """
        
        plugin_settings = settings.PLUGINS_CONFIG['nautobot_secret_providers']
        if 'cyberark' not in plugin_settings:
            raise exceptions.SecretProviderError(secret, cls, "CyberARK is not configured")
        
        cyberark_settings = plugin_settings["cyberark"]

        if "url" not in cyberark_settings:
            raise exceptions.SecretProviderError(secret, cls, "CyberARK url is not set in PLUGINS_CONFIG['nautobot_secret_providers']['cyberark']")
        
        parameters = secret.rendered_parameters(obj=obj)
        try:
            secret_username = parameters["username"]
            secret_object = parameters["object"]
        except KeyError as err:
            msg = f"The secret parameter could not be retrieved for field {err}"
            raise exceptions.SecretParametersError(secret, cls, msg) from err
        
        try:
            if "token" in cyberark_settings:
                token = cyberark_settings["token"]
            else:
                cyberark_settings["username"]
                cyberark_settings["password"]
            cyberark_settings["auth_method"]
        except KeyError as err:
            raise exceptions.SecretProviderError(secret, cls, f"Can't retrieve field {err} from PLUGINS_CONFIG['nautobot_secret_providers']['cyberark']")
        
        if "token" not in cyberark_settings:
            response = requests.post(
                f"{cyberark_settings['url']}/PasswordVault/API/auth/{cyberark_settings['auth_method']}/Logon",
                verify = cyberark_settings['verifySsl'],  # If needs to disable cert check only for CyberARK
                data = {
                    "username": cyberark_settings["username"],
                    "password": cyberark_settings["password"]
                }
            )
            if response.status_code != 200:
                raise exceptions.SecretProviderError(secret, cls, f"Can't get token: {response.status_code} {response.text}")
            
            token = response.text.replace('"', '')
        
        response = requests.get(
            f"{cyberark_settings['url']}/PasswordVault/api/Accounts/?search={secret_username}",  # This call can be very long to answer depending of the CyberARK instance setup
            verify = cyberark_settings['verifySsl'],
            headers = {"Authorization": token},
        )
        
        if response.status_code != 200:
            raise exceptions.SecretProviderError(secret, cls, f"Can't get value: {response.status_code} {response.text}")
        return requests.post(
            f"{cyberark_settings['url']}/PasswordVault/api/Accounts/{response.json()['value'][0]['id']}/Password/Retrieve",
            verify = cyberark_settings["verifySsl"],
            headers = { 'Authorization': token },
        ).text.replace('"', '')