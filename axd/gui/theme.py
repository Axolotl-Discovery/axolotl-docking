"""Hojas de estilo dark/light — mismos tokens de color usados en los
wireframes del canvas de diseño, para que la app construida se vea como lo
que ya se aprobó."""
from __future__ import annotations

DARK = {
    "bg": "#121212", "panel": "#1C1C1C", "panel_alt": "#262626", "border": "#3A3A3A",
    "text": "#F2F2F2", "text_secondary": "#9A9A9A", "muted": "#6E6E6E",
    "accent": "#FF5FAF", "accent_hover": "#FF7FC0", "accent_pressed": "#E04B96",
    "success": "#5FD68A", "warning": "#E6C14D", "error": "#E05C5C",
    "warning_bg": "#2A2416", "error_bg": "#2A1616", "success_bg": "#16241C",
}

LIGHT = {
    "bg": "#FAFAFA", "panel": "#FFFFFF", "panel_alt": "#F0F0F0", "border": "#D9D9D9",
    "text": "#1A1A1A", "text_secondary": "#6B6B6B", "muted": "#8A8A8A",
    "accent": "#E0458F", "accent_hover": "#F05FA3", "accent_pressed": "#C53A78",
    "success": "#2E9E5B", "warning": "#B8860B", "error": "#C94444",
    "warning_bg": "#FDF3DC", "error_bg": "#FBEAEA", "success_bg": "#E8F5EC",
}


def stylesheet(tokens: dict) -> str:
    t = tokens
    return f"""
    QWidget {{ background: {t['bg']}; color: {t['text']}; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    #TopBar {{ background: {t['panel']}; border-bottom: 1px solid {t['border']}; }}
    #Brand {{ color: {t['accent']}; font-weight: 700; font-size: 14px; letter-spacing: 2px; }}
    #Chip {{ background: {t['panel_alt']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px 10px; color: {t['text_secondary']}; font-size: 12px; }}
    #ChipOffline {{ background: {t['error_bg']}; border: 1px solid {t['error']}; border-radius: 6px; padding: 4px 10px; color: {t['error']}; font-size: 12px; font-weight: 600; }}
    #ChipOk {{ color: {t['success']}; font-size: 12px; }}
    QTabWidget::pane {{ border-top: 1px solid {t['border']}; background: {t['bg']}; }}
    QTabBar {{ background: {t['panel']}; }}
    QTabBar::tab {{ background: transparent; color: {t['text_secondary']}; padding: 12px 18px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {t['accent']}; font-weight: 600; border-bottom: 2px solid {t['accent']}; }}
    QListWidget, QTreeWidget, QTableWidget {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 10px; gridline-color: {t['border']}; }}
    QHeaderView::section {{ background: {t['panel_alt']}; color: {t['text_secondary']}; border: none; padding: 6px; text-transform: uppercase; font-size: 11px; }}
    QPushButton {{ background: {t['panel_alt']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 8px 14px; }}
    QPushButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:checked {{ background: {t['accent']}; color: #FFFFFF; border-color: {t['accent']}; font-weight: 600; }}
    QPushButton:disabled {{ color: {t['muted']}; }}
    QPushButton#Primary {{ background: {t['accent']}; color: #FFFFFF; border: none; font-weight: 700; }}
    QPushButton#Primary:hover {{ background: {t['accent_hover']}; }}
    QPushButton#Primary:pressed {{ background: {t['accent_pressed']}; }}
    QPushButton#Danger {{ background: transparent; color: {t['error']}; border: 1px solid {t['error']}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{ background: {t['panel']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 6px; }}
    QProgressBar {{ background: {t['panel_alt']}; border: 1px solid {t['border']}; border-radius: 6px; text-align: center; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 6px; }}
    QLabel#Muted {{ color: {t['text_secondary']}; }}
    QLabel#Title {{ font-size: 18px; font-weight: 700; }}
    QFrame#Banner {{ border-radius: 8px; padding: 10px; }}
    QFrame#BannerWarning {{ background: {t['warning_bg']}; border: 1px solid {t['warning']}; }}
    QFrame#BannerError {{ background: {t['error_bg']}; border: 1px solid {t['error']}; }}
    QFrame#BannerSuccess {{ background: {t['success_bg']}; border: 1px solid {t['success']}; }}
    QDockWidget {{ titlebar-close-icon: none; }}
    QDockWidget::title {{ background: {t['panel']}; padding: 6px; border-bottom: 1px solid {t['border']}; }}
    """


def tokens_for(theme: str) -> dict:
    return DARK if theme == "dark" else LIGHT


def apply_theme(widget, theme: str) -> None:
    widget.setStyleSheet(stylesheet(tokens_for(theme)))
