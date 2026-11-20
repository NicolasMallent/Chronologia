"""Mesure du texte avec les polices Qt (nécessite une QGuiApplication)."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetricsF

from .layout import TextMeasurer


def make_measurer(font: QFont) -> tuple[TextMeasurer, float]:
    """Renvoie (fonction de mesure, hauteur de ligne) pour ``font``."""
    metrics = QFontMetricsF(font)
    return (lambda text: metrics.horizontalAdvance(text)), metrics.height()
