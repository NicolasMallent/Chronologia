# PyInstaller : dossier autonome (onedir). Lancer depuis la racine :
#   pyinstaller --noconfirm --clean packaging/chronologia.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "src", "chronologia")

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=[
        (os.path.join(PKG, "translations", "*.qm"), "chronologia/translations"),
        (os.path.join(PKG, "defaults", "*.json"), "chronologia/defaults"),
        (os.path.join(PKG, "resources", "*.png"), "chronologia/resources"),
    ],
    # modules Qt inutiles pour l'application : on garde le paquet léger
    excludes=[
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
        "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtNetwork",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chronologia",
    console=False,  # application graphique
    icon=os.path.join(ROOT, "packaging", "icon.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="chronologia")
