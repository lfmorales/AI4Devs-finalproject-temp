from sqlalchemy import ColumnElement, Numeric, case, cast

from app.infrastructure.persistence.models.delivery import DailyDeliveryRecord
from app.infrastructure.persistence.models.masters import ChannelRecord


def delivered_in_channel_metric(metric: ColumnElement[str] | None = None) -> ColumnElement[object]:
    """What one delivery row counts as delivered: its OTS on a channel counted in OTS, its impressions otherwise.

    The channel is the one of the enclosing query, so it belongs inside a subquery that sums the delivery of a line
    whose channel the outer query joins. The amount is a four-decimal number whichever the unit. `metric` replaces the
    channel's metric now, for a closed flight read in the metric it was closed in.
    """
    unit = ChannelRecord.delivery_metric if metric is None else metric
    return case(
        (unit == "ots", DailyDeliveryRecord.ots),
        else_=cast(DailyDeliveryRecord.impressions, Numeric(18, 4)),
    )
