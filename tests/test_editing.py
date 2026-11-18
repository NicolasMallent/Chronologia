from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from chronologia.csv_io import parse_events, read_events
from chronologia.event_form import build_event
from chronologia.main_window import MainWindow

EXEMPLE = Path(__file__).parent.parent / "input_claude" / "exemple_timeline.csv"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    w = MainWindow()
    csv = tmp_path / "t.csv"
    csv.write_bytes(b"start,end,title,color\n1900,1900,A,red\n1910,1920,B,black\n1930,1930,C,red\n")
    assert w.load_file(csv)
    yield w
    w.document.stack.setClean()  # évite la question à la fermeture
    w.close()


def make(title="Nouveau", start="1950", end="", color="red"):
    event, errors = build_event(title, start, end, color, "")
    assert not errors
    return event


def titles(w):
    return [e.title for e in w.document.events]


def test_ajout_modification_suppression_et_annulation(window):
    w = window
    assert w.view.displayed_count == 3 and w.document.stack.isClean()

    new = make()
    w.add_event(new)
    assert titles(w) == ["A", "B", "C", "Nouveau"] and w.view.displayed_count == 4
    assert not w.document.stack.isClean() and w.windowTitle().endswith("*")

    edited = make("Renommé", "1951", "1960", "green")  # nouvelle couleur → nouvelle catégorie
    w.replace_event(new, edited)
    assert titles(w)[-1] == "Renommé"
    assert w._category_entries()[-1][0] == "Législation agricole française"

    w.remove_event(w.document.events[0])
    assert titles(w) == ["B", "C", "Renommé"] and w.view.displayed_count == 3

    for _ in range(3):
        w.document.stack.undo()
    assert titles(w) == ["A", "B", "C"] and w.document.stack.isClean()
    w.document.stack.redo()
    assert titles(w) == ["A", "B", "C", "Nouveau"]


def test_annuler_une_suppression_remet_a_la_meme_place(window):
    w = window
    middle = w.document.events[1]
    w.remove_event(middle)
    w.document.stack.undo()
    assert w.document.events[1] is middle


def test_doublons_distingues_par_identite(window):
    w = window
    a = make("Même", "1900")
    b = make("Même", "1900")
    w.add_event(a)
    w.add_event(b)
    w.remove_event(b)
    assert w.document.events[-1] is a and len(w.document.events) == 4


def test_ajout_dans_categorie_masquee_la_reaffiche(window):
    w = window
    w.filters.visibleChanged.emit({"Contexte politique international"})
    w.filters.set_categories(w._category_entries())  # tout recoché
    w.filters.visibleChanged.emit({"Contexte politique international"})
    w.add_event(make("Rouge", "1960", "", "red"))
    assert "Evènements historiques" in w.filters.visible_categories()


def test_enregistrement_et_relecture(window, tmp_path):
    w = window
    w.add_event(make("=Piège", "1960", "1970", "blue"))
    assert w.save() and w.document.stack.isClean()
    again = read_events(w._path).events
    assert [e.title for e in again] == titles(w)
    assert again[-1].start.to_csv() == "1960" and again[-1].color == "blue"


def test_enregistrer_apres_import_avec_lignes_ignorees_demande_un_nouveau_nom(
    app, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    bad = tmp_path / "src.csv"
    bad.write_bytes(b"start,end,title,color\n1900,1900,A,red\nxx,1,B,red\n")
    w = MainWindow()
    assert w.load_file(bad) and w._lossy
    target = tmp_path / "copie.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    assert w.save()
    assert target.exists() and "xx" in bad.read_text()  # l'original n'est pas touché
    w.close()


@pytest.mark.skipif(not EXEMPLE.exists(), reason="CSV d'exemple absent")
def test_exemple_aller_retour_apres_edition(app, tmp_path):
    w = MainWindow()
    w.load_file(EXEMPLE)
    original = list(w.document.events)
    w.replace_event(original[0], make("Modifié", "1862", "", "grey"))
    out = tmp_path / "out.csv"
    w._write(out)
    again = parse_events(out.read_bytes())
    assert again.issues == [] and len(again.events) == 223
    assert again.events[0].title == "Modifié"
    w.close()
