"""Préférences : langue de l'interface et raccourcis clavier."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .i18n import LANGUAGES, effective_language
from .shortcuts import ShortcutManager, find_conflict


class PreferencesDialog(QDialog):
    """Modifie une copie ; rien n'est appliqué avant ``apply_shortcuts`` / ``selected_language``."""

    def __init__(self, shortcuts: ShortcutManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Préférences"))
        self.resize(560, 520)
        self._manager = shortcuts
        self._ids = shortcuts.ids()
        self._pending: dict[str, list[QKeySequence]] = shortcuts.assignments()
        self._editors: dict[str, QKeySequenceEdit] = {}

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), self.tr("Général"))
        tabs.addTab(self._shortcuts_tab(), self.tr("Raccourcis"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --- onglet Général --------------------------------------------------------------

    def _general_tab(self) -> QWidget:
        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(self.language.findData(effective_language()))
        hint = QLabel(self.tr("La nouvelle langue est appliquée au prochain démarrage."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6b7280;")
        form = QFormLayout()
        form.addRow(self.tr("Langue"), self.language)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def selected_language(self) -> str:
        return str(self.language.currentData())

    # --- onglet Raccourcis -----------------------------------------------------------

    def _shortcuts_tab(self) -> QWidget:
        self._table = QTableWidget(len(self._ids), 3)
        self._table.setHorizontalHeaderLabels(
            [self.tr("Action"), self.tr("Raccourci"), self.tr("Réinitialiser")]
        )
        self._table.verticalHeader().hide()
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for row, action_id in enumerate(self._ids):
            self._table.setItem(row, 0, QTableWidgetItem(self._manager.label(action_id)))
            edit = QKeySequenceEdit(self._first(self._pending[action_id]))
            edit.setMaximumSequenceLength(1)
            edit.setClearButtonEnabled(True)
            edit.setMinimumWidth(190)
            for field in edit.findChildren(QLineEdit):
                field.setPlaceholderText(self.tr("Appuyer sur un raccourci"))
            edit.keySequenceChanged.connect(lambda seq, i=action_id: self._edited(i, seq))
            self._editors[action_id] = edit
            self._table.setCellWidget(row, 1, edit)
            reset = QPushButton(self.tr("Réinitialiser"))
            reset.clicked.connect(lambda _checked=False, i=action_id: self._reset(i))
            self._table.setCellWidget(row, 2, reset)

        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.setStyleSheet("color: #b00020;")
        reset_all = QPushButton(self.tr("Tout réinitialiser"))
        reset_all.clicked.connect(self._reset_all)
        fixed = QLabel(
            self.tr(
                "Touches fixes : Suppr supprime l'événement sélectionné, Échap le désélectionne, "
                "molette = zoom, Maj + molette = défilement vertical."
            )
        )
        fixed.setWordWrap(True)
        fixed.setStyleSheet("color: #6b7280;")

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._table)
        bottom = QHBoxLayout()
        bottom.addWidget(self._message, 1)
        bottom.addWidget(reset_all)
        layout.addLayout(bottom)
        layout.addWidget(fixed)
        return page

    @staticmethod
    def _first(sequences: list[QKeySequence]) -> QKeySequence:
        return sequences[0] if sequences else QKeySequence()

    def _edited(self, action_id: str, sequence: QKeySequence) -> None:
        """Un raccourci est saisi : refusé (et annulé) s'il est déjà utilisé."""
        owner = find_conflict(self._pending, action_id, sequence)
        if owner is not None:
            self._message.setText(
                self.tr("Ce raccourci est déjà utilisé par « %1 ».").replace(
                    "%1", self._manager.label(owner)
                )
            )
            self._set_editor(action_id, self._first(self._pending[action_id]))
            return
        self._message.clear()
        self._pending[action_id] = [sequence] if not sequence.isEmpty() else []

    def _set_editor(self, action_id: str, sequence: QKeySequence) -> None:
        edit = self._editors[action_id]
        edit.blockSignals(True)
        edit.setKeySequence(sequence)
        edit.blockSignals(False)

    def _reset(self, action_id: str) -> None:
        default = self._manager.default(action_id)
        owner = find_conflict(self._pending, action_id, self._first(default))
        if owner is not None:
            self._message.setText(
                self.tr("Ce raccourci est déjà utilisé par « %1 ».").replace(
                    "%1", self._manager.label(owner)
                )
            )
            return
        self._message.clear()
        self._pending[action_id] = default
        self._set_editor(action_id, self._first(default))

    def _reset_all(self) -> None:
        self._message.clear()
        for action_id in self._ids:
            self._pending[action_id] = self._manager.default(action_id)
            self._set_editor(action_id, self._first(self._pending[action_id]))

    def pending_shortcuts(self) -> dict[str, list[QKeySequence]]:
        return {k: list(v) for k, v in self._pending.items()}

    def apply_shortcuts(self) -> None:
        """Applique les raccourcis choisis (à appeler après OK)."""
        self._manager.apply_all(self._pending)
