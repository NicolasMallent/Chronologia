"""Gestion des catégories : ajout, modification, suppression, ordre, valeurs par défaut."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .categories import Category, CategoryError, CategoryRegistry, default_registry
from .colors import resolve_color
from .event_dialog import _swatch
from .messages import category_error_text
from .textutil import plain


class CategoryEditDialog(QDialog):
    """Nom et couleur d'une catégorie ; validés par le registre de travail."""

    def __init__(
        self,
        registry: CategoryRegistry,
        category: Category | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._category = category
        self.setWindowTitle(
            self.tr("Modifier la catégorie") if category else self.tr("Nouvelle catégorie")
        )
        self.setMinimumWidth(400)
        self.name = QLineEdit(category.name if category else "")
        self.color = QLineEdit(category.color if category else "")
        self.color.setPlaceholderText(self.tr("red ou #FF0000"))
        self._swatch = QLabel()
        self._swatch.setFixedSize(22, 22)
        pick = QPushButton(self.tr("Choisir…"))
        pick.clicked.connect(self._pick_color)
        row = QHBoxLayout()
        row.addWidget(self.color)
        row.addWidget(self._swatch)
        row.addWidget(pick)
        self._error = QLabel()
        self._error.setStyleSheet("color: #b00020;")
        self._error.setWordWrap(True)
        form = QFormLayout()
        form.addRow(self.tr("Nom"), self.name)
        form.addRow(self.tr("Couleur"), row)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addWidget(self._buttons)
        self.name.textChanged.connect(self._validate)
        self.color.textChanged.connect(self._validate)
        self._validate()
        self.name.setFocus()

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(resolve_color(self.color.text()) or "#808080"), self)
        if chosen.isValid():
            self.color.setText(chosen.name())

    def _validate(self) -> None:
        resolved = resolve_color(self.color.text())
        self._swatch.setStyleSheet(
            f"background: {resolved}; border: 1px solid #666;"
            if resolved
            else "border: 1px solid #b00020;"
        )
        message = ""
        try:
            self._registry.check(self.name.text(), self.color.text(), ignore=self._category)
        except CategoryError as exc:
            # un champ encore vide n'est pas signalé comme une erreur
            empty_name = exc.code == CategoryError.NAME_INVALID and not self.name.text().strip()
            empty_color = exc.code == CategoryError.COLOR_UNKNOWN and not self.color.text().strip()
            if not (empty_name or empty_color):
                message = category_error_text(exc)
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        else:
            self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self._error.setText(message)

    def values(self) -> tuple[str, str]:
        return self.name.text(), self.color.text()


class CategoriesDialog(QDialog):
    """Édite une copie du registre ; ``registry()`` donne le résultat après ``accept``."""

    def __init__(self, registry: CategoryRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._work = CategoryRegistry(list(registry))
        self.setWindowTitle(self.tr("Gérer les catégories"))
        self.resize(460, 420)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _item: self._edit())
        self._list.currentRowChanged.connect(self._update_buttons)

        self._add = QPushButton(self.tr("Ajouter…"))
        self._edit_btn = QPushButton(self.tr("Modifier…"))
        self._remove = QPushButton(self.tr("Supprimer"))
        self._up = QPushButton(self.tr("Monter"))
        self._down = QPushButton(self.tr("Descendre"))
        reset = QPushButton(self.tr("Valeurs par défaut"))
        self._add.clicked.connect(self._add_category)
        self._edit_btn.clicked.connect(self._edit)
        self._remove.clicked.connect(self._remove_category)
        self._up.clicked.connect(lambda: self._move(-1))
        self._down.clicked.connect(lambda: self._move(1))
        reset.clicked.connect(self._reset)

        side = QVBoxLayout()
        for button in (self._add, self._edit_btn, self._remove, self._up, self._down):
            side.addWidget(button)
        side.addStretch()
        side.addWidget(reset)
        body = QHBoxLayout()
        body.addWidget(self._list, 1)
        body.addLayout(side)

        hint = QLabel(
            self.tr(
                "L'ordre ci-dessous est celui des lignes de la frise. "
                "Les événements d'une couleur sans catégorie restent affichés."
            )
        )
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(body)
        layout.addWidget(buttons)
        self._refresh()

    def registry(self) -> CategoryRegistry:
        return self._work

    def _selected(self) -> Category | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _refresh(self, select: Category | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for category in self._work:
            item = QListWidgetItem(_swatch(category.color_hex), category.name)
            item.setData(Qt.ItemDataRole.UserRole, category)
            self._list.addItem(item)
            if category is select:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._update_buttons()

    def _update_buttons(self, *_: object) -> None:
        selected = self._selected()
        row = self._list.currentRow()
        self._edit_btn.setEnabled(selected is not None)
        self._remove.setEnabled(selected is not None)
        self._up.setEnabled(selected is not None and row > 0)
        self._down.setEnabled(selected is not None and row < self._list.count() - 1)

    def _add_category(self) -> None:
        dialog = CategoryEditDialog(self._work, parent=self)
        if dialog.exec():
            try:
                added = self._work.add(*dialog.values())
            except CategoryError as exc:
                QMessageBox.warning(self, self.windowTitle(), plain(category_error_text(exc)))
                return
            self._refresh(added)

    def _edit(self) -> None:
        category = self._selected()
        if category is None:
            return
        dialog = CategoryEditDialog(self._work, category, parent=self)
        if dialog.exec():
            try:
                updated = self._work.update(category, *dialog.values())
            except CategoryError as exc:
                QMessageBox.warning(self, self.windowTitle(), plain(category_error_text(exc)))
                return
            self._refresh(updated)

    def _remove_category(self) -> None:
        category = self._selected()
        if category is None:
            return
        answer = QMessageBox.question(
            self,
            self.windowTitle(),
            plain(self.tr("Supprimer la catégorie « %1 » ?").replace("%1", category.name)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._work.remove(category)
            self._refresh()

    def _move(self, offset: int) -> None:
        category = self._selected()
        if category is not None:
            self._work.move(category, offset)
            self._refresh(category)

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self,
            self.windowTitle(),
            self.tr("Remplacer toutes les catégories par celles livrées avec l'application ?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._work = default_registry()
            self._refresh()
