"""Boîte de dialogue d'export PDF : format de page, titre, période, aperçu."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .categories import CategoryRegistry
from .layout import end_position, start_position
from .model import Event
from .pdf_export import PAGE_SIZES_MM, PDF_COMFORT_LIMIT_MM
from .poster import PosterPlan, PosterPlanner, render_preview

MIN_READABLE_PT = 6.0
MIN_SIDE_CM, MAX_SIDE_CM = 10.0, 1000.0
CUSTOM = "custom"


class ExportDialog(QDialog):
    def __init__(
        self,
        events: list[Event],
        registry: CategoryRegistry,
        visible: set[str] | None,
        default_title: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Exporter en PDF"))
        self._events, self._registry, self._visible = events, registry, visible
        self._planner: PosterPlanner | None = None
        self._plan: PosterPlan | None = None

        shown = [e for e in events if visible is None or registry.category_name(e) in visible]
        self._year_bounds = (
            (
                max(1, math.floor(min(start_position(e.start) for e in shown))),
                math.ceil(max(end_position(e.end) for e in shown)),
            )
            if shown
            else (1, 2)
        )

        self.format = QComboBox()
        for name in PAGE_SIZES_MM:
            self.format.addItem(name, name)
        self.format.addItem(self.tr("Personnalisé"), CUSTOM)
        self.format.setCurrentIndex(self.format.findData("A0"))
        self.landscape = QComboBox()
        self.landscape.addItem(self.tr("Paysage"), True)
        self.landscape.addItem(self.tr("Portrait"), False)
        self.width_cm = self._side_spin()
        self.height_cm = self._side_spin()
        size_row = QHBoxLayout()
        for widget in (self.width_cm, QLabel("×"), self.height_cm, QLabel("cm")):
            size_row.addWidget(widget)

        self.title = QLineEdit(default_title)
        self.title.setPlaceholderText(self.tr("Titre affiché en haut de la frise (facultatif)"))

        self.limit_period = QCheckBox(self.tr("Limiter à la période"))
        low, high = self._year_bounds
        self.year_from = QSpinBox()
        self.year_to = QSpinBox()
        for spin, value in ((self.year_from, low), (self.year_to, high)):
            spin.setRange(1, 9999)
            spin.setValue(value)
            spin.setEnabled(False)
        period_row = QHBoxLayout()
        for widget in (self.limit_period, self.year_from, QLabel("→"), self.year_to):
            period_row.addWidget(widget)
        period_row.addStretch()

        self._info = QLabel()
        self._info.setWordWrap(True)
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet("color: #b00020;")
        self._preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(720, 360)
        self._preview.setStyleSheet("background: #888;")

        form = QFormLayout()
        form.addRow(self.tr("Format"), self.format)
        form.addRow(self.tr("Orientation"), self.landscape)
        form.addRow(self.tr("Dimensions"), size_row)
        form.addRow(self.tr("Titre"), self.title)
        form.addRow(self.tr("Période"), period_row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Exporter…"))
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._info)
        layout.addWidget(self._warning)
        layout.addWidget(self._preview, 1)
        layout.addWidget(self._buttons)

        # recalcul différé : le calcul des mises en page prend quelques centaines de ms
        self._rebuild_timer = QTimer(self, singleShot=True, interval=300)
        self._rebuild_timer.timeout.connect(self._rebuild)
        self._refresh_timer = QTimer(self, singleShot=True, interval=120)
        self._refresh_timer.timeout.connect(self.refresh)

        self.format.currentIndexChanged.connect(self._apply_format)
        self.landscape.currentIndexChanged.connect(self._apply_format)
        self.width_cm.valueChanged.connect(self._size_edited)
        self.height_cm.valueChanged.connect(self._size_edited)
        self.title.textChanged.connect(self._refresh_timer.start)
        self.limit_period.toggled.connect(self._period_toggled)
        self.year_from.valueChanged.connect(self._rebuild_timer.start)
        self.year_to.valueChanged.connect(self._rebuild_timer.start)

        self._apply_format()
        self._rebuild()

    # --- accès ---------------------------------------------------------------------------

    def _side_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(MIN_SIDE_CM, MAX_SIDE_CM)
        spin.setDecimals(1)
        spin.setSingleStep(5.0)
        return spin

    def plan(self) -> PosterPlan | None:
        """Mise en page correspondant aux réglages actuels."""
        return self._plan

    def document_title(self) -> str:
        return self.title.text().strip()

    # --- réglages ------------------------------------------------------------------------

    def _apply_format(self) -> None:
        key = self.format.currentData()
        if key != CUSTOM:
            w, h = PAGE_SIZES_MM[key]
            if self.landscape.currentData():
                w, h = h, w
            self._set_size(w / 10, h / 10)
        self.landscape.setEnabled(key != CUSTOM)
        self.refresh()

    def _set_size(self, width_cm: float, height_cm: float) -> None:
        for spin, value in ((self.width_cm, width_cm), (self.height_cm, height_cm)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _size_edited(self) -> None:
        self.format.blockSignals(True)
        self.format.setCurrentIndex(self.format.findData(CUSTOM))
        self.format.blockSignals(False)
        self.landscape.setEnabled(False)
        self._refresh_timer.start()

    def _period_toggled(self, on: bool) -> None:
        self.year_from.setEnabled(on)
        self.year_to.setEnabled(on)
        self._rebuild_timer.start()

    def _time_range(self) -> tuple[float, float] | None:
        if not self.limit_period.isChecked():
            return None
        start, end = sorted((self.year_from.value(), self.year_to.value()))
        return float(start), float(end + 1)  # l'année de fin est incluse

    # --- calcul --------------------------------------------------------------------------

    def _rebuild(self) -> None:
        self._planner = PosterPlanner(
            self._events, self._registry, self._visible, self._time_range()
        )
        self.refresh()

    def refresh(self) -> None:
        """Recalcule le plan pour la page actuelle et met à jour l'aperçu et les messages."""
        if self._planner is None:
            return
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self._planner.is_empty:
            self._plan = None
            self._info.setText(self.tr("Aucun événement à exporter avec les filtres actuels."))
            self._warning.clear()
            self._preview.clear()
            ok_button.setEnabled(False)
            return
        width_mm, height_mm = self.width_cm.value() * 10, self.height_cm.value() * 10
        self._plan = self._planner.plan(width_mm, height_mm, self.title.text())
        plan = self._plan
        self._info.setText(
            self.tr("%1 événements, %2 catégories. Taille du texte sur la page : %3 pt.")
            .replace("%1", str(plan.event_count))
            .replace("%2", str(len(plan.layout.lanes)))
            .replace("%3", f"{plan.font_pt:.1f}")
        )
        warnings = []
        if plan.font_pt < MIN_READABLE_PT:
            warnings.append(
                self.tr(
                    "Texte très petit : choisissez un format plus grand ou une période plus courte."
                )
            )
        if max(width_mm, height_mm) > PDF_COMFORT_LIMIT_MM:
            warnings.append(
                self.tr(
                    "Au-delà de 5 m, certains lecteurs PDF refusent la page. Le PDF est vectoriel : "
                    "exportez à la moitié ou au dixième de la taille, puis agrandissez à l'impression."
                )
            )
        self._warning.setText("\n".join(warnings))
        ok_button.setEnabled(True)
        image = render_preview(plan, 1400)
        self._preview.setPixmap(
            QPixmap.fromImage(image).scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_timer.start()
