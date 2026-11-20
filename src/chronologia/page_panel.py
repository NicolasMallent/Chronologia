"""Panneau de réglage de la feuille (mode Feuille) : format, titre, période, texte."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .formats import (
    MAX_SIDE_MM,
    MIN_SIDE_MM,
    STANDARD_FORMATS,
    FormatError,
    PageFormat,
    PageSettings,
    check_format,
)
from .pdf_export import PDF_COMFORT_LIMIT_MM
from .poster import DEFAULT_FONT_PT, DEFAULT_MAX_LABEL_LINES, PosterPlan
from .rulers import format_length
from .textutil import plain

MIN_READABLE_PT = 6.0
CUSTOM = "\0custom"  # clé interne du format « Personnalisé » (aucun nom de format ne la contient)
DEFAULT_FORMAT = "A0"


def format_error_text(exc: FormatError) -> str:
    """Erreur de format de feuille, dans la langue de l'interface."""
    if exc.code == FormatError.NAME_INVALID:
        return QCoreApplication.translate("Formats", "Le nom du format est vide ou trop long.")
    if exc.code == FormatError.NAME_EXISTS:
        return QCoreApplication.translate("Formats", "Un format porte déjà ce nom.")
    if exc.code == FormatError.SIZE_INVALID:
        return QCoreApplication.translate(
            "Formats", "Les dimensions doivent être comprises entre 5 cm et 20 m."
        )
    if exc.code == FormatError.TOO_MANY:
        return QCoreApplication.translate("Formats", "Trop de formats enregistrés.")
    return str(exc)


