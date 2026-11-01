"""Tests with a mocked PDU (no real device is switched)."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.intellinet_pdu.api import parse_delays, parse_status
from custom_components.intellinet_pdu.const import DOMAIN

HOST = "10.0.0.51"
STATUS = """<response>
<cur0>2.1</cur0>
<stat0>normal</stat0>
<curBan>2.1</curBan>
<tempBan>20</tempBan>
<humBan>41</humBan>
<statBan>normal</statBan>
<outletStat0>on</outletStat0>
<outletStat1>off</outletStat1>
<outletStat2>on</outletStat2>
<outletStat3>on</outletStat3>
<outletStat4>on</outletStat4>
<outletStat5>on</outletStat5>
<outletStat6>on</outletStat6>
<outletStat7>on</outletStat7>

<userVerifyRes>0</userVerifyRes>

</response>"""
INFO = """<table><tr><td><strong>Product  model</strong></td><td>IP PDU</td></tr>
<tr><td><strong>Firmware  version</strong></td><td>1.0.7</td></tr></table>
<form><tr><td><strong>MAC  address</strong></td><td><input value="00:50:56:C2:3C:45"></td></tr>
<tr><td><strong>System  name</strong></td><td><input name="sysname" value="PDU_M1-1"></td></tr></form>"""


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


CONFIG = "".join(
    f'<input type="text" name="otlt{i}" value="outlet{i + 1}">'
    f'<input name="ondly{i}" type="text" value="{i}">'
    f'<input value="{i}" name="ofdly{i}">'
    for i in range(8)
)


def mock_pdu(aioclient_mock):
    aioclient_mock.get(f"http://{HOST}/status.xml", text=STATUS)
    aioclient_mock.get(f"http://{HOST}/config_PDU.htm", text=CONFIG)
    aioclient_mock.get(f"http://{HOST}/info_system.htm", text=INFO)
    aioclient_mock.get(f"http://{HOST}/control_outlet.htm", text="ok")


def control_calls(aioclient_mock):
    return [
        dict(url.query)
        for method, url, _data, _headers in aioclient_mock.mock_calls
        if url.path == "/control_outlet.htm"
    ]


async def setup_entry(hass: HomeAssistant, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=HOST,
        title="PDU M1-1",
        data={
            CONF_HOST: HOST,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "pw",
            "prefix": "m1",
            "first_outlet": 9,
            "mac": "00:50:56:C2:3C:45",
            "firmware": "1.0.7",
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def test_parse_status():
    status = parse_status(STATUS)
    assert status.current == 2.1
    assert status.temperature == 20
    assert status.humidity == 41
    assert status.status == "normal"
    assert status.outlets == [True, False, True, True, True, True, True, True]


def test_parse_delays():
    on, off = parse_delays(CONFIG)
    assert on == [0, 1, 2, 3, 4, 5, 6, 7]
    assert off == [0, 1, 2, 3, 4, 5, 6, 7]


async def test_scene_like_calls_become_one_request(hass: HomeAssistant, aioclient_mock) -> None:
    """Several switch calls at once (as a scene does) go out as one request;
    outlets already in the wanted state are left out."""
    mock_pdu(aioclient_mock)
    await setup_entry(hass)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": ["switch.pdu_m1_09", "switch.pdu_m1_10", "switch.pdu_m1_16"]},
        blocking=True,
    )
    # 09 and 16 are already on, only 10 (index 1) is sent
    assert control_calls(aioclient_mock) == [{"outlet1": "1", "op": "0"}]
    aioclient_mock.mock_calls.clear()
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": ["switch.pdu_m1_11", "switch.pdu_m1_15", "switch.pdu_m1_16"]},
        blocking=True,
    )
    assert control_calls(aioclient_mock) == [
        {"outlet2": "1", "outlet6": "1", "outlet7": "1", "op": "1"}
    ]


async def test_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: HOST,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "pw",
            "name": "",
            "prefix": "M1",
            "first_outlet": 1,
        },
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "PDU_M1-1"
    assert result["data"]["prefix"] == "m1"
    assert result["data"]["firmware"] == "1.0.7"
    assert result["data"]["mac"] == "00:50:56:C2:3C:45"
    await hass.async_block_till_done()
    assert hass.states.get("switch.pdu_m1_01").state == "on"
    assert hass.states.get("switch.pdu_m1_02").state == "off"


async def test_config_flow_wrong_password(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(f"http://{HOST}/status.xml", text=STATUS)
    aioclient_mock.get(f"http://{HOST}/info_system.htm", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: HOST, CONF_USERNAME: "admin", CONF_PASSWORD: "x", "first_outlet": 1},
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    await setup_entry(hass)
    # second strip of a cinema: outlets 9..16
    assert hass.states.get("switch.pdu_m1_09").state == "on"
    assert hass.states.get("switch.pdu_m1_10").state == "off"
    assert hass.states.get("switch.pdu_m1_16").state == "on"
    assert hass.states.get("switch.pdu_m1_09").attributes["friendly_name"] == "PDU M1-1 Out 9"
    assert hass.states.get("sensor.pdu_m1_1_strom") or hass.states.get("sensor.pdu_m1_1_current")
    states = {s.entity_id: s.state for s in hass.states.async_all("sensor")}
    assert "2.1" in states.values()
    assert hass.states.async_all("binary_sensor")[0].state == "on"


async def test_switch_sends_one_request(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    await setup_entry(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.pdu_m1_11"}, blocking=True
    )
    assert control_calls(aioclient_mock) == [{"outlet2": "1", "op": "1"}]
    # PDU still reports "on" (own delay) -> switch shows the wanted state
    assert hass.states.get("switch.pdu_m1_11").state == "off"


async def test_set_outlets_action(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    await setup_entry(hass)
    await hass.services.async_call(
        DOMAIN,
        "set_outlets",
        {"entity_id": ["switch.pdu_m1_09", "switch.pdu_m1_12"], "state": "on"},
        blocking=True,
    )
    assert control_calls(aioclient_mock) == [{"outlet0": "1", "outlet3": "1", "op": "0"}]


async def test_outlet_names_keep_entity_id(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 5, "name_1": "Projektor"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    state = hass.states.get("switch.pdu_m1_09")
    assert state.attributes["friendly_name"] == "PDU M1-1 Projektor"
    assert hass.states.get("switch.pdu_m1_10").attributes["friendly_name"] == "PDU M1-1 Out 10"
    assert er.async_get(hass).async_get("switch.pdu_m1_09") is not None


async def test_unreachable(hass: HomeAssistant, aioclient_mock) -> None:
    mock_pdu(aioclient_mock)
    entry = await setup_entry(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"http://{HOST}/status.xml", exc=TimeoutError())
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("switch.pdu_m1_09").state == "unavailable"
    assert hass.states.async_all("binary_sensor")[0].state == "off"
