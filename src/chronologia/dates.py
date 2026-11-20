"""Lecture et écriture des dates de la frise.

Formats acceptés en entrée (mélangeables dans un même fichier) :
``aaaammjj``, ``aaaamm``, ``aaaa``, ``jj/mm/aaaa`` et ``mm/aaaa`` (forme d'affichage d'un mois).
Dans ``aaaammjj``, un jour ``00`` (``19720400``) signifie « jour inconnu » et un mois ``00``
(``19720000``) « mois inconnu », convention présente dans les fichiers existants.
Une date partielle est conservée avec sa précision : ``aaaa`` vaut le 1er janvier,
``aaaamm`` le 1er du mois, pour le placement sur l'axe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum


class Precision(Enum):
    YEAR = "aaaa"
    MONTH = "aaaamm"
    DAY = "aaaammjj"


@dataclass(frozen=True, order=True)
class PartialDate:
    """Date avec sa précision d'origine. Le tri se fait sur la date réelle."""

    value: date
    precision: Precision = Precision.DAY

    def to_csv(self) -> str:
        """Réécrit la date dans le format compact correspondant à sa précision."""
        if self.precision is Precision.YEAR:
            return f"{self.value.year:04d}"
        if self.precision is Precision.MONTH:
            return f"{self.value.year:04d}{self.value.month:02d}"
        return f"{self.value.year:04d}{self.value.month:02d}{self.value.day:02d}"

    def to_display(self) -> str:
        """Forme lisible selon la précision : ``1870``, ``09/1870`` ou ``04/09/1870``."""
        v = self.value
        if self.precision is Precision.YEAR:
            return f"{v.year:04d}"
        if self.precision is Precision.MONTH:
            return f"{v.month:02d}/{v.year:04d}"
        return f"{v.day:02d}/{v.month:02d}/{v.year:04d}"


class DateParseError(ValueError):
    """La chaîne ne correspond à aucun format de date accepté."""


_COMPACT = re.compile(r"^(\d{4})(\d{2})?(\d{2})?$")
_FRENCH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_FRENCH_MONTH = re.compile(r"^(\d{2})/(\d{4})$")


def parse_date(text: str) -> PartialDate:
    """Convertit ``text`` en :class:`PartialDate`, ou lève :class:`DateParseError`."""
    s = text.strip()
    try:
        m = _FRENCH.match(s)
        if m:
            d, mo, y = (int(g) for g in m.groups())
            return PartialDate(date(y, mo, d), Precision.DAY)
        m = _FRENCH_MONTH.match(s)
        if m:
            mo, y = (int(g) for g in m.groups())
            return PartialDate(date(y, mo, 1), Precision.MONTH)
        m = _COMPACT.match(s)
        if m and len(s) in (4, 6, 8):
            y = int(m.group(1))
            mo = int(m.group(2)) if m.group(2) else 0  # 0 : mois inconnu
            d = int(m.group(3)) if m.group(3) else 0  # 0 : jour inconnu
            if mo == 0 and d == 0:  # aaaa ou aaaa0000
                return PartialDate(date(y, 1, 1), Precision.YEAR)
            if d == 0:  # aaaamm ou aaaamm00
                return PartialDate(date(y, mo, 1), Precision.MONTH)
            return PartialDate(date(y, mo, d), Precision.DAY)
    except ValueError as exc:  # mois ou jour hors limites, année 0000
        raise DateParseError(f"date invalide : {text!r}") from exc
    raise DateParseError(f"format de date non reconnu : {text!r}")
