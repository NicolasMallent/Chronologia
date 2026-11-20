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
    assert not w.document.stack.isClean() and w.windowTitle() == "Chronologia *"

    edited = make("Renommé", "1951", "1960", "green")  # nouvelle couleur → nouvelle catégorie
    w.replace_event(new, edited)
    assert titles(w)[-1] == "Renommé"
    entries = {name: count for name, _color, count in w._category_entries()}
    assert entries["Législation agricole française"] == 1  # la nouvelle catégorie compte 1

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


def test_nouvel_evenement_ici_prend_la_categorie_de_la_ligne(window):
    from chronologia.event_dialog import EventDialog

    window.resize(1400, 800)
    window.show()
    view = window.view
    lanes = view._layout.lanes
    black, red = lanes[0], lanes[1]  # dans l'exemple : noir puis rouge
    assert view.lane_color_at(0) == ""  # sur l'axe : aucune ligne
    for lane in (black, red):
        scene_y = 30 + lane.y + lane.height / 2
        view_y = view.mapFromScene(0, scene_y).y()
        assert view.lane_color_at(view_y) == lane.color_hex

    dialog = EventDialog(window._registry, start_hint="1950", color_hint=red.color_hex)
    assert dialog.color.text() == window._registry.for_color(red.color_hex).color
    assert dialog.start.text() == "1950"
    inconnue = EventDialog(window._registry, color_hint="#123456")
    assert inconnue.color.text() == "#123456"
    sans = EventDialog(window._registry)
    assert sans.color.text() == next(iter(window._registry)).color
    window.hide()


def test_categorie_creee_sans_evenement_apparait_dans_la_frise_et_le_panneau(window, monkeypatch):
    from chronologia import main_window
    from chronologia.categories import CategoryRegistry

    monkeypatch.setattr(main_window, "save_registry", lambda reg: None)
    registry = CategoryRegistry(list(window._registry))
    registry.add("Nouvelle catégorie", "#123456")
    window.apply_registry(registry)
    panel = [entry for entry in window._category_entries() if entry[0] == "Nouvelle catégorie"]
    assert panel == [("Nouvelle catégorie", "#123456", 0)]
    assert "Nouvelle catégorie" in window.filters.visible_categories()
    assert "Nouvelle catégorie" in [lane.name for lane in window.view._layout.lanes]


def test_titre_sans_nom_de_fichier(window):
    assert window.windowTitle() == "Chronologia"  # fichier "t.csv" ouvert, mais pas dans le titre


def _recolor_through_dialog(monkeypatch, registry, old_name, new_color):
    """Modifie la couleur de la catégorie ``old_name`` comme le ferait l'utilisateur."""
    from chronologia import categories_dialog
    from chronologia.categories_dialog import CategoriesDialog

    dialog = CategoriesDialog(registry)
    names = [c.name for c in dialog.registry()]
    dialog._list.setCurrentRow(names.index(old_name))

    class FakeEdit:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return True

        def values(self):
            return old_name, new_color

    monkeypatch.setattr(categories_dialog, "CategoryEditDialog", FakeEdit)
    dialog._edit()
    return dialog


def test_changer_la_couleur_d_une_categorie_recolore_ses_evenements(window, monkeypatch):
    from chronologia import main_window

    monkeypatch.setattr(main_window, "save_registry", lambda reg: None)
    before = window.view.displayed_count
    red_before = [e.title for e in window.document.events if e.color == "red"]
    assert red_before  # « A » et « C » sont rouges
    old_name = window._registry.for_color("red").name

    dialog = _recolor_through_dialog(monkeypatch, window._registry, old_name, "#7c3aed")
    assert dialog.color_changes() == {"#ff0000": "#7c3aed"}
    window.apply_registry(dialog.registry(), dialog.color_changes())

    assert window.view.displayed_count == before  # rien ne disparaît
    assert [e.title for e in window.document.events if e.color == "#7c3aed"] == red_before
    lane_names = [lane.name for lane in window.view._layout.lanes]
    assert old_name in lane_names and "#ff0000" not in lane_names
    assert old_name in window.filters.visible_categories()
    entries = {name: count for name, _color, count in window._category_entries()}
    assert entries[old_name] == len(red_before)

    # un seul « annuler » rend aux événements leur ancienne couleur
    window.document.stack.undo()
    assert [e.title for e in window.document.events if e.color == "red"] == red_before


