"""Small HTTP client for the Intellinet "IP PDU" web interface.

The PDU has no official API. Two pages are used:
- GET /status.xml (no password): current, temperature, humidity, outlet states
- GET /control_outlet.htm?outletN=1&op=X (Basic auth): op 0 = on, 1 = off
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re

import aiohttp

from .const import OUTLET_COUNT, REQUEST_TIMEOUT

_TAG = re.compile(r"<(\w+)>([^<]*)</\1>")
_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
# The labels contain double spaces ("Firmware  version").
_FIRMWARE = re.compile(r"Firmware\s+version.*?(\d+\.\d+(?:\.\d+)?)", re.S | re.I)
_SYSTEM_NAME = re.compile(r"System\s+name.*?value=\"([^\"]*)\"", re.S | re.I)


class PduError(Exception):
    """Base error."""


class PduConnectionError(PduError):
    """PDU not reachable or unexpected answer."""


class PduAuthError(PduError):
    """Wrong user name or password."""


@dataclass(slots=True)
class PduStatus:
    """Parsed content of status.xml."""

    current: float | None
    temperature: float | None
    humidity: float | None
    status: str | None
    outlets: list[bool | None]


@dataclass(slots=True)
class PduDeviceInfo:
    """Data from info_system.htm."""

    mac: str | None
    firmware: str | None
    name: str | None


def _number(raw: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        try:
            return float(raw[key])
        except (KeyError, ValueError):
            continue
    return None


def parse_status(text: str) -> PduStatus:
    """Parse status.xml."""
    raw = {key: value.strip() for key, value in _TAG.findall(text)}
    if not any(key.startswith("outletStat") for key in raw):
        raise PduConnectionError("status.xml has no outlet states")
    outlets: list[bool | None] = []
    for index in range(OUTLET_COUNT):
        value = raw.get(f"outletStat{index}", "").lower()
        outlets.append(True if value == "on" else False if value == "off" else None)
    return PduStatus(
        current=_number(raw, "curBan", "cur0"),
        temperature=_number(raw, "tempBan"),
        humidity=_number(raw, "humBan"),
        status=raw.get("statBan") or raw.get("stat0") or None,
        outlets=outlets,
    )


def parse_device_info(text: str) -> PduDeviceInfo:
    """Parse info_system.htm (best effort)."""
    mac = _MAC.search(text)
    firmware = _FIRMWARE.search(text)
    name = _SYSTEM_NAME.search(text)
    return PduDeviceInfo(
        mac=mac.group(0).upper().replace("-", ":") if mac else None,
        firmware=firmware.group(1) if firmware else None,
        name=(name.group(1).strip() or None) if name else None,
    )


class PduClient:
    """Talks to one PDU. Requests are sent one after another (simple firmware)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
    ) -> None:
        self.host = host
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)
        self._lock = asyncio.Lock()

    async def _get(
        self, path: str, params: dict[str, str] | None = None, auth: bool = True
    ) -> str:
        url = f"http://{self.host}/{path}"
        async with self._lock:
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    async with self._session.get(
                        url, params=params, auth=self._auth if auth else None
                    ) as resp:
                        if resp.status == 401:
                            raise PduAuthError("wrong user name or password")
                        if resp.status != 200:
                            raise PduConnectionError(f"HTTP {resp.status} from {path}")
                        return await resp.text(errors="replace")
            except (aiohttp.ClientError, TimeoutError) as err:
                raise PduConnectionError(f"{self.host}: {err!r}") from err

    async def get_status(self) -> PduStatus:
        """Read status.xml (no password needed)."""
        return parse_status(await self._get("status.xml", auth=False))

    async def get_device_info(self) -> PduDeviceInfo:
        """Read info_system.htm (needs password, so it also checks the login)."""
        return parse_device_info(await self._get("info_system.htm"))

    async def set_outlets(self, indexes: list[int], turn_on: bool) -> None:
        """Switch outlets (index 0..7) in one request."""
        wanted = sorted(set(indexes))
        if not wanted or any(i < 0 or i >= OUTLET_COUNT for i in wanted):
            raise ValueError(f"invalid outlet indexes: {indexes}")
        params = {f"outlet{i}": "1" for i in wanted}
        params["op"] = "0" if turn_on else "1"
        await self._get("control_outlet.htm", params)
