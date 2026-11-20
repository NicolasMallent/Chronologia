"""Boîte de dialogue d'ajout / modification d'un événement."""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import event_form
from .categories import CategoryRegistry
from .colors import resolve_color
from .model import Event


def _swatch(color_hex: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(color_hex))
    return QIcon(pixmap)


class EventDialog(QDialog):
    def __init__(
        self,
        registry: CategoryRegistry,
        event: Event | None = None,
        start_hint: str = "",
        color_hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._result: Event | None = None
        self.delete_requested = False
        self.setWindowTitle(
            self.tr("Modifier l'événement") if event else self.tr("Nouvel événement")
        )
        self.setMinimumWidth(460)

        self.title = QLineEdit()
        self.start = QLineEdit()
        self.end = QLineEdit()
        date_hint = self.tr("aaaa, aaaamm, aaaammjj ou jj/mm/aaaa")
        self.start.setPlaceholderText(date_hint)
        self.end.setPlaceholderText(self.tr("vide = événement ponctuel"))
        self.source = QPlainTextEdit()
        self.source.setPlaceholderText(self.tr("Commentaire ou source (affiché au survol)"))
        self.source.setFixedHeight(70)

        self.category = QComboBox()
        self.category.addItem(self.tr("Couleur personnalisée"), "")
        for c in registry:
            self.category.addItem(_swatch(c.color_hex), c.name, c.color)
        self.color = QLineEdit()
        self.color.setPlaceholderText(self.tr("red ou #FF0000"))
        self._swatch_label = QLabel()
        self._swatch_label.setFixedSize(22, 22)
        pick = QPushButton(self.tr("Choisir…"))
        pick.clicked.connect(self._pick_color)
        color_row = QHBoxLayout()
        color_row.addWidget(self.color)
        color_row.addWidget(self._swatch_label)
        color_row.addWidget(pick)

        self._error = QLabel()
        self._error.setStyleSheet("color: #b00020;")
        self._error.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.tr("Titre"), self.title)
        form.addRow(self.tr("Début"), self.start)
        form.addRow(self.tr("Fin"), self.end)
        form.addRow(self.tr("Catégorie"), self.category)
        form.addRow(self.tr("Couleur"), color_row)
        form.addRow(self.tr("Source"), self.source)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._accept)
        self._buttons.rejected.connect(self.reject)
        if event is not None:
            delete = self._buttons.addButton(
                self.tr("Supprimer"), QDialogButtonBox.ButtonRole.DestructiveRole
            )
            delete.setAutoDefault(False)
            delete.clicked.connect(self._request_delete)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)

        if event is not None:
            self.title.setText(event.title)
            self.start.setText(event.start.to_display())
            self.end.setText("" if event.is_point else event.end.to_display())
            self.color.setText(event.color)
            self.source.setPlainText(event.source)
        else:
            self.start.setText(start_hint)
            if color_hint:  # ligne cliquée : sa catégorie, ou à défaut sa couleur
                found = registry.for_color(color_hint)
                self.color.setText(found.color if found else color_hint)
            else:
                first = next(iter(registry), None)
                self.color.setText(first.color if first else "grey")

        for edit in (self.title, self.start, self.end, self.color):
            edit.textChanged.connect(self._validate)
        self.source.textChanged.connect(self._validate)
        self.category.activated.connect(self._category_chosen)
        self.color.textChanged.connect(self._sync_color_widgets)
        self._sync_color_widgets()
        self._validate()
        self.title.setFocus()

    # --- couleur ---------------------------------------------------------------------

    def _category_chosen(self, index: int) -> None:
        color = self.category.itemData(index)
        if color:
            self.color.setText(color)

    def _sync_color_widgets(self) -> None:
        resolved = resolve_color(self.color.text())
        self._swatch_label.setStyleSheet(
            f"background: {resolved}; border: 1px solid #666;"
            if resolved
            else "border: 1px solid #b00020;"
        )
        found = self._registry.for_color(self.color.text())
        self.category.blockSignals(True)
        self.category.setCurrentIndex(0 if found is None else self.category.findText(found.name))
        self.category.blockSignals(False)

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(resolve_color(self.color.text()) or "#808080"), self)
        if chosen.isValid():
            self.color.setText(chosen.name())

    # --- validation ------------------------------------------------------------------

    def _messages(self) -> dict[str, str]:
        return {
            event_form.TITLE_EMPTY: self.tr("Le titre est obligatoire."),
            event_form.TITLE_TOO_LONG: self.tr("Le titre est trop long."),
            event_form.START_INVALID: self.tr(
                "Date de début invalide (aaaa, aaaamm, aaaammjj, mm/aaaa ou jj/mm/aaaa)."
            ),
            event_form.END_INVALID: self.tr("Date de fin invalide."),
            event_form.END_BEFORE_START: self.tr("La fin ne peut pas précéder le début."),
            event_form.COLOR_INVALID: self.tr(
                "Couleur inconnue (nom comme « red » ou code #FF0000)."
            ),
            event_form.SOURCE_TOO_LONG: self.tr("La source est trop longue."),
        }

    def _validate(self) -> None:
        event, errors = event_form.build_event(
            self.title.text(),
            self.start.text(),
            self.end.text(),
            self.color.text(),
            self.source.toPlainText(),
        )
        self._result = event
        messages = self._messages()
        # le titre vide n'est pas signalé tant que la saisie n'a pas commencé
        shown = [messages[code] for code in errors.values() if code != event_form.TITLE_EMPTY]
        self._error.setText("\n".join(shown))
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(event is not None)

    def _request_delete(self) -> None:
        self.delete_requested = True
        self.reject()

    def _accept(self) -> None:
        if self._result is not None:
            self.accept()

    def result_event(self) -> Event | None:
        """L'événement saisi (valide), ou ``None``. (``event`` est réservé par Qt.)"""
        return self._result
