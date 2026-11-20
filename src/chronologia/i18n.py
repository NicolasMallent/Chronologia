"""Langue de l'interface : français (langue source), anglais, espagnol.

Le choix de l'utilisateur est le seul réglage enregistré (``QSettings``, fichier local) ;
aucune autre donnée n'est conservée. Sans choix, on suit la langue du système.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QSettings, QTranslator

LANGUAGES = {"fr": "Français", "en": "English", "es": "Español"}
SOURCE_LANGUAGE = "fr"  # langue des textes dans le code : aucun fichier .qm nécessaire
DEFAULT_FALLBACK = "en"  # langue système non prise en charge
TRANSLATIONS_DIR = Path(__file__).parent / "translations"
_KEY = "language"


def _settings() -> QSettings:
    return QSettings("Chronologia", "Chronologia")


def saved_language() -> str | None:
    value = _settings().value(_KEY)
    return value if value in LANGUAGES else None


def save_language(code: str) -> None:
    if code not in LANGUAGES:
        raise ValueError(f"langue non prise en charge : {code!r}")
    settings = _settings()
    settings.setValue(_KEY, code)
    settings.sync()


def system_language() -> str:
    code = QLocale.system().name().split("_")[0]
    return code if code in LANGUAGES else DEFAULT_FALLBACK


def effective_language() -> str:
    return saved_language() or system_language()


def install_translators(app: QCoreApplication, language: str) -> list[QTranslator]:
    """Installe les traductions de l'application et celles de Qt (boutons standards).

    Renvoie les traducteurs : l'appelant doit les garder en vie.
    """
    QLocale.setDefault(QLocale(language))
    installed: list[QTranslator] = []
    if language == SOURCE_LANGUAGE:
        return installed
    candidates = (
        (TRANSLATIONS_DIR, f"chronologia_{language}"),
        (Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)), f"qtbase_{language}"),
    )
    for directory, name in candidates:
        translator = QTranslator(app)
        if translator.load(name, str(directory)):
            app.installTranslator(translator)
            installed.append(translator)
    return installed
