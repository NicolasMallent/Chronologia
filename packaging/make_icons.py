"""Génère icon.png (256 px) et icon.ico à partir de icon.svg. Usage : python packaging/make_icons.py"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

here = Path(__file__).parent
app = QGuiApplication(sys.argv)
renderer = QSvgRenderer(str(here / "icon.svg"))
for size, name in ((256, "icon.png"), (256, "icon.ico")):
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(here / name)):
        raise SystemExit(f"échec de l'écriture de {name}")
    print("écrit", name)
