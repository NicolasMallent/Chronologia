from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from chronologia.main_window import MainWindow

CSV = b"start,end,title,color\n1900,1900,A,red\n1910,1920,B,black\n"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    w = MainWindow()
    yield w
    w.document.stack.setClean()
    w.close()


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "frise.csv"
    path.write_bytes(CSV)
    return path


def mime_for(*targets) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([t if isinstance(t, QUrl) else QUrl.fromLocalFile(str(t)) for t in targets])
    return mime


def enter(window, mime) -> QDragEnterEvent:
    event = QDragEnterEvent(
        QPoint(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    QApplication.sendEvent(window, event)
    return event


def drop(window, mime) -> QDropEvent:
    """Qt ne livre un dépôt que si l'entrée du glisser a été acceptée : on rejoue les deux."""
    enter(window, mime)
    event = QDropEvent(
        QPointF(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    QApplication.sendEvent(window, event)
    QApplication.processEvents()  # l'ouverture est différée
    return event


def test_la_fenetre_accepte_les_depots_et_les_vues_laissent_remonter(window):
    assert window.acceptDrops()
    for widget in (window.view, window.view.viewport(), window.filters._list, window.search):
        assert not widget.acceptDrops()
    assert not window.filters._list.viewport().acceptDrops()


def test_un_csv_depose_est_ouvert(window, csv_file):
    assert enter(window, mime_for(csv_file)).isAccepted()
    assert window._drop_overlay.isVisibleTo(window)  # retour visuel pendant le survol
    drop(window, mime_for(csv_file))
    assert [e.title for e in window.document.events] == ["A", "B"]
    assert window._path == csv_file
    assert not window._drop_overlay.isVisibleTo(window)


def test_extension_en_majuscules_acceptee(window, tmp_path):
    path = tmp_path / "FRISE.CSV"
    path.write_bytes(CSV)
    assert enter(window, mime_for(path)).isAccepted()
    drop(window, mime_for(path))
    assert len(window.document.events) == 2


@pytest.mark.parametrize("kind", ["txt", "dossier", "distant", "absent"])
def test_depots_refuses(window, tmp_path, kind):
    if kind == "txt":
        target = tmp_path / "notes.txt"
        target.write_bytes(CSV)
    elif kind == "dossier":
        target = tmp_path / "dossier.csv"
        target.mkdir()
    elif kind == "distant":
        target = QUrl("https://example.org/frise.csv")
    else:
        target = tmp_path / "absent.csv"
    assert not enter(window, mime_for(target)).isAccepted()
    assert not window._drop_overlay.isVisibleTo(window)
    drop(window, mime_for(target))
    assert window.document.events == [] and window._path is None
    assert window.statusBar().currentMessage()  # « Seuls les fichiers CSV… »


def test_plusieurs_fichiers_ouvre_le_premier_csv_et_le_dit(window, tmp_path, csv_file):
    second = tmp_path / "autre.csv"
    second.write_bytes(CSV)
    note = tmp_path / "notes.txt"
    note.write_text("x")
    drop(window, mime_for(note, csv_file, second))
    assert window._path == csv_file
    assert "2" in window.statusBar().currentMessage()  # 2 fichiers CSV déposés


def test_modifications_en_cours_question_posee_et_annuler_garde_le_document(
    window, csv_file, tmp_path, monkeypatch
):
    from chronologia.event_form import build_event

    other = tmp_path / "other.csv"
    other.write_bytes(b"start,end,title,color\n1800,1800,Z,blue\n")
    window.load_file(csv_file)
    event, _ = build_event("Nouveau", "1950", "", "red", "")
    window.add_event(event)  # document modifié
    asked = []
    monkeypatch.setattr(window, "_confirm_discard", lambda: asked.append(1) or False)
    drop(window, mime_for(other))
    assert asked and window._path == csv_file  # annulé : le document reste
    assert "Nouveau" in [e.title for e in window.document.events]
    monkeypatch.setattr(window, "_confirm_discard", lambda: True)
    drop(window, mime_for(other))
    assert [e.title for e in window.document.events] == ["Z"]


def test_fichier_illisible_ne_plante_pas(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    bad = tmp_path / "vide.csv"
    bad.write_bytes(b"")
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[1:]))
    drop(window, mime_for(bad))
    assert shown and window.document.events == []


def test_deplacement_au_dessus_de_la_fenetre(window, csv_file):
    mime = mime_for(csv_file)
    enter(window, mime)
    event = QDragMoveEvent(
        QPoint(60, 60), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    QApplication.sendEvent(window, event)
    assert event.isAccepted()
    assert isinstance(csv_file, Path)
