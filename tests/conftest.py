import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # tests de l'interface sans écran


@pytest.fixture(scope="session", autouse=True)
def _isolated_settings(tmp_path_factory):
    """Les tests n'écrivent jamais dans la configuration réelle de l'utilisateur."""
    from PySide6.QtCore import QSettings

    config = tmp_path_factory.mktemp("config")  # catégories de l'utilisateur (categories.py)
    os.environ["XDG_CONFIG_HOME"] = str(config)
    os.environ["APPDATA"] = str(config)

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path_factory.mktemp("qsettings")),
    )
