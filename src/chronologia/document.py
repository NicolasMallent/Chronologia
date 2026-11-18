"""Liste des événements en cours d'édition, avec annuler/rétablir."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .model import Event


def _index_of(events: list[Event], event: Event) -> int:
    """Position par identité (deux événements peuvent avoir le même contenu)."""
    for i, candidate in enumerate(events):
        if candidate is event:
            return i
    raise ValueError("événement absent du document")


class _Add(QUndoCommand):
    def __init__(self, doc: Document, event: Event) -> None:
        super().__init__(QCoreApplication.translate("Document", "Ajouter un événement"))
        self._doc, self._event = doc, event

    def redo(self) -> None:
        self._doc.events.append(self._event)
        self._doc.changed.emit(self._event)

    def undo(self) -> None:
        del self._doc.events[_index_of(self._doc.events, self._event)]
        self._doc.changed.emit(None)


class _Replace(QUndoCommand):
    def __init__(self, doc: Document, old: Event, new: Event) -> None:
        super().__init__(QCoreApplication.translate("Document", "Modifier un événement"))
        self._doc, self._old, self._new = doc, old, new

    def redo(self) -> None:
        self._doc.events[_index_of(self._doc.events, self._old)] = self._new
        self._doc.changed.emit(self._new)

    def undo(self) -> None:
        self._doc.events[_index_of(self._doc.events, self._new)] = self._old
        self._doc.changed.emit(self._old)


class _Remove(QUndoCommand):
    def __init__(self, doc: Document, event: Event) -> None:
        super().__init__(QCoreApplication.translate("Document", "Supprimer un événement"))
        self._doc, self._event, self._index = doc, event, 0

    def redo(self) -> None:
        self._index = _index_of(self._doc.events, self._event)
        del self._doc.events[self._index]
        self._doc.changed.emit(None)

    def undo(self) -> None:
        self._doc.events.insert(self._index, self._event)
        self._doc.changed.emit(self._event)


class Document(QObject):
    """``changed(événement)`` : émis après chaque modification, annulation ou rétablissement.
    L'argument est l'événement à mettre en évidence, ou ``None``."""

    changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.events: list[Event] = []
        self.stack = QUndoStack(self)

    def reset(self, events: list[Event]) -> None:
        """Remplace tout le contenu (ouverture d'un fichier) et vide l'historique."""
        self.events = list(events)
        self.stack.clear()
        self.changed.emit(None)

    def add(self, event: Event) -> None:
        self.stack.push(_Add(self, event))

    def replace(self, old: Event, new: Event) -> None:
        self.stack.push(_Replace(self, old, new))

    def remove(self, event: Event) -> None:
        self.stack.push(_Remove(self, event))
