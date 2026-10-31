import pytest

from ddt4all.core.ecu.ecu_ident import EcuIdent


def ident(protocol):
    return EcuIdent("", "", "", "", "ECU", "Group", "ecu.json", protocol, ["ALL"], "10")


@pytest.mark.parametrize("declared, expected", [
    ("CAN", "CAN"),
    ("KWP2000", "KWP2000"),
    ("ISO8", "ISO8"),
    ("DOIP", "DOIP"),
    ("J1850VPW", "J1850VPW"),
    ("SAE J1850 VPW", "J1850VPW"),
    ("something else", "UNKNOWN"),
])
def test_protocol_is_normalised(declared, expected):
    assert ident(declared).protocol == expected
