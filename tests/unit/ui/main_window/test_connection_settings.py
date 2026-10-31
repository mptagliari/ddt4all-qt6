import pytest

from ddt4all import options
from ddt4all.ui.main_window import connection_settings as cs

_ = options.translator('ddt4all')


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setattr(options, "configuration", {})
    saved = []
    monkeypatch.setattr(options, "save_config", lambda: saved.append(dict(options.configuration)))
    return saved


def test_defaults_when_nothing_was_saved():
    settings = cs.load()

    assert (settings.adapter, settings.port, settings.speed, settings.can2) == ("STD_USB", "", 38400, False)
    assert settings.wifi == cs.DEFAULT_WIFI and settings.uart_speed == ""


def test_what_is_saved_is_what_is_loaded_and_written_to_disk(isolated_config):
    original = cs.ConnectionSettings(adapter="OBDLINK", port="/dev/ttyUSB0", port_name="OBDLink SX", speed=115200,
                                     wifi="10.0.0.5:35000", can2=True, uart_speed="2000000")

    cs.save(original)

    assert isolated_config                                   # save_config() was called
    assert cs.load() == original


def test_damaged_values_fall_back_to_defaults():
    options.configuration.update({"conn_adapter": "NOT_AN_ADAPTER", "conn_speed": "fast", "conn_port": None})

    settings = cs.load()

    assert (settings.adapter, settings.speed, settings.port) == ("STD_USB", 38400, "")


def test_serial_adapters_open_the_port_and_wifi_opens_the_address():
    assert cs.ConnectionSettings(adapter="STD_USB", port="/dev/ttyUSB0").target == "/dev/ttyUSB0"
    assert cs.ConnectionSettings(adapter="STD_WIFI", port="/dev/ttyUSB0", wifi=" 10.0.0.5:35000 ").target == "10.0.0.5:35000"


def test_connecting_needs_a_port_or_a_wifi_address():
    assert cs.ConnectionSettings(adapter="STD_USB").problem() == _("No port chosen")
    assert cs.ConnectionSettings(adapter="STD_USB", port="/dev/ttyUSB0").problem() == ""
    assert cs.ConnectionSettings(adapter="STD_WIFI", wifi=" ").problem() == _("Enter the Wi-Fi adapter address")
    assert cs.ConnectionSettings(adapter="STD_WIFI").problem() == ""            # the default address is usable


def test_uart_speed_is_passed_as_no_when_unset():
    assert cs.ConnectionSettings().raise_port_speed == "No"
    assert cs.ConnectionSettings(uart_speed="57600").raise_port_speed == "57600"
