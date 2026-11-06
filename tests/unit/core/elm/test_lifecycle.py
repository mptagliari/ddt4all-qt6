from types import SimpleNamespace
from unittest.mock import Mock
import gc
import threading
import weakref

import pytest
import ddt4all.options as options
from ddt4all.core.elm import elm
from ddt4all.core.elm.port import Port
from ddt4all.ui.parameters import param_widget


@pytest.fixture
def fake_serial(monkeypatch):
    handles = []

    def serial_factory(**kwargs):
        handle = Mock(is_open=True)
        handle.close.side_effect = lambda: setattr(handle, 'is_open', False)
        handles.append(handle)
        return handle

    monkeypatch.setattr(options, 'elm', None)
    monkeypatch.setattr(options, 'simulation_mode', False)
    monkeypatch.setattr(options, 'log', '')
    monkeypatch.setattr(options, 'get_device_settings', lambda *a: None)
    monkeypatch.setattr(options, 'save_device_settings', lambda *a: None)
    monkeypatch.setattr(elm, 'get_logs_dir', lambda: '/tmp/ddt4all-mock-logs')
    monkeypatch.setattr('ddt4all.core.elm.port.serial.Serial', serial_factory)
    monkeypatch.setattr(Port, 'expect', lambda *a, **kw: 'ELM327 v1.5\r>')
    return handles


def test_initial_connection_selection_and_query_keep_transport(fake_serial, monkeypatch):
    connection = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    from ddt4all.core.ecu.ecu_file import EcuFile
    monkeypatch.setattr(elm, 'get_can_addr', lambda _: '01')
    # Exercise actual ECU selection initialization with protocol operations mocked.
    monkeypatch.setattr(connection, 'init_can', Mock())
    monkeypatch.setattr(connection, 'set_can_addr', Mock())
    ecu = SimpleNamespace(ecuname='fake ABS', ecu_protocol='CAN', ecu_send_id='740',
                          ecu_recv_id='760', baudrate=500000)
    assert EcuFile.connect_to_hardware(ecu)
    assert 'ELM327' in connection.send_raw('ATI')
    assert options.elm is connection
    assert connection.connectionStat()
    fake_serial[0].close.assert_not_called()
    elm.close_elm()


def test_replacement_closes_before_open_even_with_old_reference(fake_serial, monkeypatch):
    old = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    constructor = elm.ELM

    def checked_constructor(*args):
        assert not fake_serial[0].is_open
        assert options.elm is None
        return constructor(*args)

    monkeypatch.setattr(elm, 'ELM', checked_constructor)
    new = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    assert old.port is None
    assert not old.connectionStatus
    with pytest.raises(ConnectionError):
        old.send_raw('ATI')
    old.close()
    old.__del__()
    assert new.connectionStat()
    elm.close_elm()


def test_deleting_global_does_not_destroy_aliased_object(fake_serial):
    alias = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    reference = weakref.ref(alias)
    del options.elm
    gc.collect()
    assert reference() is alias
    assert alias.connectionStat()
    alias.close()
    options.elm = None


@pytest.mark.parametrize('raise_on_probe', [False, True])
def test_checker_closes_local_probe_on_success_and_exception(fake_serial, monkeypatch, raise_on_probe):
    monkeypatch.setattr(elm, 'cmdb', '#1;C;ATI')
    if raise_on_probe:
        monkeypatch.setattr(elm.ELM, 'send_raw', Mock(side_effect=RuntimeError('probe failed')))
    result = elm.elm_checker('/dev/fake', 38400, 'STD_USB', Mock(), Mock())
    assert result is not raise_on_probe
    assert options.elm is None
    assert all(not h.is_open for h in fake_serial)


def test_close_failure_still_invalidates_port():
    port = Port.__new__(Port)
    port._lock = threading.RLock()
    port.hdr = Mock()
    port.hdr.close.side_effect = OSError('disconnected')
    port.connectionStatus = True
    port.close()
    assert port.hdr is None
    assert not port.connectionStatus


def test_ui_failed_reconnect_never_queries_stale_connection(monkeypatch):
    connection = Mock()
    connection.connectionStat.return_value = False
    connection.request.return_value = '59 02 FF'
    window = Mock()
    monkeypatch.setattr(options, 'simulation_mode', False)
    monkeypatch.setattr(options, 'elm', connection)
    monkeypatch.setattr(options, 'main_window', window)
    monkeypatch.setattr(param_widget, 'reconnect_elm', lambda: False)
    page = SimpleNamespace(logview=Mock())
    page._sendElm = lambda *a: param_widget.ParamWidget._sendElm(page, *a)
    assert 'WRONG RESPONSE' in param_widget.ParamWidget.sendElm(page, '1902FF')
    connection.request.assert_not_called()
    window.setConnected.assert_called_with(False)


