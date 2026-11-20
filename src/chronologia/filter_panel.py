"""Panneau de filtres : une case à cocher par catégorie."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _swatch(color_hex: str) -> QIcon:
    """Pastille ronde de la couleur de la catégorie."""
    pixmap = QPixmap(32, 32)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color_hex))
    painter.drawEllipse(1, 1, 14, 14)
    painter.end()
    return QIcon(pixmap)


class FilterPanel(QWidget):
    """Émet ``visibleChanged(set[str])`` : noms des catégories cochées."""

    visibleChanged = Signal(object)
    editRequested = Signal(str)  # nom de la catégorie sur laquelle on a fait un clic droit

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.itemChanged.connect(self._emit)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_menu)
        all_button = QPushButton(self.tr("Tout"))
        none_button = QPushButton(self.tr("Aucun"))
        all_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        none_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        buttons = QHBoxLayout()
        buttons.addWidget(all_button)
        buttons.addWidget(none_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 8)
        layout.setSpacing(8)
        layout.addLayout(buttons)
        layout.addWidget(self._list)
        self._list.setIconSize(QSize(16, 16))
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setAcceptDrops(False)  # le dépôt d'un CSV est géré par la fenêtre
        self._list.viewport().setAcceptDrops(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)

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

    def _show_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction(self.tr("Modifier la catégorie…")).triggered.connect(
            lambda: self.editRequested.emit(name)
        )
        menu.exec(self._list.viewport().mapToGlobal(pos))

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
