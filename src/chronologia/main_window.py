"""Fenêtre principale."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import QMimeData, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QGuiApplication,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from .categories import CategoryError, CategoryRegistry, load_registry, save_registry
from .categories_dialog import CategoriesDialog, CategoryEditDialog
from .csv_io import CsvFormatError, read_events, write_events
from .document import Document
from .event_dialog import EventDialog
from .filter_panel import FilterPanel
from .formats import load_formats, save_formats
from .i18n import effective_language, save_language
from .icons import make_icon
from .messages import category_error_text, format_error_text, issue_text
from .model import Event
from .page_controller import PageController
from .page_panel import PagePanel
from .page_view import PageContainer
from .pdf_export import write_pdf
from .preferences_dialog import PreferencesDialog
from .shortcuts import ShortcutManager
from .textutil import plain
from .timeline_view import TimelineView

MAX_ISSUES_SHOWN = 200
PAGE_DOCK_WIDTH = 350  # largeur initiale du panneau Feuille
PAGE_DOCK_MIN_WIDTH = (
    330  # en dessous, ses champs seraient coupés : le volet ne peut pas être plus étroit
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.resize(self._initial_size())

        self._registry, warning = load_registry()
        self.document = Document(self)
        self._path: Path | None = None
        self._lossy = False  # l'import a ignoré des lignes : ne pas écraser le fichier d'origine

        self.view = TimelineView()  # mode Libre
        self.page_container = PageContainer()  # mode Feuille
        self.page_view = self.page_container.view
        self._stack = QStackedWidget()
        self._stack.addWidget(self.view)
        self._stack.addWidget(self.page_container)
        self.setCentralWidget(self._stack)
        self._page_mode = False
        self._page_dock_sized = False
        self._reveal_in_page: Event | None = None
        self.setAcceptDrops(True)  # glisser-déposer d'un CSV n'importe où dans la fenêtre
        self._drop_overlay = QLabel(self.tr("Déposez un fichier CSV pour l'ouvrir"), self._stack)
        self._drop_overlay.setObjectName("dropOverlay")
        self._drop_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_overlay.hide()

        self.filters = FilterPanel()
        dock = QDockWidget(self.tr("Catégories"), self)
        dock.setWidget(self.filters)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.filters.visibleChanged.connect(self.view.set_visible_categories)
        self.filters.visibleChanged.connect(lambda _names: self._push_page_data())
        self.filters.editRequested.connect(self.edit_category)

        formats, formats_warning = load_formats()
        self.page_panel = PagePanel(formats)
        self.page = PageController(self.page_panel, self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(PAGE_DOCK_MIN_WIDTH)
        scroll.setWidget(self.page_panel)
        self._page_dock = QDockWidget(self.tr("Feuille"), self)
        self._page_dock.setWidget(scroll)
        self._page_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._page_dock)
        self._page_dock.hide()
        self.resizeDocks([self._page_dock], [PAGE_DOCK_WIDTH], Qt.Orientation.Horizontal)
        self.page.planChanged.connect(self._on_plan_changed)
        self.page_panel.exportRequested.connect(self.export_pdf)
        self.page_panel.formatsChanged.connect(self._save_formats)
        self.page_view.editRequested.connect(self.edit_event)
        self.page_view.deleteRequested.connect(self.delete_event)
        self.page_view.newRequested.connect(self.new_event)

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
        self.set_mode(QSettings("Chronologia", "Chronologia").value("view/mode") == "page")
        if formats_warning:
            self.statusBar().showMessage(
                self.tr("Formats personnalisés illisibles, ignorés : %1").replace(
                    "%1", formats_warning
                ),
                10000,
            )
        if warning:
            self.statusBar().showMessage(
                self.tr(
                    "Catégories personnalisées illisibles, valeurs par défaut utilisées : %1"
                ).replace("%1", warning),
                10000,
            )

    @staticmethod
    def _initial_size() -> QSize:
        """1400 × 800, sans dépasser l'écran (un panneau ne doit pas sortir de l'écran)."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(1400, 800)
        area = screen.availableGeometry()
        return QSize(min(1400, int(area.width() * 0.94)), min(800, int(area.height() * 0.92)))

    # --- actions ---------------------------------------------------------------------

    def _build_actions(self) -> None:
        self.shortcuts = ShortcutManager()
        reg = self.shortcuts.register
        open_action = QAction(self.tr("&Ouvrir un CSV…"), self)
        reg("open", open_action, QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_dialog)
        save_action = QAction(self.tr("&Enregistrer"), self)
        reg("save", save_action, QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save)
        save_as_action = QAction(self.tr("Enregistrer &sous…"), self)
        reg("save_as", save_as_action, QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        export_action = QAction(self.tr("E&xporter en PDF…"), self)
        reg("export_pdf", export_action, "Ctrl+E")
        export_action.triggered.connect(self.export_pdf)
        quit_action = QAction(self.tr("&Quitter"), self)
        reg("quit", quit_action, QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        preferences_action = QAction(self.tr("&Préférences…"), self)
        reg("preferences", preferences_action, QKeySequence.StandardKey.Preferences)
        preferences_action.triggered.connect(self.show_preferences)
        file_menu = self.menuBar().addMenu(self.tr("&Fichier"))
        for action in (open_action, save_action, save_as_action, export_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(preferences_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        new_action = QAction(self.tr("&Nouvel événement…"), self)
        reg("new_event", new_action, QKeySequence.StandardKey.New)
        new_action.triggered.connect(lambda: self.new_event())
        self.undo_action = QAction(make_icon("undo"), self.tr("Annuler"), self)
        reg("undo", self.undo_action, QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.document.stack.undo)
        self.redo_action = QAction(make_icon("redo"), self.tr("Rétablir"), self)
        reg("redo", self.redo_action, QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.document.stack.redo)
        stack = self.document.stack
        stack.canUndoChanged.connect(self._update_undo_actions)
        stack.canRedoChanged.connect(self._update_undo_actions)
        stack.undoTextChanged.connect(self._update_undo_actions)
        stack.redoTextChanged.connect(self._update_undo_actions)
        self._update_undo_actions()
        categories_action = QAction(self.tr("&Gérer les catégories…"), self)
        reg("categories", categories_action, None)
        categories_action.triggered.connect(self.manage_categories)
        edit_menu = self.menuBar().addMenu(self.tr("&Édition"))
        for action in (new_action, self.undo_action, self.redo_action):
            edit_menu.addAction(action)
        edit_menu.addSeparator()
        edit_menu.addAction(categories_action)

        zoom_in = QAction(make_icon("zoom_in"), self.tr("Zoom +"), self)
        reg("zoom_in", zoom_in, QKeySequence.StandardKey.ZoomIn)
        zoom_in.triggered.connect(lambda: self._zoom_by(1.25))
        zoom_out = QAction(make_icon("zoom_out"), self.tr("Zoom −"), self)
        reg("zoom_out", zoom_out, QKeySequence.StandardKey.ZoomOut)
        zoom_out.triggered.connect(lambda: self._zoom_by(1 / 1.25))
        fit = QAction(make_icon("fit"), self.tr("Ajuster"), self)
        reg("fit", fit, "Ctrl+0")
        fit.triggered.connect(self._fit)

        self.search = QLineEdit()
        self.search.setPlaceholderText(self.tr("Rechercher un événement…"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(300)
        self.search.addAction(
            make_icon("search", "#8b91a1"), QLineEdit.ActionPosition.LeadingPosition
        )
        self.search.textChanged.connect(self.view.set_search)
        self.search.textChanged.connect(self.page_view.set_search)
        self.search.setAcceptDrops(False)  # un fichier déposé ici ouvre le CSV, pas du texte

        free_action = QAction(self.tr("Libre"), self)
        free_action.setCheckable(True)
        free_action.setToolTip(self.tr("Frise libre : le zoom dévoile les titres"))
        page_action = QAction(self.tr("Feuille"), self)
        page_action.setCheckable(True)
        page_action.setToolTip(self.tr("Feuille : la frise au format d'impression"))
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)
        for action in (free_action, page_action):
            self._mode_group.addAction(action)
        self._mode_actions = (free_action, page_action)
        reg("mode_free", free_action, None, label=self.tr("Mode Libre"))
        reg("mode_page", page_action, None, label=self.tr("Mode Feuille"))
        free_action.triggered.connect(lambda: self._mode_chosen(False))
        page_action.triggered.connect(lambda: self._mode_chosen(True))

        fit_width_page = QAction(self.tr("Largeur de la feuille"), self)
        reg("fit_width_page", fit_width_page, "Ctrl+1")
        fit_width_page.triggered.connect(self.page_view.fit_width)
        fit_height_page = QAction(self.tr("Hauteur de la feuille"), self)
        reg("fit_height_page", fit_height_page, "Ctrl+2")
        fit_height_page.triggered.connect(self.page_view.fit_height)
        actual_size = QAction(self.tr("Taille réelle (100 %)"), self)
        reg("actual_size", actual_size, "Ctrl+3")
        actual_size.triggered.connect(self.page_view.actual_size)
        settings = QSettings("Chronologia", "Chronologia")
        self._rulers_action = QAction(self.tr("Règles"), self)
        self._rulers_action.setCheckable(True)
        self._rulers_action.setChecked(settings.value("page/rulers", True, type=bool))
        reg("toggle_rulers", self._rulers_action, None)
        self._rulers_action.toggled.connect(self._toggle_rulers)
        self._navigator_action = QAction(self.tr("Mini-carte"), self)
        self._navigator_action.setCheckable(True)
        self._navigator_action.setChecked(settings.value("page/navigator", True, type=bool))
        reg("toggle_navigator", self._navigator_action, None)
        self._navigator_action.toggled.connect(self._toggle_navigator)
        self._page_only_actions = (
            fit_width_page,
            fit_height_page,
            actual_size,
            self._rulers_action,
            self._navigator_action,
        )
        self.page_container.set_rulers_visible(self._rulers_action.isChecked())
        self.page_container.set_navigator_enabled(self._navigator_action.isChecked())

        tool_new = QAction(
            make_icon("plus", "#ffffff", "#ffffff"), self.tr("Nouvel événement"), self
        )
        tool_new.triggered.connect(lambda: self.new_event())

        bar = QToolBar(self.tr("Outils"))
        bar.setMovable(False)
        bar.setIconSize(QSize(20, 20))
        bar.addAction(tool_new)
        button = bar.widgetForAction(tool_new)
        if isinstance(button, QToolButton):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setProperty("primary", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addSeparator()
        for action in (self.undo_action, self.redo_action):
            bar.addAction(action)
        bar.addSeparator()
        for action in (zoom_in, zoom_out, fit):
            bar.addAction(action)
        bar.addSeparator()
        for action in self._mode_actions:
            bar.addAction(action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        bar.addWidget(self.search)
        self.addToolBar(bar)

        view_menu = self.menuBar().addMenu(self.tr("&Affichage"))
        for action in (zoom_in, zoom_out, fit):
            view_menu.addAction(action)
        view_menu.addSeparator()
        for action in (fit_width_page, fit_height_page, actual_size):
            view_menu.addAction(action)
        view_menu.addSeparator()
        for action in (self._rulers_action, self._navigator_action):
            view_menu.addAction(action)
        view_menu.addSeparator()
        for action in self._mode_actions:
            view_menu.addAction(action)

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(self.shortcuts, parent=self)
        if not dialog.exec():
            return
        dialog.apply_shortcuts()
        if dialog.selected_language() != effective_language():
            save_language(dialog.selected_language())
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

    # --- modes Libre et Feuille ---------------------------------------------------------

    @property
    def page_mode(self) -> bool:
        return self._page_mode

    def set_mode(self, page: bool) -> None:
        """Affiche la frise libre (``False``) ou la feuille au format d'impression (``True``)."""
        changed = page != self._page_mode
        self._page_mode = page
        self._stack.setCurrentWidget(self.page_container if page else self.view)
        self._page_dock.setVisible(page)
        if page and not self._page_dock_sized:
            # le volet prendrait sinon la largeur préférée du panneau (très variable selon le système)
            self.resizeDocks([self._page_dock], [PAGE_DOCK_WIDTH], Qt.Orientation.Horizontal)
            self._page_dock_sized = True
        self._mode_actions[1 if page else 0].setChecked(True)
        for action in self._page_only_actions:
            action.setEnabled(page)
        self._push_page_data()
        self.page.activate(page)
        if changed:  # la sélection suit d'un mode à l'autre
            if page:
                self.page_view.select(self.view.selected_event)
            else:
                self.view.select(self.page_view.selected_event)
        self._update_status()

    def _mode_chosen(self, page: bool) -> None:
        """Choix de l'utilisateur : le mode est mémorisé pour le prochain démarrage."""
        self.set_mode(page)
        settings = QSettings("Chronologia", "Chronologia")
        settings.setValue("view/mode", "page" if page else "free")
        settings.sync()

    def _toggle_rulers(self, on: bool) -> None:
        self.page_container.set_rulers_visible(on)
        QSettings("Chronologia", "Chronologia").setValue("page/rulers", on)

    def _toggle_navigator(self, on: bool) -> None:
        self.page_container.set_navigator_enabled(on)
        QSettings("Chronologia", "Chronologia").setValue("page/navigator", on)

    def _zoom_by(self, factor: float) -> None:
        (self.page_view if self._page_mode else self.view).zoom_by(factor)

    def _fit(self) -> None:
        if self._page_mode:
            self.page_view.fit_page()
        else:
            self.view.fit_width()

    def _push_page_data(self) -> None:
        """Transmet événements, catégories et filtre à la mise en page de la feuille."""
        self.page.set_data(self.document.events, self._registry, self.view.visible_categories)

    def _on_plan_changed(self, plan) -> None:
        self.page_view.set_plan(plan)
        if self._reveal_in_page is not None:
            self.page_view.reveal(self._reveal_in_page)
            self._reveal_in_page = None
        self._update_status()

    def _save_formats(self, formats) -> None:
        try:
            save_formats(formats)
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Formats"),
                plain(self.tr("Format appliqué mais non enregistré : %1").replace("%1", str(exc))),
            )

    # --- édition des événements ------------------------------------------------------

    def new_event(self, start_hint: str = "", color_hint: str = "") -> None:
        dialog = EventDialog(
            self._registry, start_hint=start_hint, color_hint=color_hint, parent=self
        )
        if dialog.exec() and (event := dialog.result_event()) is not None:
            self.add_event(event)

    def edit_event(self, event: Event) -> None:
        dialog = EventDialog(self._registry, event=event, parent=self)
        accepted = dialog.exec()
        if dialog.delete_requested:
            self.delete_event(event)  # avec confirmation
        elif accepted and (new := dialog.result_event()) is not None:
            self.replace_event(event, new)

    def delete_event(self, event: Event) -> None:
        answer = QMessageBox.question(
            self,
            self.tr("Supprimer l'événement"),
            plain(self.tr("Supprimer « %1 » ? (Annulable avec Ctrl+Z)").replace("%1", event.title)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.remove_event(event)

    def manage_categories(self) -> None:
        dialog = CategoriesDialog(self._registry, parent=self)
        if dialog.exec():
            self.apply_registry(dialog.registry(), dialog.color_changes())

    def edit_category(self, name: str) -> None:
        """Modifie une catégorie (clic droit dans le panneau) : nom et couleur.

        Une couleur sans catégorie (nommée par son code) est proposée à l'ajout.
        """
        work = CategoryRegistry(list(self._registry))
        category = work.by_name(name)
        if category is None:  # couleur d'événements sans catégorie : on la crée
            dialog = CategoryEditDialog(work, parent=self, color=name)
        else:
            dialog = CategoryEditDialog(work, category, parent=self)
        if not dialog.exec():
            return
        try:
            if category is None:
                work.add(*dialog.values())
                changes: dict[str, str] = {}
            else:
                updated = work.update(category, *dialog.values())
                changes = (
                    {category.color_hex: updated.color}
                    if category.color_hex != updated.color_hex
                    else {}
                )
        except CategoryError as exc:
            QMessageBox.warning(self, self.tr("Catégories"), plain(category_error_text(exc)))
            return
        self.apply_registry(work, changes)

    def apply_registry(self, registry, color_changes: dict[str, str] | None = None) -> None:
        """Adopte de nouvelles catégories, les enregistre et rafraîchit l'affichage.

        ``color_changes`` : couleurs de catégories modifiées ; les événements concernés prennent
        la nouvelle couleur (annulable), car la couleur d'un événement est sa catégorie.
        """
        self._registry = registry
        self.view.set_registry(registry)
        self._push_page_data()
        if not (color_changes and self.document.recolor(color_changes)):
            self.filters.set_categories(self._category_entries(), keep_state=True)
        try:
            save_registry(registry)
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Catégories"),
                plain(
                    self.tr("Catégories appliquées mais non enregistrées : %1").replace(
                        "%1", str(exc)
                    )
                ),
            )

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
        self.view.select(focus)  # l'événement ajouté ou modifié est mis en valeur
        self.page_view.select(focus)
        self._push_page_data()
        if focus is not None:
            self.filters.ensure_checked(self._registry.category_name(focus))
            self.view.reveal(focus)
            self._reveal_in_page = focus

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
        """Exporte la feuille réglée en PDF vectoriel (réduit à 1/N au-delà de 5 m)."""
        if not self._page_mode:
            self._mode_chosen(True)
            self.statusBar().showMessage(
                self.tr("Réglez la feuille (format, titre…), puis exportez-la en PDF."), 8000
            )
            return
        plan = self.page.ensure_current()
        if plan is None:
            QMessageBox.information(
                self,
                self.tr("Exporter en PDF"),
                self.tr("Aucun événement à exporter avec les filtres actuels."),
            )
            return
        divisor = self.page.divisor
        suggested = str(self._path.with_suffix(".pdf")) if self._path else "frise.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Exporter en PDF"), suggested, self.tr("Fichiers PDF (*.pdf)")
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            write_pdf(path, plan, plan.title, divisor)
        except OSError as exc:
            QMessageBox.critical(self, self.tr("Export impossible"), plain(str(exc)))
            return
        message = self.tr("PDF exporté : %1").replace("%1", Path(path).name)
        if divisor > 1:
            message += " — " + self.tr("à imprimer à %1 %").replace("%1", str(divisor * 100))
        self.statusBar().showMessage(message, 10000 if divisor > 1 else 5000)

    # --- glisser-déposer -----------------------------------------------------------------

    @staticmethod
    def dropped_csv_files(mime: QMimeData) -> list[Path]:
        """Fichiers CSV locaux d'un dépôt (les dossiers, URL distantes et autres types sont ignorés)."""
        paths = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() == ".csv" and path.is_file():
                paths.append(path)
        return paths

    def _show_drop_overlay(self, visible: bool) -> None:
        if visible:
            self._drop_overlay.setGeometry(self.view.rect().adjusted(8, 8, -8, -8))
            self._drop_overlay.raise_()
        self._drop_overlay.setVisible(visible)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self.dropped_csv_files(event.mimeData()):
            event.acceptProposedAction()
            self._show_drop_overlay(True)
        else:
            event.ignore()
            self.statusBar().showMessage(
                self.tr("Seuls les fichiers CSV peuvent être déposés."), 4000
            )

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self.dropped_csv_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._show_drop_overlay(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._show_drop_overlay(False)
        paths = self.dropped_csv_files(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        # ouverture différée : ne pas bloquer le gestionnaire de fichiers pendant une question
        QTimer.singleShot(0, lambda: self._open_dropped(paths))

    def _open_dropped(self, paths: list[Path]) -> None:
        """Ouvre le premier CSV déposé (après avoir proposé d'enregistrer les modifications)."""
        if not self._confirm_discard():
            return
        if self.load_file(paths[0]) and len(paths) > 1:
            self.statusBar().showMessage(
                self.tr("%1 fichiers déposés : « %2 » est ouvert, les autres sont ignorés.")
                .replace("%1", str(len(paths)))
                .replace("%2", paths[0].name),
                6000,
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
        # pas de nom de fichier dans le titre ; l'astérisque signale des modifications non enregistrées
        dirty = "" if self.document.stack.isClean() else " *"
        self.setWindowTitle(f"Chronologia{dirty}")

    def _category_entries(self) -> list[tuple[str, str, int]]:
        """(nom, couleur, nombre d'événements) : toutes les catégories du registre, même vides."""
        events = self.document.events
        counts = Counter(self._registry.category_name(e) for e in events)
        colors = {c.name: c.color_hex for c in self._registry}
        for event in events:
            found = self._registry.for_color(event.color)
            colors.setdefault(
                self._registry.category_name(event), found.color_hex if found else event.color_hex
            )
        order = [c.name for c in self._registry]
        order += sorted((n for n in counts if n not in order), key=lambda n: -counts[n])
        return [(n, colors[n], counts.get(n, 0)) for n in order]

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
        if self._page_mode:
            self._update_page_status()
            return
        total = len(self.document.events)
        text = self.tr("%1 événements affichés / %2").replace("%1", str(self.view.displayed_count))
        text = text.replace("%2", str(total))
        hidden = self.view.hidden_titles
        if hidden:
            text += " — " + self.tr("%1 titres masqués (zoomez pour les voir)").replace(
                "%1", str(hidden)
            )
        matches = self.view.match_count
        if matches is not None:
            text += " — " + self.tr("%1 correspondances").replace("%1", str(matches))
        self._status.setText(text)

    def _update_page_status(self) -> None:
        plan = self.page.plan
        text = self.page_panel.format_label()
        if plan is not None:
            text += " — " + self.tr("texte %1 pt").replace(
                "%1", f"{plan.font_pt:.1f}".replace(".", ",")
            )
            text += " — " + self.tr("%1 titres complets, %2 tronqués, %3 masqués").replace(
                "%1", str(plan.titles_full)
            ).replace("%2", str(plan.titles_truncated)).replace("%3", str(plan.titles_hidden))
        matches = self.page_view.match_count
        if matches is not None:
            text += " — " + self.tr("%1 correspondances").replace("%1", str(matches))
        self._status.setText(text)
