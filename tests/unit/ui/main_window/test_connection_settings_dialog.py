import pytest

from ddt4all import options
from ddt4all.qt import core, widgets
from ddt4all.ui.main_window import main_window_options as mwo

_ = options.translator('ddt4all')

PORTS = [("/dev/ttyUSB0", "ELM327 USB", "USB VID:PID=067B:2303", "online"),
         ("/dev/ttyUSB1", "OBDLink SX", "USB VID:PID=0403:6015", "online"),
         ("/dev/ttyS0", "n/a", "", "offline")]


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr(options, "configuration", {})
    writes = []
    monkeypatch.setattr(options, "save_config", lambda: writes.append(dict(options.configuration)))
    return writes


@pytest.fixture
def make(monkeypatch, qapp, config):
    """Builds the dialog without scanning real ports."""
    monkeypatch.setattr(mwo.MainWindowOptions, "rescan_ports", lambda self: None)
    monkeypatch.setattr(mwo.elm, "detect_usb_device", lambda: None)
    built = []

    def build(**kwargs):
        dialog = mwo.MainWindowOptions(qapp, **kwargs)
        built.append(dialog)
        return dialog

    yield build
    for dialog in built:
        dialog.timer.stop()
        dialog.close()
        dialog.deleteLater()
    # Destroy the dialogs now: left alive, PySide6 crashes while the interpreter shuts down
    core.QCoreApplication.sendPostedEvents(None, core.QEvent.DeferredDelete)
    qapp.processEvents()


def settle(app):
    for _ in range(3):
        app.processEvents()


def test_the_screen_has_no_connect_or_edition_buttons_and_no_safety_checkbox(make):
    dialog = make()

    texts = {b.text() for b in dialog.findChildren(widgets.QPushButton)}
    assert _("Connected mode") not in texts and _("Edition mode") not in texts
    assert _("Close") in texts and _("ELM benchmark") in texts
    assert not hasattr(dialog, "safetycheck")


def test_saved_settings_are_put_back_when_the_screen_opens(make, config):
    options.configuration.update({"conn_adapter": "OBDLINK", "conn_speed": 115200, "conn_wifi": "10.0.0.5:35000",
                                  "conn_can2": True, "conn_uart_speed": "1000000"})

    dialog = make()

    assert dialog.adapter == "OBDLINK" and dialog.obdlinkbutton.isChecked() and not dialog.usbbutton.isChecked()
    assert dialog.speedcombo.currentText() == "115200"
    assert dialog.wifiinput.text() == "10.0.0.5:35000"
    assert dialog.safetyCAN2check.isChecked()
    assert dialog.obdlinkspeedcombo.currentText() == "1000000"
    assert config == []                                    # looking at the settings writes nothing


def test_changing_the_speed_is_saved_at_once(make, config, qapp):
    dialog = make()

    dialog.speedcombo.setCurrentIndex(dialog.speedcombo.findText("57600"))
    settle(qapp)

    assert options.configuration["conn_speed"] == 57600 and config


def test_choosing_an_adapter_is_saved(make, config, qapp):
    dialog = make()

    dialog.obdlinkbutton.click()
    settle(qapp)

    assert options.configuration["conn_adapter"] == "OBDLINK"


def test_wifi_address_can2_and_uart_speed_are_saved(make, qapp):
    dialog = make()
    dialog.obdlinkbutton.click()                           # offers the UART speeds
    settle(qapp)

    dialog.wifiinput.setText("10.1.1.1:35000")
    dialog.wifiinput.editingFinished.emit()
    dialog.safetyCAN2check.setChecked(True)
    dialog.obdlinkspeedcombo.setCurrentIndex(dialog.obdlinkspeedcombo.findText("500000"))
    settle(qapp)

    assert options.configuration["conn_wifi"] == "10.1.1.1:35000"
    assert options.configuration["conn_can2"] is True
    assert options.configuration["conn_uart_speed"] == "500000"


def test_the_port_the_user_picks_is_saved(make, qapp):
    dialog = make()
    dialog._on_ports_found(PORTS)

    second = next(dialog.listview.item(i) for i in range(dialog.listview.count()) if "ttyUSB1" in dialog.listview.item(i).text())
    dialog.listview.setCurrentItem(second)
    settle(qapp)

    assert options.configuration["conn_port"] == "/dev/ttyUSB1"
    assert options.configuration["conn_port_name"] == "OBDLink SX"


def test_the_saved_port_is_selected_again_when_it_shows_up(make, config):
    options.configuration["conn_port"] = "/dev/ttyUSB1"
    dialog = make()

    dialog._on_ports_found(PORTS)

    assert "ttyUSB1" in dialog.listview.currentItem().text()
    assert config == []                                    # selecting it for the user is not a change


def test_rescanning_the_ports_never_overwrites_the_saved_port(make, qapp):
    options.configuration["conn_port"] = "/dev/ttyUSB9"          # the adapter is unplugged right now
    dialog = make()

    dialog._on_ports_found(PORTS)                                # the list has another device: auto-selected
    settle(qapp)
    dialog._on_ports_found([PORTS[2]])                           # and then fewer
    settle(qapp)

    assert options.configuration["conn_port"] == "/dev/ttyUSB9"


def test_settings_are_locked_and_not_saved_while_connected(make, config, qapp):
    options.configuration["conn_adapter"] = "STD_USB"
    dialog = make(connected=True)

    assert not dialog.listview.isEnabled() and not dialog.speedcombo.isEnabled() and not dialog.obdlinkbutton.isEnabled()
    assert not dialog.timer.isActive()                           # no port probing while the adapter is open
    dialog.speedcombo.setCurrentIndex(3)
    settle(qapp)
    assert "conn_speed" not in options.configuration


def test_doip_fields_are_saved_without_closing_the_screen(make, config):
    dialog = make()

    dialog.doip_ipinput.setText("192.168.5.5")
    dialog.doip_ipinput.editingFinished.emit()
    dialog.doip_timeoutinput.setValue(7)

    assert options.configuration["doip_target_ip"] == "192.168.5.5"
    assert options.configuration["doip_timeout"] == 7
    assert dialog.isVisible() is False and dialog.result() == 0   # still open from the user's point of view
