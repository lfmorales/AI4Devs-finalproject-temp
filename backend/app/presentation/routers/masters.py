from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.orm import Session

from app.domain.models.user import RoleName
from app.presentation.dependencies.auth import require_roles, get_current_user
from app.presentation.dependencies.providers import get_db_session
from app.infrastructure.persistence.models.masters import (
    AgencyRecord,
    AdvertiserRecord,
    DSPRecord,
    ChannelRecord,
    FormatRecord,
    CampaignTypeRecord,
    SectorRecord,
    SalesRepRecord,
)
from pydantic import BaseModel


# Response schemas
class MasterItem(BaseModel):
    id: int
    name: str


class DSPItem(BaseModel):
    id: int
    name: str
    is_active: bool


router = APIRouter(prefix="/masters", tags=["masters"])


@router.get(
    "/agencies",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_agencies(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all agencies for form picker."""
    agencies = session.query(AgencyRecord).order_by(AgencyRecord.name).all()
    return [{"id": a.id, "name": a.name} for a in agencies]


@router.get(
    "/advertisers",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_advertisers(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all advertisers for form picker."""
    advertisers = session.query(AdvertiserRecord).order_by(AdvertiserRecord.name).all()
    return [{"id": a.id, "name": a.name} for a in advertisers]


@router.get(
    "/dsps",
    response_model=list[DSPItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_active_dsps(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get only active DSPs. Inactive ones not offered at registration."""
    dsps = session.query(DSPRecord).filter_by(is_active=True).order_by(DSPRecord.name).all()
    return [{"id": d.id, "name": d.name, "is_active": d.is_active} for d in dsps]


@router.get(
    "/channels",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_channels(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all channels for form picker."""
    channels = session.query(ChannelRecord).order_by(ChannelRecord.name).all()
    return [{"id": c.id, "name": c.name} for c in channels]


@router.get(
    "/formats",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_formats(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all formats for form picker."""
    formats = session.query(FormatRecord).order_by(FormatRecord.name).all()
    return [{"id": f.id, "name": f.name} for f in formats]


@router.get(
    "/campaign-types",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_campaign_types(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all campaign types for form picker."""
    types = session.query(CampaignTypeRecord).order_by(CampaignTypeRecord.name).all()
    return [{"id": t.id, "name": t.name} for t in types]


@router.get(
    "/sectors",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_sectors(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all sectors for form picker."""
    sectors = session.query(SectorRecord).order_by(SectorRecord.name).all()
    return [{"id": s.id, "name": s.name} for s in sectors]


@router.get(
    "/sales-reps",
    response_model=list[MasterItem],
    dependencies=[Depends(require_roles(RoleName.OPERATIONS, RoleName.BUSINESS, RoleName.FINANCE))]
)
async def get_sales_reps(
    session: Annotated[Session, Depends(get_db_session)],
    current_user = Depends(get_current_user),
):
    """Get all sales reps for form picker."""
    reps = session.query(SalesRepRecord).order_by(SalesRepRecord.name).all()
    return [{"id": r.id, "name": r.name} for r in reps]
