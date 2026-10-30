from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.ui.parameters import param_widget
from ddt4all.ui.parameters.param_widget import ParamWidget


class FakeTimer:
    def __init__(self, interval=param_widget.TESTER_INTERVAL_MS):
        self._interval = interval

    def interval(self):
        return self._interval

    def setInterval(self, value):
        self._interval = value


def make_page(response, command='3E'):
    return SimpleNamespace(
        tester_presend_command=command,
        tester_timer=FakeTimer(),
        sendElm=Mock(return_value=response),
    )


@pytest.fixture(autouse=True)
def no_auto_refresh(monkeypatch):
    monkeypatch.setattr(options, 'auto_refresh', False)


def test_interval_doubles_while_ecu_does_not_answer_and_is_capped():
    page = make_page('WRONG RESPONSE: NO DATA')
    seen = []
    for _ in range(6):
        ParamWidget.tester_send(page)
        seen.append(page.tester_timer.interval())

    assert seen[:3] == [3000, 6000, 12000]
    assert max(seen) == param_widget.TESTER_MAX_INTERVAL_MS


def test_interval_returns_to_normal_once_ecu_answers():
    page = make_page('WRONG RESPONSE')
    ParamWidget.tester_send(page)
    ParamWidget.tester_send(page)
    assert page.tester_timer.interval() > param_widget.TESTER_INTERVAL_MS

    page.sendElm.return_value = '7E 00'
    ParamWidget.tester_send(page)

    assert page.tester_timer.interval() == param_widget.TESTER_INTERVAL_MS


def test_negative_response_counts_as_alive():
    page = make_page('7F 3E 12')
    ParamWidget.tester_send(page)

    assert page.tester_timer.interval() == param_widget.TESTER_INTERVAL_MS


def test_nothing_is_sent_without_a_tester_command_or_during_auto_refresh(monkeypatch):
    page = make_page('7E 00', command='')
    ParamWidget.tester_send(page)
    page.sendElm.assert_not_called()

    monkeypatch.setattr(options, 'auto_refresh', True)
    page = make_page('7E 00')
    ParamWidget.tester_send(page)
    page.sendElm.assert_not_called()
