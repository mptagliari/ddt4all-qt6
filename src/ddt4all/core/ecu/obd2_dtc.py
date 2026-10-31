"""Standard OBD-II (SAE J1979) trouble code services, for ECUs on J1850 VPW.

03 = stored codes, 07 = pending codes, 0A = permanent codes, 01 PID 01 = MIL and code count.
Read only: nothing here sends 04 (clear codes).
"""
import json
import os
import re

SERVICES = (("03", "stored"), ("07", "pending"), ("0A", "permanent"))
_HEX = re.compile(r"^[0-9A-Fa-f]{2}$")


def decode_dtc(high, low):
    """Two bytes of a trouble code to its name: 0x02 0x37 -> P0237, 0x41 0x00 -> C0100."""
    return "PCBU"[high >> 6] + "%X%X%02X" % ((high >> 4) & 3, high & 0xF, low)


def frames(response, service):
    """Data bytes of every answer frame to a service request.

    The adapter answers one line per frame ("43 02 37 21 22 01 18"); the echo of the request, the prompt
    and messages such as NO DATA are not frames and are skipped.
    """
    answer = "%02X" % (int(service, 16) + 0x40)
    out = []
    for line in str(response).replace("\r", "\n").split("\n"):
        tokens = line.split()
        if len(tokens) > 1 and all(_HEX.match(t) for t in tokens) and tokens[0].upper() == answer:
            out.append([int(t, 16) for t in tokens[1:]])
    return out


def codes_from_response(response, service):
    """Trouble codes in the answer; the 00 00 padding of the last frame is not a code."""
    codes = []
    for data in frames(response, service):
        for i in range(0, len(data) - 1, 2):
            if data[i] or data[i + 1]:
                code = decode_dtc(data[i], data[i + 1])
                if code not in codes:
                    codes.append(code)
    return codes


def monitor_status(response):
    """(MIL on, number of stored codes) from the answer to 01 01, or (None, None)."""
    for line in str(response).replace("\r", "\n").split("\n"):
        tokens = line.split()
        if len(tokens) >= 3 and all(_HEX.match(t) for t in tokens) and tokens[0] == "41" and tokens[1] == "01":
            a = int(tokens[2], 16)
            return bool(a & 0x80), a & 0x7F
    return None, None


def read_codes(adapter, attempts=3):
    """{"stored": [...], "pending": [...], "permanent": [...]} read from a connected adapter.

    Frames get lost on VPW, so each service is read several times and the answers are merged.
    """
    result = {}
    for service, kind in SERVICES:
        codes = []
        for _ in range(attempts):
            for code in codes_from_response(adapter.cmd(service), service):
                if code not in codes:
                    codes.append(code)
        result[kind] = codes
    return result


def load_names(ecu_file):
    """{code: [{"d": description, "p": printed manual page, "diesel": bool}]} from "<ecu>.dtcnames", or {}.

    The file is optional and local: the descriptions come from the user's own service manual.
    """
    for path in (str(ecu_file) + ".dtcnames", os.path.join("json", os.path.basename(str(ecu_file)) + ".dtcnames")):
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    return json.load(handle).get("codes", {})
            except (OSError, ValueError):
                return {}
    return {}


def describe(names, code):
    """(description, manual page) of a code, the diesel entry first; ("", "") when unknown."""
    entries = sorted(names.get(code, []), key=lambda e: not e.get("diesel"))
    return (entries[0]["d"], entries[0]["p"]) if entries else ("", "")
