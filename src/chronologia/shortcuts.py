"""Raccourcis clavier personnalisables.

Chaque action de menu est enregistrée sous un identifiant stable avec ses raccourcis par défaut.
La personnalisation (un raccourci par action, ou aucun) est conservée dans ``QSettings``, avec la
langue : réglage local, sans donnée personnelle. Sans personnalisation, les valeurs par défaut
(souvent propres à chaque système, ``QKeySequence.StandardKey``) s'appliquent.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence

GROUP = "shortcuts"
_PORTABLE = QKeySequence.SequenceFormat.PortableText


class ShortcutConflict(ValueError):
    """Le raccourci est déjà utilisé ; ``owner`` est l'identifiant de l'action titulaire."""

    def __init__(self, owner: str) -> None:
        super().__init__(f"raccourci déjà utilisé par {owner!r}")
        self.owner = owner


# Certains systèmes (ou plateformes Qt minimales) ne définissent pas ces raccourcis standard.
_FALLBACKS = {
    QKeySequence.StandardKey.Quit: "Ctrl+Q",
    QKeySequence.StandardKey.Preferences: "Ctrl+,",
}


def _defaults(spec: QKeySequence.StandardKey | str | None) -> list[QKeySequence]:
    if spec is None or spec == "":
        return []
    if isinstance(spec, QKeySequence.StandardKey):
        found = [s for s in QKeySequence.keyBindings(spec) if not s.isEmpty()]
        return found or ([QKeySequence(_FALLBACKS[spec])] if spec in _FALLBACKS else [])
    return [QKeySequence(spec)]


def find_conflict(
    assignments: Mapping[str, list[QKeySequence]], action_id: str, sequence: QKeySequence
) -> str | None:
    """Identifiant d'une *autre* action qui utilise déjà ``sequence``, s'il y en a une."""
    if sequence.isEmpty():
        return None
    for other, sequences in assignments.items():
        if other != action_id and any(s == sequence for s in sequences):
            return other
    return None


class ShortcutManager:
    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings("Chronologia", "Chronologia")
        self._actions: dict[str, QAction] = {}
        self._labels: dict[str, str] = {}
        self._defaults: dict[str, list[QKeySequence]] = {}

    # --- enregistrement --------------------------------------------------------------

    def register(
        self,
        action_id: str,
        action: QAction,
        default: QKeySequence.StandardKey | str | None = None,
        label: str | None = None,
    ) -> None:
        """Enregistre ``action`` ; ``label`` : intitulé affiché (par défaut, son texte sans « & »)."""
        if action_id in self._actions:
            raise ValueError(f"identifiant déjà enregistré : {action_id!r}")
        self._actions[action_id] = action
        self._defaults[action_id] = _defaults(default)
        text = label if label is not None else action.text()
        self._labels[action_id] = text.replace("&", "").rstrip("… ").strip()
        self._apply(action_id)

    def ids(self) -> list[str]:
        return list(self._actions)

    def label(self, action_id: str) -> str:
        return self._labels[action_id]

    def default(self, action_id: str) -> list[QKeySequence]:
        return list(self._defaults[action_id])

    # --- lecture ---------------------------------------------------------------------

    def effective(self, action_id: str) -> list[QKeySequence]:
        """Raccourcis actuellement actifs (personnalisation, sinon valeurs par défaut)."""
        key = f"{GROUP}/{action_id}"
        if not self._settings.contains(key):
            return self.default(action_id)
        text = str(self._settings.value(key) or "")
        return [QKeySequence(text, _PORTABLE)] if text else []

    def is_customized(self, action_id: str) -> bool:
        return self._settings.contains(f"{GROUP}/{action_id}")

    def assignments(self) -> dict[str, list[QKeySequence]]:
        return {i: self.effective(i) for i in self._actions}

    def conflict(self, action_id: str, sequence: QKeySequence) -> str | None:
        return find_conflict(self.assignments(), action_id, sequence)

    # --- modification ----------------------------------------------------------------

    def set(self, action_id: str, sequence: QKeySequence) -> None:
        """Affecte un seul raccourci (vide : aucun raccourci). Refuse un raccourci déjà pris."""
        if (owner := self.conflict(action_id, sequence)) is not None:
            raise ShortcutConflict(owner)
        if [sequence] == self._defaults[action_id]:
            self._settings.remove(f"{GROUP}/{action_id}")
        else:
            self._settings.setValue(f"{GROUP}/{action_id}", sequence.toString(_PORTABLE))
        self._settings.sync()
        self._apply(action_id)

    def reset(self, action_id: str) -> None:
        self._settings.remove(f"{GROUP}/{action_id}")
        self._settings.sync()
        self._apply(action_id)

    def reset_all(self) -> None:
        for action_id in self._actions:
            self._settings.remove(f"{GROUP}/{action_id}")
        self._settings.sync()
        for action_id in self._actions:
            self._apply(action_id)

    def apply_all(self, assignments: Mapping[str, list[QKeySequence]]) -> None:
        """Applique d'un coup un état complet (boîte de préférences), déjà validé sans conflit."""
        for action_id, sequences in assignments.items():
            if sequences == self._defaults[action_id]:
                self._settings.remove(f"{GROUP}/{action_id}")
            else:
                first = sequences[0] if sequences else QKeySequence()
                self._settings.setValue(f"{GROUP}/{action_id}", first.toString(_PORTABLE))
        self._settings.sync()
        for action_id in assignments:
            self._apply(action_id)

    def _apply(self, action_id: str) -> None:
        self._actions[action_id].setShortcuts(self.effective(action_id))
