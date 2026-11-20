import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from chronologia import i18n
from chronologia.csv_io import CsvFormatError, parse_events
from chronologia.main_window import MainWindow
from chronologia.messages import format_error_text, issue_text


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def language(app):
    """Installe une langue le temps d'un test, puis revient au français."""
    installed = []

    def use(code):
        installed.extend(i18n.install_translators(app, code))

    yield use
    for translator in installed:
        app.removeTranslator(translator)


def menu_titles(window):
    return [a.text() for a in window.menuBar().actions()]


@pytest.mark.parametrize(
    "code, file_menu, edit_menu",
    [("fr", "&Fichier", "&Édition"), ("en", "&File", "&Edit"), ("es", "&Archivo", "&Edición")],
)
def test_menus_traduits(language, code, file_menu, edit_menu):
    language(code)
    window = MainWindow()
    assert menu_titles(window)[:2] == [file_menu, edit_menu]
    window.close()


def test_textes_hors_fenetre_traduits(language):
    language("en")
    assert QCoreApplication.translate("Document", "Ajouter un événement") == "Add an event"
    result = parse_events(b"start,end,title,color\nxx,1900,A,red\n")
    assert "invalid start date" in issue_text(result.issues[0])
    with pytest.raises(CsvFormatError) as error:
        parse_events(b"a,b\n")
    assert format_error_text(error.value) == "Required columns missing: start, end, title, color"


def test_boutons_standards_de_qt_traduits(language):
    language("es")
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") != "Cancel"


def test_aucune_traduction_inachevee_ni_manquante():
    import re

    for lang in ("en", "es"):
        text = (i18n.TRANSLATIONS_DIR / f"chronologia_{lang}.ts").read_text(encoding="utf-8")
        assert 'type="unfinished"' not in text
        assert not re.search(r"<translation></translation>", text)
        assert (i18n.TRANSLATIONS_DIR / f"chronologia_{lang}.qm").stat().st_size > 1000


def test_choix_de_langue_enregistre_et_valide():
    assert i18n.saved_language() is None or i18n.saved_language() in i18n.LANGUAGES
    i18n.save_language("es")
    assert i18n.saved_language() == "es" and i18n.effective_language() == "es"
    with pytest.raises(ValueError):
        i18n.save_language("xx")
    i18n.save_language("fr")
