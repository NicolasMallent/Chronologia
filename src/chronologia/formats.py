"""Formats de feuille : formats normalisés (A6 à A0) et formats personnalisés enregistrés.

Les formats personnalisés (ex. « Banderole 10 m × 1 m ») sont conservés dans le dossier de
configuration de l'utilisateur, comme les catégories : fichier JSON local, écriture atomique,
taille et contenu bornés, repli sur « aucun format » si le fichier est illisible.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .categories import config_dir

FORMATS_FILE_NAME = "formats.json"
FORMAT_VERSION = 1
MIN_SIDE_MM = 50.0
MAX_SIDE_MM = 20000.0  # 20 m
MAX_FORMATS = 50
MAX_NAME_LENGTH = 60
MAX_CONFIG_BYTES = 256 * 1024


class FormatError(ValueError):
    """Format invalide (nom vide ou déjà pris, dimensions hors limites)."""

    NAME_INVALID = "name_invalid"
    NAME_EXISTS = "name_exists"
    SIZE_INVALID = "size_invalid"
    TOO_MANY = "too_many"

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PageFormat:
    name: str
    width_mm: float  # en portrait pour les formats normalisés (largeur <= hauteur)
    height_mm: float

    def oriented(self, landscape: bool) -> tuple[float, float]:
        """(largeur, hauteur) en paysage ou en portrait."""
        short, long = sorted((self.width_mm, self.height_mm))
        return (long, short) if landscape else (short, long)


STANDARD_FORMATS: tuple[PageFormat, ...] = (
    PageFormat("A6", 105.0, 148.0),
    PageFormat("A5", 148.0, 210.0),
    PageFormat("A4", 210.0, 297.0),
    PageFormat("A3", 297.0, 420.0),
    PageFormat("A2", 420.0, 594.0),
    PageFormat("A1", 594.0, 841.0),
    PageFormat("A0", 841.0, 1189.0),
)


def valid_size(width_mm: float, height_mm: float) -> bool:
    return all(math.isfinite(v) and MIN_SIDE_MM <= v <= MAX_SIDE_MM for v in (width_mm, height_mm))


def check_format(
    name: str, width_mm: float, height_mm: float, existing: list[PageFormat]
) -> PageFormat:
    """Valide un nouveau format personnalisé (``existing`` : formats personnalisés déjà connus)."""
    name = name.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise FormatError("nom de format vide ou trop long", FormatError.NAME_INVALID)
    if not valid_size(width_mm, height_mm):
        raise FormatError("dimensions hors limites", FormatError.SIZE_INVALID)
    taken = {f.name.casefold() for f in STANDARD_FORMATS} | {f.name.casefold() for f in existing}
    if name.casefold() in taken:
        raise FormatError(f"le nom {name!r} existe déjà", FormatError.NAME_EXISTS)
    if len(existing) >= MAX_FORMATS:
        raise FormatError("trop de formats", FormatError.TOO_MANY)
    return PageFormat(name, float(width_mm), float(height_mm))


def formats_path() -> Path:
    return config_dir() / FORMATS_FILE_NAME


def _to_json(formats: list[PageFormat]) -> str:
    data = {
        "version": FORMAT_VERSION,
        "formats": [
            {"name": f.name, "width_mm": f.width_mm, "height_mm": f.height_mm} for f in formats
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _from_json(text: str) -> list[PageFormat]:
    try:
        raw = json.loads(text)["formats"]
        result: list[PageFormat] = []
        for item in raw:
            result.append(
                check_format(
                    str(item["name"]), float(item["width_mm"]), float(item["height_mm"]), result
                )
            )
        return result
    except FormatError:
        raise
    except (ValueError, KeyError, TypeError) as exc:
        raise FormatError(f"fichier de formats illisible : {exc}") from exc


def load_formats(path: Path | None = None) -> tuple[list[PageFormat], str | None]:
    """Formats personnalisés de l'utilisateur. Renvoie ``(formats, avertissement)``.

    Fichier absent : liste vide, sans avertissement. Fichier illisible : liste vide et message
    (le fichier n'est pas écrasé).
    """
    path = path or formats_path()
    if not path.exists():
        return [], None
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            raise FormatError("fichier de formats trop volumineux")
        return _from_json(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, FormatError) as exc:
        return [], f"{path} : {exc}"


def save_formats(formats: list[PageFormat], path: Path | None = None) -> Path:
    """Enregistre les formats de façon atomique."""
    path = path or formats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_to_json(formats))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


@dataclass(frozen=True)
class PageSettings:
    """Réglages de la feuille, partagés entre le panneau et la mise en page."""

    width_mm: float
    height_mm: float
    title: str = ""
    font_pt: float = 8.0  # taille du texte demandée sur la feuille
    max_label_lines: int = 3
    time_range: tuple[float, float] | None = None

    @property
    def landscape(self) -> bool:
        return self.width_mm > self.height_mm
