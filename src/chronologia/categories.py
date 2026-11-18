"""Catégories de la frise : correspondance nom de catégorie ↔ couleur.

La couleur d'un événement fait office de catégorie (pas de colonne dédiée dans le CSV).
Deux couleurs identiques une fois résolues (``grey`` et ``#808080``) désignent la même
catégorie. Les valeurs par défaut sont fournies avec l'application
(``defaults/categories.json``) ; la copie de l'utilisateur est stockée dans son dossier de
configuration, ce qui la rend persistante et modifiable (ajout, suppression, renommage).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from .colors import resolve_color
from .model import Event

APP_DIR_NAME = "chronologia"
CONFIG_FILE_NAME = "categories.json"
FORMAT_VERSION = 1
MAX_NAME_LENGTH = 200


class CategoryError(ValueError):
    """Catégorie invalide (nom vide, couleur inconnue, couleur ou nom déjà pris)."""


@dataclass(frozen=True)
class Category:
    name: str
    color: str  # texte saisi (``skyblue`` ou ``#87CEEB``)

    @property
    def color_hex(self) -> str:
        resolved = resolve_color(self.color)
        if resolved is None:  # garanti par CategoryRegistry
            raise CategoryError(f"couleur inconnue : {self.color!r}")
        return resolved


def config_dir() -> Path:
    """Dossier de configuration de l'utilisateur (``%APPDATA%`` sous Windows, XDG sous Linux)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR_NAME


def default_config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


class CategoryRegistry:
    """Liste ordonnée de catégories ; l'ordre est celui des lignes de la frise."""

    def __init__(self, categories: list[Category] | None = None) -> None:
        self._items: list[Category] = []
        for category in categories or []:
            self.add(category.name, category.color)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def _check(self, name: str, color: str, ignore: Category | None = None) -> tuple[str, str]:
        name = name.strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise CategoryError("nom de catégorie vide ou trop long")
        hex_color = resolve_color(color)
        if hex_color is None:
            raise CategoryError(f"couleur inconnue : {color!r}")
        for other in self._items:
            if other is ignore:
                continue
            if other.name.casefold() == name.casefold():
                raise CategoryError(f"le nom {name!r} existe déjà")
            if other.color_hex == hex_color:
                raise CategoryError(f"la couleur {color!r} est déjà utilisée par {other.name!r}")
        return name, color.strip()

    def add(self, name: str, color: str) -> Category:
        name, color = self._check(name, color)
        category = Category(name, color)
        self._items.append(category)
        return category

    def update(self, old: Category, name: str, color: str) -> Category:
        """Renomme ou recolore ``old`` en gardant sa position."""
        name, color = self._check(name, color, ignore=old)
        new = Category(name, color)
        self._items[self._items.index(old)] = new
        return new

    def remove(self, category: Category) -> None:
        self._items.remove(category)

    def for_color(self, color: str) -> Category | None:
        hex_color = resolve_color(color)
        return next((c for c in self._items if c.color_hex == hex_color), None)

    def category_name(self, event: Event) -> str:
        """Nom de la catégorie d'un événement ; à défaut, sa couleur résolue."""
        found = self.for_color(event.color)
        return found.name if found else event.color_hex

    def to_json(self) -> str:
        data = {
            "version": FORMAT_VERSION,
            "categories": [{"name": c.name, "color": c.color} for c in self._items],
        }
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> CategoryRegistry:
        """Lit un JSON ; lève :class:`CategoryError` s'il est mal formé."""
        try:
            data = json.loads(text)
            raw = data["categories"]
            return cls([Category(str(item["name"]), str(item["color"])) for item in raw])
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, CategoryError):
                raise
            raise CategoryError(f"fichier de catégories illisible : {exc}") from exc


def default_registry() -> CategoryRegistry:
    """Catégories livrées avec l'application."""
    text = resources.files("chronologia").joinpath("defaults", "categories.json")
    return CategoryRegistry.from_json(text.read_text(encoding="utf-8"))


def load_registry(path: Path | None = None) -> tuple[CategoryRegistry, str | None]:
    """Charge la configuration de l'utilisateur, ou les valeurs par défaut.

    Renvoie ``(registre, avertissement)``. Fichier absent : défauts, sans avertissement.
    Fichier illisible : défauts et message à afficher (le fichier n'est pas écrasé).
    """
    path = path or default_config_path()
    if not path.exists():
        return default_registry(), None
    try:
        return CategoryRegistry.from_json(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, CategoryError) as exc:
        return default_registry(), f"{path} : {exc}"


def save_registry(registry: CategoryRegistry, path: Path | None = None) -> Path:
    """Enregistre la configuration de façon atomique (pas de fichier tronqué en cas de panne)."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(registry.to_json())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
