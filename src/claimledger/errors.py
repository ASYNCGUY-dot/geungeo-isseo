class DataSourceError(RuntimeError):
    """Raised when a source cannot provide a trustworthy response."""


class IdentityRequiredError(ValueError):
    """Raised when product identity has not been confirmed by the user."""


class DecisionInvariantError(ValueError):
    """Raised when a verdict would violate a safety invariant."""
