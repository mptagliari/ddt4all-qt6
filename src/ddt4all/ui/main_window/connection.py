"""Connect to / disconnect from the diagnostic adapter on demand.

Connecting asks one question (the risk warning) and uses the settings saved in Tools > Connection settings.

The application starts offline (``options.simulation_mode`` is True and
``options.elm`` is None). Connecting is an explicit user action, so browsing the
ECU database never waits on the adapter.

Invariant kept by this module: ``options.simulation_mode`` is False if and only
if ``options.elm`` is a live, initialized ELM.
"""
import threading

from ddt4all.qt import core
from ddt4all.qt import gui
from ddt4all.qt import widgets

import ddt4all.core.elm.elm as elm
import ddt4all.options as options
from ddt4all.ui.main_window import connection_settings
from ddt4all.ui.main_window.icons_paths import ICON_OBD
import ddt4all.version as version

_ = options.translator('ddt4all')


def _message(text):
    msgbox = widgets.QMessageBox()
    msgbox.setWindowIcon(gui.QIcon(ICON_OBD))
    msgbox.setWindowTitle(version.__appname__)
    msgbox.setText(text)
    msgbox.exec()


class ConnectWorker(core.QThread):
    """Runs the (slow, blocking) ELM handshake off the UI thread."""
    progress = core.Signal(str)

    def __init__(self, port, speed, adapter, raise_port_speed):
        super().__init__()
        self.args = (port, speed, adapter, raise_port_speed)
        self.cancel_event = threading.Event()
        self.adapter = None
        self.error = None

    def run(self):
        try:
            self.adapter = elm.ELM(*self.args, cancel_event=self.cancel_event,
                                   progress=self.progress.emit)
        except Exception as exc:  # reported on the UI thread
            self.error = str(exc)


def _open_adapter(settings):
    """Open the adapter on a worker thread behind a Cancel button.

    Returns (adapter, error, cancelled); the UI stays responsive meanwhile. The progress
    dialog is application modal, so nothing can use the adapter before it is ready.
    """
    worker = ConnectWorker(settings.target, settings.speed, settings.adapter, settings.raise_port_speed)
    progress = widgets.QProgressDialog(_("Connecting to the adapter..."), _("Cancel"), 0, 0)
    progress.setWindowTitle(version.__appname__)
    progress.setWindowIcon(gui.QIcon(ICON_OBD))
    progress.setWindowModality(core.Qt.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)

    loop = core.QEventLoop()
    worker.finished.connect(loop.quit)
    worker.progress.connect(progress.setLabelText)

    def cancel():
        # The handshake stops between baud rate attempts; wait for the worker to return
        worker.cancel_event.set()
        progress.setLabelText(_("Cancelling..."))
        progress.setCancelButton(None)

    progress.canceled.connect(cancel)
    worker.start()
    progress.show()
    if not worker.isFinished():
        loop.exec()
    worker.wait()
    progress.canceled.disconnect(cancel)
    progress.hide()
    progress.deleteLater()
    return worker.adapter, worker.error, worker.cancel_event.is_set()


def confirm_risk():
    """The warning shown before every connection. OK goes on; Cancel (or closing the box) does not."""
    box = widgets.QMessageBox()
    box.setIcon(widgets.QMessageBox.Warning)
    box.setWindowIcon(gui.QIcon(ICON_OBD))
    box.setWindowTitle(version.__appname__)
    box.setText(_("I'm aware that I can harm my car if badly used"))
    box.setStandardButtons(widgets.QMessageBox.Ok | widgets.QMessageBox.Cancel)
    box.setDefaultButton(widgets.QMessageBox.Ok)
    return box.exec() == widgets.QMessageBox.Ok


def connect_adapter(app, open_settings=None):
    """Confirm the warning and connect with the saved settings. Returns True when connected.

    open_settings is called when the settings are not complete yet (no port chosen), so the user lands
    where it is fixed. On any failure the application stays offline (simulation_mode True, elm None).
    """
    was_offline = options.simulation_mode
    connected = False
    try:
        if not confirm_risk():
            return False

        settings = connection_settings.load()
        problem = settings.problem()
        if problem:
            _message(problem + ". " + _("Choose the adapter and the port in Tools > Connection settings."))
            if open_settings is not None:
                open_settings()
            return False

        options.opt_can2 = settings.can2
        options.promode = False
        options.port = settings.target
        options.port_name = settings.port_name

        # ELM() only opens the port when simulation_mode is False
        options.simulation_mode = False
        print(_("Initializing ELM with speed %i...") % settings.speed)
        options.elm, error, cancelled = _open_adapter(settings)

        if cancelled:
            return False
        if error is not None:
            options.last_error = error
        if error is not None or options.elm is None or options.elm_failed:
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
