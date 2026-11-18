from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from chronologia.main_window import MainWindow

EXEMPLE = Path(__file__).parent.parent / "input_claude" / "exemple_timeline.csv"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = MainWindow()
    yield w
    w.close()


@pytest.mark.skipif(not EXEMPLE.exists(), reason="CSV d'exemple absent")
def test_ouverture_filtre_recherche_zoom(window):
    assert window.load_file(EXEMPLE)
    view = window.view
    assert view.displayed_count == 223

    window.filters.visibleChanged.emit({"Luttes agricoles"})
    assert view.displayed_count == 41
    window.filters.visibleChanged.emit(set())
    assert view.displayed_count == 0
    window.filters.set_categories(window._category_entries())  # tout recoché
    assert view.displayed_count == 223

    window.search.setText("loi")
    assert view.match_count and view.match_count > 0
    window.search.setText("")
    assert view.match_count is None

    before = view._ppy
    view.zoom_by(2)
    assert view._ppy == pytest.approx(before * 2)
    view.fit_width()
    assert view._ppy == pytest.approx(before)


def test_fichier_invalide_ne_plante_pas(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    assert window.load_file(bad) is False


def test_auto_diagnostic_de_l_installation(window):
    from chronologia.app import run_smoke_test

    assert run_smoke_test(window) == 0
