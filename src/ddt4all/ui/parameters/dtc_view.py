from ddt4all.qt import core
from ddt4all.qt import widgets

import ddt4all.options as options

_ = options.translator('ddt4all')


class DtcView(widgets.QWidget):
    """The "Trouble codes" tab: code, kind, description and manual page of the last Read DTC."""

    HEADERS = ("Code", "Kind", "Description", "Manual page")

    def __init__(self, on_reread=None, parent=None):
        super().__init__(parent)
        layout = widgets.QVBoxLayout(self)

        top = widgets.QHBoxLayout()
        self.summary = widgets.QLabel()
        self.summary.setWordWrap(True)
        top.addWidget(self.summary, 1)
        self.reread = widgets.QPushButton(_("Read again"))
        if on_reread is not None:
            self.reread.clicked.connect(on_reread)
        top.addWidget(self.reread, 0, core.Qt.AlignRight)
        layout.addLayout(top)

        self.table = widgets.QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels([_(h) for h in self.HEADERS])
        self.table.setEditTriggers(widgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(widgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(2, widgets.QHeaderView.Stretch)
        layout.addWidget(self.table)
        self.clear()

    def clear(self):
        self.table.setRowCount(0)
        self.summary.setText(_("Press Read DTC to list the trouble codes of the selected ECU."))

    def set_rows(self, rows, summary):
        self.summary.setText(summary)
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, widgets.QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(2, widgets.QHeaderView.Stretch)
