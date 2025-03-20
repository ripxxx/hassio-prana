from homeassistant.components.number import (
    DOMAIN as ENTITY_DOMAIN,
    NumberEntity,
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

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_devices):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_devices([PranaBrightness(hass, coordinator, config_entry.data["name"], config_entry.entry_id)])

class BasePranaNumber(CoordinatorEntity, NumberEntity):
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

class PranaBrightness(BasePranaNumber):
    @property
    def name(self) -> str:
        """Return the name of the control."""
        return self._name + " brightness"

    @property
    def native_max_value(self):
        return 6

    @property
    def native_min_value(self):
        return 0

    @property
    def native_step(self):
        return 1

    @property
    def mode(self):
        return "slider"

    @property
    def native_value(self):
        """Return brightness of the fan."""
        return self.coordinator.brightness

    @property
    def native_unit_of_measurement(self):
        return "%"

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.set_brightness(value)

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self.coordinator.mac.replace(":", "")+ "_brightness"
