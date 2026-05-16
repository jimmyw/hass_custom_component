"""Jimmy custom"""
import logging

from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.helpers import discovery

DOMAIN = "jimmy_custom"
LOGGER = logging.getLogger(__name__)

def setup(hass, config):
    """Setup component."""

    #hass.states.get("jimmy_custom.hello", "World")
    # Test log
    LOGGER.info("Hello from jimmy async")
    def ha_started(_):
        discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)

    hass.bus.listen_once(EVENT_HOMEASSISTANT_START, ha_started)
    # hass.config_entries.async_forward_entry_setup
    return True

