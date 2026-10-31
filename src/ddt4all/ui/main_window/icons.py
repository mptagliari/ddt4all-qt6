"""Icons drawn in code, so no resource has to be rebuilt."""
from ddt4all.qt import core
from ddt4all.qt import gui

# A zig-zag lightning bolt, in a 0..1 square (the "run" bolt of the old Delphi IDE)
_BOLT = ((0.62, 0.04), (0.20, 0.56), (0.46, 0.56), (0.36, 0.96), (0.82, 0.40), (0.56, 0.40), (0.74, 0.04))


def bolt_icon(connected=False, size=64):
    """Yellow lightning bolt: connect. The same bolt struck through in red: disconnect."""
    pixmap = gui.QPixmap(size, size)
    pixmap.fill(core.Qt.transparent)
    painter = gui.QPainter(pixmap)
    painter.setRenderHint(gui.QPainter.Antialiasing)

    outline = gui.QPen(gui.QColor("#6b4f00"))
    outline.setWidthF(size / 22)
    outline.setJoinStyle(core.Qt.RoundJoin)
    painter.setPen(outline)
    painter.setBrush(gui.QColor("#f7c600"))
    painter.drawPolygon(gui.QPolygonF([core.QPointF(x * size, y * size) for x, y in _BOLT]))

    if connected:
        slash = gui.QPen(gui.QColor("#d32f2f"))
        slash.setWidthF(size / 9)
        slash.setCapStyle(core.Qt.RoundCap)
        painter.setPen(slash)
        painter.drawLine(core.QPointF(0.10 * size, 0.10 * size), core.QPointF(0.90 * size, 0.90 * size))

    painter.end()
    return gui.QIcon(pixmap)
