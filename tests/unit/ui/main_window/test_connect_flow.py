from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.ui.main_window import main_widget
from ddt4all.ui.main_window.main_widget import MainWidget

ECU = ("file.json", "745", "EMS3190", True)


def make_window(current_ecu=ECU):
    window = SimpleNamespace(
        paramview=Mock(), scrollview=Mock(), treeview_params=Mock(), treeview_ecu=Mock(),
        screennames=["screen"], diagaction=Mock(), hexinput=Mock(), cominput=Mock(),
        connectaction=Mock(), ui_edit_button=Mock(), expert=Mock(), tabbedview=Mock(),
        requesteditor=Mock(), dataitemeditor=Mock(), buttonEditor=Mock(), ecuparameditor=Mock(),
        screenlogfile=None, logview=Mock(), setConnected=Mock(), set_param_file=Mock(),
        current_ecu=current_ecu,
    )
    window.paramview_before = window.paramview
    window.closeCurrentEcu = lambda: MainWidget.closeCurrentEcu(window)
    return window


@pytest.fixture(autouse=True)
def restore_options(monkeypatch, qapp):
    monkeypatch.setattr(options, "simulation_mode", True)
    monkeypatch.setattr(options, "mode_edit", False)
    monkeypatch.setattr(options, "promode", False)
    monkeypatch.setattr(main_widget, "get_logs_dir", lambda: Path("/tmp"))


def test_close_current_ecu_stops_timers_and_disables_ecu_actions():
    window = make_window()
    previous = window.paramview

    MainWidget.closeCurrentEcu(window)

    previous.timer.stop.assert_called_once()
    previous.tester_timer.stop.assert_called_once()
    assert window.paramview is None
    window.treeview_params.clear.assert_called_once()
    assert window.screennames == []
    for action in (window.diagaction, window.hexinput, window.cominput):
        action.setEnabled.assert_called_once_with(False)
    assert window.current_ecu == ECU          # remembered for going back offline


def test_connecting_unloads_the_ecu_instead_of_starting_its_session():
    window = make_window()
    options.simulation_mode = False

    MainWidget.applyConnectionState(window)

    assert window.paramview is None
    window.set_param_file.assert_not_called()
    window.logview.append.assert_called_once()
    window.ui_edit_button.setEnabled.assert_called_once_with(False)


def test_going_back_offline_shows_the_remembered_ecu_again():
    window = make_window()
    window.paramview = None
    options.simulation_mode = True

    MainWidget.applyConnectionState(window)

    window.set_param_file.assert_called_once_with(*ECU)
    window.ui_edit_button.setEnabled.assert_called_once_with(True)


def test_offline_start_without_a_remembered_ecu_opens_nothing():
    window = make_window(current_ecu=None)
    window.paramview = None

    MainWidget.applyConnectionState(window)

    window.set_param_file.assert_not_called()
