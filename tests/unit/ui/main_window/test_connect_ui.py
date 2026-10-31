from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from ddt4all import options
from ddt4all.ui.main_window import main_widget
from ddt4all.ui.main_window.icons import bolt_icon
from ddt4all.ui.main_window.main_widget import MainWidget


def pixels(icon, size=64):
    return icon.pixmap(size, size).toImage()


def opaque(image):
    return sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0)


def test_the_connect_icon_is_a_drawn_bolt(qapp):
    icon = bolt_icon()

    assert not icon.isNull()
    image = pixels(icon)
    covered = opaque(image)
    assert 0.15 * 64 * 64 < covered < 0.60 * 64 * 64                 # a bolt: more than a speck, less than a square
    assert image.pixelColor(0, 0).alpha() == 0                       # transparent corners


def test_the_disconnect_icon_is_the_bolt_struck_through_in_red(qapp):
    connect, disconnect = pixels(bolt_icon(False)), pixels(bolt_icon(True))

    assert connect != disconnect
    reds = sum(1 for x in range(64) for y in range(64)
               if disconnect.pixelColor(x, y).red() > 180 and disconnect.pixelColor(x, y).green() < 90)
    assert reds > 100
    assert sum(1 for x in range(64) for y in range(64)
               if connect.pixelColor(x, y).red() > 180 and connect.pixelColor(x, y).green() < 90) == 0


def test_connect_button_opens_the_settings_when_there_is_nothing_to_connect_to(monkeypatch):
    seen = {}
    monkeypatch.setattr(main_widget, "connect_adapter", lambda app, open_settings: seen.update(open_settings=open_settings) or False)
    monkeypatch.setattr(options, "simulation_mode", True)
    window = SimpleNamespace(app=object(), showConnectionSettings=Mock(), applyConnectionState=Mock())

    MainWidget.toggleConnection(window)

    assert seen["open_settings"] is window.showConnectionSettings
    window.applyConnectionState.assert_not_called()                  # not connected: nothing to apply


class FakeSettingsDialog:
    modes = []
    built = []

    def __init__(self, app, connected=False):
        type(self).built.append(connected)
        self.mode = 0

    def exec(self):
        self.mode = type(self).modes.pop(0)


@pytest.fixture
def window(monkeypatch):
    FakeSettingsDialog.modes, FakeSettingsDialog.built = [], []
    monkeypatch.setattr(main_widget, "MainWindowOptions", FakeSettingsDialog)
    monkeypatch.setattr(main_widget, "widgets", MagicMock())
    monkeypatch.setattr(options, "configuration", {"lang": "pt_BR"})
    monkeypatch.setattr(options, "simulation_mode", True)
    return SimpleNamespace(app=object())


def test_the_settings_screen_opens_once_and_closes(window):
    FakeSettingsDialog.modes = [0]

    MainWidget.showConnectionSettings(window)

    assert FakeSettingsDialog.built == [False]


def test_the_screen_is_rebuilt_after_a_language_or_doip_change(window):
    FakeSettingsDialog.modes = [3, 3, 0]

    MainWidget.showConnectionSettings(window)

    assert FakeSettingsDialog.built == [False, False, False]


def test_while_connected_the_screen_knows_the_port_is_busy(window, monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", False)
    FakeSettingsDialog.modes = [0]

    MainWidget.showConnectionSettings(window)

    assert FakeSettingsDialog.built == [True]
    assert options.simulation_mode is False                           # the screen does not change the state


def test_the_online_state_survives_the_screen_changing_it(window, monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", True)

    class FlipsTheFlag(FakeSettingsDialog):
        def exec(self):
            super().exec()
            options.simulation_mode = False                           # the ELM benchmark does this

    monkeypatch.setattr(main_widget, "MainWindowOptions", FlipsTheFlag)
    FakeSettingsDialog.modes = [0]

    MainWidget.showConnectionSettings(window)

    assert options.simulation_mode is True


def test_changing_the_language_tells_the_user_to_restart(window, monkeypatch):
    class ChangesLanguage(FakeSettingsDialog):
        def exec(self):
            super().exec()
            options.configuration["lang"] = "en_US"

    monkeypatch.setattr(main_widget, "MainWindowOptions", ChangesLanguage)
    FakeSettingsDialog.modes = [3, 0]

    MainWidget.showConnectionSettings(window)

    main_widget.widgets.QMessageBox.assert_called()                   # the "restart to apply" note
