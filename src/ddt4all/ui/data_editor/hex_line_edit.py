from ddt4all.qt import widgets

class HexLineEdit(widgets.QLineEdit):
    def __init__(self, num, alpha):
        widgets.QLineEdit.__init__(self)
        if not alpha:
            self.setInputMask("H" * num)
        else:
            self.setInputMask("N" * num)
