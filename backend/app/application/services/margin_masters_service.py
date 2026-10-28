
from app.domain.repositories.margin_repositories import MarginMastersTransaction
from app.domain.value_objects.platform_rate import NewPlatformRateSetting, PlatformRateSetting
from app.domain.value_objects.rebate import NewRebateSchedule


class MarginMastersService:
    """Creates rebate schedules and platform rates, each in one transaction."""

    def __init__(self, transaction: MarginMastersTransaction) -> None:
        self._transaction = transaction

    def create_schedule(self, new: NewRebateSchedule) -> int:
        try:
            schedule_id = self._transaction.schedules.add_schedule(new)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return schedule_id

    def set_platform_rate(self, new: NewPlatformRateSetting) -> PlatformRateSetting:
        try:
            setting = self._transaction.platform_rates.add_setting(new)
        except BaseException:
            self._transaction.rollback()
            raise
        self._transaction.commit()
        return setting
