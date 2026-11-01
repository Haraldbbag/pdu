"""Constants for the Intellinet IP PDU integration."""

DOMAIN = "intellinet_pdu"

OUTLET_COUNT = 8

CONF_PREFIX = "prefix"
CONF_FIRST_OUTLET = "first_outlet"
CONF_FIRMWARE = "firmware"
CONF_MAC = "mac"

# Factory login of the PDUs (not a secret, all strips use it).
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 2
REQUEST_TIMEOUT = 5

# The PDU switches with its own ON/OFF delay (0-7 s per outlet as configured).
# For this long a switch shows the requested state even if status.xml still
# reports the old one.
PENDING_SECONDS = 12

SERVICE_SET_OUTLETS = "set_outlets"


def outlet_name_key(index: int) -> str:
    """Options key for the name of outlet index 0..7."""
    return f"name_{index + 1}"
