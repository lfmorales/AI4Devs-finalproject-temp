from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.entities.dsp_mapping import DspMapping
from app.domain.exceptions import (
    CampaignLineNotFoundError,
    DspNotSupportedError,
    DspReportTimeoutError,
    DspUnreachableError,
    DuplicateDspMappingError,
)
from app.domain.repositories.dsp_catalog_query_repository import DspCatalogQueryRepository
from app.domain.repositories.dsp_mapping_repository import DspMappingRepository
from app.domain.services.dsp_delivery_client import DspDeliveryClient
from app.domain.value_objects.delivery import ExternalLineKey


class IdentifierCheck(StrEnum):
    FOUND = "found"
    UNKNOWN = "unknown"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class MappingCreationResult:
    mapping: DspMapping
    check: IdentifierCheck
    # The latest date the pair delivered impressions according to the catalogue; None if unknown or never.
    last_impressions_date: date | None = None


class DspMappingService:
    """Creates the mapping of a campaign line to a DSP identifier pair, checking the pair with the DSP.

    The mapping is created whether the pair is found, unknown or the DSP is unreachable; only a found pair
    gets validated_at. Through the Adform stats API, "unknown" also covers a line item that exists but has not
    delivered in the lookback period: the API reports delivery, not configuration, so the two look alike.
    """

    def __init__(
        self,
        repository: DspMappingRepository,
        client_for_dsp: Callable[[str], DspDeliveryClient | None],
        clock: Callable[[], datetime],
        catalog: DspCatalogQueryRepository | None = None,
    ) -> None:
        self._repository = repository
        self._client_for_dsp = client_for_dsp
        self._clock = clock
        self._catalog = catalog

    def create_mapping(
        self, campaign_line_id: int, external_campaign_id: str, external_line_item_id: str
    ) -> MappingCreationResult:
        line_dsp = self._repository.get_line_dsp(campaign_line_id)
        if line_dsp is None:
            raise CampaignLineNotFoundError(f"campaign line {campaign_line_id} does not exist")
        client = self._client_for_dsp(line_dsp.dsp_name)
        if client is None:
            raise DspNotSupportedError(f"no connector for {line_dsp.dsp_name}")

        key = ExternalLineKey.from_raw(external_campaign_id, external_line_item_id)
        # Checked before asking the DSP: every question spends part of an agency-wide request quota.
        if self._repository.pair_exists(line_dsp.dsp_id, key):
            raise DuplicateDspMappingError("pair already mapped")

        check = self._check_with_dsp(client, key)
        validated_at = self._clock() if check is IdentifierCheck.FOUND else None
        mapping = self._repository.add(campaign_line_id, line_dsp.dsp_id, key, validated_at)
        last_impressions_date = None if self._catalog is None else self._catalog.find_last_impressions_date(
            line_dsp.dsp_id, key)
        return MappingCreationResult(mapping, check, last_impressions_date)

    @staticmethod
    def _check_with_dsp(client: DspDeliveryClient, key: ExternalLineKey) -> IdentifierCheck:
        try:
            resolved = client.resolve_identifiers(key.external_campaign_id, key.external_line_item_id)
        except (DspUnreachableError, DspReportTimeoutError):
            # Any other DSP failure, such as refused credentials, propagates: it is not "unreachable".
            return IdentifierCheck.UNREACHABLE
        return IdentifierCheck.UNKNOWN if resolved is None else IdentifierCheck.FOUND
