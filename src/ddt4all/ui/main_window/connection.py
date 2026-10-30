"""Connect to / disconnect from the diagnostic adapter on demand.

The application starts offline (``options.simulation_mode`` is True and
``options.elm`` is None). Connecting is an explicit user action, so browsing the
ECU database never waits on the adapter.

Invariant kept by this module: ``options.simulation_mode`` is False if and only
if ``options.elm`` is a live, initialized ELM.
"""
from ddt4all.qt import core
from ddt4all.qt import gui
from ddt4all.qt import widgets

import ddt4all.core.elm.elm as elm
import ddt4all.options as options
from ddt4all.ui.main_window.icons_paths import ICON_OBD
from ddt4all.ui.main_window.main_window_options import MainWindowOptions
import ddt4all.version as version

_ = options.translator('ddt4all')


def _message(text):
    msgbox = widgets.QMessageBox()
    msgbox.setWindowIcon(gui.QIcon(ICON_OBD))
    msgbox.setWindowTitle(version.__appname__)
    msgbox.setText(text)
    msgbox.exec()


def _ask_adapter(app):
    """Show the adapter dialog; return it when the user asked to connect, else None."""
    dialog = MainWindowOptions(app)
    while True:
        result = dialog.exec()
        if dialog.mode == 0 or result == widgets.QDialog.Rejected:
            return None
        # Language/DoIP change: rebuild the dialog and ask again
        if dialog.mode == 3:
            dialog = MainWindowOptions(app)
            continue
        # Mode 2 is the old "demo" button: the app is already offline
        return dialog if dialog.mode == 1 else None


def connect_adapter(app):
    """Let the user pick an adapter and connect. Returns True when connected.

    On any failure the application stays offline (simulation_mode True, elm None).
    """
    was_offline = options.simulation_mode
    connected = False
    try:
        dialog = _ask_adapter(app)
        if dialog is None:
            return False

        options.opt_can2 = dialog.CAN2
        options.promode = False
        options.port = str(dialog.port)
        if not dialog.port:
            _message(_("No COM port selected"))
            return False

        # ELM() only opens the port when simulation_mode is False
        options.simulation_mode = False
        print(_("Initializing ELM with speed %i...") % dialog.selectedportspeed)
        app.setOverrideCursor(core.Qt.WaitCursor)
        try:
            options.elm = elm.ELM(options.port, dialog.selectedportspeed,
                                  dialog.adapter, dialog.raise_port_speed)
        finally:
            app.restoreOverrideCursor()

        if options.elm_failed:
            _message(_("No ELM327 or OBDLINK-SX detected on COM port ") + options.port)
            return False
        connected = True
        return True
    except Exception as exc:  # the port or the adapter misbehaved
        options.last_error = str(exc)
        _message(_("No ELM327 or OBDLINK-SX detected on COM port ") + str(options.port))
        return False
    finally:
        if not connected:
            _release_elm()
            options.simulation_mode = was_offline


def _release_elm():
    adapter, options.elm = options.elm, None
    if adapter is not None:
        try:
            adapter.close()
        except Exception:
            pass  # nothing more to release


def disconnect_adapter():
    """Go back offline and release the serial port."""
    options.simulation_mode = True
    options.promode = False
    _release_elm()
