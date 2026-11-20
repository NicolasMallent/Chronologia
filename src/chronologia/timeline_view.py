"""Vue de la frise (QGraphicsView) : dessine le résultat de ``layout.compute_layout``."""

from __future__ import annotations

import unicodedata

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QMenu,
)

from .categories import CategoryRegistry
from .layout import Layout, LayoutItem, LayoutOptions, compute_layout
from .measure import make_measurer
from .model import Event
from .shapes import item_shape_path
from .textutil import plain

LEFT_COLUMN = 190.0  # noms des catégories, fixes pendant le défilement horizontal
HEADER = 30.0  # axe des années, fixe pendant le défilement vertical
MARGIN = 24.0
LABEL_ALLOWANCE = 220.0  # place laissée à droite pour le titre du dernier événement
MIN_PX_PER_YEAR = 0.5
MAX_PX_PER_YEAR = 400.0


def _normalize(text: str) -> str:
    """Minuscules sans accents, pour une recherche tolérante."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def event_tooltip(event: Event) -> str:
    dates = event.start.to_display()
    if not event.is_point:
        dates += " → " + event.end.to_display()
    lines = [event.title, dates]
    if event.source:
        lines.append(event.source)
    return "\n".join(lines)


class TimelineView(QGraphicsView):
    layoutChanged = Signal()  # nombre d'événements affichés ou échelle modifiés
    editRequested = Signal(object)  # Event
    deleteRequested = Signal(object)  # Event
    newRequested = Signal(
        str, str
    )  # date de début proposée (aaaa), couleur de la ligne ; vides si inconnues

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self._events: list[Event] = []
        self._registry = CategoryRegistry()
        self._visible: set[str] | None = None
        self._query = ""
        self._ppy = 10.0
        self._layout: Layout | None = None
        self._shift = 0.0  # x de la scène correspondant à x = 0 de la mise en page
        self._font = QFont(self.font())
        self._font.setPointSizeF(9.0)
        self._matches = 0
        self._groups: dict[QGraphicsItemGroup, Event] = {}
        self._selected: Event | None = None  # comparé par identité
        self._halo: QGraphicsRectItem | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # --- données ---------------------------------------------------------------------

    def set_data(self, events: list[Event], registry: CategoryRegistry) -> None:
        self._events = events
        self._registry = registry
        self._visible = None
        self._query = ""
        self.rebuild()
        self.fit_width()

    def set_registry(self, registry: CategoryRegistry) -> None:
        """Change les catégories en gardant filtres, recherche et échelle."""
        self._registry = registry
        self.rebuild()

    def set_events(self, events: list[Event], rebuild: bool = True) -> None:
        """Met à jour les événements en gardant filtres, recherche et échelle."""
        self._events = events
        if rebuild:
            self.rebuild()

    @property
    def selected_event(self) -> Event | None:
        return self._selected

    def select(self, event: Event | None) -> None:
        """Met un événement en valeur (cadre autour de la barre et du titre) ; ``None`` efface."""
        self._selected = event
        self._update_selection()

    def _update_selection(self) -> None:
        if self._halo is not None:
            if self._halo.scene() is not None:
                self._scene.removeItem(self._halo)
            self._halo = None
        if self._selected is None:
            return
        for group, candidate in self._groups.items():
            if candidate is self._selected:
                accent = self.palette().highlight().color()
                fill = QColor(accent)
                fill.setAlpha(45)
                rect = group.sceneBoundingRect().adjusted(-4, -3, 4, 3)
                halo = QGraphicsRectItem(rect)
                halo.setPen(QPen(accent, 2.5))
                halo.setBrush(fill)
                halo.setZValue(-1)  # sous l'événement : sa couleur reste lisible
                self._scene.addItem(halo)
                self._halo = halo
                return

    def reveal(self, event: Event) -> None:
        """Amène un événement dans la zone visible, s'il est affiché."""
        for group, candidate in self._groups.items():
            if candidate is event:
                self.ensureVisible(group, 80, 80)
                return

    def year_at_view_x(self, view_x: float) -> float | None:
        if self._layout is None or not self._layout.lanes:
            return None
        scene_x = self.horizontalScrollBar().value() + view_x
        return self._layout.t_start + (scene_x - self._shift) / self._ppy

    def lane_color_at(self, view_y: float) -> str:
        """Couleur (``#rrggbb``) de la catégorie dont la ligne est à cette hauteur ; vide sinon."""
        if self._layout is None:
            return ""
        scene_y = self.mapToScene(0, round(view_y)).y()
        for lane in self._layout.lanes:  # les bandes se touchent : 7 px de marge de chaque côté
            top = HEADER + lane.y - 7
            if top <= scene_y < top + lane.height + 14:
                return lane.color_hex
        return ""

    def set_visible_categories(self, names: set[str] | None) -> None:
        self._visible = names
        self.rebuild()

    def set_search(self, text: str) -> None:
        self._query = _normalize(text.strip())
        self.rebuild()

    @property
    def visible_categories(self) -> set[str] | None:
        """Catégories affichées (``None`` : toutes)."""
        return self._visible

    @property
    def displayed_count(self) -> int:
        return sum(len(lane.items) for lane in self._layout.lanes) if self._layout else 0

    @property
    def hidden_titles(self) -> int:
        """Nombre de titres cachés faute de place à l'échelle actuelle."""
        return self._layout.titles_hidden if self._layout is not None else 0

    @property
    def match_count(self) -> int | None:
        """Nombre d'événements correspondant à la recherche (``None`` sans recherche)."""
        return self._matches if self._query else None

    # --- zoom ------------------------------------------------------------------------

    def zoom_by(self, factor: float, anchor_view_x: float | None = None) -> None:
        self.set_scale(self._ppy * factor, anchor_view_x)

    def set_scale(self, px_per_year: float, anchor_view_x: float | None = None) -> None:
        new = min(max(px_per_year, MIN_PX_PER_YEAR), MAX_PX_PER_YEAR)
        if new == self._ppy or self._layout is None:
            return
        vx = self.viewport().width() / 2 if anchor_view_x is None else anchor_view_x
        bar = self.horizontalScrollBar()
        year = self._layout.t_start + (bar.value() + vx - self._shift) / self._ppy
        self._ppy = new
        self.rebuild()
        if self._layout is not None:
            bar.setValue(round(self._shift + (year - self._layout.t_start) * new - vx))

    def fit_width(self) -> None:
        if self._layout is None or not self._layout.lanes:
            return
        years = max(self._layout.t_end - self._layout.t_start, 1.0)
        usable = self.viewport().width() - LEFT_COLUMN - 2 * MARGIN - LABEL_ALLOWANCE
        self._ppy = min(max(max(usable, 100.0) / years, MIN_PX_PER_YEAR), MAX_PX_PER_YEAR)
        self.rebuild()
        self.horizontalScrollBar().setValue(0)

    def wheelEvent(self, event) -> None:
        """Molette : zoom autour du curseur. Maj + molette : défilement vertical."""
        delta = event.angleDelta()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - (delta.y() or delta.x()))
            event.accept()
        elif delta.y() != 0:
            self.zoom_by(1.15 ** (delta.y() / 120), event.position().x())
            event.accept()
        else:  # défilement horizontal (pavé tactile)
            super().wheelEvent(event)

    # --- interactions d'édition ------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.select(self._event_at(event.position().toPoint()))
        super().mousePressEvent(event)

    def _event_at(self, pos) -> Event | None:
        item = self.itemAt(pos)
        while item is not None and item not in self._groups:
            item = item.parentItem()
        return self._groups.get(item) if item is not None else None

    def mouseDoubleClickEvent(self, event) -> None:
        found = self._event_at(event.position().toPoint())
        if found is not None:
            self.editRequested.emit(found)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        """Suppr : supprime l'événement sélectionné (après confirmation) ; Échap : désélectionne."""
        if event.key() == Qt.Key.Key_Delete and self._selected is not None:
            self.deleteRequested.emit(self._selected)
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self._selected is not None:
            self.select(None)
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        found = self._event_at(event.pos())
        menu = QMenu(self)
        if found is not None:
            menu.addAction(self.tr("Modifier…")).triggered.connect(
                lambda: self.editRequested.emit(found)
            )
            menu.addAction(self.tr("Supprimer")).triggered.connect(
                lambda: self.deleteRequested.emit(found)
            )
        else:
            year = self.year_at_view_x(event.pos().x())
            hint = f"{int(year):04d}" if year is not None and year >= 1 else ""
            color = self.lane_color_at(event.pos().y())
            menu.addAction(self.tr("Nouvel événement ici…")).triggered.connect(
                lambda: self.newRequested.emit(hint, color)
            )
        menu.exec(event.globalPos())

    # --- construction de la scène ----------------------------------------------------

    def rebuild(self) -> None:
        self._scene.clear()
        self._groups = {}
        self._halo = None
        measure, line_height = make_measurer(self._font)
        opts = LayoutOptions(px_per_year=self._ppy, line_height=line_height)
        self._layout = compute_layout(
            self._events,
            self._registry,
            measure,
            opts,
            visible_categories=self._visible,
            include_empty=True,
        )
        layout = self._layout
        self._matches = 0
        if not layout.lanes:
            self._shift = 0.0
            self._scene.setSceneRect(QRectF(0, 0, 1, 1))
            self.layoutChanged.emit()
            self.viewport().update()
            return

        self._shift = LEFT_COLUMN + MARGIN - layout.x_min
        for lane in layout.lanes:
            for item in lane.items:
                self._add_item(item, opts)
        self._scene.setSceneRect(
            QRectF(
                0,
                0,
                self._shift + layout.x_max + MARGIN,
                HEADER + layout.height + 2 * MARGIN,
            )
        )
        self._update_selection()
        self.layoutChanged.emit()
        self.viewport().update()

    def _add_item(self, item: LayoutItem, opts: LayoutOptions) -> None:
        event = item.event
        color = QColor(event.color_hex)
        pen = QPen(color.darker(120), 1.1)
        text_color = self.palette().text().color()
        top = HEADER + item.y
        group = QGraphicsItemGroup()

        shape = QGraphicsPathItem(item_shape_path(item, opts.point_width, self._shift, HEADER))
        if item.is_point:
            shape.setBrush(color)
        else:
            fill = QColor(color)
            fill.setAlpha(80)
            shape.setBrush(fill)
        shape.setPen(pen)
        group.addToGroup(shape)

        first_y = top + (item.height - len(item.label_lines) * opts.line_height) / 2
        for i, line in enumerate(item.label_lines):
            text = QGraphicsSimpleTextItem(line)
            text.setFont(self._font)
            text.setBrush(text_color)
            text.setPos(self._shift + item.label_x, first_y + i * opts.line_height)
            group.addToGroup(text)

        group.setToolTip(plain(event_tooltip(event)))
        self._groups[group] = event
        if self._query:
            haystack = _normalize(f"{event.title} {event.source}")
            if self._query in haystack:
                self._matches += 1
            else:
                group.setOpacity(0.2)
        self._scene.addItem(group)

    # --- fond et avant-plan (axe et noms de catégories fixes) -----------------------------

    def _visible_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self.palette().base())
        layout = self._layout
        if layout is None or not layout.lanes:
            return
        band = QColor(self.palette().alternateBase().color())
        for i, lane in enumerate(layout.lanes):
            if i % 2 == 0:
                painter.fillRect(
                    QRectF(rect.left(), HEADER + lane.y - 7, rect.width(), lane.height + 14), band
                )
        grid = QPen(self.palette().mid().color(), 0.8, Qt.PenStyle.DotLine)
        painter.setPen(grid)
        for tick in layout.ticks:
            x = self._shift + tick.x
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        layout = self._layout
        visible = self._visible_rect()
        base = self.palette().base()
        text_color = self.palette().text().color()
        muted = self.palette().placeholderText().color()
        line_color = self.palette().midlight().color()
        painter.setFont(self._font)

        if layout is None or not layout.lanes:
            painter.setPen(muted)
            painter.drawText(
                visible, Qt.AlignmentFlag.AlignCenter, self.tr("Ouvrez un fichier CSV (Ctrl+O)")
            )
            return

        # axe des années
        header = QRectF(visible.left(), visible.top(), visible.width(), HEADER)
        painter.fillRect(header, base)
        painter.setPen(muted)
        for tick in layout.ticks:
            x = self._shift + tick.x
            painter.drawText(
                QRectF(x - 30, visible.top(), 60, HEADER),
                Qt.AlignmentFlag.AlignCenter,
                tick.label,
            )
        painter.setPen(QPen(line_color, 1))
        painter.drawLine(
            QPointF(visible.left(), visible.top() + HEADER),
            QPointF(visible.right(), visible.top() + HEADER),
        )

        # colonne des catégories
        painter.fillRect(QRectF(visible.left(), visible.top(), LEFT_COLUMN, visible.height()), base)
        painter.setPen(QPen(line_color, 1))
        painter.drawLine(
            QPointF(visible.left() + LEFT_COLUMN, visible.top()),
            QPointF(visible.left() + LEFT_COLUMN, visible.bottom()),
        )
        bold = QFont(self._font)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        metrics = painter.fontMetrics()
        for lane in layout.lanes:
            y = HEADER + lane.y
            painter.setBrush(QColor(lane.color_hex))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(visible.left() + 16, y + 9), 5.5, 5.5)
            painter.setPen(text_color)
            name = metrics.elidedText(lane.name, Qt.TextElideMode.ElideRight, int(LEFT_COLUMN - 40))
            painter.drawText(QPointF(visible.left() + 30, y + 13), name)
