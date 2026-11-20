"""Modèle de données de la frise."""

from __future__ import annotations

from dataclasses import dataclass, field

from .colors import DEFAULT_COLOR_HEX, resolve_color
from .dates import PartialDate

# Limites de robustesse : un fichier démesuré ne doit pas figer l'application.
MAX_TITLE_LENGTH = 500
MAX_SOURCE_LENGTH = 5000
MAX_EVENTS = 5000


@dataclass
class Event:
    """Un événement ponctuel (début == fin) ou une période.

    ``color`` garde le texte saisi (``skyblue`` ou ``#87CEEB``) pour que l'export CSV
    le restitue tel quel ; ``color_hex`` est la valeur résolue pour l'affichage.
    La catégorie d'un événement est sa couleur résolue.
    """

    start: PartialDate
    end: PartialDate
    title: str
    color: str
    source: str = ""

    @property
    def color_hex(self) -> str:
        return resolve_color(self.color) or DEFAULT_COLOR_HEX

    @property
    def is_point(self) -> bool:
        return self.start.value == self.end.value


@dataclass(frozen=True)
class ImportIssue:
    """Anomalie rencontrée à l'import. ``line`` est le numéro de ligne du fichier."""

    line: int
    message: str  # texte de secours (français), l'interface traduit à partir de ``code``
    skipped: bool = False  # True : la ligne n'a pas été importée
    code: str = ""
    detail: str = ""  # valeur fautive (date ou couleur saisie)

    TITLE_TRUNCATED = "title_truncated"
    SOURCE_TRUNCATED = "source_truncated"
    TOO_MANY_EVENTS = "too_many_events"
    EMPTY_TITLE = "empty_title"
    INVALID_START = "invalid_start"
    INVALID_END = "invalid_end"
    END_BEFORE_START = "end_before_start"
    UNKNOWN_COLOR = "unknown_color"


@dataclass
class ImportResult:
    events: list[Event] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
