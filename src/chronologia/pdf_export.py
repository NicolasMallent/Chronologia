"""Écriture du PDF vectoriel (taille de page personnalisée)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QIODevice, QMarginsF, QSaveFile, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

from .poster import PosterPlan, paint_poster

# Au-delà, certains lecteurs PDF (Acrobat) refusent la page : 200 pouces = 5,08 m.
PDF_COMFORT_LIMIT_MM = 5080.0
PAGE_SIZES_MM = {  # format en portrait (largeur, hauteur)
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
}


class PdfExportError(OSError):
    """Le PDF n'a pas pu être écrit."""


def _page_layout(width_mm: float, height_mm: float) -> QPageLayout:
    size = QPageSize(
        QSizeF(width_mm, height_mm),
        QPageSize.Unit.Millimeter,
        "Chronologia",
        QPageSize.SizeMatchPolicy.ExactMatch,
    )
    orientation = QPageLayout.Orientation.Portrait
    if size.id() != QPageSize.PageSizeId.Custom and width_mm > height_mm:
        orientation = QPageLayout.Orientation.Landscape  # format normalisé : stocké en portrait
    return QPageLayout(size, orientation, QMarginsF(0, 0, 0, 0))


def write_pdf(path: str | Path, plan: PosterPlan, document_title: str = "") -> None:
    """Écrit ``plan`` en PDF. L'écriture est atomique : l'ancien fichier reste intact en cas d'échec."""
    target = QSaveFile(str(path))
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise PdfExportError(target.errorString())
    try:
        writer = QPdfWriter(target)
        writer.setResolution(72)  # 1 unité de peintre = 1 point
        writer.setPageLayout(
            _page_layout(
                plan.page_width_pt / 72 * 25.4,
                plan.page_height_pt / 72 * 25.4,
            )
        )
        writer.setCreator("Chronologia")
        writer.setTitle(document_title or plan.title or "Chronologia")
        painter = QPainter(writer)
        if not painter.isActive():
            raise PdfExportError("impossible d'initialiser le PDF")
        try:
            plan.apply_transform(painter)
            paint_poster(painter, plan)
        finally:
            painter.end()
        if not target.commit():
            raise PdfExportError(target.errorString())
    except BaseException:
        target.cancelWriting()
        raise
