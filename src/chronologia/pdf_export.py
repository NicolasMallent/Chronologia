"""Écriture du PDF vectoriel (taille de page personnalisée)."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QIODevice, QMarginsF, QSaveFile, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter

from .formats import STANDARD_FORMATS
from .poster import PosterPlan, paint_poster

# Au-delà, certains lecteurs PDF (Acrobat) refusent la page : 200 pouces = 5,08 m.
PDF_COMFORT_LIMIT_MM = 5080.0
PAGE_SIZES_MM = {f.name: (f.width_mm, f.height_mm) for f in STANDARD_FORMATS}  # en portrait


def export_divisor(width_mm: float, height_mm: float) -> int:
    """Plus petit entier N tel que la page réduite à 1/N tienne dans la limite des lecteurs PDF.

    1 = pas de réduction. Au-delà, le PDF est écrit à l'échelle 1/N (vectoriel, sans perte) et
    doit être imprimé à N × 100 %.
    """
    return max(1, math.ceil(max(width_mm, height_mm) / PDF_COMFORT_LIMIT_MM))


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


def write_pdf(
    path: str | Path, plan: PosterPlan, document_title: str = "", divisor: int = 1
) -> None:
    """Écrit ``plan`` en PDF. L'écriture est atomique : l'ancien fichier reste intact en cas d'échec.

    ``divisor`` > 1 : page réduite à 1/``divisor`` (à imprimer à ``divisor`` × 100 %).
    """
    if divisor < 1:
        raise ValueError("le diviseur d'export doit être >= 1")
    target = QSaveFile(str(path))
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise PdfExportError(target.errorString())
    try:
        writer = QPdfWriter(target)
        writer.setResolution(72)  # 1 unité de peintre = 1 point
        writer.setPageLayout(
            _page_layout(
                plan.page_width_pt / 72 * 25.4 / divisor,
                plan.page_height_pt / 72 * 25.4 / divisor,
            )
        )
        writer.setCreator("Chronologia")
        writer.setTitle(document_title or plan.title or "Chronologia")
        painter = QPainter(writer)
        if not painter.isActive():
            raise PdfExportError("impossible d'initialiser le PDF")
        try:
            painter.scale(1 / divisor, 1 / divisor)
            plan.apply_transform(painter)
            paint_poster(painter, plan)
        finally:
            painter.end()
        if not target.commit():
            raise PdfExportError(target.errorString())
    except BaseException:
        target.cancelWriting()
        raise
