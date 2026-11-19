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


def test_application_des_categories(window, monkeypatch):
    from chronologia import main_window
    from chronologia.categories import CategoryRegistry

    saved = []
    monkeypatch.setattr(main_window, "save_registry", lambda reg: saved.append(reg))
    registry = CategoryRegistry()
    registry.add("Seule", "red")
    window.apply_registry(registry)
    assert saved == [registry]
    assert window._registry is registry


def test_dialogue_categories_edite_une_copie(app):
    from chronologia.categories import CategoryRegistry
    from chronologia.categories_dialog import CategoriesDialog, CategoryEditDialog

    original = CategoryRegistry()
    original.add("A", "red")
    original.add("B", "blue")
    dialog = CategoriesDialog(original)
    dialog._list.setCurrentRow(1)
    dialog._move(-1)
    assert [c.name for c in dialog.registry()] == ["B", "A"]
    assert [c.name for c in original] == ["A", "B"]  # l'original n'est pas touché

    edit = CategoryEditDialog(dialog.registry(), dialog.registry().for_color("red"))
    edit.name.setText("B")  # doublon
    assert not edit._buttons.button(edit._buttons.StandardButton.Ok).isEnabled()
    assert edit._error.text()
    edit.name.setText("Renommée")
    assert edit._buttons.button(edit._buttons.StandardButton.Ok).isEnabled()


def test_suppression_depuis_la_boite_de_modification(window, monkeypatch):
    from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

    from chronologia.event_dialog import EventDialog

    window.add_event(make("A supprimer"))
    event = window.document.events[-1]
    dialog = EventDialog(window._registry, event=event)
    buttons = dialog.findChildren(QDialogButtonBox)[0]
    delete = next(b for b in buttons.buttons() if b.text() == dialog.tr("Supprimer"))
    delete.click()
    assert dialog.delete_requested

    # la fenêtre demande confirmation puis supprime
    monkeypatch.setattr(EventDialog, "exec", lambda self: self._request_delete() or 0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.edit_event(event)
    assert "A supprimer" not in titles(window)


def test_creation_n_a_pas_de_bouton_supprimer(window):
    from PySide6.QtWidgets import QDialogButtonBox

    from chronologia.event_dialog import EventDialog

    dialog = EventDialog(window._registry)
    buttons = dialog.findChildren(QDialogButtonBox)[0]
    assert all(b.text() != dialog.tr("Supprimer") for b in buttons.buttons())


def test_selection_met_en_valeur_et_suppr_supprime_la_selection(window, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox

    window.resize(1400, 800)
    window.show()
    view = window.view
    event = window.document.events[0]
    group = next(g for g, e in view._groups.items() if e is event)
    center = view.mapFromScene(group.sceneBoundingRect().center())

    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(center))
    assert view.selected_event is event
    assert view._halo is not None

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    asked = []
    view.deleteRequested.connect(asked.append)
    QTest.keyClick(view, Qt.Key.Key_Delete)
    assert asked == [event]

    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert view.selected_event is None and view._halo is None

    # la sélection survit à un changement d'échelle (reconstruction de la scène)
    view.select(event)
    view.zoom_by(1.5)
    assert view._halo is not None
    window.hide()


def test_evenement_ajoute_est_selectionne(window):
    window.add_event(make("Nouveau"))
    assert window.view.selected_event is window.document.events[-1]
    assert window.view.selected_event.title == "Nouveau"


def _wheel(view, delta_y, modifiers=None):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(300, 200)
    event = QWheelEvent(
        pos,
        view.viewport().mapToGlobal(pos),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        modifiers or Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.viewport(), event)


def test_molette_zoome_et_maj_molette_defile(window):
    from PySide6.QtCore import Qt

    window.resize(1400, 800)
    window.show()
    view = window.view
    before = view._ppy
    _wheel(view, 120)
    assert view._ppy > before
    _wheel(view, -120)
    assert view._ppy == pytest.approx(before)
    _wheel(view, 120, Qt.KeyboardModifier.ControlModifier)  # Ctrl + molette zoome aussi
    assert view._ppy > before

    view.set_scale(before)
    bar = view.verticalScrollBar()
    bar.setRange(0, 1000)
    bar.setValue(500)
    _wheel(view, -120, Qt.KeyboardModifier.ShiftModifier)
    assert bar.value() > 500 and view._ppy == pytest.approx(before)
    window.hide()
