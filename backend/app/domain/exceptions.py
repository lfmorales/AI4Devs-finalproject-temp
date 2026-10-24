class DomainError(Exception):
    """Base class for domain rule violations."""


class InvalidIdentityTokenError(DomainError):
    """The presented token is missing, malformed, expired or not issued for this application."""


class IdentityProviderUnavailableError(DomainError):
    """The identity provider's signing keys could not be retrieved."""


class UnregisteredUserError(DomainError):
    """The identity is valid but has no local user. Users are never auto-provisioned."""


class InactiveUserError(DomainError):
    """The local user exists but has been deactivated."""


class MissingRoleError(DomainError):
    """The user holds none of the roles an operation accepts."""


class DuplicateOrderReferenceError(DomainError):
    """A purchase order with this reference already exists."""


class DuplicateCampaignNameError(DomainError):
    """A campaign with this name already exists."""


class DeliveryOutsideRangeError(DomainError):
    """A delivery row is dated outside the range the run is replacing."""


class DeliveryForUnknownLineError(DomainError):
    """A delivery row belongs to a campaign line the run is not replacing."""
