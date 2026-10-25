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


class UnsupportedCurrencyError(DomainError):
    """A DSP reported delivery in a currency other than EUR. Nothing is converted; the run fails."""


class DspUnreachableError(DomainError):
    """The DSP could not be reached: a timeout or a connection failure."""


class DspAuthenticationError(DomainError):
    """The DSP refused the credentials or the token."""


class DspReportFailedError(DomainError):
    """The DSP rejected the report request or the report ended in a state other than succeeded."""

    def __init__(self, message: str, status: str | None = None) -> None:
        super().__init__(message)
        self.status = status  # The operation status the DSP reported, when the failure is about one.


class DspReportTimeoutError(DomainError):
    """The DSP report was still running after the configured number of polling attempts."""


class DspResponseFormatError(DomainError):
    """The DSP answered in a shape the client does not recognise."""


class DuplicateDspMappingError(DomainError):
    """The external identifier pair is already mapped to a campaign line of this DSP."""


class CampaignLineNotFoundError(DomainError):
    """No campaign line has this id."""


class DspNotSupportedError(DomainError):
    """The campaign line's DSP has no connector yet."""


class DspNotConfiguredError(DomainError):
    """The DSP has a connector but its credentials are not configured."""


class IngestionExceptionNotFoundError(DomainError):
    """No ingestion exception has this id."""


class IngestionExceptionAlreadyResolvedError(DomainError):
    """The ingestion exception was already resolved."""


class LineDatesOutsideCampaignError(DomainError):
    """A campaign line starts before its campaign or ends after it."""


class FlightVolumesIncompleteError(DomainError):
    """The monthly volumes miss a month the line runs in, name one it does not, or repeat a month."""


class FlightVolumesMismatchError(DomainError):
    """The monthly volumes do not add up to the line's total."""


class FlightVolumeNotPositiveError(DomainError):
    """A monthly volume is zero or negative."""


class LineDatesInvalidError(DomainError):
    """A campaign line starts after it ends."""


class VolumeTooSmallForFlightsError(DomainError):
    """Splitting a line's volume by days would leave a flight with no impressions."""


class LineNotFoundError(DomainError):
    """No campaign line has this id (the answer of the link operation)."""


class ExceptionNotLinkableError(DomainError):
    """Only an unmatched-delivery exception can be linked to a campaign line."""


class MappingPairTakenError(DomainError):
    """The exception's identifier pair is already mapped to a campaign line of its DSP."""


class LineDspMismatchError(DomainError):
    """The campaign line runs on a different DSP than the identifier pair."""


class MappingNotFoundError(DomainError):
    """The campaign line has no DSP mapping."""


class AmbiguousMappingError(DomainError):
    """The campaign line has several DSP mappings, so it is not clear which delivery came from which."""
