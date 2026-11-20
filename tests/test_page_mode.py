import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from chronologia import main_window
from chronologia.categories import default_registry
from chronologia.csv_io import parse_events
from chronologia.event_form import build_event
from chronologia.formats import PageFormat
from chronologia.main_window import MainWindow
from chronologia.page_controller import PageController
from chronologia.page_panel import CUSTOM, PagePanel

CSV = (
    b"start,end,title,color\n1900,1950,Periode longue,red\n1920,1920,Evenement,black\n"
    b"1960,1960,Autre evenement,red\n1930,1940,Une periode,skyblue\n"
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "save_formats", lambda formats: None)
    w = MainWindow()
    csv = tmp_path / "t.csv"
    csv.write_bytes(CSV)
    assert w.load_file(csv)
    yield w
    w.shortcuts.reset_all()
    QSettings("Chronologia", "Chronologia").remove("view")
    w.document.stack.setClean()
    w.close()


# --- panneau --------------------------------------------------------------------------------


def test_panneau_formats_normalises_et_orientation(app):
    panel = PagePanel()
    names = [panel.format.itemData(i) for i in range(panel.format.count())]
    assert names == ["A6", "A5", "A4", "A3", "A2", "A1", "A0", CUSTOM]
    assert (panel.width_cm.value(), panel.height_cm.value()) == (118.9, 84.1)  # A0 paysage
    panel.landscape.setCurrentIndex(1)  # portrait
    assert (panel.width_cm.value(), panel.height_cm.value()) == (84.1, 118.9)
    panel.format.setCurrentIndex(panel.format.findData("A6"))
    assert (panel.width_cm.value(), panel.height_cm.value()) == (10.5, 14.8)
    panel.width_cm.setValue(30.0)  # saisie manuelle → personnalisé
    assert panel.format.currentData() == CUSTOM and not panel.landscape.isEnabled()
    assert panel.settings().width_mm == pytest.approx(300.0)
    assert panel.format_label() == "30 × 14,8 cm"


def test_panneau_formats_personnalises_enregistres_et_supprimes(app, monkeypatch):
    panel = PagePanel([PageFormat("Banderole", 10000, 1000)])
    emitted = []
    panel.formatsChanged.connect(emitted.append)
    index = panel.format.findData("Banderole")
    assert index > 0 and "10 m" in panel.format.itemText(index)
    panel.format.setCurrentIndex(index)
    assert (panel.width_cm.value(), panel.height_cm.value()) == (1000.0, 100.0)
    assert panel.delete_format.isEnabled()
    panel.landscape.setCurrentIndex(1)  # la banderole peut être tournée en portrait
    assert (panel.width_cm.value(), panel.height_cm.value()) == (100.0, 1000.0)

    panel.set_size_mm(5000, 700)  # nouvelle taille → à enregistrer
    assert panel.format.currentData() == CUSTOM and not panel.delete_format.isEnabled()
    fmt = panel.add_preset("Calicot")
    assert fmt == PageFormat("Calicot", 5000.0, 700.0)
    assert panel.format.currentData() == "Calicot" and emitted[-1][-1] == fmt
    panel.remove_preset("Calicot")
    assert panel.format.currentData() == "A0" and [f.name for f in emitted[-1]] == ["Banderole"]


