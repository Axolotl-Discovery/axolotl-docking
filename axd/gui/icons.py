"""Iconos de la GUI: SVG de trazo propios (24×24), coloreados al vuelo con el
color del tema. Sin dependencias ni archivos externos; los de CPU/GPU son
genéricos (chip/tarjeta) y el fabricante se indica con texto, no con logotipos."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_P = {
    # navegación
    "project": '<path d="M3 7h6l2 2h10v10H3z"/>',
    "process": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>',
    "results": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 9v11"/>',
    "postproc": '<path d="M4 20V4M4 20h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "env": '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    "viewer": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    # acciones
    "theme": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "back": '<path d="M15 5l-7 7 7 7"/>',
    "expand": '<path d="M15 5l-7 7 7 7"/><path d="M20 4v16" />',
    "collapse": '<path d="M9 5l7 7-7 7"/><path d="M4 4v16" />',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M4 20h16"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
    "folder-open": '<path d="M3 7h6l2 2h10v10H3z"/><path d="M3 19l3-7h17l-3 7"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    # dispositivos
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5"/>'
           '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    "gpu": '<rect x="2" y="6" width="20" height="11" rx="1.5"/><circle cx="9" cy="11.5" r="3"/>'
           '<path d="M15 9.5h4M15 12h4M15 14.5h4M5 17v3M19 17v3"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _P.get(name, _P["file"]).replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def pixmap(name: str, color: str, size: int = 20, dpr: float = 2.0) -> QPixmap:
    px = QPixmap(QSize(int(size * dpr), int(size * dpr)))
    px.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(_svg(name, color)))
    p = QPainter(px)
    r.render(p)
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str, active_color: str | None = None, size: int = 20) -> QIcon:
    """QIcon con el color normal y, si se da, otro para el estado activo (checked)."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, active_color or color, size), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def names() -> list[str]:
    return list(_P)
