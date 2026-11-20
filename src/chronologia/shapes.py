"""Formes des événements, partagées par la vue écran et l'export PDF."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath

from .layout import LayoutItem

BAR_RADIUS = 6.0
POINT_RADIUS = 1.5


def item_shape_path(
    item: LayoutItem, point_width: float, x_shift: float, y_top: float
) -> QPainterPath:
    """Rectangle vertical plein (événement ponctuel) ou barre arrondie (période).

    ``x_shift`` : position de x = 0 de la mise en page ; ``y_top`` : position de y = 0.
    """
    path = QPainterPath()
    top = y_top + item.y
    if item.is_point:
        rect = QRectF(x_shift + item.x0 - point_width / 2, top, point_width, item.height)
        path.addRoundedRect(rect, POINT_RADIUS, POINT_RADIUS)
    else:
        rect = QRectF(x_shift + item.x0, top, item.x1 - item.x0, item.height)
        radius = min(BAR_RADIUS, item.height / 2)
        path.addRoundedRect(rect, radius, radius)
    return path
