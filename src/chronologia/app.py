"""Point d'entrée de l'application."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .i18n import effective_language, install_translators
from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    app = QApplication(args)
    app.setApplicationName("Chronologia")
    translators = install_translators(app, effective_language())  # noqa: F841 (gardés en vie)
    window = MainWindow()
    window.show()
    if len(args) > 1:
        window.load_file(Path(args[1]))
    return app.exec()
