"""Textes traduits des erreurs et anomalies d'import (la logique d'import reste sans Qt)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from .csv_io import CsvFormatError
from .model import ImportIssue


def issue_text(issue: ImportIssue) -> str:
    """Anomalie d'import, dans la langue de l'interface."""
    code, detail = issue.code, issue.detail
    if code == ImportIssue.EMPTY_TITLE:
        return QCoreApplication.translate("Messages", "titre vide")
    if code == ImportIssue.INVALID_START:
        return QCoreApplication.translate("Messages", "date de début invalide : %1").replace(
            "%1", repr(detail)
        )
    if code == ImportIssue.INVALID_END:
        return QCoreApplication.translate("Messages", "date de fin invalide : %1").replace(
            "%1", repr(detail)
        )
    if code == ImportIssue.END_BEFORE_START:
        return QCoreApplication.translate(
            "Messages", "fin avant début : dates remises dans l'ordre"
        )
    if code == ImportIssue.UNKNOWN_COLOR:
        return QCoreApplication.translate("Messages", "couleur inconnue %1 : gris utilisé").replace(
            "%1", repr(detail)
        )
    return issue.message


def format_error_text(error: CsvFormatError) -> str:
    """Erreur de format de fichier, dans la langue de l'interface."""
    if error.code == CsvFormatError.EMPTY_FILE:
        return QCoreApplication.translate("Messages", "Le fichier est vide.")
    if error.code == CsvFormatError.MISSING_COLUMNS:
        return QCoreApplication.translate(
            "Messages", "Colonnes obligatoires absentes : %1"
        ).replace("%1", error.detail)
    if error.code == CsvFormatError.FILE_TOO_LARGE:
        return QCoreApplication.translate("Messages", "Le fichier est trop volumineux.")
    return str(error)
