from homeassistant.components.select import (
    DOMAIN as ENTITY_DOMAIN,
    SelectEntity,
)

from homeassistant.components.sensor import (
    DOMAIN as ENTITY_DOMAIN,
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)

"""Support for Prana fan."""
from . import DOMAIN

from datetime import datetime, timedelta
import logging
import math

from homeassistant.components.fan import PLATFORM_SCHEMA, FanEntity, FanEntityFeature
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_MODE,
    CONF_HOST,
    CONF_NAME,
    CONF_TOKEN,
)

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from homeassistant.helpers import device_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import STATE_OFF
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import dispatcher_send, async_dispatcher_connect
from homeassistant.util.percentage import (
    int_states_in_range,
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import PranaState, Speed, PranaSensorsState, Display, PranaTimer

LOGGER = logging.getLogger(__name__)

DISPLAYS = {
    'FAN' : Display.FAN,
    'TEMPERATURE IN' : Display.TEMPERATURE_IN,
    'TEMPERATURE OUT' : Display.TEMPERATURE_OUT,
    'CO2' : Display.CO2,
    'VOC' : Display.VOC,
    'HUMIDITY' : Display.HUMIDITY,
    'QUALITY_FAN' : Display.QUALITY_FAN,
    'PRESURE' : Display.PRESURE,
    'FAN_2' : Display.FAN_2,
    'DATE' : Display.DATE,
    'TIME' : Display.TIME,
}

PRANA_TIMERS = {
    'STOP' : PranaTimer.STOP,
    'RUN' : PranaTimer.RUN,
    '10M' : PranaTimer.RUN_10M,
    '20M' : PranaTimer.RUN_20M,
    '30M' : PranaTimer.RUN_30M,
    '1H' : PranaTimer.RUN_1H,
    '1H30M' : PranaTimer.RUN_1H30M,
    '2H' : PranaTimer.RUN_2H,
    '3H' : PranaTimer.RUN_3H,
    '5H' : PranaTimer.RUN_5H,
    '9H' : PranaTimer.RUN_9H,
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    controls_to_add = []

    controls_to_add.append(PranaDisplaySelect(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaTimerSelect(hass, coordinator, config_entry.data["name"], config_entry.entry_id))

    async_add_entities(controls_to_add)

class BasePranaSelect(CoordinatorEntity, SelectEntity):
    # Implement one of these methods.
    """Representation of a Prana fan."""
    def __init__(self, hass, coordinator, name: str, entry_id: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        _attr_has_entity_name = True
        self._hass = hass
        self.coordinator = coordinator
        self._name = name
        self._entry_id = entry_id
        self._hass.bus.async_listen("prana_update", self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self):
        """Return state of the fan."""
        return self.coordinator.lastRead != None and (self.coordinator.lastRead > datetime.now() - timedelta(minutes=5))

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.coordinator.mac)
            },
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC, self.coordinator.mac)},
        )

class PranaDisplaySelect(BasePranaSelect):
    def __init__(self, hass, coordinator, name: str, entry_id: str):
        self.current_option = self.get_option_name(coordinator.display)
        self.options = list(DISPLAYS.keys())
        super().__init__(hass, coordinator, name, entry_id)

    @property
    def name(self) -> str:
        """Return the name of the control."""
        return "Display"

    async def async_update(self) -> None:
        self.current_option = self.get_option_name(self.coordinator.display)
        await self.coordinator.async_request_refresh()

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.set_display(DISPLAYS[option])

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_display"

    @property
    def state(self):
        return self.get_option_name(self.coordinator.display)

    def get_option_name(self, display: Display) -> str:
        if display == None:
            return None
        displays_r = dict(zip(DISPLAYS.values(), DISPLAYS.keys()))
        return displays_r[display]

class PranaTimerSelect(BasePranaSelect):
    def __init__(self, hass, coordinator, name: str, entry_id: str):
        self.current_option = self.get_option_name(coordinator.timer_on)
        self.options = list(PRANA_TIMERS.keys())
        super().__init__(hass, coordinator, name, entry_id)

    @property
    def name(self) -> str:
        """Return the name of the control."""
        return "Timer"

    async def async_update(self) -> None:
        self.current_option = self.get_option_name(self.coordinator.timer_on)
        await self.coordinator.async_request_refresh()

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.set_timer(PRANA_TIMERS[option])

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_timer"

    @property
    def state(self):
        return self.get_option_name(self.coordinator.timer_on)

    def get_option_name(self, timer_on: bool) -> str:
        prana_timers_r = dict(zip(PRANA_TIMERS.values(), PRANA_TIMERS.keys()))
        if timer_on:
            return prana_timers_r[PranaTimer.RUN]
        return prana_timers_r[PranaTimer.STOP]
