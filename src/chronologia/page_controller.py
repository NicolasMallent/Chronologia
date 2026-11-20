"""Calcule la mise en page de la feuille quand les données ou les réglages changent.

Les mises en page candidates (``PosterPlanner``, ~48 calculs) ne dépendent ni du format ni du
titre : un changement de format ne recalcule que le choix final (instantané). Les changements
d'événements, de catégories, de filtres, de période ou de lignes par titre refont les candidats
(temporisé, car quelques centaines de millisecondes avec beaucoup d'événements).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QObject, QTimer, Signal

from .categories import CategoryRegistry
from .layout import end_position, start_position
from .model import Event
from .page_panel import PagePanel
from .pdf_export import export_divisor
from .poster import PosterPlan, PosterPlanner

REBUILD_DELAY_MS = 300
REPLAN_DELAY_MS = 60


class PageController(QObject):
    planChanged = Signal(object)  # PosterPlan | None

    def __init__(self, panel: PagePanel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.panel = panel
        self._events: list[Event] = []
        self._registry = CategoryRegistry()
        self._visible: set[str] | None = None
        self._planner: PosterPlanner | None = None
        self._planner_dirty = True
        self._active = False
        self.plan: PosterPlan | None = None
        self.divisor = 1

        self._rebuild_timer = QTimer(self, singleShot=True, interval=REBUILD_DELAY_MS)
        self._rebuild_timer.timeout.connect(self._rebuild)
        self._replan_timer = QTimer(self, singleShot=True, interval=REPLAN_DELAY_MS)
        self._replan_timer.timeout.connect(self._replan)
        panel.settingsChanged.connect(self._settings_changed)
        panel.plannerSettingsChanged.connect(self._planner_settings_changed)

    # --- entrées ------------------------------------------------------------------------------

    def set_data(
        self, events: list[Event], registry: CategoryRegistry, visible: set[str] | None
    ) -> None:
        """Nouvelles données (événements, catégories ou filtre) : les candidats sont à refaire."""
        self._events, self._registry, self._visible = events, registry, visible
        shown = [e for e in events if visible is None or registry.category_name(e) in visible]
        if shown:
            low = max(1, math.floor(min(start_position(e.start) for e in shown)))
            high = math.ceil(max(end_position(e.end) for e in shown))
            self.panel.set_year_bounds(low, high)
        self._planner_dirty = True
        if self._active:
            self._rebuild_timer.start()

    def activate(self, active: bool) -> None:
        """Le mode Feuille est affiché (le calcul est inutile sinon)."""
        self._active = active
        if active:
            self.ensure_current()

    def _settings_changed(self) -> None:
        if self._active:
            self._replan_timer.start()

    def _planner_settings_changed(self) -> None:
        self._planner_dirty = True
        if self._active:
            self._rebuild_timer.start()

    # --- calcul ---------------------------------------------------------------------------------

    def ensure_current(self) -> PosterPlan | None:
        """Termine tout calcul en attente et renvoie la mise en page à jour."""
        self._rebuild_timer.stop()
        self._replan_timer.stop()
        if self._planner_dirty or self._planner is None:
            self._rebuild()
        else:
            self._replan()
        return self.plan

    def _rebuild(self) -> None:
        self._rebuild_timer.stop()
        s = self.panel.settings()
        self._planner = PosterPlanner(
            self._events,
            self._registry,
            self._visible,
            s.time_range,
            max_label_lines=s.max_label_lines,
        )
        self._planner_dirty = False
        self._replan()

    def _replan(self) -> None:
        self._replan_timer.stop()
        planner = self._planner
        if planner is None or planner.is_empty:
            self.plan, self.divisor = None, 1
        else:
            s = self.panel.settings()
            self.plan = planner.plan(s.width_mm, s.height_mm, s.title, s.font_pt)
            self.divisor = export_divisor(s.width_mm, s.height_mm)
        self.panel.show_plan(self.plan, self.divisor)
        self.planChanged.emit(self.plan)
