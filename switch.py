from homeassistant.components.switch import (
    DOMAIN as ENTITY_DOMAIN,
    SwitchEntity,
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

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    controls_to_add = []

    controls_to_add.append(PranaHeating(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaWinterMode(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaAutoMode(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaFlowLock(hass, coordinator, config_entry.data["name"], config_entry.entry_id))

    controls_to_add.append(PranaNightMode(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaAutoPlusMode(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    controls_to_add.append(PranaBoostMode(hass, coordinator, config_entry.data["name"], config_entry.entry_id))

    async_add_entities(controls_to_add)

class BasePranaSwitch(CoordinatorEntity, SwitchEntity):
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

class PranaHeating(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_heating"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Heating"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.mini_heating_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.set_heating(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.set_heating(False)

class PranaWinterMode(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_winter_mode"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Winter Mode"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.winter_mode_enabled

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.set_winter_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.set_winter_mode(False)

class PranaAutoMode(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_auto_mode"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Auto Mode"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.auto_mode

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.toggle_auto_mode()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.toggle_auto_mode()

class PranaAutoPlusMode(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_auto_plus_mode"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Auto+ Mode"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.auto_mode_plus

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.toggle_auto_plus_mode()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.toggle_auto_plus_mode()

class PranaNightMode(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_night_mode"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Night Mode"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.night_mode

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.toggle_night_mode()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.toggle_night_mode()

class PranaBoostMode(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_boost_mode"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Boost"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.boost_mode

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.toggle_boost_mode()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.toggle_boost_mode()

class PranaFlowLock(BasePranaSwitch):
    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_flow_lock"

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "Flow Lock"

    @property
    def is_on(self):
        """Return state of the fan."""
        return self.coordinator.flows_locked

    @property
    def should_poll(self):
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the entity."""
        await self.coordinator.toggle_flow_lock()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.toggle_flow_lock()
