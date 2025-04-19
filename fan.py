"""Support for Prana fan."""
from . import DOMAIN

import asyncio
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

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .const import PranaState, Speed, PranaSensorsState, Display

LOGGER = logging.getLogger(__name__)

SPEED_AUTO = "auto"
SPEED_MANUAL = "manual"
SPEED_RANGE = (1, 5)

DATA_KEY = "fan.prana"

PRANA_SERVICE_BASE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

PRANA_SERVICE_SET_SPEED_SCHEMA = PRANA_SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required("speed") : vol.All(vol.Coerce(int), vol.Clamp(min=0, max=6))
    }
)

PRANA_SERVICE_SET_BRIGHTNESS_SCHEMA = PRANA_SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required("brightness") : vol.All(vol.Coerce(int), vol.Clamp(min=0, max=6))
    }
)

PRANA_SERVICE_SET_DISPLAY_SCHEMA = PRANA_SERVICE_BASE_SCHEMA.extend(
    {
        vol.Required("display") : vol.All(vol.Coerce(int), vol.Clamp(min=0, max=10))
    }
)

async def async_setup_entry(hass, config_entry, async_add_devices):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    devices = []

    device = PranaFan(coordinator, config_entry)

    devices.append(device)
    hass.data[DATA_KEY][config_entry.entry_id] = device

    async_add_devices(devices)

    async def async_service_handler(service):
        """Map services to methods on XiaomiAirPurifier."""
        method = "async_" + service.service
        params = {
            key: value for key, value in service.data.items() if key != ATTR_ENTITY_ID
        }
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            devices = [
                device
                for device in hass.data[DATA_KEY].values()
                if device.entity_id in entity_ids
            ]
        else:
            devices = hass.data[DATA_KEY].values()

        update_tasks = []
        for device in devices:
            if not hasattr(device, method):
                continue
            await getattr(device, method)(**params)
            update_tasks.append(asyncio.create_task(device.async_update_ha_state(True)))

        if update_tasks:
            await asyncio.wait(update_tasks)

    hass.services.async_register(DOMAIN, "set_speed", async_service_handler, schema=PRANA_SERVICE_SET_SPEED_SCHEMA)
    hass.services.async_register(DOMAIN, "set_speed_in", async_service_handler, schema=PRANA_SERVICE_SET_SPEED_SCHEMA)
    hass.services.async_register(DOMAIN, "set_speed_out", async_service_handler, schema=PRANA_SERVICE_SET_SPEED_SCHEMA)
    hass.services.async_register(DOMAIN, "set_brightness", async_service_handler, schema=PRANA_SERVICE_SET_BRIGHTNESS_SCHEMA)
    hass.services.async_register(DOMAIN, "set_display", async_service_handler, schema=PRANA_SERVICE_SET_DISPLAY_SCHEMA)

