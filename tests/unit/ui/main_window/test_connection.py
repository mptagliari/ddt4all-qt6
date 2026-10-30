from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.ui.main_window import connection


class FakeDialog:
    """Stands in for MainWindowOptions: each exec() pops the next scripted outcome."""
    script = []
    created = 0

    def __init__(self, app):
        type(self).created += 1
        self.mode = 0
        self.port = "/dev/ttyUSB0"
        self.CAN2 = False
        self.selectedportspeed = 38400
        self.adapter = "STD_USB"
        self.raise_port_speed = "No"

    def exec(self):
        outcome = type(self).script.pop(0)
        self.mode = outcome.get("mode", 0)
        self.port = outcome.get("port", self.port)
        # the real dialog flips this global when it checks the adapter
        options.simulation_mode = False
        return outcome.get("result", connection.widgets.QDialog.Accepted)


class FakeElm:
    closed = False

    def __init__(self, port, speed, adapter, maxspeed="No"):
        self.args = (port, speed, adapter, maxspeed)

    def close(self):
        self.closed = True


@pytest.fixture
def env(monkeypatch):
    FakeDialog.script, FakeDialog.created = [], 0
    messages = []
    monkeypatch.setattr(connection, "MainWindowOptions", FakeDialog)
    monkeypatch.setattr(connection, "_message", messages.append)
    monkeypatch.setattr(connection.elm, "ELM", FakeElm)
    monkeypatch.setattr(options, "simulation_mode", True)
    monkeypatch.setattr(options, "elm", None)
    monkeypatch.setattr(options, "elm_failed", False)
    monkeypatch.setattr(options, "promode", True)
    return SimpleNamespace(app=Mock(), messages=messages)


def test_connect_goes_online_with_a_live_elm(env):
    FakeDialog.script = [{"mode": 1}]

    assert connection.connect_adapter(env.app) is True

    assert options.simulation_mode is False
    assert isinstance(options.elm, FakeElm)
    assert options.elm.args == ("/dev/ttyUSB0", 38400, "STD_USB", "No")
    assert options.promode is False
    env.app.setOverrideCursor.assert_called_once()
    env.app.restoreOverrideCursor.assert_called_once()


@pytest.mark.parametrize("outcome", [
    {"mode": 0},                                         # closed
    {"mode": 1, "result": 0},                            # rejected (Cancel)
    {"mode": 2},                                         # old "demo" button
])
def test_leaving_the_dialog_keeps_the_app_offline(env, outcome):
    FakeDialog.script = [outcome]

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True      # the dialog had flipped it
    assert options.elm is None


def test_empty_port_is_not_attempted(env):
    FakeDialog.script = [{"mode": 1, "port": ""}]

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True and options.elm is None
    assert env.messages            # the user is told


def test_adapter_failure_stays_offline_and_releases_the_adapter(env, monkeypatch):
    created = []

    class FailingElm(FakeElm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)
            options.elm_failed = True

    monkeypatch.setattr(connection.elm, "ELM", FailingElm)
    FakeDialog.script = [{"mode": 1}]

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True and options.elm is None
    assert env.messages and "/dev/ttyUSB0" in env.messages[0]
    env.app.restoreOverrideCursor.assert_called_once()


def test_exception_while_opening_is_reported_not_raised(env, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("device busy")

    monkeypatch.setattr(connection.elm, "ELM", boom)
    FakeDialog.script = [{"mode": 1}]

    assert connection.connect_adapter(env.app) is False

    assert options.simulation_mode is True and options.elm is None
    assert env.messages
    env.app.restoreOverrideCursor.assert_called_once()


def test_language_reload_shows_the_dialog_again(env):
    FakeDialog.script = [{"mode": 3}, {"mode": 1}]

    assert connection.connect_adapter(env.app) is True
    assert FakeDialog.created == 2


def test_disconnect_closes_the_adapter_and_goes_offline(env):
    adapter = FakeElm("p", 1, "STD")
    options.elm, options.simulation_mode, options.promode = adapter, False, True

    connection.disconnect_adapter()

    assert adapter.closed is True
    assert options.elm is None
    assert options.simulation_mode is True
    assert options.promode is False


def test_disconnect_while_offline_is_harmless(env):
    connection.disconnect_adapter()

    assert options.simulation_mode is True and options.elm is None