def test_panneau_refuse_les_formats_invalides(app, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    panel = PagePanel([PageFormat("Banderole", 10000, 1000)])
    assert panel.add_preset("") is None and panel.add_preset("a0") is None
    assert panel.add_preset("banderole") is None
    assert len(shown) == 3 and panel.presets() == [PageFormat("Banderole", 10000, 1000)]


def test_panneau_periode_et_signaux(app):
    panel = PagePanel()
    settings, planner = [], []
    panel.settingsChanged.connect(lambda: settings.append(1))
    panel.plannerSettingsChanged.connect(lambda: planner.append(1))
    panel.title.setText("Titre")
    panel.text_size.setValue(10)
    assert len(settings) == 2 and not planner  # recalcul rapide seulement
    panel.max_lines.setValue(2)
    assert len(planner) == 1
    panel.set_year_bounds(1900, 1960)
    assert (panel.year_from.value(), panel.year_to.value()) == (1900, 1960)
    assert panel.time_range() is None
    panel.limit_period.setChecked(True)
    panel.year_from.setValue(1950)
    panel.year_to.setValue(1930)  # inversés : remis dans l'ordre, l'année de fin est incluse
    assert panel.time_range() == (1930.0, 1951.0)
    assert panel.settings().max_label_lines == 2 and panel.settings().title == "Titre"


# --- contrôleur -------------------------------------------------------------------------------


def make_controller(events, visible=None):
    panel = PagePanel()
    controller = PageController(panel)
    controller.set_data(events, default_registry(), visible)
    return panel, controller


def test_changer_de_format_ne_refait_pas_les_candidats(app):
    events = parse_events(CSV).events
    panel, controller = make_controller(events)
    controller.activate(True)
    planner = controller._planner
    first = controller.plan
    assert first is not None and controller.divisor == 1
    panel.format.setCurrentIndex(panel.format.findData("A4"))
    controller.ensure_current()
    assert controller._planner is planner  # mêmes candidats : seul le choix final change
    assert controller.plan is not first and controller.plan.page_width_pt < first.page_width_pt
    panel.max_lines.setValue(1)
    controller.ensure_current()
    assert controller._planner is not planner  # réglage qui change les candidats


def test_controleur_inactif_ne_calcule_pas_et_banderole_reduite(app):
    events = parse_events(CSV).events
    panel, controller = make_controller(events)
    assert controller.plan is None  # mode Feuille non affiché : aucun calcul
    panel.set_size_mm(10000, 1000)
    controller.activate(True)
    assert controller.plan is not None and controller.divisor == 2
    assert "1/2" in panel._warning.text() and "200" in panel._warning.text()
    panel.set_size_mm(1189, 841)
    controller.ensure_current()
    assert controller.divisor == 1


def test_controleur_sans_evenement_visible(app):
    events = parse_events(CSV).events
    panel, controller = make_controller(events, visible=set())
    controller.activate(True)
    assert controller.plan is None and not panel.export_button.isEnabled()
    controller.set_data(events, default_registry(), None)
    controller.ensure_current()
    assert controller.plan is not None and panel.export_button.isEnabled()


# --- fenêtre ----------------------------------------------------------------------------------


def test_bascule_libre_feuille(window):
    assert not window.page_mode and window._stack.currentWidget() is window.view
    assert not window._page_dock.isVisibleTo(window)
    assert not any(a.isEnabled() for a in window._page_only_actions)
    window.set_mode(True)
    assert window._stack.currentWidget() is window.page_container
    assert window._page_dock.isVisibleTo(window) and window.page_view.plan is not None
    assert all(a.isEnabled() for a in window._page_only_actions)
    assert window._mode_actions[1].isChecked()
    assert "A0" in window._status.text() and "pt" in window._status.text()
    window.set_mode(False)
    assert window._stack.currentWidget() is window.view and window._mode_actions[0].isChecked()


def test_le_mode_choisi_est_memorise_pas_le_mode_programmatique(window):
    settings = QSettings("Chronologia", "Chronologia")
    window.set_mode(True)
    assert settings.value("view/mode") is None
    window._mode_chosen(True)
    assert settings.value("view/mode") == "page"
    other = MainWindow()  # prochain démarrage
    assert other.page_mode
    other.document.stack.setClean()
    other.close()
    window._mode_chosen(False)
    assert settings.value("view/mode") == "free"


def test_filtre_recherche_et_selection_partages(window):
    window.set_mode(True)
    lanes = [lane.name for lane in window.page_view.plan.layout.lanes]
    assert len(lanes) == 3
    window.filters._set_all(Qt.CheckState.Unchecked)
    window.page.ensure_current()
    assert window.page_view.plan is None  # plus rien d'affiché
    window.filters._set_all(Qt.CheckState.Checked)
    window.page.ensure_current()
    assert len(window.page_view.plan.layout.lanes) == 3
    window.search.setText("evenement")
    assert window.page_view.match_count == 2
    window._update_status()
    assert "2 correspondances" in window._status.text()
    event = window.document.events[0]
    window.page_view.select(event)  # sélection faite dans la feuille
    window.set_mode(False)
    assert window.view.selected_event is event  # suivie dans la frise libre
    window.set_mode(True)
    assert window.page_view.selected_event is event


def test_edition_en_mode_feuille(window, monkeypatch):
    window.set_mode(True)
    edited, deleted, created = [], [], []
    monkeypatch.setattr(window, "edit_event", edited.append)
    monkeypatch.setattr(window, "delete_event", deleted.append)
    monkeypatch.setattr(window, "new_event", lambda *a: created.append(a))
    # les signaux ont été branchés sur les méthodes d'origine : on les déclenche via la vue
    event = window.document.events[0]
    window.page_view.editRequested.disconnect()
    window.page_view.deleteRequested.disconnect()
    window.page_view.newRequested.disconnect()
    window.page_view.editRequested.connect(window.edit_event)
    window.page_view.deleteRequested.connect(window.delete_event)
    window.page_view.newRequested.connect(window.new_event)
    window.page_view.editRequested.emit(event)
    window.page_view.deleteRequested.emit(event)
    window.page_view.newRequested.emit("1950", "#ff0000")
    assert edited == [event] and deleted == [event] and created == [("1950", "#ff0000")]


def test_ajout_et_suppression_mettent_la_feuille_a_jour(window):
    window.set_mode(True)
    before = window.page_view.plan.event_count
    new, _ = build_event("Nouveau", "1970", "", "red", "")
    window.add_event(new)
    window.page.ensure_current()
    assert window.page_view.plan.event_count == before + 1
    assert window.page_view.selected_event is window.document.events[-1]
    window.remove_event(window.document.events[-1])
    window.page.ensure_current()
    assert window.page_view.plan.event_count == before


def test_categories_modifiees_rafraichissent_la_feuille(window, monkeypatch):
    from chronologia.categories import CategoryRegistry

    monkeypatch.setattr(main_window, "save_registry", lambda reg: None)
    window.set_mode(True)
    registry = CategoryRegistry(list(window._registry))
    old = registry.for_color("red")
    registry.update(old, "Rouge", "#7c3aed")
    window.apply_registry(registry, {"#ff0000": "#7c3aed"})
    window.page.ensure_current()
    assert "Rouge" in [lane.name for lane in window.page_view.plan.layout.lanes]


def test_export_depuis_le_mode_libre_bascule_sans_exporter(window, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: called.append(1) or ("", "")
    )
    window.export_pdf()
    assert window.page_mode and not called
    assert window.statusBar().currentMessage()


def test_export_banderole_reduit_et_l_indique(window, tmp_path, monkeypatch):
    import re

    window.set_mode(True)
    window.page_panel.set_size_mm(10000, 1000)
    out = tmp_path / "banderole.pdf"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    window.export_pdf()
    match = re.search(rb"/MediaBox \[0 0 ([\d.]+) ([\d.]+)\]", out.read_bytes())
    assert float(match.group(1)) * 25.4 / 72 == pytest.approx(5000, rel=1e-3)  # 10 m → 5 m
    assert "200" in window.statusBar().currentMessage()


def test_export_sans_evenement_previent(window, monkeypatch):
    window.set_mode(True)
    window.filters._set_all(Qt.CheckState.Unchecked)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a))
    window.export_pdf()
    assert shown


