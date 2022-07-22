"""Exception classes specific to secrets."""


class ConnectorError(Exception):
    """General purpose exception class for failures raised when secret value access fails."""

    def __init__(self, connector_class, message, *args, **kwargs):
        """Collect some additional data."""
        super().__init__(message, *args, **kwargs)
        self.connector_class = connector_class
        self.message = message

    def __str__(self):
        """Format the Exception as a string."""
        return f"{self.__class__.__name__}: " f'(connector "{self.connector_class.__name__}"): {self.message}'


class SecretValueNotFoundError(Exception):
    """General purpose exception class for failures raised when secret value access fails."""

    def __init__(self, connector_class, message, *args, **kwargs):
        """Collect some additional data."""
        super().__init__(message, *args, **kwargs)
        self.connector_class = connector_class
        self.message = message

    def __str__(self):
        """Format the Exception as a string."""
        return f"{self.__class__.__name__}: " f'(connector "{self.connector_class.__name__}"): {self.message}'
