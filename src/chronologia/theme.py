"""Thème visuel clair et épuré de l'application (palette + feuille de style)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4f46e5"
ACCENT_HOVER = "#4338ca"
ACCENT_SOFT = "#eef0ff"
BACKGROUND = "#f3f4f9"  # fenêtre
SURFACE = "#ffffff"  # zones de contenu
BAND = "#f6f7fc"  # bandes alternées de la frise
BORDER = "#e1e4ee"
GRID = "#d5d9e6"
TEXT = "#1f2430"
MUTED = "#6b7280"
DISABLED = "#b6bcc9"

STYLESHEET = f"""
* {{ outline: 0; }}
QMainWindow, QDialog {{ background: {BACKGROUND}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{
    background: {TEXT}; color: white; border: none; padding: 5px 8px; border-radius: 4px;
}}

QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px;
}}
QMenu::item {{ padding: 6px 26px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QToolBar {{
    background: {SURFACE}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 10px; spacing: 4px;
}}
QToolBar::separator {{ background: {BORDER}; width: 1px; margin: 6px 8px; }}
QToolButton {{
    border: none; border-radius: 8px; padding: 6px; background: transparent;
}}
QToolButton:hover {{ background: {ACCENT_SOFT}; }}
QToolButton:pressed {{ background: #dfe3ff; }}
QToolButton:disabled {{ color: {DISABLED}; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600; }}
QToolButton[primary="true"] {{
    background: {ACCENT}; color: white; padding: 6px 14px; font-weight: 600;
}}
QToolButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}

QPushButton {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 6px 14px; min-height: 18px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:disabled {{ color: {DISABLED}; background: {BACKGROUND}; }}
QPushButton:default {{
    background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 600;
}}
QPushButton:default:hover {{ background: {ACCENT_HOVER}; color: white; }}
QPushButton:default:disabled {{ background: #c7c9ee; border-color: #c7c9ee; color: white; }}

QLineEdit, QPlainTextEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 9px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}

QDockWidget {{ font-weight: 600; color: {MUTED}; }}
QDockWidget::title {{ background: {BACKGROUND}; padding: 10px 12px 4px 12px; text-align: left; }}

QListWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px;
}}
QListWidget::item {{ padding: 6px 6px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {BACKGROUND}; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}

QGraphicsView {{ border: none; background: {SURFACE}; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar::item {{ border: none; }}
QLabel {{ background: transparent; }}
QLabel#dropOverlay {{
    background: rgba(238, 240, 255, 245); border: 3px dashed {ACCENT}; border-radius: 14px;
    color: {ACCENT}; font-size: 20px; font-weight: 600;
}}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: #b9bfd3; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def build_palette() -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: BAND,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: MUTED,
        QPalette.ColorRole.Mid: GRID,
        QPalette.ColorRole.Midlight: BORDER,
        QPalette.ColorRole.ToolTipBase: TEXT,
        QPalette.ColorRole.ToolTipText: "#ffffff",
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    return palette


def apply_theme(app: QApplication) -> None:
    """Applique le thème clair (identique sur Linux et Windows, quel que soit le thème système)."""
    app.setStyle("Fusion")
    app.setPalette(build_palette())
    app.setStyleSheet(STYLESHEET)
