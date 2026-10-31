from ddt4all.qt import core
from ddt4all.qt import gui
from ddt4all.qt import widgets

import ddt4all.options as options
from ddt4all.ui.utils import PATH_PNG_ODB

_ = options.translator('ddt4all')


class DtcDialog(widgets.QDialog):
    """Read-only list of trouble codes: code, kind, description and where the manual covers it."""

    HEADERS = ("Code", "Kind", "Description", "Manual page")

    def __init__(self, rows, summary, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Trouble codes"))
        self.setWindowIcon(gui.QIcon(PATH_PNG_ODB))
        layout = widgets.QVBoxLayout(self)

        self.summary = widgets.QLabel(summary)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.table = widgets.QTableWidget(len(rows), len(self.HEADERS))
        self.table.setHorizontalHeaderLabels([_(h) for h in self.HEADERS])
        self.table.setEditTriggers(widgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(widgets.QAbstractItemView.SelectRows)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, widgets.QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(2, widgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        close = widgets.QPushButton(_("Close"))
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, core.Qt.AlignRight)
        self.resize(900, 420)