def test_enregistrer_un_format_depuis_la_fenetre(window, monkeypatch):
    saved = []
    monkeypatch.setattr(main_window, "save_formats", saved.append)
    window.set_mode(True)
    window.page_panel.set_size_mm(5000, 700)
    window.page_panel.add_preset("Calicot")
    assert saved and saved[-1][0].name == "Calicot"
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: errors.append(a))

    def boom(formats):
        raise OSError("disque plein")

    monkeypatch.setattr(main_window, "save_formats", boom)
    window.page_panel.set_size_mm(4000, 600)
    window.page_panel.add_preset("Autre")
    assert errors and window.page_panel.format.findData("Autre") >= 0  # appliqué malgré l'échec


def test_actions_et_raccourcis_du_mode_feuille(window):
    ids = set(window.shortcuts.ids())
    assert {"fit_width_page", "fit_height_page", "actual_size", "mode_free", "mode_page"} <= ids
    assert {"toggle_rulers", "toggle_navigator"} <= ids
    assert window.shortcuts.effective("fit_width_page")[0].toString() == "Ctrl+1"
    assert window.shortcuts.effective("actual_size")[0].toString() == "Ctrl+3"


def test_zoom_et_ajuster_agissent_sur_la_vue_active(window):
    window.set_mode(True)
    window.page_view.set_zoom(window.page_view.real_size_zoom())
    before = window.page_view.zoom
    window._zoom_by(1.25)
    assert window.page_view.zoom == pytest.approx(before * 1.25)
    window._fit()
    assert window.page_view.visible_scene_rect().contains(window.page_view.page_rect())
    window.set_mode(False)
    ppy = window.view._ppy
    window._zoom_by(1.25)
    assert window.view._ppy == pytest.approx(ppy * 1.25)


