"""A simulated ELM327 on the J1850 VPW bus of the Ram, shared by the VPW tests."""
import ddt4all.core.elm.elm as elm

# What the PCM of the truck answered (headers off, one line per frame), by request without spaces
TRUCK = {
    "0100": ["41 00 98 3A 80 15"],
    "0101": ["41 01 91 77 00 00"],
    "010C": ["41 0C 1A F8"],          # 1726 rpm
    "0123": ["41 23 4A 27"],          # 1898.3 bar
    "0142": ["41 42 30 3B"],          # 12.347 V
    "0105": ["41 05 38"],             # 16 C
    "010F": ["41 0F 00"],             # -40 C
    "010B": ["41 0B 7F"],             # 127 kPa
    "0133": ["41 33 3C"],             # 60 kPa
    "0111": ["41 11 80"],
    "0104": ["41 04 16"],             # 8.6 %
    "010D": ["41 0D 00"],             # 0 km/h
    "03": ["43 02 37 21 22 01 18", "43 01 13 01 07 00 73"],
    "07": ["47 02 37 21 22 01 18", "47 01 13 01 07 00 73"],
}


class FakeElm327:
    """An ELM327 on a J1850 VPW bus, seen from the port: write() a command, expect() the answer."""

    connectionStatus = True                      # what Port exposes; ELM.connectionStat() reads it

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
