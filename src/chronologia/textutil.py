"""Affichage sûr de texte venant d'un fichier (titres, sources, noms de fichier)."""

from __future__ import annotations

from PySide6.QtGui import Qt


def plain(text: str) -> str:
    """Rend ``text`` inoffensif pour un widget qui détecte le HTML (info-bulle, boîte de message).

    Sans cela, un titre comme ``<img src=...>`` serait interprété comme du HTML : la balise est
    échappée et le texte s'affiche tel quel.
    """
    return Qt.convertFromPlainText(text)
