"""实体基类"""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LongyanWaterCoordinator


class LongyanWaterEntity(CoordinatorEntity[LongyanWaterCoordinator]):
    """实体基类"""

    def __init__(self, coordinator: LongyanWaterCoordinator, meter: dict, key: str = "") -> None:
        super().__init__(coordinator)
        self._meter_bsh = meter.get("bsh", "")
        self._key = key
        self._meter = meter

    def _current_meter(self) -> dict:
        for m in self.coordinator.data.get("meters", []):
            if m.get("bsh") == self._meter_bsh:
                return m
        return self._meter

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._meter_bsh)},
            "name": f"自来水 {self._meter_bsh}",
            "manufacturer": "龙岩水发自来水",
            "model": "水表户号",
        }

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data.get("meters"))
