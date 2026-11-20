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


@pytest.fixture(autouse=True)
def _delete_widgets_after_each_test():
    """Détruit les fenêtres et dialogues créés par un test, tant que Python fonctionne.

    Sans cela, des widgets restent vivants jusqu'à l'arrêt de l'interpréteur ; PySide les détruit
    alors dans le désordre et provoque parfois une erreur de segmentation à la sortie (ce qui fait
    échouer la CI même quand tous les tests passent).
    """
    yield
    import gc

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.hide()  # pas de close() : il pourrait poser la question « enregistrer ? »
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()
    app.processEvents()
