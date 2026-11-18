# Composants tiers / Third-party components

Chronologia est distribué avec les composants suivants, sous leurs propres licences.

| Composant | Licence | Source |
|-----------|---------|--------|
| Qt 6 / PySide6 (Qt for Python) | LGPL-3.0 (Qt GPL/LGPL) | https://www.qt.io/ , https://pypi.org/project/PySide6/ |
| Python | PSF License | https://www.python.org/ |
| PyInstaller (outil de construction, bootloader inclus) | GPL-2.0 avec exception pour les programmes empaquetés | https://pyinstaller.org/ |
| Noto Sans / polices système | selon la police | utilisées via le système |

## Qt / PySide6 (LGPL-3.0)

Les bibliothèques Qt sont fournies sous forme de bibliothèques dynamiques distinctes, dans le
dossier de l'application (`_internal/PySide6/Qt/lib`). Vous pouvez les remplacer par une version
modifiée de Qt, conformément à la licence LGPL-3.0, dont le texte est disponible sur
https://www.gnu.org/licenses/lgpl-3.0.html. Le code source de Qt est disponible sur
https://download.qt.io/ .

The Qt libraries are shipped as separate shared libraries in the application folder; you may
replace them with a modified version of Qt as permitted by the LGPL-3.0.
