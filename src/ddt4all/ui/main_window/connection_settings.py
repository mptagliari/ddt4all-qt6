"""What a connection needs, saved the moment it is changed in Tools > Connection settings.

The Connect button reads it back, so connecting never asks for the adapter, port or speed again.
"""
from dataclasses import dataclass

import ddt4all.options as options

_ = options.translator('ddt4all')

ADAPTERS = ("STD_USB", "STD_WIFI", "STD_BT", "OBDLINK", "ELS27", "VLINKER", "DERLEK", "VGATE", "DOIP")
SPEEDS = (38400, 57600, 115200, 230400, 500000, 1000000)
DEFAULT_WIFI = "192.168.0.10:35000"

_PREFIX = "conn_"


@dataclass
class ConnectionSettings:
    adapter: str = "STD_USB"
    port: str = ""                  # device of the chosen list entry, e.g. /dev/ttyUSB0
    port_name: str = ""             # its description (kept for reconnecting)
    speed: int = 38400
    wifi: str = DEFAULT_WIFI
    can2: bool = False
    uart_speed: str = ""            # speed to switch the adapter's UART to; empty = leave it alone

    @property
    def target(self):
        """What the ELM opens: the Wi-Fi address, or the serial device."""
        return self.wifi.strip() if self.adapter == "STD_WIFI" else self.port

    @property
    def raise_port_speed(self):
        return self.uart_speed or "No"

    def problem(self):
        """Why these settings cannot connect yet, or "" when they can."""
        if self.adapter == "STD_WIFI":
            return "" if self.wifi.strip() else _("Enter the Wi-Fi adapter address")
        return "" if self.port else _("No port chosen")


def load():
    cfg = options.configuration
    adapter = cfg.get(_PREFIX + "adapter", "STD_USB")
    try:
        speed = int(cfg.get(_PREFIX + "speed", 38400))
    except (TypeError, ValueError):
        speed = 38400
    return ConnectionSettings(
        adapter=adapter if adapter in ADAPTERS else "STD_USB",
        port=str(cfg.get(_PREFIX + "port", "") or ""),
        port_name=str(cfg.get(_PREFIX + "port_name", "") or ""),
        speed=speed,
        wifi=str(cfg.get(_PREFIX + "wifi", DEFAULT_WIFI) or DEFAULT_WIFI),
        can2=bool(cfg.get(_PREFIX + "can2", False)),
        uart_speed=str(cfg.get(_PREFIX + "uart_speed", "") or ""),
    )


def save(settings):
    cfg = options.configuration
    cfg[_PREFIX + "adapter"] = settings.adapter
    cfg[_PREFIX + "port"] = settings.port
    cfg[_PREFIX + "port_name"] = settings.port_name
    cfg[_PREFIX + "speed"] = settings.speed
    cfg[_PREFIX + "wifi"] = settings.wifi
    cfg[_PREFIX + "can2"] = settings.can2
    cfg[_PREFIX + "uart_speed"] = settings.uart_speed
    options.save_config()
