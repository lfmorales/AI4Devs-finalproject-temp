from datetime import date

from app.domain.exceptions import LineDatesOutsideCampaignError


def validate_line_dates(line_start: date, line_end: date, campaign_start: date, campaign_end: date) -> None:
    """A line runs inside its campaign: the dates may touch the campaign's but never go beyond them."""
    if line_start > line_end:
        raise ValueError("line start must be <= line end")
    if line_start < campaign_start or line_end > campaign_end:
        raise LineDatesOutsideCampaignError("line dates fall outside the campaign dates")