def test_ui_does_not_init_or_read_dtc_on_closed_connection(monkeypatch):
    monkeypatch.setattr(options, 'simulation_mode', False)
    monkeypatch.setattr(options, 'elm', None)
    monkeypatch.setattr(options, 'main_window', Mock())
    page = SimpleNamespace(logview=Mock(), ecurequestsparser=Mock())
    assert param_widget.ParamWidget.initELM(page) is False
    param_widget.ParamWidget.readDTC(page)
    page.ecurequestsparser.connect_to_hardware.assert_not_called()


def test_baud_fallback_closes_first_handle(fake_serial, monkeypatch):
    monkeypatch.setattr(Port, 'expect', lambda *a, **kw: '>' if len(fake_serial) == 1 else 'ELM327 v1.5\r>')
    connection = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    assert len(fake_serial) == 2
    assert not fake_serial[0].is_open
    assert connection.connectionStat()
    elm.close_elm()


def test_write_failure_does_not_deadlock_during_close(fake_serial):
    port = Port('/dev/fake', 38400, 'STD_USB')
    fake_serial[0].write.side_effect = RuntimeError('transport failed')
    worker = threading.Thread(target=port.write, args=(b'ATI\r',), daemon=True)
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert port.hdr is None
    assert not port.connectionStatus


def test_ui_reconnect_reinitializes_before_query(monkeypatch):
    monkeypatch.setattr(options, 'simulation_mode', False)
    monkeypatch.setattr(options, 'promode', False)
    window = Mock()
    monkeypatch.setattr(options, 'main_window', window)
    old = Mock()
    old.connectionStat.return_value = False
    new = Mock()
    new.request.return_value = '59 02 FF'
    monkeypatch.setattr(options, 'elm', old)
    events = []

    def reconnect():
        options.elm = new
        events.append('reconnect')
        return True

    monkeypatch.setattr(param_widget, 'reconnect_elm', reconnect)
    page = SimpleNamespace(logview=Mock(), initELM=lambda: events.append('init') or True)
    page._sendElm = lambda *a: param_widget.ParamWidget._sendElm(page, *a)
    new.request.side_effect = lambda *a, **kw: events.append('query') or '59 02 FF'
    assert param_widget.ParamWidget.sendElm(page, '1902FF') == '59 02 FF'
    assert events == ['reconnect', 'init', 'query']
    old.request.assert_not_called()
    window.setConnected.assert_called_with(True)


def test_ui_protocol_init_failure_does_not_mark_connected(monkeypatch):
    monkeypatch.setattr(options, 'simulation_mode', False)
    monkeypatch.setattr(options, 'main_window', Mock())
    connection = Mock()
    monkeypatch.setattr(options, 'elm', connection)
    parser = Mock()
    parser.connect_to_hardware.return_value = False
    page = SimpleNamespace(logview=Mock(), ecurequestsparser=parser, canline=0)
    assert param_widget.ParamWidget.initELM(page) is False
    options.main_window.setConnected.assert_called_with(False)


def test_database_loading_does_not_own_or_close_connection(fake_serial, monkeypatch):
    from ddt4all.core.ecu import ecu_scanner
    connection = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    database = Mock(numecu=5673)
    monkeypatch.setattr(ecu_scanner, 'EcuDatabase', lambda: database)
    scanner = ecu_scanner.EcuScanner()
    assert scanner.getNumEcuDb() == 5673
    assert options.elm is connection
    assert connection.connectionStat()
    fake_serial[0].close.assert_not_called()
    elm.close_elm()


def test_ui_transport_exception_marks_disconnected(monkeypatch):
    monkeypatch.setattr(options, 'main_window', Mock())
    page = SimpleNamespace(logview=Mock(), _sendElm=Mock(side_effect=ConnectionError('closed')))
    assert 'WRONG RESPONSE' in param_widget.ParamWidget.sendElm(page, '1902FF')
    options.main_window.setConnected.assert_called_with(False)


def test_closing_ecu_page_stops_both_timers(qtbot, monkeypatch):
    monkeypatch.setattr(param_widget.ParamWidget, 'initXML', lambda self: None)
    page = param_widget.ParamWidget(None, 'fake.json', '01', 'fake', Mock(), None, 0)
    qtbot.addWidget(page)
    page.timer.start(1000)
    assert page.tester_timer.isActive()
    page.close()
    assert not page.timer.isActive()
    assert not page.tester_timer.isActive()


def test_serial_write_loss_is_reported_as_transport_error(fake_serial):
    import serial
    connection = elm.replace_elm('/dev/fake', 38400, 'STD_USB')
    fake_serial[0].write.side_effect = serial.SerialException('disconnected')
    with pytest.raises(ConnectionError, match='write failed'):
        connection.send_raw('ATI')
    assert not connection.connectionStat()
    assert not connection.connectionStatus
    elm.close_elm()
