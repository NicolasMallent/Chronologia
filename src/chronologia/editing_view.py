"""Comportement d'édition commun aux vues de la frise (mode Libre et mode Feuille).

Sélection d'un événement (clic), modification (double-clic), suppression (Suppr), menu
contextuel. Les sous-classes disent quel événement se trouve sous un point de la vue.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QGraphicsView, QMenu

from .model import Event


class EditableView(QGraphicsView):
    editRequested = Signal(object)  # Event
    deleteRequested = Signal(object)  # Event
    newRequested = Signal(
        str, str
    )  # année proposée (aaaa), couleur de la ligne ; vides si inconnues

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected: Event | None = None  # comparé par identité
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(False)  # le dépôt d'un CSV est géré par la fenêtre
        self.viewport().setAcceptDrops(False)

    # --- à fournir par les sous-classes -----------------------------------------------

    def _event_at(self, pos: QPoint) -> Event | None:
        """Événement sous ce point de la vue."""
        raise NotImplementedError

    def _year_hint(self, pos: QPoint) -> str:
        """Année proposée pour un nouvel événement créé à ce point (``aaaa``, ou vide)."""
        raise NotImplementedError

    def lane_color_at(self, view_y: float) -> str:
        raise NotImplementedError

    def _update_selection(self) -> None:
        """Affiche la mise en valeur de ``self._selected``."""
        raise NotImplementedError

    # --- sélection --------------------------------------------------------------------

    @property
    def selected_event(self) -> Event | None:
        return self._selected

    def select(self, event: Event | None) -> None:
        """Met un événement en valeur ; ``None`` efface."""
        self._selected = event
        self._update_selection()

    # --- interactions d'édition ---------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.select(self._event_at(event.position().toPoint()))
        super().mousePressEvent(event)

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
            hint = self._year_hint(event.pos())
            color = self.lane_color_at(event.pos().y())
            menu.addAction(self.tr("Nouvel événement ici…")).triggered.connect(
                lambda: self.newRequested.emit(hint, color)
            )
        menu.exec(event.globalPos())
