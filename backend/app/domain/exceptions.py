from app.domain.value_objects.review import ReviewState



class DomainError(Exception):
    """Base class for domain rule violations."""


class InvalidIdentityTokenError(DomainError):
    """The presented token is missing, malformed, expired or not issued for this application."""


class IdentityProviderUnavailableError(DomainError):
    """The identity provider's signing keys could not be retrieved."""


class UnregisteredUserError(DomainError):
    """The identity is valid but has no local user. Users are never auto-provisioned."""


class IdentityConflictError(DomainError):
    """The (issuer, subject) pair already belongs to another user, so it cannot be linked again."""


class UserNotFoundError(DomainError):
    """No user has the email an operation was asked to act on."""


class CannotDeactivateSelfError(DomainError):
    """A user tried to deactivate their own account."""


class LastActiveOperationsUserError(DomainError):
    """Deactivating this user would leave the system without an active operations user."""


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


class InvalidEquativPackageError(DomainError):
    """The pair written for a line on Equativ is not one auction package id in both ids.

    A package id is a whole number above zero, in ASCII digits, with no leading zero.
    """


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


class MixedDeliveryMetricsError(DomainError):
    """The lines of a campaign are counted in different delivery metrics (for example OTS and impressions)."""


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


class RebateRuleError(DomainError):
    """A rebate rule was broken: an invalid bracket table, or ambiguous schedules. Carries a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SystemPlatformRateMissingError(DomainError):
    """No system platform rate is stored, so a flight with no more specific rate cannot be priced."""


class PreviousMonthOpenError(DomainError):
    """A month cannot be closed while an earlier month of the same year has ended flights without frozen rates."""

    def __init__(self, year: int, month: int) -> None:
        super().__init__(f"{year}-{month:02d} is still open")
        self.year = year
        self.month = month


class MonthDeliveryNotLoadedError(DomainError):
    """A month cannot be closed, nor a campaign of it reviewed, until the DSP of each of its flights concerned has loaded
    the month's last day.

    A target flight earns what its DSP reports and a committed flight bills its delivery, so a month closed or a
    campaign reviewed before its last day was ingested would rest on a revenue short of that day. `next_step` is what
    the user does once the day is loaded: close the month, or review the campaign.
    """

    def __init__(self, year: int, month: int, dsp_name: str, next_step: str = "close the month") -> None:
        super().__init__(f"{year}-{month:02d} is not loaded up to its last day from {dsp_name}")
        self.year = year
        self.month = month
        self.dsp_name = dsp_name
        self.next_step = next_step


class CampaignNotFoundError(DomainError):
    """The campaign named by a request does not exist."""


class MonthNotReviewedError(DomainError):
    """A month cannot be closed while a campaign with flights in it is in progress or pending review.

    `campaigns` names each such campaign with its state, by campaign name: a campaign in progress has a flight of the
    month that has not ended, so a month is never closed before its last flight has ended.
    """

    def __init__(self, year: int, month: int, campaigns: tuple[tuple[str, ReviewState], ...]) -> None:
        listed = ", ".join(f"{name} ({state.value.replace('_', ' ')})" for name, state in campaigns)
        super().__init__(f"{year}-{month:02d} has campaigns not reviewed: {listed}")
        self.year = year
        self.month = month
        self.campaigns = campaigns


class CarryoverError(DomainError):
    """A carry-over broke a rule of campaign/carryover. Carries a stable code: `invalid_carryover`,
    `no_previous_flight`, `previous_flight_not_ended`, `carryover_exceeds_shortfall`, `month_closed` or, for the
    billable flag, `no_carryover`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FlightNotFoundError(DomainError):
    """The flight a request names does not exist."""


class TargetLineNotAdjustableError(DomainError):
    """The flight belongs to a target line, which bills what its DSP reports: no adjustment, no billable carry-over."""


class BillingAdjustmentError(DomainError):
    """A billing adjustment broke a rule of finance/billing-adjustment. Carries a stable code: `invalid_adjustment`,
    `flight_not_ended` or `flight_closed`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MonthlyReviewError(DomainError):
    """A review or a withdrawal broke a rule of finance/monthly-review. Carries a stable code:
    `campaign_month_not_found`, `campaign_month_in_progress`, `campaign_month_closed` or `not_reviewed`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
