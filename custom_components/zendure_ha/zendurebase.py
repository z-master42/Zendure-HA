"""Zendure Integration base class."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from homeassistant.components.number import NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.template import Template

from .binary_sensor import ZendureBinarySensor
from .const import DOMAIN
from .number import ZendureNumber
from .select import ZendureRestoreSelect, ZendureSelect
from .sensor import ZendureRestoreSensor, ZendureSensor
from .switch import ZendureSwitch

_LOGGER = logging.getLogger(__name__)


class ZendureBase:
    """A Base Class for all zendure classes."""

    empty = Entity()

    def __init__(self, hass: HomeAssistant, name: str, model: str, snNumber: str, parent: str | None = None, swVersion: str | None = None) -> None:
        """Initialize ZendureDevice."""
        self._hass = hass
        self.name = name
        self.unique = "".join(self.name.split())
        self.entities: dict[str, Entity | None] = {}
        self.attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.name)},
            name=self.name,
            manufacturer="Zendure",
            model=model,
            serial_number=snNumber,
        )
        if parent is not None:
            self.attr_device_info["via_device"] = (DOMAIN, parent)
        if swVersion is not None:
            self.attr_device_info["sw_version"] = swVersion

    def entitiesCreate(self) -> None:
        return

    def entitiesBattery(self, _sensors: list[ZendureSensor]) -> None:
        return

    def entityAdd(self, entity: Entity, value: Any) -> None:
        try:
            _LOGGER.info(f"Add sensor: {entity.unique_id}")
            ZendureSensor.addSensors([entity])
            entity.update_value(value)

        except Exception as err:
            _LOGGER.error(err)
            _LOGGER.error(traceback.format_exc())

    def entityChanged(self, _key: str, _entity: Entity, _value: Any) -> None:
        return

    def entityUpdated(self, _key: str, _entity: Entity, _value: Any) -> None:
        return

    def entityUpdate(self, key: Any, value: Any) -> bool:
        # check if entity is already created
        if (entity := self.entities.get(key, None)) is None:
            if key.endswith("Switch"):
                entity = self.binary(key, None, "switch")
            elif key.endswith("power"):
                entity = self.sensor(key, None, "w", "power", "measurement")
            elif key.endswith(("Temperature", "Temp")):
                entity = self.sensor(key, "{{ (value | float/10 - 273.15) | round(2) }}", "°C", "temperature", "measurement")
            elif key.endswith("PowerCycle"):
                entity = self.empty
            else:
                entity = ZendureSensor(self.attr_device_info, key)

            # set current entity to None in order to prevent error during async initialization
            self.entities[key] = entity
            if entity != self.empty:
                self._hass.loop.call_soon_threadsafe(self.entityAdd, entity, value)
            return False

        # update entity state
        if entity is not None and entity.platform:
            # update energy sensors
            if value is not None:
                self.entityUpdated(key, entity, value)

            if entity.state != value:
                entity.update_value(value)
                self.entityChanged(key, entity, value)
                return True
        return False

    def entityWrite(self, _entity: Entity, _value: Any) -> None:
        return

    def binary(
        self,
        uniqueid: str,
        template: str | None = None,
        deviceclass: Any | None = None,
    ) -> ZendureBinarySensor:
        tmpl = Template(template, self._hass) if template else None
        s = ZendureBinarySensor(self.attr_device_info, uniqueid, tmpl, deviceclass)
        self.entities[uniqueid] = s
        return s

    def number(
        self,
        uniqueid: str,
        template: str | None = None,
        uom: str | None = None,
        deviceclass: Any | None = None,
        minimum: int = 0,
        maximum: int = 2000,
        mode: NumberMode = NumberMode.AUTO,
        onwrite: Callable | None = None,
    ) -> ZendureNumber:
        def _write_property(entity: Entity, value: Any) -> None:
            self.entityWrite(entity, value)

        if onwrite is None:
            onwrite = _write_property

        tmpl = Template(template, self._hass) if template else None
        s = ZendureNumber(
            self.attr_device_info,
            uniqueid,
            onwrite,
            tmpl,
            uom,
            deviceclass,
            maximum,
            minimum,
            mode,
        )
        self.entities[uniqueid] = s
        return s

    def select(self, uniqueid: str, options: dict[int, str], onwrite: Callable | None = None, persistent: bool = False) -> ZendureSelect:
        def _write_property(entity: Entity, value: Any) -> None:
            self.entityWrite(entity, value)

        if onwrite is None:
            onwrite = _write_property

        if persistent:
            s = ZendureRestoreSelect(self.attr_device_info, uniqueid, options, onwrite)
        else:
            s = ZendureSelect(self.attr_device_info, uniqueid, options, onwrite)
        self.entities[uniqueid] = s
        return s

    def sensor(
        self,
        uniqueid: str,
        template: str | None = None,
        uom: str | None = None,
        deviceclass: Any | None = None,
        stateclass: Any | None = None,
        precision: int | None = None,
        persistent: bool = False,
    ) -> ZendureSensor:
        tmpl = Template(template, self._hass) if template else None
        if persistent:
            s = ZendureRestoreSensor(self.attr_device_info, uniqueid, tmpl, uom, deviceclass, stateclass, precision)
        else:
            s = ZendureSensor(self.attr_device_info, uniqueid, tmpl, uom, deviceclass, stateclass, precision)
        self.entities[uniqueid] = s
        return s

    def switch(
        self,
        uniqueid: str,
        template: str | None = None,
        deviceclass: Any | None = None,
    ) -> ZendureSwitch:
        def _write_property(entity: Entity, value: Any) -> None:
            self.entityWrite(entity, value)

        tmpl = Template(template, self._hass) if template else None
        s = ZendureSwitch(self.attr_device_info, uniqueid, _write_property, tmpl, deviceclass)
        self.entities[uniqueid] = s
        return s

    def asInt(self, name: str) -> int:
        if (sensor := self.entities.get(name, None)) and sensor.state is not None:
            try:
                return int(sensor.state)
            except ValueError:
                return 0

        return 0

    def asFloat(self, name: str) -> float:
        if (sensor := self.entities.get(name, None)) and sensor.state is not None:
            try:
                return float(sensor.state)
            except ValueError:
                return 0

        if (sensor := self.entities.get(name, None)) and isinstance(sensor.state, (int, float)):
            return sensor.state
        return 0

    def isEqual(self, name: str, value: Any) -> bool:
        if (sensor := self.entities.get(name, None)) and sensor.state:
            return sensor.state == value
        return False
