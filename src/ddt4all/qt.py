"""Qt binding selection.

PySide6 is used by default. PyQt5 stays supported as a fallback for platforms
Qt 6 does not run on (Windows 7, 32-bit systems, Python 3.8). Set the
``DDT4ALL_QT`` environment variable to ``pyside6`` or ``pyqt5`` to force one.

The rest of the code base imports ``core``, ``gui`` and ``widgets`` from here
instead of importing a binding directly, and only uses the API subset that is
identical on both. Differences are patched below, in one place.
"""
import importlib
import os
from types import SimpleNamespace

_BINDINGS = ("pyside6", "pyqt5")


def _binding_order():
    forced = os.environ.get("DDT4ALL_QT", "").strip().lower()
    if forced in _BINDINGS:
        return (forced,)
    return _BINDINGS


def _load_pyside6():
    core = importlib.import_module("PySide6.QtCore")
    gui = importlib.import_module("PySide6.QtGui")
    widgets = importlib.import_module("PySide6.QtWidgets")
    return core, gui, widgets


def _load_pyqt5():
    core = importlib.import_module("PyQt5.QtCore")
    gui = importlib.import_module("PyQt5.QtGui")
    widgets = importlib.import_module("PyQt5.QtWidgets")
    # Names PySide6 (Qt6) uses
    core.Signal = core.pyqtSignal
    core.Slot = core.pyqtSlot
    # QAction moved from QtWidgets to QtGui in Qt6
    gui.QAction = widgets.QAction
    gui.QActionGroup = widgets.QActionGroup
    gui.QShortcut = widgets.QShortcut
    return core, gui, widgets


def _load_webengine(binding):
    """Return a namespace with QWebEngineView/QWebEngineSettings, or None."""
    try:
        if binding == "pyside6":
            view = importlib.import_module("PySide6.QtWebEngineWidgets").QWebEngineView
            settings = importlib.import_module("PySide6.QtWebEngineCore").QWebEngineSettings
        else:
            module = importlib.import_module("PyQt5.QtWebEngineWidgets")
            view, settings = module.QWebEngineView, module.QWebEngineSettings
    except ImportError:
        return None
    # Qt6 scopes the enum (Settings.WebAttribute.X), Qt5 does not
    attributes = getattr(settings, "WebAttribute", settings)
    return SimpleNamespace(
        QWebEngineView=view,
        QWebEngineSettings=settings,
        WebAttribute=attributes,
    )


BINDING = None
for _name in _binding_order():
    try:
        core, gui, widgets = {"pyside6": _load_pyside6, "pyqt5": _load_pyqt5}[_name]()
    except ImportError:
        continue
    BINDING = _name
    break
else:
    raise ImportError(
        "No Qt binding found. Install PySide6 (pip install PySide6) "
        "or, on legacy systems, PyQt5."
    )

webengine = _load_webengine(BINDING)
HAS_WEBENGINE = webengine is not None
