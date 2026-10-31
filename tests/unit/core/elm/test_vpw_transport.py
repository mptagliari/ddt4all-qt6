from pathlib import Path

import pytest

from ddt4all import options
from ddt4all.core.ecu.ecu_file import EcuFile

from .fake_elm327 import TRUCK, make_adapter

ECU_FILE = Path(__file__).resolve().parents[3] / "resources" / "dodge_ram_2500_cummins" / "Dodge_Ram_2500_Cummins_PCM.json"

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