class PagePanel(QWidget):
    """Réglages de la feuille. N'effectue aucun calcul : il émet des signaux.

    ``settingsChanged`` : taille, titre ou taille minimale du texte (recalcul instantané) ;
    ``plannerSettingsChanged`` : période ou lignes par titre (les mises en page candidates sont
    à recalculer) ; ``formatsChanged`` : formats personnalisés ajoutés ou supprimés.
    """

    settingsChanged = Signal()
    plannerSettingsChanged = Signal()
    formatsChanged = Signal(object)  # list[PageFormat]
    exportRequested = Signal()

    def __init__(
        self,
        custom_formats: list[PageFormat] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._presets: list[PageFormat] = list(custom_formats or [])
        self._year_bounds = (1, 2)

        self.format = QComboBox()
        self.landscape = QComboBox()
        self.landscape.addItem(self.tr("Paysage"), True)
        self.landscape.addItem(self.tr("Portrait"), False)
        self.width_cm = self._side_spin()
        self.height_cm = self._side_spin()
        size_row = QHBoxLayout()
        for widget in (self.width_cm, QLabel("×"), self.height_cm, QLabel("cm")):
            size_row.addWidget(widget)
        self.save_format = QPushButton(self.tr("Enregistrer ce format…"))
        self.delete_format = QPushButton(self.tr("Supprimer ce format"))
        format_buttons = QVBoxLayout()  # l'un sous l'autre : le panneau reste étroit
        format_buttons.setSpacing(4)
        format_buttons.addWidget(self.save_format)
        format_buttons.addWidget(self.delete_format)

        self.title = QLineEdit()
        self.title.setPlaceholderText(self.tr("Titre affiché en haut de la frise (facultatif)"))

        self.limit_period = QCheckBox(self.tr("Limiter à la période"))
        self.year_from = QSpinBox()
        self.year_to = QSpinBox()
        for spin in (self.year_from, self.year_to):
            spin.setRange(1, 9999)
            spin.setEnabled(False)
        period_row = QHBoxLayout()
        for widget in (self.year_from, QLabel("→"), self.year_to):
            period_row.addWidget(widget)

        self.text_size = QDoubleSpinBox()
        self.text_size.setRange(2.0, 72.0)
        self.text_size.setDecimals(1)
        self.text_size.setSingleStep(0.5)
        self.text_size.setSuffix(" pt")
        self.text_size.setValue(DEFAULT_FONT_PT)
        self.text_size.setToolTip(
            self.tr(
                "Taille du texte sur la feuille. La frise s'élargit quand le texte est plus petit : "
                "plus de titres s'affichent en entier."
            )
        )
        self.max_lines = QSpinBox()
        self.max_lines.setRange(1, 6)
        self.max_lines.setValue(DEFAULT_MAX_LABEL_LINES)
        self.max_lines.setToolTip(
            self.tr(
                "Un titre trop long pour la place disponible passe sur plusieurs lignes "
                "(jusqu'à ce nombre) : plus de titres s'affichent en entier, "
                "mais les lignes de la frise deviennent plus hautes."
            )
        )

        for combo in (self.format, self.landscape):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(8)

        self.setMinimumWidth(300)
        self._info = QLabel()
        self._warning = QLabel()
        for label in (self._info, self._warning):
            label.setWordWrap(True)
            # un libellé long ne doit pas imposer sa largeur au panneau
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self._warning.setStyleSheet("color: #b00020;")
        self.export_button = QPushButton(self.tr("Exporter en PDF…"))
        self.export_button.setDefault(True)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)  # étroit : libellé au-dessus
        form.addRow(self.tr("Format"), self.format)
        form.addRow(self.tr("Orientation"), self.landscape)
        form.addRow(self.tr("Dimensions"), size_row)
        form.addRow("", format_buttons)
        form.addRow(self.tr("Titre"), self.title)
        form.addRow(self.limit_period, period_row)
        form.addRow(self.tr("Taille du texte"), self.text_size)
        form.addRow(self.tr("Lignes maximum par titre"), self.max_lines)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._info)
        layout.addWidget(self._warning)
        layout.addStretch()
        layout.addWidget(self.export_button)

        self._fill_formats()
        self._select(DEFAULT_FORMAT)
        self._apply_format()

        self.format.currentIndexChanged.connect(self._apply_format)
        self.landscape.currentIndexChanged.connect(self._apply_format)
        self.width_cm.valueChanged.connect(self._size_edited)
        self.height_cm.valueChanged.connect(self._size_edited)
        self.title.textChanged.connect(self.settingsChanged)
        self.text_size.valueChanged.connect(self.settingsChanged)
        self.limit_period.toggled.connect(self._period_toggled)
        self.year_from.valueChanged.connect(self.plannerSettingsChanged)
        self.year_to.valueChanged.connect(self.plannerSettingsChanged)
        self.max_lines.valueChanged.connect(self.plannerSettingsChanged)
        self.save_format.clicked.connect(self._save_format)
        self.delete_format.clicked.connect(self._delete_format)
        self.export_button.clicked.connect(self.exportRequested)

    # --- formats ----------------------------------------------------------------------------

    @staticmethod
    def _side_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(MIN_SIDE_MM / 10, MAX_SIDE_MM / 10)
        spin.setDecimals(1)
        spin.setSingleStep(5.0)
        return spin

    def _fill_formats(self) -> None:
        with QSignalBlocker(self.format):
            current = self.format.currentData()
            self.format.clear()
            for f in STANDARD_FORMATS:
                self.format.addItem(f.name, f.name)
            for f in self._presets:
                label = f"{f.name} ({format_length(max(f.width_mm, f.height_mm))})"
                self.format.addItem(label, f.name)
            self.format.addItem(self.tr("Personnalisé"), CUSTOM)
            if current is not None:
                self._select(current)

    def _select(self, key: str) -> None:
        index = self.format.findData(key)
        with QSignalBlocker(self.format):
            self.format.setCurrentIndex(index if index >= 0 else self.format.findData(CUSTOM))

    def _format_named(self, name: str) -> PageFormat | None:
        for f in (*STANDARD_FORMATS, *self._presets):
            if f.name == name:
                return f
        return None

    def current_format(self) -> PageFormat | None:
        """Format normalisé ou enregistré sélectionné (``None`` : dimensions personnalisées)."""
        key = self.format.currentData()
        return None if key == CUSTOM else self._format_named(key)

    def _apply_format(self) -> None:
        fmt = self.current_format()
        if fmt is not None:
            w, h = fmt.oriented(bool(self.landscape.currentData()))
            self._set_size(w / 10, h / 10)
        self.landscape.setEnabled(fmt is not None)
        self.delete_format.setEnabled(fmt is not None and fmt in self._presets)
        self.settingsChanged.emit()

    def _set_size(self, width_cm: float, height_cm: float) -> None:
        for spin, value in ((self.width_cm, width_cm), (self.height_cm, height_cm)):
            with QSignalBlocker(spin):
                spin.setValue(value)

    def _size_edited(self) -> None:
        self._select(CUSTOM)  # saisie manuelle : format personnalisé
        self.landscape.setEnabled(False)
        self.delete_format.setEnabled(False)
        self.settingsChanged.emit()

    def set_size_mm(
        self, width_mm: float, height_mm: float, format_name: str | None = None
    ) -> None:
        """Choisit une taille (et le format correspondant s'il existe)."""
        fmt = self._format_named(format_name) if format_name else None
        if fmt is not None:
            self._select(fmt.name)
            with QSignalBlocker(self.landscape):
                self.landscape.setCurrentIndex(0 if width_mm >= height_mm else 1)
        else:
            self._select(CUSTOM)
        self._set_size(width_mm / 10, height_mm / 10)
        self.landscape.setEnabled(fmt is not None)
        self.delete_format.setEnabled(fmt is not None and fmt in self._presets)
        self.settingsChanged.emit()

    def presets(self) -> list[PageFormat]:
        return list(self._presets)

    def _save_format(self) -> None:
        name, ok = QInputDialog.getText(
            self, self.tr("Enregistrer ce format"), self.tr("Nom du format :")
        )
        if ok:
            self.add_preset(name)

    def add_preset(self, name: str) -> PageFormat | None:
        """Enregistre les dimensions actuelles sous ce nom ; ``None`` (et message) si refusé."""
        try:
            fmt = check_format(
                name, self.width_cm.value() * 10, self.height_cm.value() * 10, self._presets
            )
        except FormatError as exc:
            QMessageBox.warning(self, self.tr("Formats"), plain(format_error_text(exc)))
            return None
        self._presets.append(fmt)
        self._fill_formats()
        self._select(fmt.name)
        self._apply_format()
        self.formatsChanged.emit(self.presets())
        return fmt

    def _delete_format(self) -> None:
        fmt = self.current_format()
        if fmt is None or fmt not in self._presets:
            return
        answer = QMessageBox.question(
            self,
            self.tr("Formats"),
            plain(self.tr("Supprimer le format « %1 » ?").replace("%1", fmt.name)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_preset(fmt.name)

    def remove_preset(self, name: str) -> None:
        self._presets = [f for f in self._presets if f.name != name]
        self._fill_formats()
        self._select(DEFAULT_FORMAT)
        self._apply_format()
        self.formatsChanged.emit(self.presets())

    # --- période ------------------------------------------------------------------------------

    def set_year_bounds(self, low: int, high: int) -> None:
        """Années extrêmes des événements affichés : bornes proposées pour la période."""
        if (low, high) == self._year_bounds:
            return
        self._year_bounds = (low, high)
        if not self.limit_period.isChecked():
            for spin, value in ((self.year_from, low), (self.year_to, high)):
                with QSignalBlocker(spin):
                    spin.setValue(value)

    def _period_toggled(self, on: bool) -> None:
        self.year_from.setEnabled(on)
        self.year_to.setEnabled(on)
        self.plannerSettingsChanged.emit()

    def time_range(self) -> tuple[float, float] | None:
        if not self.limit_period.isChecked():
            return None
        start, end = sorted((self.year_from.value(), self.year_to.value()))
        return float(start), float(end + 1)  # l'année de fin est incluse

    # --- lecture et affichage ---------------------------------------------------------------------

    def settings(self) -> PageSettings:
        return PageSettings(
            width_mm=self.width_cm.value() * 10,
            height_mm=self.height_cm.value() * 10,
            title=self.title.text().strip(),
            font_pt=self.text_size.value(),
            max_label_lines=self.max_lines.value(),
            time_range=self.time_range(),
        )

    def format_label(self) -> str:
        """« A0 — 118,9 × 84,1 cm » ou « 1000 × 100 cm » pour une taille personnalisée."""
        s = self.settings()
        size = f"{s.width_mm / 10:g} × {s.height_mm / 10:g} cm".replace(".", ",")
        fmt = self.current_format()
        return f"{fmt.name} — {size}" if fmt is not None else size

    def show_plan(self, plan: PosterPlan | None, divisor: int = 1) -> None:
        """Résumé et avertissements pour la mise en page affichée."""
        if plan is None:
            self._info.setText(self.tr("Aucun événement à afficher avec les filtres actuels."))
            self._warning.clear()
            self.export_button.setEnabled(False)
            return
        self.export_button.setEnabled(True)
        self._info.setText(
            self.tr("%1 événements, %2 catégories. Taille du texte sur la page : %3 pt.")
            .replace("%1", str(plan.event_count))
            .replace("%2", str(len(plan.layout.lanes)))
            .replace("%3", f"{plan.font_pt:.1f}".replace(".", ","))
        )
        warnings = []
        unseen = plan.titles_truncated + plan.titles_hidden
        if unseen:
            warnings.append(
                self.tr(
                    "%1 titres tronqués ou masqués : choisissez une page plus grande "
                    "ou réduisez la taille du texte pour en afficher davantage."
                ).replace("%1", str(unseen))
            )
        if plan.requested_font_pt and plan.font_pt < plan.requested_font_pt - 0.05:
            warnings.append(
                self.tr(
                    "Texte réduit à %1 pt (au lieu de %2 pt) pour que la frise tienne dans la "
                    "hauteur de la page : choisissez une page plus haute ou un texte plus petit."
                )
                .replace("%1", f"{plan.font_pt:.1f}".replace(".", ","))
                .replace("%2", f"{plan.requested_font_pt:g}".replace(".", ","))
            )
        if plan.font_pt < MIN_READABLE_PT:
            warnings.append(
                self.tr(
                    "Texte très petit : choisissez un format plus grand ou une période plus courte."
                )
            )
        s = self.settings()
        if max(s.width_mm, s.height_mm) > PDF_COMFORT_LIMIT_MM and divisor > 1:
            warnings.append(
                self.tr(
                    "Au-delà de 5 m, certains lecteurs PDF refusent la page : le PDF sera exporté "
                    "à l'échelle 1/%1 (vectoriel, sans perte). Imprimez-le à %2 %."
                )
                .replace("%1", str(divisor))
                .replace("%2", str(divisor * 100))
            )
        self._warning.setText("\n".join(warnings))
