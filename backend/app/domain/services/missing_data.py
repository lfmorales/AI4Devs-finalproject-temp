from datetime import date, timedelta


def has_missing_data(latest_delivery_date: date | None, today: date) -> bool:
    """True when the latest delivery predates D-1, with D the day the check runs (after the nightly ingestion).

    Computed from the stored latest date on every read, so the flag clears by itself once an
    ingestion brings delivery for D-1. Which campaigns are active is the caller's decision.
    """
    if latest_delivery_date is None:
        return True
    return latest_delivery_date < today - timedelta(days=1)