class PranaFan(CoordinatorEntity, FanEntity):
    """Representation of a Prana fan."""
    def __init__(self, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.coordinator = coordinator
        self._name = config_entry.data["name"]
        LOGGER.debug('entry id : %s', config_entry.entry_id)
        self._entry_id = f"{config_entry.entry_id}_fan"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        LOGGER.debug('Received data is on: %s', self.coordinator.is_on)
        self.async_write_ha_state()

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self.coordinator.mac.replace(":", "")

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return self._name

    @property
    def is_on(self):
        """Return state of the fan."""
        LOGGER.debug('Reading if device data is on: %s', self.coordinator.is_on)
        return self.coordinator.is_on

    @property
    def available(self):
        """Return state of the fan."""
        return self.coordinator.lastRead != None and (self.coordinator.lastRead > datetime.now() - timedelta(minutes=5))

    @property
    def extra_state_attributes(self):
        """Provide attributes for display on device card."""
        LOGGER.debug("Setting device attributes")
        attributes = {
            "brightness": self.coordinator.brightness,
            "humidity": self.coordinator.humidity,
            "pressure": self.coordinator.pressure,
            "temperature_in": self.coordinator.temperature_in,
            "temperature_out": self.coordinator.temperature_out,
            "co2": self.coordinator.co2,
            "voc": self.coordinator.voc,
            "auto_mode": self.coordinator.auto_mode,
            "auto_mode_plus": self.coordinator.auto_mode_plus,
            "night_mode": self.coordinator.night_mode,
            "boost_mode": self.coordinator.boost_mode,
            "thaw_on": self.coordinator.winter_mode_enabled,
            "heater_on": self.coordinator.mini_heating_enabled,
            "speed_in&out": self.coordinator.speed_locked,
            "speed_in": self.coordinator.speed_in,
            "speed_out": self.coordinator.speed_out,
            "air_in": self.coordinator.is_input_fan_on,
            "air_out": self.coordinator.is_output_fan_on,
            "last_updated": self.coordinator.lastRead,
            "flows_locked": self.coordinator.flows_locked,
            "display": self.coordinator.display,
            "timer_on": self.coordinator.timer_on,
            "timer": self.coordinator.timer,
        }
        return attributes

    @property
    def device_info(self):
        """Return device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.coordinator.mac)
            },
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC, self.coordinator.mac)}
        )

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return FanEntityFeature.SET_SPEED | FanEntityFeature.DIRECTION | FanEntityFeature.PRESET_MODE | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON

    async def async_turn_on(self, speed: str = None, percentage=None, preset_mode=None, **kwargs) -> None:
        """Turn on the entity."""
        LOGGER.debug("BEFORE FAN TURN ON")
        await self.coordinator.turn_on()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the entity."""
        await self.coordinator.turn_off()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_direction(self, direction: str):
        """Set the direction of the fan."""
        if direction == 'reverse':
            if not self.coordinator.is_input_fan_on:
                await self.coordinator.toggle_air_in_off()

            await self.coordinator.toggle_air_out_off()
        elif direction == 'forward':
            if not self.coordinator.is_output_fan_on:
                await self.coordinator.toggle_air_out_off()

            await self.coordinator.toggle_air_in_off()

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the preset mode of the fan."""
        if preset_mode == SPEED_AUTO:
            await self.coordinator.set_auto_mode()
        else:
            await self.coordinator.toggle_auto_mode()
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def preset_modes(self):
        """Return state of the fan."""
        return [SPEED_MANUAL, SPEED_AUTO]

    @property
    def preset_mode(self) -> str:
        """Return preset mode of the fan."""
        if self.coordinator.auto_mode:
            return SPEED_AUTO
        else:
            return SPEED_MANUAL

    @property
    def percentage(self) -> int:
        """Return percentage of the fan."""
        return ranged_value_to_percentage(SPEED_RANGE, self.coordinator.speed)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        LOGGER.debug("Changing fan speed percentage to %s", percentage)

        speed = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        if speed == 0 or percentage == None:
            await self.coordinator.turn_off()
        else:
            await self.coordinator.set_speed(speed)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def speed_count(self) -> int:
        """Return the number of speeds the fan supports."""
        return int_states_in_range(SPEED_RANGE)

    @property
    def current_direction(self) -> str:
        """Fan direction."""
        if not self.coordinator.speed:
            return None
        elif not self.coordinator.is_input_fan_on:
            return "forward"
        elif not self.coordinator.is_output_fan_on:
            return "reverse"
        else:
            return "reverse & forward"

    async def async_set_brightness(self, brightness: int):
        await self.coordinator.set_brightness(brightness)

    async def async_set_speed(self, speed: int):
        await self.coordinator.set_speed(speed)

    async def async_set_speed_in(self, speed: int):
        await self.coordinator.set_speed_in(speed)

    async def async_set_speed_out(self, speed: int):
        await self.coordinator.set_speed_out(speed)

    async def async_set_display(self, display: int):
        await self.coordinator.set_display(Display(display))
