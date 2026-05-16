"""Jimmy custom"""
import logging
import datetime

from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.helpers import discovery
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle, dt
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

DOMAIN = "jimmy_custom"
LOGGER = logging.getLogger(__name__)

class HeatingStrategy(Entity):
    def __init__(self, tibber_home, percent=20.0, horizon=3):
        self._tibber_home = tibber_home
        self._percent = percent
        self._horizon = horizon
        LOGGER.info(self._tibber_home.info)
        self._name = tibber_home.info["viewer"]["home"]["address"].get("address1", "")

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Heating strategy {}".format(self._name)

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def model(self):
        """Return the model of the sensor."""
        return "Heating Strategy Sensor"

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:thermometer"

    #@property
    #def unit_of_measurement(self):
    #    """Return the unit of measurement of this entity."""
    #    return "state"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return "Heating Strategy"

    def get_prices(self, time_from = None, time_to = None):
        return [v for k, v in self._tibber_home.price_total.items() if (not time_from or dt.parse_datetime(k) >= time_from) and (not time_to or dt.parse_datetime(k) <= time_to)]

    def get_average_price(self, time_from = None, time_to = None):
        values = self.get_prices(time_from, time_to)
        LOGGER.debug(values)
        if len(values) == 0:
            return 0
        return sum(values) / len(values)

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self.data()

    def data(self):
        res = {}
        datehour = dt.now()
        res['datehour_now'] = datehour.replace(minute=0, second=0, microsecond=0)
        res['datehour_coming'] = res['datehour_now'] + datetime.timedelta(hours=1)
        res['datehour_coming_end'] = res['datehour_now'] + datetime.timedelta(hours=self._horizon)
        res['average_price'] = self.get_average_price(res['datehour_now'])
        res['price_now'] = self.get_average_price(res['datehour_now'], res['datehour_now'])
        res['price_coming'] = self.get_average_price(res['datehour_coming'], res['datehour_coming_end'])
        if not res['price_now'] or not res['price_coming']:
            return None

        res['delta'] = res['price_coming'] - res['price_now']
        res['delta_percent'] = 100.0 * res['delta'] / res['average_price']
        return res

    @property
    def state(self):
        """Return the state of the device."""
        d = self.data()

        LOGGER.info(f"Price now: {d['price_now']}, Price coming: {d['price_coming']}, Average price: {d['average_price']}, Delta: {d['delta']}, PricePercent: {d['delta_percent']}")


        if d['delta_percent'] > self._percent:
            return "BOOST"
        if d['delta_percent'] < -self._percent:
            return "SAVE"
        return "NORMAL"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup component."""
    dev = []
    LOGGER.info("jimmy async_setup_platform")
    for entry in hass.config_entries.async_entries("tibber"):
        if hasattr(entry, 'runtime_data') and entry.runtime_data:
            tibber_connection = await entry.runtime_data.async_get_client(hass)
            for home in tibber_connection.get_homes(only_active=True):
                LOGGER.info(home)
                dev.append(HeatingStrategy(home))
    async_add_entities(dev)

