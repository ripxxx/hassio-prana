import asyncio
from datetime import datetime, timedelta
import binascii
import async_timeout

from homeassistant.components import bluetooth
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import PranaState, Speed, PranaSensorsState, Display, PranaTimer

from typing import Dict, List, Union, Optional
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTCharacteristic, BleakGATTServiceCollection
from bleak.exc import BleakDBusError
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakError,
    BleakNotFoundError,
    ble_device_has_changed,
    establish_connection,
)
from typing import Any, TypeVar, cast, Tuple
from collections.abc import Callable
from math import log2
import traceback
import asyncio
import logging
import struct


LOGGER = logging.getLogger(__name__)
WRITE_CHARACTERISTIC_UUIDS = ["0000cccc-0000-1000-8000-00805f9b34fb"]
READ_CHARACTERISTIC_UUIDS  = ["0000cccc-0000-1000-8000-00805f9b34fb"]

DEFAULT_ATTEMPTS = 3
DISCONNECT_DELAY = 120
BLEAK_BACKOFF_TIME = 0.25
RETRY_BACKOFF_EXCEPTIONS = (BleakDBusError,)
WrapFuncType = TypeVar("WrapFuncType", bound=Callable[..., Any])

def retry_bluetooth_connection_error(func: WrapFuncType) -> WrapFuncType:
    """Define a wrapper to retry on bleak error.

    The accessory is allowed to disconnect us any time so
    we need to retry the operation.
    """

    async def _async_wrap_retry_bluetooth_connection_error(
        self: "Prana", *args: Any, **kwargs: Any
    ) -> Any:
        attempts = DEFAULT_ATTEMPTS
        max_attempts = attempts - 1

        for attempt in range(attempts):
            try:
                return await func(self, *args, **kwargs)
            except BleakNotFoundError:
                # The lock cannot be found so there is no
                # point in retrying.
                raise
            except RETRY_BACKOFF_EXCEPTIONS as err:
                if attempt >= max_attempts:
                    LOGGER.debug("%s: %s error calling %s, reach max attempts (%s/%s)",self.name,type(err),func,attempt,max_attempts,exc_info=True,)
                    raise
                LOGGER.debug("%s: %s error calling %s, backing off %ss, retrying (%s/%s)...",self.name,type(err),func,BLEAK_BACKOFF_TIME,attempt,max_attempts,exc_info=True,)
                await asyncio.sleep(BLEAK_BACKOFF_TIME)
            except BLEAK_EXCEPTIONS as err:
                if attempt >= max_attempts:
                    LOGGER.debug("%s: %s error calling %s, reach max attempts (%s/%s): %s",self.name,type(err),func,attempt,max_attempts,err,exc_info=True,)
                    raise
                LOGGER.debug("%s: %s error calling %s, retrying  (%s/%s)...: %s",self.name,type(err),func,attempt,max_attempts,err,exc_info=True,)

    return cast(WrapFuncType, _async_wrap_retry_bluetooth_connection_error)

