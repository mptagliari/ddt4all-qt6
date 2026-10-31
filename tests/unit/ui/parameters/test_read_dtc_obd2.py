import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ddt4all import options
from ddt4all.ui.parameters.dtc_dialog import DtcDialog
from ddt4all.ui.parameters.param_widget import ParamWidget

_ = options.translator('ddt4all')

from tests.unit.core.elm.fake_elm327 import TRUCK, make_adapter


def make_page(tmp_path, names=None):
    ecu = tmp_path / "Dodge.json"
    if names is not None:
        (tmp_path / "Dodge.json.dtcnames").write_text(json.dumps({"codes": names}))
    return SimpleNamespace(ddtfile=str(ecu), logview=Mock(), showDtcDialog=Mock())


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", False)
    adapter, port = make_adapter(TRUCK)
    monkeypatch.setattr(options, "elm", adapter)
    return port


def test_codes_are_read_decoded_and_described(connected, tmp_path):
    page = make_page(tmp_path, {"P0237": [{"d": "MAP SENSOR VOLTAGE TOO LOW", "p": "9-1168", "diesel": True}]})

    ParamWidget.readDtcObd2(page)

    rows, summary = page.showDtcDialog.call_args[0]
    assert [r[0] for r in rows] == ["P0237", "P2122", "P0118", "P0113", "P0107", "P0073"]
    assert rows[0] == ("P0237", _("Stored") + " + " + _("Pending"), "MAP SENSOR VOLTAGE TOO LOW", "9-1168")
    assert rows[1][2:] == ("-", "-")                                   # no description known: shown as a dash
    assert _("MIL on") in summary and _("the ECU counts %d stored codes") % 17 in summary


def test_the_summary_warns_when_the_ecu_counts_more_codes_than_were_read(connected, tmp_path):
    page = make_page(tmp_path)

    ParamWidget.readDtcObd2(page)

    # the ECU counts 17, 6 were returned here
    assert _("Some codes may be missing (frames lost on the bus): read again.") in page.showDtcDialog.call_args[0][1]


def test_only_read_services_are_sent(connected, tmp_path):
    ParamWidget.readDtcObd2(make_page(tmp_path))

    sent = {c.replace(" ", "") for c in connected.commands if not c.startswith("AT")}
    assert sent <= {"03", "07", "0A", "0101"}                           # never 04 (clear)


def test_without_a_connection_nothing_is_sent_and_the_user_is_told(monkeypatch, tmp_path):
    monkeypatch.setattr(options, "simulation_mode", True)
    page = make_page(tmp_path)

    ParamWidget.readDtcObd2(page)

    page.showDtcDialog.assert_not_called()
    page.logview.append.assert_called_once()


def test_the_dialog_lists_every_row(qapp):
    rows = [("P0237", "Stored", "MAP SENSOR VOLTAGE TOO LOW", "9-1168"), ("P2122", "Pending", "-", "-")]

    dialog = DtcDialog(rows, "MIL on", None)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 2).text() == "MAP SENSOR VOLTAGE TOO LOW"
    assert dialog.table.item(1, 0).text() == "P2122"
