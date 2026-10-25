"""In-memory doubles for the registration service: they record what is written so a test can assert nothing was."""

from types import SimpleNamespace

from app.domain.entities.campaign import Campaign
from app.domain.repositories.campaign_repository import CampaignRepository
from app.domain.repositories.master_repository import MasterRepository
from app.domain.repositories.purchase_order_repository import PurchaseOrderRepository


class InMemoryMasterRepository(MasterRepository):
    """Every reference exists except the ids listed as unknown."""

    def __init__(self, unknown_channel_ids: frozenset[int] = frozenset()) -> None:
        self._unknown_channel_ids = unknown_channel_ids

    async def _known(self, identifier: int):
        return SimpleNamespace(id=identifier, name="fixture", is_active=True)

    async def get_agency(self, agency_id): return await self._known(agency_id)
    async def get_advertiser(self, advertiser_id): return await self._known(advertiser_id)
    async def get_dsp(self, dsp_id): return await self._known(dsp_id)
    async def get_format(self, format_id): return await self._known(format_id)
    async def get_campaign_type(self, campaign_type_id): return await self._known(campaign_type_id)
    async def get_sector(self, sector_id): return await self._known(sector_id)
    async def get_sales_rep(self, sales_rep_id): return await self._known(sales_rep_id)

    async def get_channel(self, channel_id):
        return None if channel_id in self._unknown_channel_ids else await self._known(channel_id)


class InMemoryPurchaseOrderRepository(PurchaseOrderRepository):
    def __init__(self) -> None:
        self.orders: list[str] = []
        self.versions: list[int] = []

    async def create_order(self, order_reference: str, received_on: str) -> int:
        self.orders.append(order_reference)
        return len(self.orders)

    async def create_version(self, purchase_order_id, version_number, issued_on, revision_reason=None):
        self.versions.append(version_number)
        return SimpleNamespace(id=len(self.versions), purchase_order_id=purchase_order_id)

    async def get_version_in_force(self, purchase_order_id):
        return None


class InMemoryCampaignRepository(CampaignRepository):
    def __init__(self) -> None:
        self.saved: list[Campaign] = []

    async def save(self, campaign: Campaign) -> int:
        self.saved.append(campaign)
        return len(self.saved)

    async def get_by_id(self, campaign_id): raise NotImplementedError
    async def get_by_name(self, name): raise NotImplementedError
    async def list_all(self): raise NotImplementedError
