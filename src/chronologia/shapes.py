"""Formes des événements, partagées par la vue écran et l'export PDF."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPolygonF

from .layout import LayoutItem

BAR_RADIUS = 6.0


def item_shape_path(
    item: LayoutItem, marker_size: float, x_shift: float, y_top: float
) -> QPainterPath:
    """Losange (événement ponctuel) ou barre arrondie (période).

    ``x_shift`` : position de x = 0 de la mise en page ; ``y_top`` : position de y = 0.
    """
    path = QPainterPath()
    top = y_top + item.y
    if item.is_point:
        cx, cy, half = x_shift + item.x0, top + item.height / 2, marker_size / 2
        path.addPolygon(
            QPolygonF(
                [
                    QPointF(cx, cy - half),
                    QPointF(cx + half, cy),
                    QPointF(cx, cy + half),
                    QPointF(cx - half, cy),
                ]
            )
        )
        path.closeSubpath()
    else:
        rect = QRectF(x_shift + item.x0, top, item.x1 - item.x0, item.height)
        radius = min(BAR_RADIUS, item.height / 2)
        path.addRoundedRect(rect, radius, radius)
    return path
