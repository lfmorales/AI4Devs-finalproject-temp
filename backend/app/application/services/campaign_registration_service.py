from datetime import date
from decimal import Decimal
from typing import Optional

from app.domain.entities.campaign import Campaign, CampaignLine, CampaignLineFlight, CampaignPeriod
from app.domain.exceptions import VolumeTooSmallForFlightsError
from app.domain.services.explicit_volumes import validate_explicit_volumes
from app.domain.services.flight_generation import generate_flights
from app.domain.services.line_dates import validate_line_dates
from app.domain.services.volume_distribution import distribute_volume_by_days
from app.domain.value_objects.flight import MonthlyVolume
from app.domain.value_objects.contracted_volume import ContractedVolume
from app.domain.services.period_expansion import PeriodExpansionService
from app.domain.repositories.campaign_repository import CampaignRepository
from app.domain.repositories.purchase_order_repository import PurchaseOrderRepository
from app.domain.repositories.master_repository import MasterRepository


class CampaignRegistrationService:
    """
    Application service for campaign registration.

    Orchestrates:
    - Campaign creation and period expansion
    - Campaign line creation with volumes
    - Purchase order versioning (version 1)
    - Master data validation
    """

    def __init__(
        self,
        campaign_repo: CampaignRepository,
        purchase_order_repo: PurchaseOrderRepository,
        master_repo: MasterRepository
    ):
        self.campaign_repo = campaign_repo
        self.purchase_order_repo = purchase_order_repo
        self.master_repo = master_repo
        self.period_service = PeriodExpansionService()

    async def register_campaign(
        self,
        name: str,
        display_name: str,
        agency_id: int,
        advertiser_id: int,
        campaign_type_id: int,
        sector_id: int,
        sales_rep_id: int,
        start_date: date,
        end_date: date,
        order_reference: str,
        order_received_on: date,
        lines_data: list[dict],
    ) -> Campaign:
        """
        Register a new campaign.

        Validates all master references, expands periods, creates purchase order v1,
        and saves everything in a single transaction.

        Raises ValueError if any master reference is unknown.
        """

        # Validate all master references exist
        agency = await self.master_repo.get_agency(agency_id)
        if not agency:
            raise ValueError(f"Unknown agency_id: {agency_id}")

        advertiser = await self.master_repo.get_advertiser(advertiser_id)
        if not advertiser:
            raise ValueError(f"Unknown advertiser_id: {advertiser_id}")

        campaign_type = await self.master_repo.get_campaign_type(campaign_type_id)
        if not campaign_type:
            raise ValueError(f"Unknown campaign_type_id: {campaign_type_id}")

        sector = await self.master_repo.get_sector(sector_id)
        if not sector:
            raise ValueError(f"Unknown sector_id: {sector_id}")

        sales_rep = await self.master_repo.get_sales_rep(sales_rep_id)
        if not sales_rep:
            raise ValueError(f"Unknown sales_rep_id: {sales_rep_id}")

        campaign = Campaign(
            id=None,
            name=name,
            display_name=display_name,
            agency_id=agency_id,
            advertiser_id=advertiser_id,
            campaign_type_id=campaign_type_id,
            sector_id=sector_id,
            sales_rep_id=sales_rep_id,
            purchase_order_id=None,
            start_date=start_date,
            end_date=end_date,
            status="active",
            periods=[],
            lines=[]
        )
        campaign.validate()

        campaign.periods = [
            CampaignPeriod(
                period_year=p.period_year,
                period_month=p.period_month,
                period_start=p.period_start,
                period_end=p.period_end,
                status="open"
            )
            for p in self.period_service.expand(start_date, end_date)
        ]

        # Every line is checked, dates and volumes included, before the first write, so a rejected
        # registration leaves nothing behind, not even the purchase order.
        for line_number, line_data in enumerate(lines_data, start=1):
            await self._validate_line_references(line_data)
            campaign.lines.append(self._build_line(line_number, line_data, campaign))

        purchase_order_id = await self.purchase_order_repo.create_order(
            order_reference, order_received_on.isoformat()
        )
        version_1 = await self.purchase_order_repo.create_version(
            purchase_order_id=purchase_order_id,
            version_number=1,
            issued_on=order_received_on.isoformat(),
            revision_reason=None
        )
        campaign.purchase_order_id = purchase_order_id
        for line in campaign.lines:
            line.purchase_order_version_id = version_1.id or 0

        # Saved with all periods, lines and flights in one atomic transaction; the repository
        # assigns their identifiers.
        await self.campaign_repo.save(campaign)

        return campaign

    async def _validate_line_references(self, line_data: dict) -> None:
        dsp_id = line_data["dsp_id"]
        dsp = await self.master_repo.get_dsp(dsp_id)
        if not dsp or not dsp.is_active:
            raise ValueError(f"DSP {dsp_id} not found or inactive")

        if not await self.master_repo.get_channel(line_data["channel_id"]):
            raise ValueError(f"Unknown channel_id: {line_data['channel_id']}")

        if not await self.master_repo.get_format(line_data["format_id"]):
            raise ValueError(f"Unknown format_id: {line_data['format_id']}")

    @staticmethod
    def _build_line(line_number: int, line_data: dict, campaign: Campaign) -> CampaignLine:
        """One campaign line with its dates and the flights its volume is split into."""
        line_start = line_data.get("start_date") or campaign.start_date
        line_end = line_data.get("end_date") or campaign.end_date
        validate_line_dates(line_start, line_end, campaign.start_date, campaign.end_date)

        total = line_data["contracted_impressions"]
        windows = generate_flights(line_start, line_end, campaign.periods)
        monthly_volumes = line_data.get("monthly_volumes")
        if monthly_volumes is None:
            volumes = distribute_volume_by_days(total, windows)
            if min(volumes) == 0:
                raise VolumeTooSmallForFlightsError("a flight would carry no impressions")
        else:
            volumes = validate_explicit_volumes(
                total,
                windows,
                [MonthlyVolume(v["year"], v["month"], v["volume"]) for v in monthly_volumes],
            )

        return CampaignLine(
            id=None,
            purchase_order_version_id=None,
            dsp_id=line_data["dsp_id"],
            channel_id=line_data["channel_id"],
            format_id=line_data["format_id"],
            scope=line_data["scope"],
            market_description=line_data["market_description"],
            volume=ContractedVolume(
                contracted_impressions=total,
                sale_cpm=Decimal(str(line_data["sale_cpm"])),
            ),
            currency="EUR",
            campaign_id=None,
            line_number=line_number,
            start_date=line_start,
            end_date=line_end,
            flights=[
                CampaignLineFlight(
                    period_year=window.period_year,
                    period_month=window.period_month,
                    flight_start=window.flight_start,
                    flight_end=window.flight_end,
                    contracted_impressions=volume,
                )
                for window, volume in zip(windows, volumes)
            ],
        )
