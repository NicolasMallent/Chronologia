"""Règles graduées en unités réelles et mini-carte de la feuille."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, BORDER, MUTED, SURFACE

if TYPE_CHECKING:
    from .page_view import PageView

PT_PER_MM = 72.0 / 25.4
RULER_SIZE = 22


def nice_step_mm(px_per_mm: float, min_px: float) -> float:
    """Pas « rond » (1, 2 ou 5 × 10^n mm) dont l'écart à l'écran vaut au moins ``min_px``."""
    if px_per_mm <= 0 or not math.isfinite(px_per_mm):
        return 1.0
    target = min_px / px_per_mm
    exponent = math.floor(math.log10(target))
    for factor in (1, 2, 5, 10):
        step = factor * 10.0**exponent
        if step >= target:
            return step
    return 10.0 ** (exponent + 1)  # inatteignable : 10 × 10^n est déjà testé


def format_length(mm: float) -> str:
    """Longueur lisible : « 5 mm », « 2,5 cm », « 1 m », « 2,5 m »."""
    value = abs(mm)
    if value >= 1000:
        text, unit = f"{mm / 1000:g}", "m"
    elif value >= 10:
        text, unit = f"{mm / 10:g}", "cm"
    else:
        text, unit = f"{mm:g}", "mm"
    return f"{text.replace('.', ',')} {unit}"


class Ruler(QWidget):
    """Règle horizontale ou verticale synchronisée avec une ``PageView``."""

    def __init__(self, view: PageView, horizontal: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._view = view
        self._horizontal = horizontal
        if horizontal:
            self.setFixedHeight(RULER_SIZE)
        else:
            self.setFixedWidth(RULER_SIZE)
        view.viewChanged.connect(self.update)

    def ticks(self) -> list[tuple[float, float]]:
        """(position dans la règle en pixels, valeur en mm) des graduations principales."""
        z = self._view.zoom
        if z <= 0 or self._view.plan is None:
            return []
        px_per_mm = z * PT_PER_MM
        step = nice_step_mm(px_per_mm, 70.0)
        visible = self._view.visible_scene_rect().intersected(self._view.page_rect())
        if self._horizontal:  # graduations sur la feuille seulement (0 = bord de la feuille)
            lo, hi = visible.left(), visible.right()
        else:
            lo, hi = visible.top(), visible.bottom()
        lo_mm, hi_mm = lo / PT_PER_MM, hi / PT_PER_MM
        first = math.ceil(lo_mm / step) * step
        result = []
        value = first
        while value <= hi_mm + 1e-9 and len(result) < 400:
            scene = value * PT_PER_MM
            point = (
                self._view.mapFromScene(QPointF(scene, 0)).x()
                if self._horizontal
                else self._view.mapFromScene(QPointF(0, scene)).y()
            )
            result.append((float(point), value))
            value += step
        return result

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(SURFACE))
        painter.setPen(QPen(QColor(BORDER), 1))
        if self._horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.setPen(QColor(MUTED))
        font = painter.font()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        offset = self._view.viewport().pos()  # la règle est alignée sur la zone de dessin
        for position, mm in self.ticks():
            if self._horizontal:
                x = position + offset.x()
                painter.drawLine(round(x), self.height() - 7, round(x), self.height() - 1)
                painter.drawText(
                    QRectF(x + 3, 0, 80, self.height() - 6),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    format_length(mm),
                )
            else:
                y = position + offset.y()
                painter.drawLine(self.width() - 7, round(y), self.width() - 1, round(y))
                painter.save()
                painter.translate(self.width() - 9, y - 3)
                painter.rotate(-90)
                painter.drawText(
                    QRectF(0, -self.width() + 9, 80, self.width() - 9),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    format_length(mm),
                )
                painter.restore()
        painter.end()


class Navigator(QWidget):
    """Mini-carte : vignette de la feuille entière avec la zone visible, cliquable et déplaçable."""

    MAX_W, MAX_H = 260, 150

    def __init__(self, view: PageView) -> None:
        super().__init__(view)
        self._view = view
        self._thumb = QImage()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        view.viewChanged.connect(self.refresh)
        self.hide()

    def set_thumbnail(self, image: QImage) -> None:
        self._thumb = image
        if not image.isNull():
            self.setFixedSize(image.width() + 8, image.height() + 8)
        self.refresh()

    def thumb_size(self) -> tuple[int, int]:
        return self._thumb.width(), self._thumb.height()

    def refresh(self) -> None:
        """Se place en bas à droite ; n'apparaît que si la feuille déborde de la vue."""
        view = self._view
        plan = view.plan
        if plan is None or self._thumb.isNull() or not view.navigator_enabled:
            self.hide()
            return
        visible = view.visible_scene_rect()
        page = view.page_rect()
        partial = visible.width() < page.width() * 0.98 or visible.height() < page.height() * 0.98
        self.setVisible(partial)
        if partial:
            sb = view.verticalScrollBar().width() if view.verticalScrollBar().isVisible() else 0
            sh = (
                view.horizontalScrollBar().height() if view.horizontalScrollBar().isVisible() else 0
            )
            self.move(
                view.width() - self.width() - 12 - sb, view.height() - self.height() - 12 - sh
            )
            self.raise_()
        self.update()

    def viewport_rect(self) -> QRectF:
        """Zone visible, en pixels de la vignette."""
        page = self._view.page_rect()
        visible = self._view.visible_scene_rect().intersected(page)
        w, h = self.thumb_size()
        if page.width() <= 0 or page.height() <= 0:
            return QRectF()
        return QRectF(
            4 + visible.left() / page.width() * w,
            4 + visible.top() / page.height() * h,
            visible.width() / page.width() * w,
            visible.height() / page.height() * h,
        )

    def scene_point(self, x: float, y: float) -> QPointF:
        """Point de la feuille (points) désigné par une position dans la vignette."""
        page = self._view.page_rect()
        w, h = self.thumb_size()
        fx = min(max((x - 4) / max(w, 1), 0.0), 1.0)
        fy = min(max((y - 4) / max(h, 1), 0.0), 1.0)
        return QPointF(fx * page.width(), fy * page.height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.setBrush(QColor(SURFACE))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 6, 6)
        painter.drawImage(4, 4, self._thumb)
        rect = self.viewport_rect()
        painter.setPen(QPen(QColor(ACCENT), 1.5))
        fill = QColor(ACCENT)
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawRect(rect)
        painter.end()

    def _move_to(self, event) -> None:
        self._view.centerOn(self.scene_point(event.position().x(), event.position().y()))
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_to(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_to(event)


def scale_bar(px_per_pt: float, min_px: float = 80.0) -> tuple[float, float]:
    """(longueur en mm, longueur en pixels) d'une barre d'échelle ronde d'au moins ``min_px``."""
    px_per_mm = px_per_pt * PT_PER_MM
    mm = nice_step_mm(px_per_mm, min_px)
    return mm, mm * px_per_mm
