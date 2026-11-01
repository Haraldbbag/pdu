"""Small HTTP client for the Intellinet "IP PDU" web interface.

The PDU has no official API. Two pages are used:
- GET /status.xml (no password): current, temperature, humidity, outlet states
- GET /control_outlet.htm?outletN=1&op=X (Basic auth): op 0 = on, 1 = off
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
import time

import aiohttp

from .const import OUTLET_COUNT, REQUEST_TIMEOUT

_TAG = re.compile(r"<(\w+)>([^<]*)</\1>")
_MAC = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")
# The labels contain double spaces ("Firmware  version").
_FIRMWARE = re.compile(r"Firmware\s+version.*?(\d+\.\d+(?:\.\d+)?)", re.S | re.I)
_SYSTEM_NAME = re.compile(r"System\s+name.*?value=\"([^\"]*)\"", re.S | re.I)
_INPUT = re.compile(r"<input\b[^>]*>", re.I)
_ATTR_NAME = re.compile(r"\bname\s*=\s*[\"']?([\w-]+)", re.I)
_ATTR_VALUE = re.compile(r"\bvalue\s*=\s*[\"']?([^\"' >]*)", re.I)

# Sent within this time, switch commands for one PDU go out as one request.
BATCH_WINDOW = 0.4
# Extra wait after the longest delay before the next control request.
BUSY_MARGIN = 1.0
DEFAULT_DELAY = 7


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


def parse_delays(text: str) -> tuple[list[int], list[int]]:
    """Parse ON/OFF delays (ondlyN / ofdlyN inputs) from config_PDU.htm."""
    values: dict[str, str] = {}
    for tag in _INPUT.findall(text):
        name = _ATTR_NAME.search(tag)
        value = _ATTR_VALUE.search(tag)
        if name and value:
            values[name.group(1)] = value.group(1)

    def read(prefix: str) -> list[int]:
        result = []
        for index in range(OUTLET_COUNT):
            try:
                result.append(max(0, int(values[f"{prefix}{index}"])))
            except (KeyError, ValueError):
                result.append(DEFAULT_DELAY)
        return result

    if not any(key.startswith("ondly") for key in values):
        raise PduConnectionError("config_PDU.htm has no delay fields")
    return read("ondly"), read("ofdly")


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
        self._control_lock = asyncio.Lock()
        self._busy_until = 0.0
        self._pending: dict[int, bool] = {}
        self._waiters: list[asyncio.Future[None]] = []
        self._flush_task: asyncio.Task[None] | None = None
        # Until read from the PDU, assume the longest usual delay.
        self.on_delays = [DEFAULT_DELAY] * OUTLET_COUNT
        self.off_delays = [DEFAULT_DELAY] * OUTLET_COUNT

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

    async def get_delays(self) -> None:
        """Read the ON/OFF delay of each outlet from config_PDU.htm."""
        on, off = parse_delays(await self._get("config_PDU.htm"))
        self.on_delays, self.off_delays = on, off

    async def set_outlets(self, indexes: list[int], turn_on: bool) -> None:
        """Switch outlets (index 0..7) in one request.

        The PDU switches them one after another with its own delays. A second
        request while it is still working drops the waiting outlets, so the
        next request waits until the previous one is done.
        """
        wanted = sorted(set(indexes))
        if not wanted or any(i < 0 or i >= OUTLET_COUNT for i in wanted):
            raise ValueError(f"invalid outlet indexes: {indexes}")
        params = {f"outlet{i}": "1" for i in wanted}
        params["op"] = "0" if turn_on else "1"
        async with self._control_lock:
            wait = self._busy_until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await self._get("control_outlet.htm", params)
            delays = self.on_delays if turn_on else self.off_delays
            self._busy_until = (
                time.monotonic() + max(delays[i] for i in wanted) + BUSY_MARGIN
            )

    async def switch(self, index: int, turn_on: bool) -> None:
        """Switch one outlet; calls arriving close together are sent as one request.

        A scene switches each outlet separately. Collecting them keeps the
        PDU's own staggering and avoids dropped outlets.
        """
        loop = asyncio.get_running_loop()
        self._pending[index] = turn_on
        waiter: asyncio.Future[None] = loop.create_future()
        self._waiters.append(waiter)
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = loop.create_task(self._flush())
        await waiter

    async def _flush(self) -> None:
        await asyncio.sleep(BATCH_WINDOW)
        while self._pending:
            pending, self._pending = self._pending, {}
            waiters, self._waiters = self._waiters, []
            try:
                for turn_on in (True, False):
                    group = [i for i, value in pending.items() if value is turn_on]
                    if group:
                        await self.set_outlets(group, turn_on)
            except Exception as err:  # noqa: BLE001 - handed to the callers
                for waiter in waiters:
                    if not waiter.done():
                        waiter.set_exception(err)
            else:
                for waiter in waiters:
                    if not waiter.done():
                        waiter.set_result(None)