def test_aucun_changement_de_couleur_si_seul_le_nom_change(window, monkeypatch):
    from chronologia.categories_dialog import CategoriesDialog

    dialog = CategoriesDialog(window._registry)
    assert dialog.color_changes() == {}
    count = window.document.stack.count()
    window.apply_registry(dialog.registry(), dialog.color_changes())
    assert window.document.stack.count() == count


def _fake_edit_dialog(monkeypatch, name, color, accepted=True):
    from chronologia import main_window

    seen = {}

    class FakeEdit:
        def __init__(self, registry, category=None, parent=None, color=""):
            seen["category"], seen["color"] = category, color

        def exec(self):
            return accepted

        def values(self):
            return name, color

    monkeypatch.setattr(main_window, "CategoryEditDialog", FakeEdit)
    monkeypatch.setattr(main_window, "save_registry", lambda reg: None)
    return seen


def test_clic_droit_sur_une_categorie_propose_de_la_modifier(window, monkeypatch):
    from PySide6.QtCore import Qt

    _fake_edit_dialog(monkeypatch, "X", "#000001", accepted=False)  # la fenêtre ouvre le dialogue

    panel = window.filters
    received = []
    panel.editRequested.connect(received.append)
    item = panel._list.item(1)
    assert item is not None
    panel.editRequested.emit(item.data(Qt.ItemDataRole.UserRole))  # ce que déclenche le menu
    assert received == [item.data(Qt.ItemDataRole.UserRole)]
    assert panel._list.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


def test_modifier_une_categorie_depuis_le_panneau_renomme_et_recolore(window, monkeypatch):
    old = window._registry.for_color("red")
    seen = _fake_edit_dialog(monkeypatch, "Rouge renommé", "#7c3aed")
    window.edit_category(old.name)
    assert seen["category"].name == old.name
    assert window._registry.by_name("Rouge renommé").color == "#7c3aed"
    assert window._registry.by_name(old.name) is None
    assert [e.title for e in window.document.events if e.color == "#7c3aed"] == ["A", "C"]
    entries = {n: c for n, _col, c in window._category_entries()}
    assert entries["Rouge renommé"] == 2
    assert window.view.displayed_count == 3


def test_renommer_une_categorie_depuis_le_panneau_garde_les_couleurs(window, monkeypatch):
    old = window._registry.for_color("red")
    _fake_edit_dialog(monkeypatch, "Autre nom", old.color)
    count = window.document.stack.count()
    window.edit_category(old.name)
    assert window._registry.by_name("Autre nom") is not None
    assert window.document.stack.count() == count  # aucun événement modifié


def test_annuler_le_dialogue_ne_change_rien(window, monkeypatch):
    old = window._registry.for_color("red")
    _fake_edit_dialog(monkeypatch, "X", "#000001", accepted=False)
    registry = window._registry
    window.edit_category(old.name)
    assert window._registry is registry


def test_couleur_sans_categorie_proposee_a_l_ajout(window, monkeypatch):
    window.add_event(make("Violet", color="purple"))
    seen = _fake_edit_dialog(monkeypatch, "Ma catégorie", "purple")
    window.edit_category("#800080")  # nom implicite de la couleur « purple »
    assert seen["category"] is None and seen["color"] == "#800080"
    assert window._registry.by_name("Ma catégorie") is not None
    assert [n for n, _c, count in window._category_entries() if count and n == "Ma catégorie"]
