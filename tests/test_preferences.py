import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication

from chronologia import i18n
from chronologia.main_window import MainWindow
from chronologia.preferences_dialog import PreferencesDialog
from chronologia.shortcuts import ShortcutConflict, ShortcutManager, find_conflict


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def manager(app, settings):
    m = ShortcutManager(settings)
    m.register("open", QAction("&Ouvrir…"), QKeySequence.StandardKey.Open)
    m.register("export", QAction("Exporter"), "Ctrl+E")
    m.register("categories", QAction("Catégories…"), None)
    return m


def seq(text):
    return QKeySequence(text)


def test_valeurs_par_defaut_et_intitules(manager):
    assert manager.effective("export") == [seq("Ctrl+E")]
    assert manager.effective("categories") == []
    assert manager.effective("open")  # raccourci standard du système
    assert manager.label("open") == "Ouvrir"  # sans « & » ni « … »
    assert manager._actions["export"].shortcut() == seq("Ctrl+E")


def test_personnalisation_persistee_et_appliquee(app, manager, settings):
    manager.set("export", seq("Ctrl+Shift+P"))
    assert manager._actions["export"].shortcut() == seq("Ctrl+Shift+P")
    assert manager.is_customized("export")
    autre = ShortcutManager(settings)  # nouvelle session : même fichier
    autre.register("export", QAction("Exporter"), "Ctrl+E")
    assert autre.effective("export") == [seq("Ctrl+Shift+P")]


def test_effacer_un_raccourci(manager):
    manager.set("export", QKeySequence())
    assert manager.effective("export") == []
    assert manager._actions["export"].shortcut().isEmpty()


def test_conflit_refuse(manager):
    with pytest.raises(ShortcutConflict) as info:
        manager.set("categories", seq("Ctrl+E"))
    assert info.value.owner == "export"
    assert manager.effective("categories") == []  # rien n'est modifié
    assert manager.conflict("export", seq("Ctrl+E")) is None  # pas de conflit avec soi-même


def test_find_conflict_ignore_le_vide():
    assert find_conflict({"a": [seq("Ctrl+A")]}, "b", QKeySequence()) is None
    assert find_conflict({"a": [seq("Ctrl+A")]}, "b", seq("Ctrl+A")) == "a"


def test_reinitialisation(manager, settings):
    manager.set("export", seq("Ctrl+Shift+P"))
    manager.reset("export")
    assert manager.effective("export") == [seq("Ctrl+E")] and not manager.is_customized("export")
    manager.set("export", seq("Ctrl+Shift+P"))
    manager.set("categories", seq("Ctrl+K"))
    manager.reset_all()
    assert manager.effective("export") == [seq("Ctrl+E")]
    assert manager.effective("categories") == []
    assert not settings.allKeys()


def test_remettre_la_valeur_par_defaut_ne_laisse_pas_de_cle(manager, settings):
    manager.set("export", seq("Ctrl+Shift+P"))
    manager.set("export", seq("Ctrl+E"))
    assert not settings.contains("shortcuts/export")


def test_identifiant_en_double_refuse(manager):
    with pytest.raises(ValueError):
        manager.register("open", QAction("Autre"), None)


# --- fenêtre et boîte de dialogue ----------------------------------------------------------


@pytest.fixture
def window(app):
    w = MainWindow()
    yield w
    w.shortcuts.reset_all()
    w.document.stack.setClean()
    w.close()


def test_menu_fichier_contient_les_preferences_et_plus_de_langue_dans_affichage(window):
    file_menu = window.menuBar().actions()[0].menu()
    texts = [a.text().replace("&", "") for a in file_menu.actions()]
    assert "Préférences…" in texts
    assert texts.index("Préférences…") < texts.index("Quitter")
    view_menu = window.menuBar().actions()[2].menu()
    assert all("Langue" not in a.text() for a in view_menu.actions())
    assert not view_menu.findChildren(type(view_menu))  # plus de sous-menu


def test_raccourcis_par_defaut_de_la_fenetre_inchanges(window):
    assert window.shortcuts.effective("export_pdf") == [seq("Ctrl+E")]
    assert window.shortcuts.effective("fit") == [seq("Ctrl+0")]
    assert window.undo_action.shortcuts()
    expected = {"open", "save", "save_as", "export_pdf", "quit", "preferences", "new_event"}
    assert expected <= set(window.shortcuts.ids())


def test_dialogue_applique_ok_et_ignore_annuler(window):
    dialog = PreferencesDialog(window.shortcuts)
    dialog._editors["export_pdf"].setKeySequence(seq("Ctrl+Shift+P"))
    assert dialog.pending_shortcuts()["export_pdf"] == [seq("Ctrl+Shift+P")]
    assert window.shortcuts.effective("export_pdf") == [seq("Ctrl+E")]  # pas encore appliqué
    dialog.apply_shortcuts()
    assert window.shortcuts.effective("export_pdf") == [seq("Ctrl+Shift+P")]
    fresh = PreferencesDialog(window.shortcuts)  # rouvert : montre l'état appliqué
    assert fresh._editors["export_pdf"].keySequence() == seq("Ctrl+Shift+P")


def test_dialogue_refuse_un_raccourci_deja_pris(window):
    dialog = PreferencesDialog(window.shortcuts)
    dialog._editors["fit"].setKeySequence(seq("Ctrl+E"))  # déjà utilisé par l'export
    assert dialog.pending_shortcuts()["fit"] == [seq("Ctrl+0")]  # annulé
    assert dialog._editors["fit"].keySequence() == seq("Ctrl+0")
    assert "Exporter en PDF" in dialog._message.text()


def test_dialogue_effacer_et_reinitialiser(window):
    dialog = PreferencesDialog(window.shortcuts)
    dialog._editors["fit"].setKeySequence(QKeySequence())
    assert dialog.pending_shortcuts()["fit"] == []
    dialog._reset("fit")
    assert dialog.pending_shortcuts()["fit"] == [seq("Ctrl+0")]
    dialog._editors["fit"].setKeySequence(seq("Ctrl+9"))
    dialog._reset_all()
    assert dialog.pending_shortcuts() == window.shortcuts.assignments()


def test_dialogue_langue(window):
    dialog = PreferencesDialog(window.shortcuts)
    assert dialog.selected_language() == i18n.effective_language()
    dialog.language.setCurrentIndex(dialog.language.findData("es"))
    assert dialog.selected_language() == "es"


def test_menu_preferences_applique_langue_et_raccourcis(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from chronologia import main_window

    def fake_exec(self):
        self._editors["fit"].setKeySequence(seq("Ctrl+9"))
        self.language.setCurrentIndex(self.language.findData("es"))
        return True

    infos = []
    monkeypatch.setattr(PreferencesDialog, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[1:]))
    saved = []
    monkeypatch.setattr(main_window, "save_language", saved.append)
    monkeypatch.setattr(main_window, "effective_language", lambda: "fr")
    window.show_preferences()
    assert window.shortcuts.effective("fit") == [seq("Ctrl+9")]
    assert saved == ["es"] and infos  # langue enregistrée, redémarrage annoncé


def test_menu_preferences_annule_ne_change_rien(window, monkeypatch):
    def fake_exec(self):
        self._editors["fit"].setKeySequence(seq("Ctrl+9"))
        return False

    monkeypatch.setattr(PreferencesDialog, "exec", fake_exec)
    window.show_preferences()
    assert window.shortcuts.effective("fit") == [seq("Ctrl+0")]
