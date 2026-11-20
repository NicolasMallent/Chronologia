import pytest
from PySide6.QtWidgets import QApplication

from chronologia import theme
from chronologia.icons import ICON_NAMES, make_icon
from chronologia.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("name", ICON_NAMES)
def test_icones_dessinees_en_code(app, name):
    icon = make_icon(name)
    assert not icon.isNull()
    assert not icon.pixmap(20, 20).toImage().isNull()


def test_icone_inconnue(app):
    with pytest.raises(ValueError):
        make_icon("inexistante")


def test_le_theme_s_applique_et_la_fenetre_se_construit(app):
    previous_style, previous_sheet = app.style().objectName(), app.styleSheet()
    try:
        theme.apply_theme(app)
        assert app.palette().highlight().color().name() == theme.ACCENT
        window = MainWindow()
        buttons = [b for b in window.findChildren(type(window.search)) if b is window.search]
        assert buttons  # barre de recherche présente
        window.document.stack.setClean()
        window.close()
    finally:
        app.setStyleSheet(previous_sheet)
        app.setStyle(previous_style)
