import json

import pytest

from ddt4all.core.ecu import obd2_dtc as dtc


@pytest.mark.parametrize("high, low, expected", [
    (0x02, 0x37, "P0237"), (0x21, 0x22, "P2122"), (0x17, 0x54, "P1754"), (0x01, 0x93, "P0193"),
    (0x41, 0x00, "C0100"), (0x81, 0x23, "B0123"), (0xC1, 0x00, "U0100"), (0x25, 0x09, "P2509"),
])
def test_two_bytes_become_a_code(high, low, expected):
    assert dtc.decode_dtc(high, low) == expected


def test_echo_prompt_and_messages_are_not_frames():
    response = "03\n43 02 37 21 22 01 18\nNO DATA\n\n>"
    assert dtc.frames(response, "03") == [[0x02, 0x37, 0x21, 0x22, 0x01, 0x18]]


def test_codes_from_several_frames_without_padding_or_repeats():
    response = ("03\n43 02 37 21 22 01 18\n43 01 13 01 07 00 73\n43 00 69 00 00 00 00\n43 02 37 00 00 00 00\n>")
    assert dtc.codes_from_response(response, "03") == ["P0237", "P2122", "P0118", "P0113", "P0107", "P0073", "P0069"]


def test_no_codes_gives_an_empty_list():
    assert dtc.codes_from_response("03\n43 00 00 00 00 00 00\n>", "03") == []
    assert dtc.codes_from_response("03\nNO DATA\n>", "03") == []


def test_pending_and_permanent_use_their_own_answer_byte():
    assert dtc.codes_from_response("07\n47 02 37 00 00 00 00", "07") == ["P0237"]
    assert dtc.codes_from_response("0A\n4A 17 54 00 00 00 00", "0A") == ["P1754"]
    assert dtc.codes_from_response("07\n43 02 37 00 00 00 00", "07") == []        # a mode 03 answer is not mode 07


def test_mil_and_count_come_from_pid_01():
    assert dtc.monitor_status("0101\n41 01 91 77 00 00\n>") == (True, 17)
    assert dtc.monitor_status("0101\n41 01 03 07 00 00\n>") == (False, 3)
    assert dtc.monitor_status("0101\nNO DATA\n>") == (None, None)


def test_read_codes_merges_the_attempts_because_vpw_loses_frames():
    answers = iter(["03\n43 02 37 21 22 00 00", "03\n43 01 18 00 00 00 00", "03\nNO DATA"])
    adapter = type("A", (), {"cmd": lambda self, c: next(answers) if c == "03" else "NO DATA"})()

    codes = dtc.read_codes(adapter, attempts=3)

    assert codes == {"stored": ["P0237", "P2122", "P0118"], "pending": [], "permanent": []}


def test_names_prefer_the_diesel_entry_and_missing_files_are_harmless(tmp_path):
    ecu = tmp_path / "Dodge.json"
    (tmp_path / "Dodge.json.dtcnames").write_text(json.dumps({"codes": {"P0193": [
        {"d": "GAS ENTRY", "p": "9-1", "diesel": False}, {"d": "FUEL PRESSURE SENSOR VOLTAGE TOO HIGH", "p": "9-1130", "diesel": True}]}}))
    names = dtc.load_names(ecu)

    assert dtc.describe(names, "P0193") == ("FUEL PRESSURE SENSOR VOLTAGE TOO HIGH", "9-1130")
    assert dtc.describe(names, "P9999") == ("", "")
    assert dtc.load_names(tmp_path / "missing.json") == {}