class PranaCoordinator(DataUpdateCoordinator):
    CONTROL_SERVICE_UUID = "0000baba-0000-1000-8000-00805f9b34fb"
    CONTROL_RW_CHARACTERISTIC_UUID = "0000cccc-0000-1000-8000-00805f9b34fb"
    STATE_MSG_PREFIX = b"\xbe\xef"
    MAX_BRIGHTNESS = 6

    class Cmd:
        STOP = bytearray([0xBE, 0xEF, 0x04, 0x01])

        CHANGE_BRIGHTNESS = bytearray([0xBE, 0xEF, 0x04, 0x02])

        TOGGLE_HEATING = bytearray([0xBE, 0xEF, 0x04, 0x05])
        TOGGLE_NIGHT_MODE = bytearray([0xBE, 0xEF, 0x04, 0x06])
        TOGGLE_BOOST_MODE = bytearray([0xBE, 0xEF, 0x04, 0x07])

        TOGGLE_FLOW_LOCK = bytearray([0xBE, 0xEF, 0x04, 0x09])

        START = bytearray([0xBE, 0xEF, 0x04, 0x0A])

        SPEED_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x0B])
        SPEED_UP = bytearray([0xBE, 0xEF, 0x04, 0x0C])

        FLOW_IN_OFF = bytearray([0xBE, 0xEF, 0x04, 0x0D])

        SPEED_IN_UP = bytearray([0xBE, 0xEF, 0x04, 0x0E])
        SPEED_IN_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x0F])

        FLOW_OUT_OFF = bytearray([0xBE, 0xEF, 0x04, 0x10])

        SPEED_OUT_UP = bytearray([0xBE, 0xEF, 0x04, 0x11])
        SPEED_OUT_DOWN = bytearray([0xBE, 0xEF, 0x04, 0x12])

        TOGGLE_TIMER = bytearray([0xBE, 0xEF, 0x04, 0x13])
        TIMER_DOWN_START = bytearray([0xBE, 0xEF, 0x04, 0x14])
        TIMER_UP_START = bytearray([0xBE, 0xEF, 0x04, 0x15])

        TOGGLE_WINTER_MODE = bytearray([0xBE, 0xEF, 0x04, 0x16])
        AUTO_MODE = bytearray([0xBE, 0xEF, 0x04, 0x18])

        DISPLAY_LEFT = bytearray([0xBE, 0xEF, 0x04, 0x19])
        DISPLAY_RIGHT = bytearray([0xBE, 0xEF, 0x04, 0x1A])

        SPEED_IN_1 = bytearray([0xBE, 0xEF, 0x04, 0x1F])
        SPEED_IN_2 = bytearray([0xBE, 0xEF, 0x04, 0x20])
        SPEED_IN_3 = bytearray([0xBE, 0xEF, 0x04, 0x21])
        SPEED_IN_4 = bytearray([0xBE, 0xEF, 0x04, 0x22])
        SPEED_IN_5 = bytearray([0xBE, 0xEF, 0x04, 0x23])
        SPEED_IN_BOOST_1 = bytearray([0xBE, 0xEF, 0x04, 0x24])
        SPEED_IN_BOOST_2 = bytearray([0xBE, 0xEF, 0x04, 0x25])
        SPEED_IN_BOOST_3 = bytearray([0xBE, 0xEF, 0x04, 0x26])
        SPEED_IN_BOOST_4 = bytearray([0xBE, 0xEF, 0x04, 0x27])
        SPEED_IN_BOOST_5 = bytearray([0xBE, 0xEF, 0x04, 0x28])

        SPEED_OUT_1 = bytearray([0xBE, 0xEF, 0x04, 0x29])
        SPEED_OUT_2 = bytearray([0xBE, 0xEF, 0x04, 0x2A])
        SPEED_OUT_3 = bytearray([0xBE, 0xEF, 0x04, 0x2B])
        SPEED_OUT_4 = bytearray([0xBE, 0xEF, 0x04, 0x2C])
        SPEED_OUT_5 = bytearray([0xBE, 0xEF, 0x04, 0x2D])
        SPEED_OUT_BOOST_1 = bytearray([0xBE, 0xEF, 0x04, 0x2E])
        SPEED_OUT_BOOST_2 = bytearray([0xBE, 0xEF, 0x04, 0x2F])
        SPEED_OUT_BOOST_3 = bytearray([0xBE, 0xEF, 0x04, 0x30])
        SPEED_OUT_BOOST_4 = bytearray([0xBE, 0xEF, 0x04, 0x31])
        SPEED_OUT_BOOST_5 = bytearray([0xBE, 0xEF, 0x04, 0x32])

        SPEED_1 = bytearray([0xBE, 0xEF, 0x04, 0x33])
        SPEED_2 = bytearray([0xBE, 0xEF, 0x04, 0x34])
        SPEED_3 = bytearray([0xBE, 0xEF, 0x04, 0x35])
        SPEED_4 = bytearray([0xBE, 0xEF, 0x04, 0x36])
        SPEED_5 = bytearray([0xBE, 0xEF, 0x04, 0x37])
        SPEED_BOOST_1 = bytearray([0xBE, 0xEF, 0x04, 0x38])
        SPEED_BOOST_2 = bytearray([0xBE, 0xEF, 0x04, 0x39])
        SPEED_BOOST_3 = bytearray([0xBE, 0xEF, 0x04, 0x3A])
        SPEED_BOOST_4 = bytearray([0xBE, 0xEF, 0x04, 0x3B])
        SPEED_BOOST_5 = bytearray([0xBE, 0xEF, 0x04, 0x3C])

        TOGGLE_AUTO_MODE_2 = bytearray([0xBE, 0xEF, 0x04, 0x43])
        TOGGLE_AUTO_PLUS_MODE = bytearray([0xBE, 0xEF, 0x04, 0x44])

        DISPLAY_TEMPERATURE_IN_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x47])
        DISPLAY_TEMPERATURE_OUT_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x48])
        DISPLAY_CO2_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x49])
        DISPLAY_VOC_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x4A])
        DISPLAY_HUMIDITY_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x4B])
        DISPLAY_PRESURE_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x4C])
        DISPLAY_COMPATIBILITY_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x4D])
        DISPLAY_ALL_SYMBOLS_LOCKED = bytearray([0xBE, 0xEF, 0x04, 0x4E])

        TIMER_STOP = bytearray([0xBE, 0xEF, 0x04, 0x50])
        TIMER_START_10M = bytearray([0xBE, 0xEF, 0x04, 0x51])
        TIMER_START_20M = bytearray([0xBE, 0xEF, 0x04, 0x52])
        TIMER_START_30M = bytearray([0xBE, 0xEF, 0x04, 0x53])
        TIMER_START_1H = bytearray([0xBE, 0xEF, 0x04, 0x54])
        TIMER_START_1H30M = bytearray([0xBE, 0xEF, 0x04, 0x55])
        TIMER_START_2H = bytearray([0xBE, 0xEF, 0x04, 0x56])
        TIMER_START_3H = bytearray([0xBE, 0xEF, 0x04, 0x57])
        TIMER_START_5H = bytearray([0xBE, 0xEF, 0x04, 0x58])
        TIMER_START_9H = bytearray([0xBE, 0xEF, 0x04, 0x59])

        DISPLAY_FAN = bytearray([0xBE, 0xEF, 0x04, 0x5A])
        DISPLAY_TEMPERATURE_IN = bytearray([0xBE, 0xEF, 0x04, 0x5B])
        DISPLAY_TEMPERATURE_OUT = bytearray([0xBE, 0xEF, 0x04, 0x5C])
        DISPLAY_CO2 = bytearray([0xBE, 0xEF, 0x04, 0x5D])
        DISPLAY_VOC = bytearray([0xBE, 0xEF, 0x04, 0x5E])
        DISPLAY_HUMIDITY = bytearray([0xBE, 0xEF, 0x04, 0x5F])
        DISPLAY_QUALITY_FAN = bytearray([0xBE, 0xEF, 0x04, 0x60])
        DISPLAY_PRESURE = bytearray([0xBE, 0xEF, 0x04, 0x61])
        DISPLAY_FAN_2 = bytearray([0xBE, 0xEF, 0x04, 0x62])
        DISPLAY_DATE = bytearray([0xBE, 0xEF, 0x04, 0x63])
        DISPLAY_TIME = bytearray([0xBE, 0xEF, 0x04, 0x64])

        SET_BRIGHTNESS_0 = bytearray([0xBE, 0xEF, 0x04, 0x6E])
        SET_BRIGHTNESS_1 = bytearray([0xBE, 0xEF, 0x04, 0x6F])
        SET_BRIGHTNESS_2 = bytearray([0xBE, 0xEF, 0x04, 0x70])
        SET_BRIGHTNESS_3 = bytearray([0xBE, 0xEF, 0x04, 0x71])
        SET_BRIGHTNESS_4 = bytearray([0xBE, 0xEF, 0x04, 0x72])
        SET_BRIGHTNESS_5 = bytearray([0xBE, 0xEF, 0x04, 0x73])
        SET_BRIGHTNESS_6 = bytearray([0xBE, 0xEF, 0x04, 0x74])

        READ_STATE = bytearray([0xBE, 0xEF, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00, 0x5A])
        READ_DEVICE_DETAILS = bytearray([0xBE, 0xEF, 0x05, 0x02, 0x00, 0x00, 0x00, 0x00, 0x5A])



    def __init__(self, address, hass) -> None:
        """Initialize prana coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="Prana ventilation",
            update_interval=timedelta(seconds=30),
        )

        self.loop = asyncio.get_running_loop()
        self.mac = address
        self._hass = hass
        self._device: BLEDevice | None = None
        self._device = bluetooth.async_ble_device_from_address(self._hass, address, connectable=True)
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._cached_services: BleakGATTServiceCollection | None = None
        self._expected_disconnect = False
        self._write_uuid = None
        self._read_uuid = None

        # Device data
        self.speed = 0 #calculated
        self.speed_locked: Optional[int] = None
        self.speed_in: Optional[int] = None
        self.speed_out: Optional[int] = None
        self.night_mode: Optional[bool] = None
        self.boost_mode: Optional[bool] = None
        self.auto_mode: Optional[bool] = None
        self.flows_locked: Optional[bool] = None
        self.is_on: Optional[bool] = None
        self.mini_heating_enabled: Optional[bool] = None
        self.winter_mode_enabled: Optional[bool] = None
        self.is_input_fan_on: Optional[bool] = None
        self.is_output_fan_on: Optional[bool] = None
        self.brightness: Optional[int] = None
        self.sensors: Optional[PranaSensorsState] = None
        self.timestamp: Optional[datetime.datetime] = None
        self.lastRead = None
        self.humidity = None
        self.pressure = None
        self.temperature_in = None
        self.temperature_out = None
        self.co2 = None
        self.voc = None
        self.air_in = None
        self.isAirInOn = None
        self.isAirOutOn = None
        self.display = None

        #Test
        self.byte4: int = 0
        #Test

    async def _async_update_data(self):
        """Fetch data from device."""
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            await self.get_status_details()

        except (Exception) as error:
            self.is_on = False
            LOGGER.error("Error getting status: %s", error)
            track = traceback.format_exc()
            LOGGER.debug(track)

    async def _write(self, data: bytearray, await_response: bool = False):
        """Send command to device and read response."""
        await self._ensure_connected()
        return await self._write_while_connected(data, await_response)

    async def _write_while_connected(self, data: bytearray, await_response: bool = False):
        LOGGER.debug("Before command")
        await self._client.write_gatt_char(self._write_uuid, data, await_response)

        # Update the info after each command
        if(self.Cmd.READ_STATE != data):
            LOGGER.debug("Before read state")
            return await self._client.write_gatt_char(self._write_uuid, self.Cmd.READ_STATE, True)

    @property
    def rssi(self):
        return self._device.rssi

# NEW DATA
    @retry_bluetooth_connection_error
    async def toggle_boost_mode(self):
        await self._write(self.Cmd.TOGGLE_BOOST_MODE)

    @retry_bluetooth_connection_error
    async def speed_up(self):
        await self._write(self.Cmd.SPEED_UP)

    @retry_bluetooth_connection_error
    async def speed_in_up(self):
        await self._write(self.Cmd.SPEED_IN_UP)

    @retry_bluetooth_connection_error
    async def speed_out_up(self):
        await self._write(self.Cmd.SPEED_OUT_UP)

    @retry_bluetooth_connection_error
    async def speed_down(self):
        await self._write(self.Cmd.SPEED_DOWN)

    @retry_bluetooth_connection_error
    async def speed_in_down(self):
        await self._write(self.Cmd.SPEED_IN_DOWN)

    @retry_bluetooth_connection_error
    async def speed_out_down(self):
        await self._write(self.Cmd.SPEED_OUT_DOWN)

    @retry_bluetooth_connection_error
    async def set_low_speed(self):
        await self._write(self.Cmd.TOGGLE_NIGHT_MODE)

    @retry_bluetooth_connection_error
    async def toggle_night_mode(self):
        await self._write(self.Cmd.TOGGLE_NIGHT_MODE)

    @retry_bluetooth_connection_error
    async def set_night_mode(self):
        await self._write(self.Cmd.TOGGLE_NIGHT_MODE)

    @retry_bluetooth_connection_error
    async def toggle_flow_lock(self):
        await self._write(self.Cmd.TOGGLE_FLOW_LOCK)

    @retry_bluetooth_connection_error
    async def set_normal_speed(self):
        await self.set_speed(Speed.SPEED_3)

    @retry_bluetooth_connection_error
    async def get_status_details(self):
        return await self._write(self.Cmd.READ_STATE)

    @retry_bluetooth_connection_error
    async def set_display(self, display: int):
        if display == Display.FAN:
            await self._write(self.Cmd.DISPLAY_FAN)
        elif display == Display.TEMPERATURE_IN:
            await self._write(self.Cmd.DISPLAY_TEMPERATURE_IN)
        elif display == Display.TEMPERATURE_OUT:
            await self._write(self.Cmd.DISPLAY_TEMPERATURE_OUT)
        elif display == Display.CO2:
            await self._write(self.Cmd.DISPLAY_CO2)
        elif display == Display.VOC:
            await self._write(self.Cmd.DISPLAY_VOC)
        elif display == Display.HUMIDITY:
            await self._write(self.Cmd.DISPLAY_HUMIDITY)
        elif display == Display.QUALITY_FAN:
            await self._write(self.Cmd.DISPLAY_QUALITY_FAN)
        elif display == Display.PRESURE:
            await self._write(self.Cmd.DISPLAY_PRESURE)
        elif display == Display.FAN_2:
            await self._write(self.Cmd.DISPLAY_FAN_2)
        elif display == Display.DATE:
            await self._write(self.Cmd.DISPLAY_DATE)
        elif display == Display.TIME:
            await self._write(self.Cmd.DISPLAY_TIME)

    @retry_bluetooth_connection_error
    async def set_speed(self, speed: int):
        if (speed == self.speed):
            return

        if speed > 0 and not self.is_on:
            await self.turn_on()

        if speed == 0:
            await self.turn_off()
        elif speed == 1:
            await self._write(self.Cmd.SPEED_1)
        elif speed == 2:
            await self._write(self.Cmd.SPEED_2)
        elif speed == 3:
            await self._write(self.Cmd.SPEED_3)
        elif speed == 4:
            await self._write(self.Cmd.SPEED_4)
        elif speed == 5:
            await self._write(self.Cmd.SPEED_5)
        elif speed == 6:
            await self._write(self.Cmd.SPEED_BOOST_5)

        self.speed = speed

    @retry_bluetooth_connection_error
    async def set_speed_in(self, speed: int):
        if (speed == self.speed_in):
            return

        if speed > 0 and not self.is_on:
            await self.turn_on()

        if speed == 0:
            await self._write(self.Cmd.FLOW_IN_OFF)
        elif speed == 1:
            await self._write(self.Cmd.SPEED_IN_1)
        elif speed == 2:
            await self._write(self.Cmd.SPEED_IN_2)
        elif speed == 3:
            await self._write(self.Cmd.SPEED_IN_3)
        elif speed == 4:
            await self._write(self.Cmd.SPEED_IN_4)
        elif speed == 5:
            await self._write(self.Cmd.SPEED_IN_5)
        elif speed == 6:
            await self._write(self.Cmd.SPEED_IN_BOOST_5)

    @retry_bluetooth_connection_error
    async def set_speed_out(self, speed: int):
        if (speed == self.speed_out):
            return

        if speed > 0 and not self.is_on:
            await self.turn_on()

        if speed == 0:
            await self._write(self.Cmd.FLOW_OUT_OFF)
        elif speed == 1:
            await self._write(self.Cmd.SPEED_OUT_1)
        elif speed == 2:
            await self._write(self.Cmd.SPEED_OUT_2)
        elif speed == 3:
            await self._write(self.Cmd.SPEED_OUT_3)
        elif speed == 4:
            await self._write(self.Cmd.SPEED_OUT_4)
        elif speed == 5:
            await self._write(self.Cmd.SPEED_OUT_5)
        elif speed == 6:
            await self._write(self.Cmd.SPEED_OUT_BOOST_5)

    @retry_bluetooth_connection_error
    async def set_timer(self, timer: int):
        if timer == PranaTimer.STOP:
            await self._write(self.Cmd.TIMER_STOP)
        elif timer == PranaTimer.RUN:
            await self._write(self.Cmd.TIMER_START_10M)
        elif timer == PranaTimer.RUN_10M:
            await self._write(self.Cmd.TIMER_START_10M)
        elif timer == PranaTimer.RUN_20M:
            await self._write(self.Cmd.TIMER_START_20M)
        elif timer == PranaTimer.RUN_30M:
            await self._write(self.Cmd.TIMER_START_30M)
        elif timer == PranaTimer.RUN_1H:
            await self._write(self.Cmd.TIMER_START_1H)
        elif timer == PranaTimer.RUN_1H30M:
            await self._write(self.Cmd.TIMER_START_1H30M)
        elif timer == PranaTimer.RUN_2H:
            await self._write(self.Cmd.TIMER_START_2H)
        elif timer == PranaTimer.RUN_3H:
            await self._write(self.Cmd.TIMER_START_3H)
        elif timer == PranaTimer.RUN_5H:
            await self._write(self.Cmd.TIMER_START_5H)
        elif timer == PranaTimer.RUN_9H:
            await self._write(self.Cmd.TIMER_START_9H)

    @retry_bluetooth_connection_error
    async def set_brightness(self, brightness: int):
        if brightness < 0 or brightness > 6:
            raise ValueError("brightness value must be in range 0-6")

        if brightness == 0:
            await self._write(self.Cmd.SET_BRIGHTNESS_0)
        elif brightness == 1:
            await self._write(self.Cmd.SET_BRIGHTNESS_1)
        elif brightness == 2:
            await self._write(self.Cmd.SET_BRIGHTNESS_2)
        elif brightness == 3:
            await self._write(self.Cmd.SET_BRIGHTNESS_3)
        elif brightness == 4:
            await self._write(self.Cmd.SET_BRIGHTNESS_4)
        elif brightness == 5:
            await self._write(self.Cmd.SET_BRIGHTNESS_5)
        elif brightness == 6:
            await self._write(self.Cmd.SET_BRIGHTNESS_6)

    @retry_bluetooth_connection_error
    async def set_brightness_pct(self, brightness_pct: int):
        """
        Set brightness in percents (0-100)
        :param brightness_pct: integer in 0-100 range
        :return:
        """
        if brightness_pct < 0 or brightness_pct > 100:
            raise ValueError("brightness_pct is percent value (range 0-100)")
        return await self.set_brightness(round(self.MAX_BRIGHTNESS * brightness_pct / 100))

    @retry_bluetooth_connection_error
    async def brightness_up(self):
        await self._write(self.Cmd.CHANGE_BRIGHTNESS)

    @retry_bluetooth_connection_error
    async def test(self):
        command = [0xBE, 0xEF, 0x04]
        command.append(self.byte4)
        await self._write(command)

    @retry_bluetooth_connection_error
    async def set_heating(self, enable: bool):
        if self.mini_heating_enabled != enable:
            LOGGER.debug("Set heating mode")
            await self._write(self.Cmd.TOGGLE_HEATING, True)
            self.mini_heating_enabled = enable

    @retry_bluetooth_connection_error
    async def set_winter_mode(self, enable: bool):
        if self.winter_mode_enabled != enable:
            return await self._write(self.Cmd.TOGGLE_WINTER_MODE)

    @retry_bluetooth_connection_error
    async def turn_off(self):
        LOGGER.debug("turn off")
        self.is_on = False
        return await self._write(self.Cmd.STOP)

    @retry_bluetooth_connection_error
    async def turn_on(self):
        LOGGER.debug("turn on")
        self.is_on = True
        return await self._write(self.Cmd.START)

    @retry_bluetooth_connection_error
    async def toggle_air_in_off(self):
        self.is_input_fan_on = not self.is_input_fan_on
        return await self._write(self.Cmd.FLOW_IN_OFF)

    @retry_bluetooth_connection_error
    async def toggle_air_out_off(self):
        self.is_output_fan_on = not self.self.is_output_fan_on
        return await self._write(self.Cmd.FLOW_OUT_OFF)

    @retry_bluetooth_connection_error
    async def toggle_auto_mode(self):
        self.auto_mode = not self.auto_mode
        return await self._write(self.Cmd.TOGGLE_AUTO_MODE_2)

    @retry_bluetooth_connection_error
    async def toggle_auto_plus_mode(self):
        self.auto_mode = not self.auto_mode
        return await self._write(self.Cmd.TOGGLE_AUTO_PLUS_MODE)

    @retry_bluetooth_connection_error
    async def set_auto_mode(self):
        if not self.auto_mode:
            self.auto_mode = True
            await self._write(self.Cmd.AUTO_MODE)


    def __parse_state(self, data: bytearray) -> Optional[PranaState]:
        if not data[:2] == self.STATE_MSG_PREFIX:
            return None
        LOGGER.warning("%s %s %s %s %s %s", data[36], data[37], data[38], data[39], data[40], data[41])
        #LOGGER.warning("DATA SIZE: %s", len(data))#137
        LOGGER.warning(''.join(format(x, '02x') + ' ' for x in data))

        s = PranaState()
        s.timestamp = datetime.now()
        s.brightness = int(log2(data[12]) + 1)
        s.speed_locked = int(data[26] / 10)
        s.speed_in = int(data[30] / 10)
        s.speed_out = int(data[34] / 10)
        s.auto_mode = bool(data[20] & 1)
        s.auto_mode_plus = bool(data[20] & 2)
        s.night_mode = bool(data[16])
        s.boost_mode = bool(data[18])
        s.flows_locked = bool(data[22])
        s.is_on = bool(data[10])
        s.mini_heating_enabled = bool(data[14])
        s.winter_mode_enabled = bool(data[42])
        s.is_input_fan_on = bool(data[28])
        s.is_output_fan_on = bool(data[32])
        s.display = Display(int(data[99]))
        s.timer_on = bool(data[38])
        s.timer = ((int(data[39]) << 8) + int(data[40]))

        if not self.is_on:
            self.speed = 0
        elif self.auto_mode:
            self.speed = self.speed_in #same as self.speedOut
        elif self.speed_locked:
            self.speed = self.speed_locked
        elif self.air_in and self.air_in:
            self.speed = int((self.speed_in + self.speed_out) / 2)
        elif self.isAirInOn:
            self.speed = self.speed_in
        elif self.isAirOutOn:
            self.speed = self.speed_out

        # Reading sensors
        sensors = PranaSensorsState()
        sensors.humidity = int(data[60] - 128)
        sensors.pressure = 512 + int(data[78])
        # co2 and voc
        sensors.co2 = int(struct.unpack_from(">h", data, 61)[0] & 0b0011111111111111)
        sensors.voc = int(struct.unpack_from(">h", data, 63)[0] & 0b0011111111111111)
        if 0 < sensors.co2 < 10000:
            # Different version of firmware ???
            sensors.temperature_in = float(struct.unpack_from(">h", data, 51)[0] & 0b0011111111111111) / 10.0
            sensors.temperature_out = float(struct.unpack_from(">h", data, 54)[0] & 0b0011111111111111) / 10.0
        else:
            sensors.temperature_in = float(data[49]) / 10
            sensors.temperature_out = float(data[55]) / 10
        # Add sensors to the state only in case device has corresponding hardware
        if sensors.humidity > 0:
            s.sensors = sensors
        return s

    async def _notification_handler(self, _sender: int, data: bytearray) -> None:
        """Handle notification responses."""
        state = self.__parse_state(data)
        self.lastRead = datetime.now()
        LOGGER.debug("State data from notifiation: %s", state)
        if state is not None:
            dict_state = state.to_dict()
            for key in dict_state:
                setattr(self, key, dict_state[key])
            if state.sensors is not None:
                sensors = state.sensors.to_dict()
                for key in sensors:
                    setattr(self, key, sensors[key])
            LOGGER.debug("Send update event %s", dict_state)
            await self.async_request_refresh()


# NEW DATA END








# OLD
    @retry_bluetooth_connection_error
    async def _ensure_connected(self) -> None:
        """Ensure connection to device is established."""
        if self._connect_lock.locked():
            LOGGER.debug(
                "%s: Connection already in progress, waiting for it to complete; RSSI: %s",
                self.name,
                self.rssi,
            )
        if self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return
        async with self._connect_lock:
            # Check again while holding the lock
            if self._client and self._client.is_connected:
                self._reset_disconnect_timer()
                return
            LOGGER.debug("%s: Connecting; RSSI: %s", self.name, self.rssi)
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self.name,
                self._disconnected,
                cached_services=self._cached_services,
                ble_device_callback=lambda: self._device,
            )
            LOGGER.debug("%s: Connected; RSSI: %s", self.name, self.rssi)

            self._read_uuid = READ_CHARACTERISTIC_UUIDS[0]
            self._write_uuid = WRITE_CHARACTERISTIC_UUIDS[0]
            self._cached_services = client.services
            self._client = client
            self._reset_disconnect_timer()

            LOGGER.debug("%s: Subscribe to notifications; RSSI: %s", self.name, self.rssi)
            await client.start_notify(self._read_uuid, self._notification_handler)


    def _reset_disconnect_timer(self) -> None:
        """Reset disconnect timer."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._expected_disconnect = False
        self._disconnect_timer = self.loop.call_later(
            DISCONNECT_DELAY, self._disconnect
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        """Disconnected callback."""
        if self._expected_disconnect:
            LOGGER.debug("%s: Disconnected from device; RSSI: %s", self.name, self.rssi)
            return
        LOGGER.warning("%s: Device unexpectedly disconnected; RSSI: %s",self.name,self.rssi,)

    def _disconnect(self) -> None:
        """Disconnect from device."""
        self._disconnect_timer = None
        asyncio.create_task(self._execute_timed_disconnect())

    async def stop(self) -> None:
        """Stop the LEDBLE."""
        # LOGGER.debug("%s: Stop", self.name)
        await self._execute_disconnect()

    async def _execute_timed_disconnect(self) -> None:
        """Execute timed disconnection."""
        LOGGER.debug(
            "%s: Disconnecting after timeout of %s",
            self.name,
            DISCONNECT_DELAY,
        )
        await self._execute_disconnect()

    async def _execute_disconnect(self) -> None:
        """Execute disconnection."""
        async with self._connect_lock:
            read_char = self._read_uuid
            client = self._client
            self._expected_disconnect = True
            self._client = None
            self._write_uuid = None
            self._read_uuid = None
            if client and client.is_connected:
                await client.stop_notify(read_char)
                await client.disconnect()
