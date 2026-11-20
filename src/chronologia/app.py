"""Point d'entrée de l'application."""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import i18n
from .categories import default_registry
from .main_window import MainWindow
from .pdf_export import write_pdf
from .poster import plan_poster
from .theme import apply_theme

SMOKE_TEST_FLAG = "--smoke-test"
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
_SMOKE_CSV = "start,end,title,color\n1900,1950,Période,red\n1930,1930,Ponctuel,skyblue\n"


def run_smoke_test(window: MainWindow) -> int:
    """Vérifie une installation : ressources, import CSV, export PDF. 0 = tout fonctionne."""
    try:
        for lang in ("en", "es"):
            if not (i18n.TRANSLATIONS_DIR / f"chronologia_{lang}.qm").is_file():
                raise RuntimeError(f"traduction {lang} absente")
        if not ICON_PATH.is_file() or len(default_registry()) == 0:
            raise RuntimeError("ressources absentes")
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "smoke.csv"
            csv_path.write_text(_SMOKE_CSV, encoding="utf-8")
            if not window.load_file(csv_path) or len(window.document.events) != 2:
                raise RuntimeError("import CSV en échec")
            plan = plan_poster(window.document.events, default_registry(), None, 420, 297)
            if plan is None:
                raise RuntimeError("mise en page vide")
            pdf_path = Path(tmp) / "smoke.pdf"
            write_pdf(pdf_path, plan)
            if not pdf_path.read_bytes().startswith(b"%PDF"):
                raise RuntimeError("PDF invalide")
    except Exception:  # noqa: BLE001 (tout échec doit donner un code de sortie non nul)
        traceback.print_exc()
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    smoke = SMOKE_TEST_FLAG in args
    args = [a for a in args if a != SMOKE_TEST_FLAG]
    app = QApplication(args)
    app.setApplicationName("Chronologia")
    apply_theme(app)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    translators = i18n.install_translators(app, i18n.effective_language())  # noqa: F841
    window = MainWindow()
    if smoke:
        return run_smoke_test(window)
    window.show()
    if len(args) > 1:
        window.load_file(Path(args[1]))
    return app.exec()
