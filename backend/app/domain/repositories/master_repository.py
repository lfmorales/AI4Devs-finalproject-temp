from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass


@dataclass
class Agency:
    """Master data: agency."""
    id: int
    name: str
    holding_group_id: int


@dataclass
class Advertiser:
    """Master data: advertiser."""
    id: int
    name: str


@dataclass
class DSP:
    """Master data: DSP (Adform, Equativ, Displayce)."""
    id: int
    name: str
    is_active: bool


@dataclass
class Channel:
    """Master data: channel (tipo_plataforma)."""
    id: int
    name: str
    # "impressions" or "ots": the unit in which the volume of the channel's lines is counted.
    delivery_metric: str


@dataclass
class Format:
    """Master data: format (tipo_formato)."""
    id: int
    name: str


@dataclass
class CampaignType:
    """Master data: campaign type."""
    id: int
    name: str


@dataclass
class Sector:
    """Master data: sector."""
    id: int
    name: str


@dataclass
class SalesRep:
    """Master data: sales representative."""
    id: int
    name: str


class MasterRepository(ABC):
    """Repository interface for master data validation."""

    @abstractmethod
    async def get_agency(self, agency_id: int) -> Optional[Agency]:
        """Validate agency exists and get holding_group_id."""
        pass

    @abstractmethod
    async def get_advertiser(self, advertiser_id: int) -> Optional[Advertiser]:
        """Validate advertiser exists."""
        pass

    @abstractmethod
    async def get_dsp(self, dsp_id: int) -> Optional[DSP]:
        """Validate DSP exists and is active."""
        pass

    @abstractmethod
    async def get_channel(self, channel_id: int) -> Optional[Channel]:
        """Validate channel exists."""
        pass

    @abstractmethod
    async def get_format(self, format_id: int) -> Optional[Format]:
        """Validate format exists."""
        pass

    @abstractmethod
    async def get_campaign_type(self, campaign_type_id: int) -> Optional[CampaignType]:
        """Validate campaign type exists."""
        pass

    @abstractmethod
    async def get_sector(self, sector_id: int) -> Optional[Sector]:
        """Validate sector exists."""
        pass

    @abstractmethod
    async def get_sales_rep(self, sales_rep_id: int) -> Optional[SalesRep]:
        """Validate sales rep exists."""
        pass
