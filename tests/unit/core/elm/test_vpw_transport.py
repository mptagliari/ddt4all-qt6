from pathlib import Path

import pytest

import ddt4all.core.elm.elm as elm
from ddt4all import options
from ddt4all.core.ecu.ecu_file import EcuFile

ECU_FILE = Path(__file__).resolve().parents[3] / "resources" / "dodge_ram_2500_cummins" / "Dodge_Ram_2500_Cummins_PCM.json"

# What the PCM of the truck answered (headers off, one line per frame), by request without spaces
TRUCK = {
    "0100": ["41 00 98 3A 80 15"],
    "0101": ["41 01 90 77 00 00"],
    "010C": ["41 0C 1A F8"],          # 1726 rpm
    "0123": ["41 23 4A 27"],          # 1898.3 bar
    "0142": ["41 42 30 3B"],          # 12.347 V
    "0105": ["41 05 38"],             # 16 C
    "010F": ["41 0F 00"],             # -40 C
    "010B": ["41 0B 7F"],             # 127 kPa
    "0133": ["41 33 3C"],             # 60 kPa
    "0111": ["41 11 80"],
    "03": ["43 02 37 21 22 01 18", "43 01 13 01 07 00 73"],
}


class FakeElm327:
    """An ELM327 on a J1850 VPW bus, seen from the port: write() a command, expect() the answer."""

    def __init__(self, answers):
        self.answers = answers
        self.written = []
        self.echo = True
        self._last = ""

    def write(self, data):
        self._last = data.decode().strip()
        self.written.append(self._last.upper())

    def expect(self, pattern, time_out=1):
        command = self._last.upper()
        compact = command.replace(" ", "")
        if compact.startswith("AT"):
            if compact == "ATE0":
                self.echo = False
            elif compact == "ATE1":
                self.echo = True
            lines = ["OK"]
        else:
            lines = self.answers.get(compact, ["NO DATA"])
        text = (command + "\r" if self.echo else "") + "\r".join(lines) + "\r\r>"
        return text.replace("\r", "\n")                 # Port.expect turns CR into LF

    def init_wifi(self, force=False):
        pass

    def close(self):
        pass

    @property
    def commands(self):
        return [c for c in self.written if c != "ATZ"]


def make_adapter(answers):
    port = FakeElm327(answers)
    adapter = elm.ELM.__new__(elm.ELM)              # no serial port: the fake stands in for it
    adapter.port = port
    adapter.rsp_cache = {}
    adapter.currentprotocol = ""
    adapter.currentsubprotocol = ""
    return adapter, port


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", False)
    adapter, port = make_adapter(TRUCK)
    monkeypatch.setattr(options, "elm", adapter)
    return adapter, port


def test_init_vpw_prepares_the_adapter(online):
    adapter, port = online

    adapter.init_vpw()

    assert port.commands == ["AT WS", "AT E1", "AT S1", "AT L1", "AT H0"]
    assert adapter.currentprotocol == "vpw"


def test_set_vpw_addr_selects_the_protocol_and_the_obd_functional_header(online):
    adapter, port = online

    adapter.set_vpw_addr("10", {"ecuname": "PCM", "protocol": "J1850VPW"})

    assert port.commands == ["AT SP 2", "AT SH 68 6A F1", "AT AT 1", "AT ST 96"]
    assert (adapter.currentprotocol, adapter.currentaddress) == ("vpw", "10")


def test_selecting_the_same_ecu_again_sends_nothing(online):
    adapter, port = online
    ecu = {"ecuname": "PCM", "protocol": "J1850VPW"}
    adapter.set_vpw_addr("10", ecu)
    sent = len(port.written)

    adapter.set_vpw_addr("10", ecu)

    assert len(port.written) == sent


def test_connecting_the_dodge_ecu_runs_the_whole_vpw_setup(online):
    adapter, port = online
    ecu = EcuFile(str(ECU_FILE), True)

    assert ecu.connect_to_hardware() is True

    assert port.commands == ["AT WS", "AT E1", "AT S1", "AT L1", "AT H0",
                             "AT SP 2", "AT SH 68 6A F1", "AT AT 1", "AT ST 96"]


@pytest.mark.parametrize("request_name, item, expected", [
    ("PID 0C Rotação do motor", "Rotação do motor", 1726),
    ("PID 23 Pressão do rail (real)", "Pressão do rail (real)", 1898.3),
    ("PID 42 Tensão do módulo", "Tensão do módulo", 12.347),
    ("PID 05 Temperatura do líquido", "Temperatura do líquido", 16),
    ("PID 0F Temperatura do ar de admissão", "Temperatura do ar de admissão", -40),
    ("PID 0B Pressão do coletor (MAP)", "Pressão do coletor (MAP)", 127),
    ("PID 33 Pressão barométrica", "Pressão barométrica", 60),
])
def test_live_values_go_from_the_bus_to_the_decoded_screen_value(online, request_name, item, expected):
    ecu = EcuFile(str(ECU_FILE), True)
    ecu.connect_to_hardware()

    values = ecu.requests[request_name].send_request()

    assert float(values[item]) == pytest.approx(expected, abs=0.05)


def test_the_first_stored_dtcs_are_returned_as_hex(online):
    ecu = EcuFile(str(ECU_FILE), True)
    ecu.connect_to_hardware()

    values = ecu.requests["Modo 03 Códigos armazenados (3 primeiros)"].send_request()

    assert [values[f"Código armazenados {i} (hex)"] for i in (1, 2, 3)] == ["0237", "2122", "0118"]    # P0237 P2122 P0118


def test_a_silent_pcm_does_not_crash_the_request(monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", False)
    adapter, port = make_adapter({})                       # every OBD request answers NO DATA
    monkeypatch.setattr(options, "elm", adapter)
    ecu = EcuFile(str(ECU_FILE), True)
    ecu.connect_to_hardware()

    result = ecu.requests["PID 0C Rotação do motor"].send_request()

    assert not result or all(v in (None, "", "NO DATA") for v in result.values())


def test_offline_mode_connects_without_touching_the_adapter(monkeypatch):
    monkeypatch.setattr(options, "simulation_mode", True)
    ecu = EcuFile(str(ECU_FILE), True)

    assert ecu.connect_to_hardware() is True
