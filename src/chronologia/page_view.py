"""Vue « Feuille » : la frise telle qu'elle sera imprimée, sur une feuille aux dimensions réelles.

La scène est exprimée en **points** (1 unité = 1/72 pouce) ; la feuille est dessinée par
``poster.paint_poster``, exactement comme dans le PDF. Le zoom est une simple caméra : il ne
modifie pas la mise en page (calculée par ``PosterPlanner`` pour le format choisi).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGridLayout,
    QToolTip,
    QWidget,
)

from .editing_view import EditableView
from .model import Event
from .poster import PosterPlan, paint_poster, render_preview
from .rulers import RULER_SIZE, Navigator, Ruler, format_length, scale_bar
from .textutil import plain
from .theme import MUTED, SURFACE
from .timeline_view import _normalize, event_tooltip

ZOOM_MAX = 32.0  # pixels d'écran par point de la feuille
MIN_ZOOM_FACTOR = 0.5  # on peut dézoomer jusqu'à la moitié de « feuille entière »
WHEEL_STEP = 1.15
PASTEBOARD = "#d9dce6"
DEFAULT_DPI = 96.0


class _PageItem(QGraphicsItem):
    """La feuille : fond blanc et dessin vectoriel, limité à la zone exposée."""

    def __init__(self, view: PageView) -> None:
        super().__init__()
        self._view = view

    def boundingRect(self) -> QRectF:
        return self._view.page_rect()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        plan = self._view.plan
        if plan is None:
            return
        painter.fillRect(self.boundingRect(), QColor("#ffffff"))
        exposed = option.exposedRect.intersected(self.boundingRect())
        if exposed.isEmpty():
            return
        painter.save()
        plan.apply_transform(painter)
        paint_poster(
            painter,
            plan,
            clip=plan.design_rect(exposed).adjusted(-30, -30, 30, 30),
            dimmed=self._view.dimmed,
            selected=self._view.selected_event,
        )
        painter.restore()


class PageView(EditableView):
    zoomChanged = Signal(float)
    viewChanged = (
        Signal()
    )  # défilement, zoom ou redimensionnement : règles et mini-carte se mettent à jour

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(EditableView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(EditableView.ViewportUpdateMode.FullViewportUpdate)
        self.setBackgroundBrush(QColor(PASTEBOARD))
        self.setTransformationAnchor(EditableView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(EditableView.ViewportAnchor.NoAnchor)
        self.plan: PosterPlan | None = None
        self.navigator_enabled = True
        self._zoom = 1.0
        self._query = ""
        self._item: _PageItem | None = None
        self.navigator = Navigator(self)

    # --- feuille -----------------------------------------------------------------------

    def page_rect(self) -> QRectF:
        if self.plan is None:
            return QRectF(0, 0, 1, 1)
        return QRectF(0, 0, self.plan.page_width_pt, self.plan.page_height_pt)

    def _margin(self) -> float:
        page = self.page_rect()
        return max(18.0, 0.04 * max(page.width(), page.height()))

    def set_plan(self, plan: PosterPlan | None) -> None:
        """Affiche une mise en page. Un changement de format recadre la vue sur la feuille."""
        old = self.page_rect()
        self.plan = plan
        self._scene.clear()
        self._item = None
        if plan is None:
            self._scene.setSceneRect(QRectF(0, 0, 1, 1))
            self.resetTransform()
            self.navigator.set_thumbnail(QImage())
            self.viewport().update()
            self.viewChanged.emit()
            return
        self._item = _PageItem(self)
        self._scene.addItem(self._item)
        m = self._margin()
        self._scene.setSceneRect(self.page_rect().adjusted(-m, -m, m, m))
        new = self.page_rect()
        if (old.width(), old.height()) != (new.width(), new.height()) or self._zoom <= 0:
            self.fit_page()
        else:
            self.viewChanged.emit()
        self._refresh_thumbnail()
        self.viewport().update()

    def _refresh_thumbnail(self) -> None:
        plan = self.plan
        if plan is None:
            return
        ratio = plan.page_height_pt / plan.page_width_pt
        width = max(40, min(Navigator.MAX_W, round(Navigator.MAX_H / ratio)))
        self.navigator.set_thumbnail(render_preview(plan, width))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(PASTEBOARD))
        if self.plan is None:
            return
        page = self.page_rect()
        shadow = max(3.0, 5.0 / max(self._zoom, 1e-6))  # ombre d'environ 5 px à l'écran
        painter.fillRect(page.translated(shadow, shadow), QColor(0, 0, 0, 55))
        painter.fillRect(page, QColor("#ffffff"))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if self.plan is None:
            painter.setPen(QColor(MUTED))
            painter.drawText(
                self.mapToScene(self.viewport().rect()).boundingRect(),
                Qt.AlignmentFlag.AlignCenter,
                self.tr("Aucun événement à afficher"),
            )
            return
        painter.setPen(QPen(QColor(0, 0, 0, 60), 0))  # cosmétique : filet de 1 px
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.page_rect())

    # --- recherche ---------------------------------------------------------------------

    def set_search(self, text: str) -> None:
        self._query = _normalize(text.strip())
        if self._item is not None:
            self._item.update()
        self.viewport().update()

    def dimmed(self, event: Event) -> bool:
        if not self._query:
            return False
        return self._query not in _normalize(f"{event.title} {event.source}")

    @property
    def match_count(self) -> int | None:
        if not self._query or self.plan is None:
            return None
        return sum(1 for item in self.plan.layout.items() if not self.dimmed(item.event))

    # --- caméra : zoom -----------------------------------------------------------------

    @property
    def zoom(self) -> float:
        """Pixels d'écran par point de la feuille."""
        return self._zoom

    def screen_dpi(self) -> float:
        screen = self.screen()
        dpi = screen.physicalDotsPerInch() if screen is not None else DEFAULT_DPI
        return dpi if math.isfinite(dpi) and 48.0 <= dpi <= 400.0 else DEFAULT_DPI

    def real_size_zoom(self) -> float:
        """Zoom pour lequel 1 cm de la feuille mesure 1 cm à l'écran."""
        return self.screen_dpi() / 72.0

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _fit_zoom(self, rect: QRectF, width: bool = True, height: bool = True) -> float:
        vw, vh = max(self.viewport().width(), 1), max(self.viewport().height(), 1)
        candidates = []
        if width:
            candidates.append(vw / rect.width())
        if height:
            candidates.append(vh / rect.height())
        return min(candidates) if candidates else 1.0

    def min_zoom(self) -> float:
        scene = self._scene.sceneRect()
        return max(1e-5, MIN_ZOOM_FACTOR * self._fit_zoom(scene))

    def set_zoom(self, zoom: float, anchor: QPoint | None = None) -> None:
        """Fixe le zoom (borné) ; le point ``anchor`` de la vue reste immobile (centre par défaut)."""
        zoom = min(max(zoom, self.min_zoom()), ZOOM_MAX)
        if anchor is None:
            anchor = self.viewport().rect().center()
        before = self.mapToScene(anchor)
        self._zoom = zoom
        self.setTransform(QTransform.fromScale(zoom, zoom))
        after = self.mapToScene(anchor)
        delta = before - after
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + round(delta.x() * zoom)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + round(delta.y() * zoom)
        )
        self.zoomChanged.emit(zoom)
        self.viewChanged.emit()
        self.viewport().update()

    def zoom_by(self, factor: float, anchor: QPoint | None = None) -> None:
        self.set_zoom(self._zoom * factor, anchor)

    def fit_page(self) -> None:
        """Feuille entière (avec sa marge) dans la vue."""
        scene = self._scene.sceneRect()
        self.set_zoom(self._fit_zoom(scene))
        self.centerOn(scene.center())
        self.viewChanged.emit()

    def fit_width(self) -> None:
        """Largeur de la feuille = largeur de la vue (on voit le haut de la feuille)."""
        scene = self._scene.sceneRect()
        self.set_zoom(self._fit_zoom(scene, height=False))
        self.centerOn(scene.center().x(), scene.top() + self.viewport().height() / 2 / self._zoom)
        self.viewChanged.emit()

    def fit_height(self) -> None:
        """Hauteur de la feuille = hauteur de la vue (on voit le début, à gauche)."""
        scene = self._scene.sceneRect()
        self.set_zoom(self._fit_zoom(scene, width=False))
        self.centerOn(scene.left() + self.viewport().width() / 2 / self._zoom, scene.center().y())
        self.viewChanged.emit()

    def actual_size(self) -> None:
        """Taille réelle : 1 cm de la feuille = 1 cm à l'écran (autour du centre de la vue)."""
        self.set_zoom(self.real_size_zoom())

    # --- molette, clavier ----------------------------------------------------------------

    def wheelEvent(self, event) -> None:
        """Molette : zoom autour du curseur. Maj : défilement vertical. Alt : horizontal."""
        delta = event.angleDelta()
        step = delta.y() or delta.x()
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - step)
            event.accept()
        elif modifiers & Qt.KeyboardModifier.AltModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - step)
            event.accept()
        elif delta.y() != 0:
            self.zoom_by(WHEEL_STEP ** (delta.y() / 120), event.position().toPoint())
            event.accept()
        else:  # défilement horizontal (pavé tactile)
            super().wheelEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewChanged.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.viewChanged.emit()

    # --- survol et édition -----------------------------------------------------------------

    def _event_at(self, pos) -> Event | None:
        if self.plan is None:
            return None
        scene = self.mapToScene(pos)
        return self.plan.event_at(scene.x(), scene.y(), tolerance=3.0 / max(self._zoom, 1e-6))

    def _year_hint(self, pos) -> str:
        if self.plan is None:
            return ""
        year = self.plan.year_at(self.mapToScene(pos).x())
        return f"{int(year):04d}" if year is not None and year >= 1 else ""

    def lane_color_at(self, view_y: float) -> str:
        if self.plan is None:
            return ""
        return self.plan.lane_color_at(self.mapToScene(0, round(view_y)).y())

    def _update_selection(self) -> None:
        if self._item is not None:
            self._item.update()
        self.viewport().update()

    def reveal(self, event: Event) -> None:
        """Amène un événement dans la zone visible, s'il est affiché."""
        if self.plan is None:
            return
        item = self.plan.item_of(event)
        if item is not None:
            self.ensureVisible(self.plan.item_rect(item), 80, 80)

    def viewportEvent(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            found = self._event_at(event.pos())
            if found is not None:
                QToolTip.showText(event.globalPos(), plain(event_tooltip(found)), self.viewport())
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)

    # --- indicateurs superposés ------------------------------------------------------------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.plan is None:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        mm, px = scale_bar(self._zoom)
        percent = round(self._zoom / self.real_size_zoom() * 100)
        label = f"{format_length(mm)}  —  {percent} %"
        font = painter.font()
        font.setPointSizeF(8.5)
        painter.setFont(font)
        width = max(px, painter.fontMetrics().horizontalAdvance(label)) + 20
        box = QRectF(10, self.viewport().height() - 44, width, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(SURFACE))
        painter.setOpacity(0.92)
        painter.drawRoundedRect(box, 6, 6)
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor("#374151"), 2))
        y = box.top() + 9
        painter.drawLine(QPointF(box.left() + 10, y), QPointF(box.left() + 10 + px, y))
        painter.drawLine(QPointF(box.left() + 10, y - 3), QPointF(box.left() + 10, y + 3))
        painter.drawLine(QPointF(box.left() + 10 + px, y - 3), QPointF(box.left() + 10 + px, y + 3))
        painter.setPen(QColor("#374151"))
        painter.drawText(QPointF(box.left() + 10, box.bottom() - 7), label)
        painter.end()


class PageContainer(QWidget):
    """Vue Feuille encadrée de ses règles (la mini-carte flotte dans la vue)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = PageView()
        self.ruler_h = Ruler(self.view, horizontal=True)
        self.ruler_v = Ruler(self.view, horizontal=False)
        self._corner = QWidget()
        self._corner.setFixedSize(RULER_SIZE, RULER_SIZE)
        self._corner.setStyleSheet(f"background: {SURFACE};")
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        grid.addWidget(self._corner, 0, 0)
        grid.addWidget(self.ruler_h, 0, 1)
        grid.addWidget(self.ruler_v, 1, 0)
        grid.addWidget(self.view, 1, 1)

    def set_rulers_visible(self, visible: bool) -> None:
        for widget in (self.ruler_h, self.ruler_v, self._corner):
            widget.setVisible(visible)

    def set_navigator_enabled(self, enabled: bool) -> None:
        self.view.navigator_enabled = enabled
        self.view.navigator.refresh()
