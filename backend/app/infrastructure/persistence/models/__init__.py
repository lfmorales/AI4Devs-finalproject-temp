"""Importing this package registers every ORM model on Base.metadata, which Alembic reads."""

from app.infrastructure.persistence.models.identity import RoleRecord, UserRecord, UserRoleRecord
from app.infrastructure.persistence.models.masters import (
    HoldingGroupRecord,
    AgencyRecord,
    AdvertiserRecord,
    DSPRecord,
    ChannelRecord,
    FormatRecord,
    CampaignTypeRecord,
    SectorRecord,
    SalesRepRecord,
)
from app.infrastructure.persistence.models.campaign import (
    CampaignRecord,
    CampaignPeriodRecord,
    CampaignLineRecord,
)
from app.infrastructure.persistence.models.purchase_order import (
    PurchaseOrderRecord,
    PurchaseOrderVersionRecord,
)
from app.infrastructure.persistence.models.dsp_mapping import DSPMappingRecord
from app.infrastructure.persistence.models.delivery import (
    IngestionBatchRecord,
    DailyDeliveryRecord,
    IngestionExceptionRecord,
)

__all__ = [
    "RoleRecord",
    "UserRecord",
    "UserRoleRecord",
    "HoldingGroupRecord",
    "AgencyRecord",
    "AdvertiserRecord",
    "DSPRecord",
    "ChannelRecord",
    "FormatRecord",
    "CampaignTypeRecord",
    "SectorRecord",
    "SalesRepRecord",
    "CampaignRecord",
    "CampaignPeriodRecord",
    "CampaignLineRecord",
    "PurchaseOrderRecord",
    "PurchaseOrderVersionRecord",
    "DSPMappingRecord",
    "IngestionBatchRecord",
    "DailyDeliveryRecord",
    "IngestionExceptionRecord",
]
