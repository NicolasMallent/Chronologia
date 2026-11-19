"""Fenêtre principale."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from .categories import load_registry
from .csv_io import CsvFormatError, read_events, write_events
from .document import Document
from .event_dialog import EventDialog
from .export_dialog import ExportDialog
from .filter_panel import FilterPanel
from .i18n import LANGUAGES, effective_language, save_language
from .messages import format_error_text, issue_text
from .model import Event
from .pdf_export import write_pdf
from .textutil import plain
from .timeline_view import TimelineView

MAX_ISSUES_SHOWN = 200


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.resize(1400, 800)

        self._registry, warning = load_registry()
        self.document = Document(self)
        self._path: Path | None = None
        self._lossy = False  # l'import a ignoré des lignes : ne pas écraser le fichier d'origine

        self.view = TimelineView()
        self.setCentralWidget(self.view)

        self.filters = FilterPanel()
        dock = QDockWidget(self.tr("Catégories"), self)
        dock.setWidget(self.filters)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.filters.visibleChanged.connect(self.view.set_visible_categories)

        self._status = QLabel()
        self.statusBar().addPermanentWidget(self._status)
        self.view.layoutChanged.connect(self._update_status)
        self.view.editRequested.connect(self.edit_event)
        self.view.deleteRequested.connect(self.delete_event)
        self.view.newRequested.connect(self.new_event)
        self.document.changed.connect(self._on_document_changed)
        self.document.stack.cleanChanged.connect(self._update_title)

        self._build_actions()
        self._update_title()
        if warning:
            self.statusBar().showMessage(
                self.tr(
                    "Catégories personnalisées illisibles, valeurs par défaut utilisées : %1"
                ).replace("%1", warning),
                10000,
            )

    # --- actions ---------------------------------------------------------------------

    def _build_actions(self) -> None:
        open_action = QAction(self.tr("&Ouvrir un CSV…"), self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_dialog)
        save_action = QAction(self.tr("&Enregistrer"), self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save)
        save_as_action = QAction(self.tr("Enregistrer &sous…"), self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        export_action = QAction(self.tr("E&xporter en PDF…"), self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.export_pdf)
        quit_action = QAction(self.tr("&Quitter"), self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu = self.menuBar().addMenu(self.tr("&Fichier"))
        for action in (open_action, save_action, save_as_action, export_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        new_action = QAction(self.tr("&Nouvel événement…"), self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(lambda: self.new_event())
        self.undo_action = QAction(self.tr("Annuler"), self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.document.stack.undo)
        self.redo_action = QAction(self.tr("Rétablir"), self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.document.stack.redo)
        stack = self.document.stack
        stack.canUndoChanged.connect(self._update_undo_actions)
        stack.canRedoChanged.connect(self._update_undo_actions)
        stack.undoTextChanged.connect(self._update_undo_actions)
        stack.redoTextChanged.connect(self._update_undo_actions)
        self._update_undo_actions()
        edit_menu = self.menuBar().addMenu(self.tr("&Édition"))
        for action in (new_action, self.undo_action, self.redo_action):
            edit_menu.addAction(action)

        zoom_in = QAction(self.tr("Zoom +"), self)
        zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in.triggered.connect(lambda: self.view.zoom_by(1.25))
        zoom_out = QAction(self.tr("Zoom −"), self)
        zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out.triggered.connect(lambda: self.view.zoom_by(1 / 1.25))
        fit = QAction(self.tr("Ajuster"), self)
        fit.setShortcut("Ctrl+0")
        fit.triggered.connect(self.view.fit_width)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Rechercher un événement…"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self.view.set_search)

        bar = QToolBar(self.tr("Outils"))
        bar.setMovable(False)
        for action in (self.undo_action, self.redo_action):
            bar.addAction(action)
        bar.addSeparator()
        for action in (zoom_in, zoom_out, fit):
            bar.addAction(action)
        bar.addSeparator()
        bar.addWidget(self.search)
        self.addToolBar(bar)

        view_menu = self.menuBar().addMenu(self.tr("&Affichage"))
        for action in (zoom_in, zoom_out, fit):
            view_menu.addAction(action)
        view_menu.addSeparator()
        language_menu = view_menu.addMenu(self.tr("&Langue"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = effective_language()
        for code, name in LANGUAGES.items():
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _checked=False, c=code: self._change_language(c))
            group.addAction(action)
            language_menu.addAction(action)

    def _change_language(self, code: str) -> None:
        save_language(code)
        QMessageBox.information(
            self,
            self.tr("Langue"),
            self.tr("La nouvelle langue sera appliquée au prochain démarrage de Chronologia."),
        )

    def _update_undo_actions(self) -> None:
        stack = self.document.stack
        self.undo_action.setEnabled(stack.canUndo())
        self.redo_action.setEnabled(stack.canRedo())
        undo_text = self.tr("Annuler")
        redo_text = self.tr("Rétablir")
        self.undo_action.setText(
            f"{undo_text} : {stack.undoText()}" if stack.canUndo() else undo_text
        )
        self.redo_action.setText(
            f"{redo_text} : {stack.redoText()}" if stack.canRedo() else redo_text
        )

    # --- édition des événements ------------------------------------------------------

    def new_event(self, start_hint: str = "") -> None:
        dialog = EventDialog(self._registry, start_hint=start_hint, parent=self)
        if dialog.exec() and (event := dialog.result_event()) is not None:
            self.add_event(event)

    def edit_event(self, event: Event) -> None:
        dialog = EventDialog(self._registry, event=event, parent=self)
        if dialog.exec() and (new := dialog.result_event()) is not None:
            self.replace_event(event, new)

    def delete_event(self, event: Event) -> None:
        answer = QMessageBox.question(
            self,
            self.tr("Supprimer l'événement"),
            plain(self.tr("Supprimer « %1 » ? (Annulable avec Ctrl+Z)").replace("%1", event.title)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_event(event)

    # Opérations sans dialogue (utilisées par les dialogues et par les tests).

    def add_event(self, event: Event) -> None:
        self.document.add(event)
        self.filters.ensure_checked(self._registry.category_name(event))
        self.view.reveal(event)

    def replace_event(self, old: Event, new: Event) -> None:
        self.document.replace(old, new)
        self.filters.ensure_checked(self._registry.category_name(new))
        self.view.reveal(new)

    def remove_event(self, event: Event) -> None:
        self.document.remove(event)

    def _on_document_changed(self, focus: Event | None) -> None:
        self.view.set_events(self.document.events, rebuild=False)
        self.filters.set_categories(self._category_entries(), keep_state=True)
        if focus is not None:
            self.filters.ensure_checked(self._registry.category_name(focus))
            self.view.reveal(focus)

    # --- fichiers --------------------------------------------------------------------

    def open_dialog(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Ouvrir un CSV"),
            "",
            self.tr("Fichiers CSV (*.csv);;Tous les fichiers (*)"),
        )
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> bool:
        try:
            result = read_events(path)
        except (OSError, CsvFormatError) as exc:
            text = format_error_text(exc) if isinstance(exc, CsvFormatError) else str(exc)
            QMessageBox.critical(self, self.tr("Import impossible"), plain(text))
            return False
        self._path = path
        self._lossy = any(i.skipped for i in result.issues)
        self.search.clear()
        self.document.reset(result.events)
        self.view.set_data(self.document.events, self._registry)
        self.filters.set_categories(self._category_entries())
        self._update_title()
        if result.issues:
            self._show_issues(result)
        return True

    def save(self) -> bool:
        if self._path is None or self._lossy:
            return self.save_as()
        return self._write(self._path)

    def save_as(self) -> bool:
        default = ""
        if self._path is not None:
            default = str(self._path.with_name(f"{self._path.stem}_modifie.csv"))
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Enregistrer sous"), default, self.tr("Fichiers CSV (*.csv)")
        )
        if not path:
            return False
        if not path.lower().endswith(".csv"):
            path += ".csv"
        return self._write(Path(path))

    def _write(self, path: Path) -> bool:
        try:
            write_events(path, self.document.events)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Enregistrement impossible"), plain(str(exc)))
            return False
        self._path = path
        self._lossy = False
        self.document.stack.setClean()
        self._update_title()
        self.statusBar().showMessage(self.tr("Enregistré : %1").replace("%1", path.name), 5000)
        return True

    def export_pdf(self) -> None:
        """Exporte la frise affichée (catégories cochées) en PDF vectoriel."""
        dialog = ExportDialog(
            self.document.events, self._registry, self.view.visible_categories, parent=self
        )
        if not dialog.exec() or (plan := dialog.plan()) is None:
            return
        suggested = str(self._path.with_suffix(".pdf")) if self._path else "frise.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exporter en PDF"), suggested, self.tr("Fichiers PDF (*.pdf)")
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            write_pdf(path, plan, dialog.document_title())
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Export impossible"), plain(str(exc)))
            return
        self.statusBar().showMessage(
            self.tr("PDF exporté : %1").replace("%1", Path(path).name), 5000
        )

    def _confirm_discard(self) -> bool:
        """Propose d'enregistrer les modifications. ``False`` : l'utilisateur annule."""
        if self.document.stack.isClean():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Modifications non enregistrées"))
        box.setText(self.tr("Enregistrer les modifications avant de continuer ?"))
        box.setStandardButtons(
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel
        )
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def _update_title(self, *_: object) -> None:
        name = self._path.name if self._path else self.tr("Sans titre")
        dirty = "" if self.document.stack.isClean() else " *"
        self.setWindowTitle(f"Chronologia — {name}{dirty}")

    def _category_entries(self) -> list[tuple[str, str, int]]:
        events = self.document.events
        counts = Counter(self._registry.category_name(e) for e in events)
        colors = {}
        for event in events:
            found = self._registry.for_color(event.color)
            colors.setdefault(
                self._registry.category_name(event), found.color_hex if found else event.color_hex
            )
        order = [c.name for c in self._registry if c.name in counts]
        order += sorted((n for n in counts if n not in order), key=lambda n: -counts[n])
        return [(n, colors[n], counts[n]) for n in order]

    def _show_issues(self, result) -> None:
        skipped = sum(1 for i in result.issues if i.skipped)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Import terminé avec des anomalies"))
        box.setText(
            self.tr("%1 événements importés, %2 lignes ignorées, %3 corrigées.")
            .replace("%1", str(len(result.events)))
            .replace("%2", str(skipped))
            .replace("%3", str(len(result.issues) - skipped))
        )
        line_word = self.tr("ligne")
        details = [
            f"{line_word} {i.line} : {issue_text(i)}" for i in result.issues[:MAX_ISSUES_SHOWN]
        ]
        box.setDetailedText("\n".join(details))
        box.exec()

    def _update_status(self) -> None:
        total = len(self.document.events)
        text = self.tr("%1 événements affichés / %2").replace("%1", str(self.view.displayed_count))
        text = text.replace("%2", str(total))
        matches = self.view.match_count
        if matches is not None:
            text += " — " + self.tr("%1 correspondances").replace("%1", str(matches))
        self._status.setText(text)
