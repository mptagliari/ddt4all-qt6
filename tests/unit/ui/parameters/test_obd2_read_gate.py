from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.ui.parameters.param_widget import ParamWidget

from tests.unit.core.elm.fake_elm327 import TRUCK, make_adapter


def sent(port):
    """Commands the adapter received, without spaces."""
    return [c.replace(" ", "") for c in port.commands]


def make_page(protocol):
    page = SimpleNamespace(ecurequestsparser=SimpleNamespace(ecu_protocol=protocol), logview=Mock())
    page.isSafeCommand = lambda command: ParamWidget.isSafeCommand(page, command)
    return page


@pytest.fixture(autouse=True)
def online(monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", False)
    monkeypatch.setattr(options, "promode", False)
    adapter, port = make_adapter(TRUCK)
    monkeypatch.setattr(options, "elm", adapter)
    return port


@pytest.mark.parametrize("command", ["010C", "01 0C", "03", "07", "0A", "0902", "02 0C 00", "0600"])
def test_vpw_ecu_may_use_the_read_only_obd2_services(command):
    assert make_page("J1850VPW").isSafeCommand(command)


@pytest.mark.parametrize("command", ["04", "05", "08", "0801", "2E0101", "3101", "11 01", "2F 11 01"])
def test_services_that_change_the_vehicle_stay_blocked(command):
    assert not make_page("J1850VPW").isSafeCommand(command)


@pytest.mark.parametrize("protocol", ["CAN", "KWP2000", "ISO8"])
def test_other_protocols_keep_the_original_list(protocol):
    page = make_page(protocol)
    assert not page.isSafeCommand("010C")          # the OBD-II list is for J1850 VPW only
    assert page.isSafeCommand("22F190")            # the DDT read services still pass


def test_live_data_request_reaches_the_bus_and_comes_back(online):
    response = ParamWidget.sendElm(make_page("J1850VPW"), "01 0C", True)

    assert response.split() == ["41", "0C", "1A", "F8"]
    assert "010C" in sent(online)


def test_clear_codes_never_reaches_the_bus(online):
    response = ParamWidget.sendElm(make_page("J1850VPW"), "04", True)

    assert response == "BLOCKED"
    assert "04" not in sent(online)


def test_expert_mode_still_decides_for_everything_else(monkeypatch, online):
    monkeypatch.setattr(options, "promode", True)

    ParamWidget.sendElm(make_page("J1850VPW"), "04", True)

    assert "04" in sent(online)             # expert mode is the user's explicit choice, as before
