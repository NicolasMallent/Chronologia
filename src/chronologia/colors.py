"""Lecture des couleurs : noms (``red``, ``skyblue``) ou hexadécimal (``#FF0000``, ``#F00``)."""

from __future__ import annotations

from PySide6.QtGui import QColor

DEFAULT_COLOR_HEX = "#808080"


def resolve_color(text: str) -> str | None:
    """Renvoie la couleur au format ``#rrggbb`` (minuscules), ou ``None`` si inconnue."""
    s = text.strip()
    if not s:
        return None
    color = QColor(s)
    return color.name() if color.isValid() else None
