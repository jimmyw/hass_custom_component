"""Jimmy custom"""
import logging
import datetime

from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.helpers import discovery
from homeassistant.helpers.entity import Entity
from homeassistant.util import dt

DOMAIN = "jimmy_custom"
LOGGER = logging.getLogger(__name__)

# Nordpool spot price sensor (without VAT)
NORDPOOL_ENTITY = "sensor.nordpool_kwh_se3_sek_3_10_0"
# Fees added on top of spot price before VAT
TIBBER_FEE = 0.06  # SEK/kWh - Tibber markup
GRID_FEE = 0.52    # SEK/kWh - grid transfer fee (nätavgift)
VAT_MULTIPLIER = 1.25
# Solar sell-back: opportunity cost = nordpool spot + this adder
SOLAR_SELL_ADDER = 0.09  # SEK/kWh
# Heating system power draw
HEATING_LOAD_KW = 3.5
# How far ahead to compare prices (hours)
LOOK_AHEAD_HOURS = 3


class HeatingStrategy(Entity):
    def __init__(self, percent=20.0, horizon=LOOK_AHEAD_HOURS):
        self._percent = percent
        self._horizon = horizon

    @property
    def name(self):
        """Return the name of the sensor."""
        return "Heating strategy"

    @property
    def available(self):
        """Return True if entity is available."""
        return True

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:thermometer"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return "Heating Strategy"

    def get_nordpool_raw_prices(self):
        """Get raw today+tomorrow price entries from Nordpool sensor.

        Each entry has 'start', 'end' (datetime) and 'value' (SEK/kWh).
        Works with both hourly and 15-minute price intervals.
        """
        if not self.hass:
            return []
        state = self.hass.states.get(NORDPOOL_ENTITY)
        if state is None:
            return []
        attrs = state.attributes
        raw = list(attrs.get('raw_today', []))
        raw.extend(attrs.get('raw_tomorrow', []))
        LOGGER.debug("Nordpool raw prices: %d slots loaded", len(raw))
        return raw

    def get_spot_price(self, target_time):
        """Get Nordpool spot price (SEK/kWh, no VAT) for the slot containing target_time."""
        for entry in self.get_nordpool_raw_prices():
            if (entry.get('start') is not None
                    and entry.get('end') is not None
                    and entry.get('value') is not None
                    and entry['start'] <= target_time < entry['end']):
                LOGGER.debug("Spot price at %s: %.4f (slot %s-%s)", target_time, entry['value'], entry['start'], entry['end'])
                return entry['value']
        LOGGER.debug("No spot price found for %s", target_time)
        return None

    def get_spot_prices_in_range(self, time_from, time_to):
        """Get all spot prices for slots overlapping the given range."""
        return [
            entry['value'] for entry in self.get_nordpool_raw_prices()
            if entry.get('start') is not None
            and entry.get('value') is not None
            and entry['start'] >= time_from
            and entry['start'] < time_to
        ]

    def get_consumer_price(self, spot):
        """Get consumer price from a spot price: (spot + fees) × VAT."""
        if spot is None:
            return None
        return (spot + TIBBER_FEE + GRID_FEE) * VAT_MULTIPLIER

    def get_solar_forecast_kwh(self, target_hour):
        """Get total solar energy forecast (kWh) for a specific hour.

        Sums forecasts from all forecast_solar config entries (east + west roof).
        """
        if not self.hass:
            return 0.0
        total_wh = 0
        entries_found = 0
        for entry in self.hass.config_entries.async_entries("forecast_solar"):
            if not hasattr(entry, 'runtime_data') or not entry.runtime_data:
                continue
            estimate = entry.runtime_data.data
            if not estimate or not estimate.wh_period:
                continue
            entries_found += 1
            for ts, wh in estimate.wh_period.items():
                ts_local = dt.as_local(ts) if ts.tzinfo else ts
                if ts_local.replace(minute=0, second=0, microsecond=0) == target_hour:
                    LOGGER.debug("Solar forecast entry: %s -> %d Wh", target_hour, wh)
                    total_wh += wh
                    break
        result = total_wh / 1000.0
        LOGGER.debug("Solar forecast total at %s: %.2f kWh (%d entries)", target_hour, result, entries_found)
        return result

    def get_effective_price(self, spot, target_hour):
        """Calculate effective heating cost considering solar production.

        Without solar: consumer price (spot + fee + VAT).
        With solar covering the load: opportunity cost (spot + 0.09 SEK/kWh).
        Partial solar: weighted average of the two.
        target_hour is rounded to the hour for solar forecast lookup.
        """
        consumer = self.get_consumer_price(spot)
        if consumer is None:
            return None
        hour = target_hour.replace(minute=0, second=0, microsecond=0)
        solar_kwh = self.get_solar_forecast_kwh(hour)
        if solar_kwh <= 0:
            LOGGER.debug("Effective price at %s: %.4f (no solar)", target_hour, consumer)
            return consumer
        sell_price = spot + SOLAR_SELL_ADDER
        solar_fraction = min(solar_kwh / HEATING_LOAD_KW, 1.0)
        effective = solar_fraction * sell_price + (1.0 - solar_fraction) * consumer
        LOGGER.debug("Effective price at %s: %.4f (solar=%.1f%%, consumer=%.4f, sell=%.4f)", target_hour, effective, solar_fraction * 100, consumer, sell_price)
        return effective

    def get_effective_prices_in_range(self, time_from, time_to):
        """Get effective prices for all slots in a time range."""
        prices = []
        for entry in self.get_nordpool_raw_prices():
            start = entry.get('start')
            value = entry.get('value')
            if start is None or value is None:
                continue
            if start >= time_from and start < time_to:
                eff = self.get_effective_price(value, start)
                if eff is not None:
                    prices.append(eff)
        return prices

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self.data()

    def data(self):
        res = {}
        now = dt.now()
        res['now'] = now
        # Next slot boundary: start of the slot after the current one
        res['coming_start'] = now.replace(second=0, microsecond=0)
        # Find the end of the current slot to know where "coming" starts
        for entry in self.get_nordpool_raw_prices():
            if (entry.get('start') is not None
                    and entry.get('end') is not None
                    and entry['start'] <= now < entry['end']):
                res['coming_start'] = entry['end']
                break
        res['coming_end'] = now + datetime.timedelta(hours=self._horizon)

        spot_now = self.get_spot_price(now)
        res['spot_price_now'] = spot_now
        res['consumer_price_now'] = self.get_consumer_price(spot_now)
        hour_now = now.replace(minute=0, second=0, microsecond=0)
        res['solar_now_kwh'] = self.get_solar_forecast_kwh(hour_now)

        res['price_now'] = self.get_effective_price(spot_now, now) if spot_now is not None else None
        coming_prices = self.get_effective_prices_in_range(res['coming_start'], res['coming_end'])
        res['price_coming'] = sum(coming_prices) / len(coming_prices) if coming_prices else None
        res['coming_slots'] = len(coming_prices)

        all_prices = ([res['price_now']] if res['price_now'] is not None else []) + coming_prices
        res['average_price'] = sum(all_prices) / len(all_prices) if all_prices else None

        LOGGER.debug(
            "Data: now=%s, coming=%s->%s, spot=%.4f, price_now=%.4f, "
            "price_coming=%.4f (%d slots), solar=%.2f kWh",
            now.isoformat(), res['coming_start'].isoformat(), res['coming_end'].isoformat(),
            spot_now or 0, res['price_now'] or 0,
            res['price_coming'] or 0, len(coming_prices), res['solar_now_kwh'],
        )

        if res['price_now'] is None or res['price_coming'] is None or res['average_price'] is None:
            LOGGER.debug("Data incomplete - returning None (price_now=%s, price_coming=%s, avg=%s)", res['price_now'], res['price_coming'], res['average_price'])
            return None
        if res['average_price'] == 0:
            return None

        res['delta'] = res['price_coming'] - res['price_now']
        res['delta_percent'] = 100.0 * res['delta'] / res['average_price']
        LOGGER.debug("Result: delta=%.4f, delta_percent=%.1f%%", res['delta'], res['delta_percent'])
        return res

    @property
    def state(self):
        """Return the state of the device."""
        d = self.data()
        if d is None:
            return None

        LOGGER.info(f"Price now: {d['price_now']}, Price coming: {d['price_coming']}, Average price: {d['average_price']}, Delta: {d['delta']}, PricePercent: {d['delta_percent']}")

        if d['delta_percent'] > self._percent:
            return "BOOST"
        if d['delta_percent'] < -self._percent:
            return "SAVE"
        return "NORMAL"


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup component."""
    LOGGER.info("jimmy async_setup_platform")
    async_add_entities([HeatingStrategy()])

