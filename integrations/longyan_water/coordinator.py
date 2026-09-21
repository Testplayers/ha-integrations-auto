"""数据更新协调器"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthError, LongyanWaterClient, LongyanWaterError
from .const import DOMAIN, UPDATE_INTERVAL_HOURS

_LOGGER = logging.getLogger(__name__)


class LongyanWaterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client: LongyanWaterClient, entry) -> None:
        self.client = client
        self.entry = entry
        self.token: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=UPDATE_INTERVAL_HOURS),
        )

    async def _ensure_token(self) -> str:
        if self.token:
            return self.token
        self.token = await self.client.login_auto(
            self.entry.data["username"], self.entry.data["password"]
        )
        return self.token

    async def _async_update_data(self) -> dict:
        try:
            token = await self._ensure_token()
            try:
                meters = await self.client.meter_list(token)
            except AuthError:
                _LOGGER.info("token 失效，重新登录")
                self.token = None
                token = await self._ensure_token()
                meters = await self.client.meter_list(token)
        except AuthError as e:
            raise UpdateFailed(str(e)) from e
        except LongyanWaterError as e:
            raise UpdateFailed(str(e)) from e
        return {"meters": meters}