def test_regles_et_mini_carte_se_masquent_et_se_memorisent(window):
    window.set_mode(True)
    window._rulers_action.setChecked(False)
    assert not window.page_container.ruler_h.isVisibleTo(window.page_container)
    window._navigator_action.setChecked(False)
    assert not window.page_view.navigator.isVisibleTo(window.page_view)
    settings = QSettings("Chronologia", "Chronologia")
    assert settings.value("page/rulers", True, type=bool) is False
    window._rulers_action.setChecked(True)
    window._navigator_action.setChecked(True)
    assert settings.value("page/rulers", True, type=bool) is True


def test_le_cadre_de_depot_couvre_aussi_le_mode_feuille(window):
    assert window._drop_overlay.parent() is window._stack
    window.set_mode(True)
    window._show_drop_overlay(True)
    assert window._drop_overlay.isVisibleTo(window)
    window._show_drop_overlay(False)
    assert not window.page_view.acceptDrops() and not window.page_view.viewport().acceptDrops()


# --- panneau étroit, taille de la fenêtre, police ---------------------------------------------


def test_le_panneau_a_une_largeur_minimale_raisonnable(app):
    panel = PagePanel()
    # seule la largeur *minimale* compte : elle ne doit pas imposer sa largeur à la fenêtre. La
    # largeur préférée varie beaucoup selon le système (594 px sous Windows) et n'est pas bornée :
    # le volet fixe la largeur, les rangées du formulaire passent sous leur libellé si besoin.
    assert panel.minimumSizeHint().width() <= main_window.PAGE_DOCK_MIN_WIDTH


def test_la_fenetre_ne_depasse_pas_l_ecran(app, window):
    from PySide6.QtGui import QGuiApplication

    area = QGuiApplication.primaryScreen().availableGeometry()
    assert window.width() <= area.width() and window.height() <= area.height()
    window.set_mode(True)
    assert window._page_dock.width() <= window.width() // 2  # le panneau ne mange pas la fenêtre
    assert window.minimumSizeHint().width() < area.width()


# --- taille du texte et largeur du volet --------------------------------------------------------


def test_taille_du_texte_directe_dans_le_panneau(app):
    panel = PagePanel()
    assert panel.text_size.value() == 8.0 and panel.settings().font_pt == 8.0
    seen = []
    panel.settingsChanged.connect(lambda: seen.append(1))
    panel.text_size.setValue(12.5)
    assert seen and panel.settings().font_pt == 12.5  # recalcul rapide : mêmes candidats
    assert not hasattr(panel, "font_family")  # plus de choix de police : seulement la taille


def test_texte_reduit_signale_dans_le_panneau(app):
    events = parse_events(CSV).events
    panel, controller = make_controller(events)
    panel.set_size_mm(105, 40)  # beaucoup trop bas pour la frise à 8 pt
    controller.activate(True)
    assert controller.plan.font_pt < 8
    assert "Texte réduit" in panel._warning.text() and "8 pt" in panel._warning.text()
    panel.set_size_mm(1189, 841)
    controller.ensure_current()
    assert "Texte réduit" not in panel._warning.text()


def test_le_volet_feuille_a_une_largeur_minimale(window):
    window.set_mode(True)
    dock = window._page_dock
    assert dock.widget().minimumWidth() >= main_window.PAGE_DOCK_MIN_WIDTH
    assert dock.minimumSizeHint().width() >= main_window.PAGE_DOCK_MIN_WIDTH
    assert window.page_panel.minimumWidth() >= 300
    scroll = dock.widget()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # le volet ne peut pas être rétréci sous son minimum
    window.resizeDocks([dock], [10], Qt.Orientation.Horizontal)
    QApplication.processEvents()
    assert dock.width() >= main_window.PAGE_DOCK_MIN_WIDTH


def test_le_volet_a_sa_largeur_initiale_a_la_premiere_apparition(window):
    window.resize(1400, 800)
    window.show()
    window.set_mode(True)
    QApplication.processEvents()
    assert window._page_dock.width() == pytest.approx(main_window.PAGE_DOCK_WIDTH, abs=40)
    window.hide()
