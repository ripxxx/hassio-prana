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

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_to_add = []

    sensors_to_add.append(PranaSensorTemperatureIn(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorTemperatureOut(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorHumidity(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorPressure(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorCO2(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorVOC(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorSpeedIn(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorSpeedOut(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorBrightness(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorRSSI(hass, coordinator, config_entry.data["name"], config_entry.entry_id))

    sensors_to_add.append(PranaSensorModeNight(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorModeBoost(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorModeAuto(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorModeWinter(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorHeating(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorFlowsLocked(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorDisplay(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorTimer(hass, coordinator, config_entry.data["name"], config_entry.entry_id))
    sensors_to_add.append(PranaSensorModeAutoPlus(hass, coordinator, config_entry.data["name"], config_entry.entry_id))

    async_add_entities(sensors_to_add)

class BasePranaSensor(CoordinatorEntity, SensorEntity):
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
        self._hass.bus.async_listen("prana_sensor_update", self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def available(self):
        """Return state of the fan."""
        return self.coordinator.lastRead != None and (self.coordinator.lastRead > datetime.now() - timedelta(minutes=5))

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

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

class PranaSensorCO2(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CO2"

    @property
    def device_class(self):
        return SensorDeviceClass.CO2

    @property
    def native_value(self):
        """Return co2 of the fan."""
        return self.coordinator.co2

    @property
    def native_unit_of_measurement(self):
        return "ppm"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_co2"

class PranaSensorVOC(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "TVOC"

    @property
    def device_class(self):
        return SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS

    @property
    def native_value(self):
        """Return voc of the fan."""
        return self.coordinator.voc

    @property
    def native_unit_of_measurement(self):
        return "ppb"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_voc"

class PranaSensorTemperatureIn(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "TemperatureIn"

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self):
        """Return temperature in of the fan."""
        return self.coordinator.temperature_in

    @property
    def native_unit_of_measurement(self):
        return "°C"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_temperature_in"

class PranaSensorTemperatureOut(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "TemperatureOut"

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self):
        """Return temperature out of the fan."""
        return self.coordinator.temperature_out

    @property
    def native_unit_of_measurement(self):
        return "°C"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_temperature_out"

class PranaSensorHumidity(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Humidity"

    @property
    def device_class(self):
        return SensorDeviceClass.HUMIDITY

    @property
    def native_value(self):
        """Return humidity of the fan."""
        return self.coordinator.humidity

    @property
    def native_unit_of_measurement(self):
        return "%"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_humidity"

class PranaSensorPressure(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Pressure"

    @property
    def device_class(self):
        return SensorDeviceClass.ATMOSPHERIC_PRESSURE

    @property
    def native_value(self):
        """Return pressure of the fan."""
        return self.coordinator.pressure

    @property
    def native_unit_of_measurement(self):
        return "mmHg"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_pressure"

class PranaSensorSpeedIn(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "SpeedIn"

    @property
    def device_class(self):
        return SensorDeviceClass.SPEED

    @property
    def native_value(self):
        """Return speed in of the fan."""
        return self.coordinator.speed_in

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_speed_in_value"

class PranaSensorSpeedOut(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "SpeedOut"

    @property
    def device_class(self):
        return SensorDeviceClass.SPEED

    @property
    def native_value(self):
        """Return speed out of the fan."""
        return self.coordinator.speed_out

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_speed_out_value"

class PranaSensorBrightness(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Brightness"

    @property
    def native_value(self):
        """Return brightness of the fan."""
        return self.coordinator.brightness

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_brightness_value"

class PranaSensorRSSI(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "RSSI"

    @property
    def device_class(self):
        return SensorDeviceClass.SIGNAL_STRENGTH

    @property
    def native_value(self):
        """Return rssi of the fan."""
        return self.coordinator.rssi

    @property
    def native_unit_of_measurement(self):
        return "dBm"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_rssi"

class PranaSensorModeNight(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Night Mode"

    @property
    def native_value(self):
        return self.coordinator.night_mode

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_night_mode_value"

class PranaSensorModeBoost(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Boost Mode"

    @property
    def native_value(self):
        return self.coordinator.boost_mode

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_boost_mode_value"

class PranaSensorModeAuto(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Auto Mode"

    @property
    def native_value(self):
        return self.coordinator.auto_mode

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_auto_mode_value"

class PranaSensorModeAutoPlus(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Auto+ Mode"

    @property
    def native_value(self):
        return self.coordinator.auto_mode_plus

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_auto_mode_plus_value"

class PranaSensorModeWinter(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Winter Mode"

    @property
    def native_value(self):
        return self.coordinator.winter_mode_enabled

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_winter_mode_value"

class PranaSensorHeating(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Heating"

    @property
    def native_value(self):
        return self.coordinator.mini_heating_enabled

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_heating_value"

class PranaSensorFlowsLocked(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Flows Locked"

    @property
    def native_value(self):
        return self.coordinator.flows_locked

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_flows_locked_value"

class PranaSensorDisplay(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Display"

    @property
    def native_value(self):
        return self.coordinator.display.value

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_display_value"

class PranaSensorTimer(BasePranaSensor):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "Timer"

    @property
    def native_value(self):
        return self.coordinator.timer_on

    @property
    def native_unit_of_measurement(self):
        return ""

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._name + "_timer_on_value"
