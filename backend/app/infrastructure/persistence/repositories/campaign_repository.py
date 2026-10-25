from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.domain.entities.campaign import Campaign, CampaignPeriod, CampaignLine
from app.domain.repositories.campaign_repository import CampaignRepository as CampaignRepositoryInterface
from app.domain.exceptions import DuplicateCampaignNameError
from app.infrastructure.persistence.models.campaign import (
    CampaignRecord,
    CampaignPeriodRecord,
    CampaignLineRecord,
    CampaignLinePeriodRecord,
)


class CampaignRepositoryImpl(CampaignRepositoryInterface):
    """SQLAlchemy implementation of campaign repository."""

    def __init__(self, session: Session):
        self.session = session

    async def save(self, campaign: Campaign) -> int:
        """
        Save campaign with periods and lines in a single transaction.

        Raises: IntegrityError if constraints violated (e.g., duplicate name)
        """
        if any(not line.flights for line in campaign.lines):
            raise ValueError("every campaign line needs at least one flight")

        try:
            # Create campaign model
            campaign_model = CampaignRecord(
                name=campaign.name,
                display_name=campaign.display_name,
                agency_id=campaign.agency_id,
                advertiser_id=campaign.advertiser_id,
                campaign_type_id=campaign.campaign_type_id,
                sector_id=campaign.sector_id,
                sales_rep_id=campaign.sales_rep_id,
                purchase_order_id=campaign.purchase_order_id,
                status=campaign.status,
                start_date=campaign.start_date,
                end_date=campaign.end_date,
            )
            self.session.add(campaign_model)
            self.session.flush()  # Get the ID without committing

            campaign_id = campaign_model.id

            # Update domain campaign with assigned ID
            campaign.id = campaign_id

            # Create period models and update domain periods
            period_models_by_key = {}
            for period in campaign.periods:
                period_model = CampaignPeriodRecord(
                    campaign_id=campaign_id,
                    period_year=period.period_year,
                    period_month=period.period_month,
                    period_start=period.period_start,
                    period_end=period.period_end,
                    status=period.status,
                )
                self.session.add(period_model)
                period_models_by_key[(period.period_year, period.period_month)] = period_model

            self.session.flush()

            # Update domain periods with assigned IDs
            for period in campaign.periods:
                key = (period.period_year, period.period_month)
                period_model = period_models_by_key[key]
                period.id = period_model.id
                period.campaign_id = campaign_id

            # Create line models, each with its flights. A flight points at the period of its own month.
            line_models = []
            flight_models = []
            for line in campaign.lines:
                first_flight = line.flights[0]
                line_model = CampaignLineRecord(
                    campaign_id=campaign_id,
                    line_number=line.line_number,
                    start_date=line.start_date,
                    end_date=line.end_date,
                    # Transitional: still mandatory in the table, filled from the first flight until the cleanup drops it.
                    campaign_period_id=period_models_by_key[(first_flight.period_year, first_flight.period_month)].id,
                    purchase_order_version_id=line.purchase_order_version_id,
                    dsp_id=line.dsp_id,
                    channel_id=line.channel_id,
                    format_id=line.format_id,
                    scope=line.scope,
                    market_description=line.market_description,
                    contracted_impressions=line.volume.contracted_impressions,
                    sale_cpm=line.volume.sale_cpm,
                    currency=line.currency,
                )
                self.session.add(line_model)
                line_models.append((line, line_model))

            self.session.flush()

            for line, line_model in line_models:
                line.id = line_model.id
                line.campaign_id = campaign_id
                line.campaign_period_id = line_model.campaign_period_id  # read by the response until 6A.10
                for flight in line.flights:
                    period_model = period_models_by_key[(flight.period_year, flight.period_month)]
                    flight_model = CampaignLinePeriodRecord(
                        campaign_line_id=line_model.id,
                        campaign_period_id=period_model.id,
                        flight_start=flight.flight_start,
                        flight_end=flight.flight_end,
                        contracted_impressions=flight.contracted_impressions,
                    )
                    self.session.add(flight_model)
                    flight_models.append((flight, flight_model))

            self.session.flush()

            for flight, flight_model in flight_models:
                flight.id = flight_model.id
                flight.campaign_period_id = flight_model.campaign_period_id

            self.session.commit()
            return campaign_id

        except IntegrityError as e:
            self.session.rollback()
            # Check for duplicate campaign name
            if "campaigns_name_key" in str(e.orig):
                raise DuplicateCampaignNameError(f"Campaign with name '{campaign.name}' already exists")
            # Re-raise other integrity violations (e.g., foreign key constraints)
            raise

    async def get_by_id(self, campaign_id: int):
        """Not implemented for MVP."""
        raise NotImplementedError()

    async def get_by_name(self, name: str):
        """Not implemented for MVP."""
        raise NotImplementedError()

    async def list_all(self) -> list[Campaign]:
        """List all campaigns (simplified, without periods and lines)."""
        campaigns = self.session.query(CampaignRecord).all()
        return [
            Campaign(
                id=c.id,
                name=c.name,
                display_name=c.display_name,
                agency_id=c.agency_id,
                advertiser_id=c.advertiser_id,
                campaign_type_id=c.campaign_type_id,
                sector_id=c.sector_id,
                sales_rep_id=c.sales_rep_id,
                purchase_order_id=c.purchase_order_id,
                start_date=c.start_date,
                end_date=c.end_date,
                status=c.status,
                periods=[],
                lines=[]
            )
            for c in campaigns
        ]
