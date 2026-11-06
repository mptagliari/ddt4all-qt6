from ddt4all.qt import gui
from ddt4all.qt import widgets

import ddt4all.options as options
from ddt4all.ui.main_window.icons_paths import ICON_OBD

_ = options.translator('ddt4all')

from ddt4all.qt import HAS_WEBENGINE, webengine as webkitwidgets

class EcuFinder(widgets.QDialog):
    def __init__(self, ecuscanner):
        super(EcuFinder, self).__init__()
        # Set window icon and title
        appIcon = gui.QIcon(ICON_OBD)
        self.setWindowIcon(appIcon)
        self.setWindowTitle(_("ECU Finder"))
        self.ecuscanner = ecuscanner
        layoutv = widgets.QVBoxLayout()
        layouth = widgets.QHBoxLayout()
        self.setLayout(layoutv)
        layoutv.addLayout(layouth)
        self.ecuaddr = widgets.QLineEdit()
        self.ecuident = widgets.QLineEdit()
        layouth.addWidget(widgets.QLabel(_("Address :")))
        layouth.addWidget(self.ecuaddr)
        layouth.addWidget(widgets.QLabel(_("ID frame :")))
        layouth.addWidget(self.ecuident)
        button = widgets.QPushButton(_("VALIDATE"))
        layouth.addWidget(button)
        button.clicked.connect(self.check)

    def check(self):
        addr = self.ecuaddr.text()
        frame = self.ecuident.text()
        self.ecuscanner.identify_from_frame(addr, frame)
