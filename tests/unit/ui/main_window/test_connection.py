import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.qt import core, widgets
from ddt4all.ui.main_window import connection
from ddt4all.ui.main_window.connection_settings import ConnectionSettings

_ = options.translator('ddt4all')


class FakeElm:
    closed = False
    delay = 0.0
    thread = None

    def __init__(self, port, speed, adapter, maxspeed="No", cancel_event=None, progress=None):
        type(self).thread = threading.current_thread()
        self.args = (port, speed, adapter, maxspeed)
        if progress is not None:
            progress("Trying to open port %s @ %i" % (port, speed))
        if cancel_event is not None and type(self).delay:
            # like the real handshake: blocks, but notices a cancel between attempts
            cancel_event.wait(type(self).delay)
            if cancel_event.is_set():
                options.elm_failed = True

    def close(self):
        self.closed = True


USB = ConnectionSettings(adapter="STD_USB", port="/dev/ttyUSB0", port_name="USB-Serial", speed=38400)


@pytest.fixture
def env(monkeypatch, qapp):
    FakeElm.delay, FakeElm.thread = 0.0, None
    messages, settings_opened = [], []
    monkeypatch.setattr(connection, "confirm_risk", lambda: True)
    monkeypatch.setattr(connection.connection_settings, "load", lambda: USB)
    monkeypatch.setattr(connection, "_message", messages.append)
    monkeypatch.setattr(connection.elm, "ELM", FakeElm)
    monkeypatch.setattr(options, "simulation_mode", True)
    monkeypatch.setattr(options, "elm", None)
    monkeypatch.setattr(options, "elm_failed", False)
    monkeypatch.setattr(options, "promode", True)
    return SimpleNamespace(app=qapp, messages=messages, opened=settings_opened,
                           open_settings=lambda: settings_opened.append(True))


def test_connect_uses_the_saved_settings_without_showing_any_settings_screen(env, monkeypatch):
    monkeypatch.setattr(connection.connection_settings, "load", lambda: ConnectionSettings(
        adapter="OBDLINK", port="/dev/ttyUSB1", port_name="OBDLink", speed=115200, can2=True, uart_speed="2000000"))

    assert connection.connect_adapter(env.app, env.open_settings) is True

    assert options.simulation_mode is False
    assert options.elm.args == ("/dev/ttyUSB1", 115200, "OBDLINK", "2000000")
    assert (options.port, options.port_name, options.opt_can2) == ("/dev/ttyUSB1", "OBDLink", True)
    assert options.promode is False
    assert env.opened == []


def test_wifi_connects_to_the_address_not_to_the_serial_port(env, monkeypatch):
    monkeypatch.setattr(connection.connection_settings, "load", lambda: ConnectionSettings(
        adapter="STD_WIFI", port="/dev/ttyUSB0", wifi="10.0.0.5:35000"))

    assert connection.connect_adapter(env.app) is True

    assert options.elm.args[0] == "10.0.0.5:35000"


def test_declining_the_warning_connects_nothing(env, monkeypatch):
    monkeypatch.setattr(connection, "confirm_risk", lambda: False)

    assert connection.connect_adapter(env.app, env.open_settings) is False

    assert options.simulation_mode is True and options.elm is None
    assert FakeElm.thread is None                          # the adapter was never opened
    assert env.messages == [] and env.opened == []


def test_no_port_chosen_sends_the_user_to_the_settings(env, monkeypatch):
    monkeypatch.setattr(connection.connection_settings, "load", lambda: ConnectionSettings(adapter="STD_USB"))

    assert connection.connect_adapter(env.app, env.open_settings) is False

    assert options.simulation_mode is True and options.elm is None
    assert FakeElm.thread is None
    assert _("No port chosen") in env.messages[0]
    assert env.opened == [True]                            # the settings screen is opened for the user


def test_adapter_failure_stays_offline_and_tells_the_user(env, monkeypatch):
    class FailingElm(FakeElm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            options.elm_failed = True

    monkeypatch.setattr(connection.elm, "ELM", FailingElm)

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True and options.elm is None
    assert env.messages and "/dev/ttyUSB0" in env.messages[0]


def test_exception_while_opening_is_reported_not_raised(env, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("device busy")

    monkeypatch.setattr(connection.elm, "ELM", boom)

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True and options.elm is None
    assert env.messages


def test_handshake_runs_on_a_worker_thread(env):
    assert connection.connect_adapter(env.app) is True

    assert FakeElm.thread is not threading.main_thread()


def test_ui_keeps_running_while_the_adapter_is_slow(env):
    FakeElm.delay = 0.4
    ticks = []
    timer = core.QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda: ticks.append(time.time()))
    timer.start()

    start = time.time()
    assert connection.connect_adapter(env.app) is True            # nobody cancels: FakeElm waits its delay
    timer.stop()

    assert time.time() - start >= 0.35
    assert len(ticks) >= 5                                        # the event loop kept spinning


def test_cancel_stops_the_handshake_and_stays_offline(env):
    FakeElm.delay = 5.0                                           # would block 5 s if the cancel were ignored

    def press_cancel():
        dialog = widgets.QApplication.activeModalWidget()
        assert isinstance(dialog, widgets.QProgressDialog)
        dialog.findChild(widgets.QPushButton).click()             # what the user does

    core.QTimer.singleShot(100, press_cancel)
    start = time.time()

    assert connection.connect_adapter(env.app) is False

    assert time.time() - start < 3
    assert options.simulation_mode is True and options.elm is None
    assert env.messages == []                                     # a deliberate cancel is not an error


def test_disconnect_closes_the_adapter_and_goes_offline(env):
    adapter = FakeElm("p", 1, "STD")
    options.elm, options.simulation_mode, options.promode = adapter, False, True

    connection.disconnect_adapter()

    assert adapter.closed is True
    assert options.elm is None and options.simulation_mode is True and options.promode is False


def test_disconnect_while_offline_is_harmless(env):
    connection.disconnect_adapter()

    assert options.simulation_mode is True and options.elm is None


@pytest.mark.parametrize("button, expected", [(widgets.QMessageBox.Ok, True), (widgets.QMessageBox.Cancel, False)])
def test_the_warning_returns_what_the_user_pressed(monkeypatch, qapp, button, expected):
    monkeypatch.setattr(widgets.QMessageBox, "exec", lambda self: button)

    assert connection.confirm_risk() is expected


def test_the_warning_is_the_old_safety_checkbox_text(monkeypatch, qapp):
    shown = []
    monkeypatch.setattr(widgets.QMessageBox, "exec", lambda self: shown.append(self.text()) or widgets.QMessageBox.Ok)

    connection.confirm_risk()

    assert shown == [_("I'm aware that I can harm my car if badly used")]
