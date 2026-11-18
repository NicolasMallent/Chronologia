"""Panneau de filtres : une case à cocher par catégorie."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _swatch(color_hex: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(QColor(color_hex))
    return QIcon(pixmap)


class FilterPanel(QWidget):
    """Émet ``visibleChanged(set[str])`` : noms des catégories cochées."""

    visibleChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.itemChanged.connect(self._emit)
        all_button = QPushButton(self.tr("Tout"))
        none_button = QPushButton(self.tr("Aucun"))
        all_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        none_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        buttons = QHBoxLayout()
        buttons.addWidget(all_button)
        buttons.addWidget(none_button)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self._list)

    def set_categories(self, entries: list[tuple[str, str, int]], keep_state: bool = False) -> None:
        """``entries`` : (nom, couleur ``#rrggbb``, nombre d'événements).

        Tout est coché, sauf avec ``keep_state`` : les catégories déjà connues gardent leur
        état et les nouvelles sont cochées.
        """
        previous = self._states() if keep_state else {}
        self._list.blockSignals(True)
        self._list.clear()
        for name, color_hex, count in entries:
            item = QListWidgetItem(_swatch(color_hex), f"{name} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checked = previous.get(name, True)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._emit()

    def _states(self) -> dict[str, bool]:
        return {
            self._list.item(i).data(Qt.ItemDataRole.UserRole): self._list.item(i).checkState()
            == Qt.CheckState.Checked
            for i in range(self._list.count())
        }

    def ensure_checked(self, name: str) -> None:
        """Coche une catégorie (pour qu'un événement qu'on vient d'ajouter soit visible)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == name:
                if item.checkState() != Qt.CheckState.Checked:
                    item.setCheckState(Qt.CheckState.Checked)  # émet visibleChanged
                return

    def visible_categories(self) -> set[str]:
        return {
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        }

    def _set_all(self, state: Qt.CheckState) -> None:
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)
        self._list.blockSignals(False)
        self._emit()

    def _emit(self, *_: object) -> None:
        self.visibleChanged.emit(self.visible_categories())
