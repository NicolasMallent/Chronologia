"""Icônes vectorielles dessinées en code (aucun fichier image, nettes à toute densité)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

GRID = 20.0  # les glyphes sont dessinés sur une grille de 20 × 20
ICON_NAMES = ("undo", "redo", "zoom_in", "zoom_out", "fit", "search", "plus")


def _glyph(name: str) -> list[QPainterPath]:
    def poly(*points: tuple[float, float]) -> QPainterPath:
        path = QPainterPath(QPointF(*points[0]))
        for p in points[1:]:
            path.lineTo(QPointF(*p))
        return path

    def lens() -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(8.5, 8.5), 5.5, 5.5)
        return path

    handle = poly((12.6, 12.6), (17, 17))
    if name in ("undo", "redo"):
        curve = QPainterPath(QPointF(4, 8))
        curve.lineTo(11, 8)
        curve.cubicTo(16.5, 8, 16.5, 15.5, 11, 15.5)
        curve.lineTo(7, 15.5)
        paths = [curve, poly((7, 4.5), (3.5, 8), (7, 11.5))]
        if name == "redo":
            for p in paths:  # symétrie gauche-droite
                for i in range(p.elementCount()):
                    e = p.elementAt(i)
                    p.setElementPositionAt(i, GRID - e.x, e.y)
        return paths
    if name == "zoom_in":
        return [lens(), handle, poly((6, 8.5), (11, 8.5)), poly((8.5, 6), (8.5, 11))]
    if name == "zoom_out":
        return [lens(), handle, poly((6, 8.5), (11, 8.5))]
    if name == "search":
        return [lens(), handle]
    if name == "fit":
        return [
            poly((3, 7), (3, 3), (7, 3)),
            poly((13, 3), (17, 3), (17, 7)),
            poly((17, 13), (17, 17), (13, 17)),
            poly((7, 17), (3, 17), (3, 13)),
        ]
    if name == "plus":
        return [poly((10, 4), (10, 16)), poly((4, 10), (16, 10))]
    raise ValueError(f"icône inconnue : {name}")


def _pixmap(name: str, color: str, size: int) -> QPixmap:
    paths = _glyph(name)  # avant le peintre : une erreur ne doit pas laisser un QPainter actif
    ratio = 2  # rendu net sur les écrans haute densité
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / GRID, size / GRID)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for path in paths:
        painter.drawPath(path)
    painter.end()
    return pixmap


def make_icon(
    name: str, color: str = "#374151", disabled: str = "#b6bcc9", size: int = 20
) -> QIcon:
    """Icône ``name`` de la couleur donnée, avec son état désactivé."""
    icon = QIcon()
    icon.addPixmap(_pixmap(name, color, size), QIcon.Mode.Normal)
    icon.addPixmap(_pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return icon
