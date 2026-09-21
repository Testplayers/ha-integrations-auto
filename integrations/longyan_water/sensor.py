"""传感器平台"""
from __future__ import annotations

import logging
from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume

from .const import DOMAIN
from .entity import LongyanWaterEntity

CURRENCY_YUAN = "CNY"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    meters = coordinator.data.get("meters", [])
    entities = []
    for meter in meters:
        entities.extend([
            LongyanWaterBalanceSensor(coordinator, meter),
            LongyanWaterArrearageSensor(coordinator, meter),
            LongyanWaterUsageSensor(coordinator, meter),
            LongyanWaterReadSensor(coordinator, meter, "currentRead", "本期读数"),
            LongyanWaterReadSensor(coordinator, meter, "lastRead", "上期读数"),
            LongyanWaterPriceSensor(coordinator, meter),
            LongyanWaterBillSensor(coordinator, meter),
            LongyanWaterReadDateSensor(coordinator, meter),
        ])
    async_add_entities(entities)


def _f(meter: dict, key: str, default=0.0) -> float:
    try:
        return float(meter.get(key) or default)
    except (TypeError, ValueError):
        return default


class LongyanWaterBalanceSensor(LongyanWaterEntity, SensorEntity):
    _attr_name = "账户余额"

    @property
    def native_value(self):
        return round(_f(self._current_meter(), "balance"), 2)

    @property
    def native_unit_of_measurement(self):
        return CURRENCY_YUAN

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_balance"

    @property
    def icon(self):
        return "mdi:wallet"


class LongyanWaterArrearageSensor(LongyanWaterEntity, SensorEntity):
    _attr_name = "欠费金额"

    @property
    def native_value(self):
        return round(_f(self._current_meter(), "arrearage"), 2)

    @property
    def native_unit_of_measurement(self):
        return CURRENCY_YUAN

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_arrearage"

    @property
    def icon(self):
        return "mdi:cash-minus"


class LongyanWaterUsageSensor(LongyanWaterEntity, SensorEntity):
    """本期（最近账单月）用水量，可接入能源面板"""
    _attr_name = "本期用水量"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _bill(self) -> dict:
        lst = self._current_meter().get("payMentList") or []
        return lst[0] if lst else {}

    @property
    def native_value(self):
        v = self._bill().get("consumedVolume")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_usage"

    @property
    def icon(self):
        return "mdi:water"

    @property
    def extra_state_attributes(self):
        bill = self._bill()
        return {
            "账单月份": bill.get("costDate"),
            "上期读数": bill.get("lastRead"),
            "本期读数": bill.get("currentRead"),
            "应缴金额": bill.get("payablePrincipal"),
            "已缴金额": bill.get("paidAmount"),
            "缴费状态": bill.get("payStatus"),
        }


class LongyanWaterReadSensor(LongyanWaterEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, meter, key, name):
        super().__init__(coordinator, meter, key)
        self._attr_name = name
        self._key = key

    @property
    def native_value(self):
        m = self._current_meter()
        v = m.get(self._key)
        if v is None:
            bill = (m.get("payMentList") or [{}])[0]
            v = bill.get(self._key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def native_unit_of_measurement(self):
        return UnitOfVolume.CUBIC_METERS

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_{self._key}"

    @property
    def icon(self):
        return "mdi:counter"


class LongyanWaterPriceSensor(LongyanWaterEntity, SensorEntity):
    _attr_name = "水价单价"

    @property
    def native_value(self):
        return round(_f(self._current_meter(), "unitprice"), 2)

    @property
    def native_unit_of_measurement(self):
        return f"{CURRENCY_YUAN}/{UnitOfVolume.CUBIC_METERS}"

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_price"

    @property
    def icon(self):
        return "mdi:tag"


class LongyanWaterBillSensor(LongyanWaterEntity, SensorEntity):
    _attr_name = "本期应缴"

    @property
    def native_value(self):
        m = self._current_meter()
        bill = (m.get("payMentList") or [{}])[0]
        try:
            return float(bill.get("payablePrincipal") or m.get("billAmount") or 0)
        except (TypeError, ValueError):
            return 0.0

    @property
    def native_unit_of_measurement(self):
        return CURRENCY_YUAN

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_bill"

    @property
    def icon(self):
        return "mdi:receipt-text"


class LongyanWaterReadDateSensor(LongyanWaterEntity, SensorEntity):
    _attr_name = "上次抄表日期"
    _attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self):
        v = self._current_meter().get("lastreaddate")
        try:
            return date.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None

    @property
    def unique_id(self):
        return f"{self._meter_bsh}_lastreaddate"

    @property
    def icon(self):
        return "mdi:calendar"
