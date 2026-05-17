"""Jimmy custom heating strategy sensor."""
import logging
import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt

from .config_flow import (
    CONF_NAME,
    CONF_NORDPOOL_ENTITY,
    CONF_SOLAR_FORECAST_DOMAIN,
    CONF_TIBBER_FEE,
    CONF_GRID_FEE,
    CONF_VAT_MULTIPLIER,
    CONF_SOLAR_SELL_ADDER,
    CONF_HEATING_LOAD_KW,
    CONF_BASE_LOAD_KW,
    CONF_LOOK_AHEAD_HOURS,
    CONF_THRESHOLD_PERCENT,
    CONF_MIN_DELTA,
)

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor from a config entry."""
    LOGGER.info("jimmy_custom sensor async_setup_entry: %s", entry.title)
    LOGGER.debug(
        "Config: nordpool=%s, solar_domain=%s, tibber_fee=%.2f, grid_fee=%.2f, "
        "vat=%.2f, sell_adder=%.2f, heating=%.1f kW, base_load=%.1f kW, "
        "horizon=%dh, threshold=%.0f%%, min_delta=%.2f SEK/kWh",
        entry.data.get(CONF_NORDPOOL_ENTITY),
        entry.data.get(CONF_SOLAR_FORECAST_DOMAIN),
        entry.data.get(CONF_TIBBER_FEE, 0),
        entry.data.get(CONF_GRID_FEE, 0),
        entry.data.get(CONF_VAT_MULTIPLIER, 0),
        entry.data.get(CONF_SOLAR_SELL_ADDER, 0),
        entry.data.get(CONF_HEATING_LOAD_KW, 0),
        entry.data.get(CONF_BASE_LOAD_KW, 0),
        entry.data.get(CONF_LOOK_AHEAD_HOURS, 0),
        entry.data.get(CONF_THRESHOLD_PERCENT, 0),
        entry.data.get(CONF_MIN_DELTA, 0),
    )
    async_add_entities([HeatingStrategy(entry)])


class HeatingStrategy(Entity):
    def __init__(self, entry: ConfigEntry):
        self._entry = entry
        self._attr_has_entity_name = True

    @property
    def _conf(self):
        return self._entry.data

    @property
    def name(self):
        return self._conf[CONF_NAME]

    @property
    def available(self):
        return True

    @property
    def icon(self):
        return "mdi:thermometer"

    @property
    def unique_id(self):
        return f"heating_strategy_{self._entry.entry_id}"

    def get_nordpool_raw_prices(self):
        """Get raw today+tomorrow price entries from Nordpool sensor."""
        if not self.hass:
            return []
        state = self.hass.states.get(self._conf[CONF_NORDPOOL_ENTITY])
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
        c = self._conf
        return (spot + c[CONF_TIBBER_FEE] + c[CONF_GRID_FEE]) * c[CONF_VAT_MULTIPLIER]

    def get_solar_forecast_kwh(self, target_hour):
        """Get total solar energy forecast (kWh) for a specific hour."""
        if not self.hass:
            return 0.0
        total_wh = 0
        entries_found = 0
        domain = self._conf[CONF_SOLAR_FORECAST_DOMAIN]
        for entry in self.hass.config_entries.async_entries(domain):
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
        """Calculate effective heating cost considering solar production."""
        consumer = self.get_consumer_price(spot)
        if consumer is None:
            return None
        hour = target_hour.replace(minute=0, second=0, microsecond=0)
        solar_kwh = self.get_solar_forecast_kwh(hour)
        if solar_kwh <= 0:
            LOGGER.debug("Effective price at %s: %.4f (no solar)", target_hour, consumer)
            return consumer
        c = self._conf
        sell_price = spot + c[CONF_SOLAR_SELL_ADDER]
        available_solar = max(solar_kwh - c[CONF_BASE_LOAD_KW], 0.0)
        solar_fraction = min(available_solar / c[CONF_HEATING_LOAD_KW], 1.0)
        if solar_fraction <= 0:
            LOGGER.debug("Effective price at %s: %.4f (solar %.2f kWh below base load %.1f kW)", target_hour, consumer, solar_kwh, c[CONF_BASE_LOAD_KW])
            return consumer
        effective = solar_fraction * sell_price + (1.0 - solar_fraction) * consumer
        LOGGER.debug("Effective price at %s: %.4f (solar=%.1f%%, avail=%.2f kWh, consumer=%.4f, sell=%.4f)", target_hour, effective, solar_fraction * 100, available_solar, consumer, sell_price)
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
        return self.data()

    def data(self):
        res = {}
        now = dt.now()
        res['now'] = now
        res['coming_start'] = now.replace(second=0, microsecond=0)
        for entry in self.get_nordpool_raw_prices():
            if (entry.get('start') is not None
                    and entry.get('end') is not None
                    and entry['start'] <= now < entry['end']):
                res['coming_start'] = entry['end']
                break
        horizon = self._conf[CONF_LOOK_AHEAD_HOURS]
        res['coming_end'] = now + datetime.timedelta(hours=horizon)

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
        d = self.data()
        if d is None:
            return None

        LOGGER.info(f"Price now: {d['price_now']}, Price coming: {d['price_coming']}, Average price: {d['average_price']}, Delta: {d['delta']}, PricePercent: {d['delta_percent']}")

        percent = self._conf[CONF_THRESHOLD_PERCENT]
        min_delta = self._conf[CONF_MIN_DELTA]
        abs_delta = abs(d['delta'])
        if d['delta_percent'] > percent and abs_delta >= min_delta:
            return "BOOST"
        if d['delta_percent'] < -percent and abs_delta >= min_delta:
            return "SAVE"
        return "NORMAL"

