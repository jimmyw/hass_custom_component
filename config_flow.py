"""Config flow for Jimmy Custom Heating Strategy."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

DOMAIN = "jimmy_custom"

CONF_NAME = "name"
CONF_NORDPOOL_ENTITY = "nordpool_entity"
CONF_SOLAR_FORECAST_DOMAIN = "solar_forecast_domain"
CONF_TIBBER_FEE = "tibber_fee"
CONF_GRID_FEE = "grid_fee"
CONF_VAT_MULTIPLIER = "vat_multiplier"
CONF_SOLAR_SELL_ADDER = "solar_sell_adder"
CONF_HEATING_LOAD_KW = "heating_load_kw"
CONF_BASE_LOAD_KW = "base_load_kw"
CONF_LOOK_AHEAD_HOURS = "look_ahead_hours"
CONF_THRESHOLD_PERCENT = "threshold_percent"
CONF_MIN_DELTA = "min_delta"

DEFAULTS = {
    CONF_NORDPOOL_ENTITY: "sensor.nordpool_kwh_se3_sek_3_10_0",
    CONF_SOLAR_FORECAST_DOMAIN: "forecast_solar",
    CONF_TIBBER_FEE: 0.06,
    CONF_GRID_FEE: 0.52,
    CONF_VAT_MULTIPLIER: 1.25,
    CONF_SOLAR_SELL_ADDER: 0.09,
    CONF_HEATING_LOAD_KW: 3.5,
    CONF_BASE_LOAD_KW: 1.0,
    CONF_LOOK_AHEAD_HOURS: 3,
    CONF_THRESHOLD_PERCENT: 20.0,
    CONF_MIN_DELTA: 0.30,
}


class JimmyCustomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jimmy Custom."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return JimmyCustomOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        schema = vol.Schema({
            vol.Required(CONF_NAME, default="Heating strategy"): str,
            vol.Required(CONF_NORDPOOL_ENTITY, default=DEFAULTS[CONF_NORDPOOL_ENTITY]): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            vol.Required(CONF_SOLAR_FORECAST_DOMAIN, default=DEFAULTS[CONF_SOLAR_FORECAST_DOMAIN]): str,
            vol.Required(CONF_TIBBER_FEE, default=DEFAULTS[CONF_TIBBER_FEE]): vol.Coerce(float),
            vol.Required(CONF_GRID_FEE, default=DEFAULTS[CONF_GRID_FEE]): vol.Coerce(float),
            vol.Required(CONF_VAT_MULTIPLIER, default=DEFAULTS[CONF_VAT_MULTIPLIER]): vol.Coerce(float),
            vol.Required(CONF_SOLAR_SELL_ADDER, default=DEFAULTS[CONF_SOLAR_SELL_ADDER]): vol.Coerce(float),
            vol.Required(CONF_HEATING_LOAD_KW, default=DEFAULTS[CONF_HEATING_LOAD_KW]): vol.Coerce(float),
            vol.Required(CONF_BASE_LOAD_KW, default=DEFAULTS[CONF_BASE_LOAD_KW]): vol.Coerce(float),
            vol.Required(CONF_LOOK_AHEAD_HOURS, default=DEFAULTS[CONF_LOOK_AHEAD_HOURS]): vol.Coerce(int),
            vol.Required(CONF_THRESHOLD_PERCENT, default=DEFAULTS[CONF_THRESHOLD_PERCENT]): vol.Coerce(float),
            vol.Required(CONF_MIN_DELTA, default=DEFAULTS[CONF_MIN_DELTA]): vol.Coerce(float),
        })

        return self.async_show_form(step_id="user", data_schema=schema)


class JimmyCustomOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                title=user_input[CONF_NAME],
                data={**self._config_entry.data, **user_input},
            )
            return self.async_create_entry(title="", data={})

        current = self._config_entry.data
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=current.get(CONF_NAME, "Heating strategy")): str,
            vol.Required(CONF_NORDPOOL_ENTITY, default=current.get(CONF_NORDPOOL_ENTITY, DEFAULTS[CONF_NORDPOOL_ENTITY])): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
            vol.Required(CONF_SOLAR_FORECAST_DOMAIN, default=current.get(CONF_SOLAR_FORECAST_DOMAIN, DEFAULTS[CONF_SOLAR_FORECAST_DOMAIN])): str,
            vol.Required(CONF_TIBBER_FEE, default=current.get(CONF_TIBBER_FEE, DEFAULTS[CONF_TIBBER_FEE])): vol.Coerce(float),
            vol.Required(CONF_GRID_FEE, default=current.get(CONF_GRID_FEE, DEFAULTS[CONF_GRID_FEE])): vol.Coerce(float),
            vol.Required(CONF_VAT_MULTIPLIER, default=current.get(CONF_VAT_MULTIPLIER, DEFAULTS[CONF_VAT_MULTIPLIER])): vol.Coerce(float),
            vol.Required(CONF_SOLAR_SELL_ADDER, default=current.get(CONF_SOLAR_SELL_ADDER, DEFAULTS[CONF_SOLAR_SELL_ADDER])): vol.Coerce(float),
            vol.Required(CONF_HEATING_LOAD_KW, default=current.get(CONF_HEATING_LOAD_KW, DEFAULTS[CONF_HEATING_LOAD_KW])): vol.Coerce(float),
            vol.Required(CONF_BASE_LOAD_KW, default=current.get(CONF_BASE_LOAD_KW, DEFAULTS[CONF_BASE_LOAD_KW])): vol.Coerce(float),
            vol.Required(CONF_LOOK_AHEAD_HOURS, default=current.get(CONF_LOOK_AHEAD_HOURS, DEFAULTS[CONF_LOOK_AHEAD_HOURS])): vol.Coerce(int),
            vol.Required(CONF_THRESHOLD_PERCENT, default=current.get(CONF_THRESHOLD_PERCENT, DEFAULTS[CONF_THRESHOLD_PERCENT])): vol.Coerce(float),
            vol.Required(CONF_MIN_DELTA, default=current.get(CONF_MIN_DELTA, DEFAULTS[CONF_MIN_DELTA])): vol.Coerce(float),
        })

        return self.async_show_form(step_id="init", data_schema=schema)
