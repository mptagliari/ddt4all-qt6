import errno
import os
from pathlib import Path
import sys
import tempfile

from ddt4all.qt import core

import ddt4all.options as options

_ = options.translator('ddt4all')

BASE_DIR = Path(__file__).resolve().parent
styles_base_dir = BASE_DIR / ".." / ".." / "resources" / "styles"

def isWritable(path):
    try:
        testfile = tempfile.TemporaryFile(dir=path)
        testfile.close()
        return True
    except OSError as e:
        if e.errno == errno.EACCES:  # 13
            return False
        e.filename = path
        return False
    except Exception:
        return False

def _set_legacy_stylesheet(app, dark):
    """Qt5 has no color scheme API: fall back to the bundled stylesheets."""
    stylefile = core.QFile(":/styles/qstyle-d.qss" if dark else ":/styles/qstyle.qss")
    stylefile.open(core.QFile.ReadOnly)
    stylesheet = bytes(stylefile.readAll()).decode()
    if sys.platform == "darwin":
        stylesheet = stylesheet.replace(
            '".AppleSystemUIFont", "Segoe UI", "Helvetica Neue",',
            '".AppleSystemUIFont", "Helvetica Neue",'
        )
    else:
        stylesheet = stylesheet.replace("font-size: 14pt;", "font-size: 10pt;")
    app.setStyleSheet(stylesheet)
    options.dark_mode = bool(dark)


def set_theme_style(app, onoff):
    """Dark forces the dark scheme; otherwise follow the desktop's own look."""
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        # Qt >= 6.8: keep the platform style and palette untouched
        app.setStyleSheet("")
        if onoff:
            hints.setColorScheme(core.Qt.ColorScheme.Dark)
        else:
            hints.unsetColorScheme()
        options.dark_mode = hints.colorScheme() == core.Qt.ColorScheme.Dark
    else:
        _set_legacy_stylesheet(app, onoff)
    options.configuration["dark"] = bool(onoff)
    options.save_config()


def set_socket_timeout(onoff):
    if (onoff):
        options.configuration["socket_timeout"] = True
    else:
        options.configuration["socket_timeout"] = False

    options.save_config()



