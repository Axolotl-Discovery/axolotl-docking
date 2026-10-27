"""Navegación principal: barra vertical de iconos a la derecha, desplegable
(sólo iconos ↔ iconos con nombre), con las acciones globales (tema, terminal)
abajo. Expone la misma API mínima que QTabWidget que usa el resto de la app
(count, widget, tabText, currentIndex, setCurrentIndex, currentChanged)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QStackedWidget, QToolButton, QVBoxLayout, QWidget

from .. import icons

EXPANDED_W = 196
COLLAPSED_W = 60


class SideTabs(QWidget):
    currentChanged = Signal(int)
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None, collapsed: bool = True):
        super().__init__(parent)
        self._tabs: list[tuple[QWidget, str, str, QToolButton]] = []
        self._actions: list[tuple[str, QToolButton]] = []
        self._colors = ("#9A9A9A", "#FF5FAF")
        self._collapsed = collapsed

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.stack = QStackedWidget()
        row.addWidget(self.stack, 1)

        self.nav = QFrame()
        self.nav.setObjectName("SideNav")
        col = QVBoxLayout(self.nav)
        col.setContentsMargins(8, 10, 8, 10)
        col.setSpacing(4)

        self.toggle_btn = self._make_button("Contraer menú")
        self.toggle_btn.setCheckable(False)
        self.toggle_btn.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        col.addWidget(self.toggle_btn)
        col.addSpacing(8)

        self._tab_col = QVBoxLayout()
        self._tab_col.setSpacing(4)
        col.addLayout(self._tab_col)
        col.addStretch(1)
        self._action_col = QVBoxLayout()
        self._action_col.setSpacing(4)
        col.addLayout(self._action_col)
        row.addWidget(self.nav)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.setCurrentIndex)
        self.set_collapsed(collapsed, emit=False)

    # ---------------------------------------------------------------- construcción
    def _make_button(self, text: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName("NavButton")
        b.setText(text)
        b.setToolTip(text)
        b.setIconSize(QSize(20, 20))
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
        return b

    def addTab(self, widget: QWidget, icon_name: str, label: str) -> int:  # noqa: N802 — API tipo Qt
        idx = len(self._tabs)
        b = self._make_button(label)
        self._group.addButton(b, idx)
        self._tab_col.addWidget(b)
        self.stack.addWidget(widget)
        self._tabs.append((widget, icon_name, label, b))
        self._apply_icon(b, icon_name)
        self._apply_style(b)
        if idx == 0:
            b.setChecked(True)
        return idx

    def addAction(self, icon_name: str, label: str, callback) -> QToolButton:  # noqa: N802
        b = self._make_button(label)
        b.setCheckable(False)
        b.clicked.connect(callback)
        self._action_col.addWidget(b)
        self._actions.append((icon_name, b))
        self._apply_icon(b, icon_name)
        self._apply_style(b)
        return b

    # ---------------------------------------------------------------- API tipo QTabWidget
    def count(self) -> int:
        return len(self._tabs)

    def widget(self, i: int) -> QWidget:
        return self._tabs[i][0]

    def tabText(self, i: int) -> str:  # noqa: N802
        return self._tabs[i][2]

    def indexOf(self, w: QWidget) -> int:  # noqa: N802
        return next((i for i, t in enumerate(self._tabs) if t[0] is w), -1)

    def currentIndex(self) -> int:  # noqa: N802
        return self.stack.currentIndex()

    def currentWidget(self) -> QWidget:  # noqa: N802
        return self.stack.currentWidget()

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if not 0 <= i < len(self._tabs) or i == self.stack.currentIndex() and self._tabs[i][3].isChecked():
            return
        self._tabs[i][3].setChecked(True)
        self.stack.setCurrentIndex(i)
        self.currentChanged.emit(i)

    # ---------------------------------------------------------------- aspecto
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, emit: bool = True) -> None:
        self._collapsed = collapsed
        self.nav.setFixedWidth(COLLAPSED_W if collapsed else EXPANDED_W)
        for b in [t[3] for t in self._tabs] + [a[1] for a in self._actions]:
            self._apply_style(b)
        self.toggle_btn.setText("Expandir menú" if collapsed else "Contraer menú")
        self.toggle_btn.setToolTip(self.toggle_btn.text())
        self._apply_icon(self.toggle_btn, "expand" if collapsed else "collapse")
        self._apply_style(self.toggle_btn)
        if emit:
            self.collapsedChanged.emit(collapsed)

    def _apply_style(self, b: QToolButton) -> None:
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if self._collapsed
                             else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setFixedWidth((COLLAPSED_W if self._collapsed else EXPANDED_W) - 16)

    def _apply_icon(self, b: QToolButton, name: str) -> None:
        normal, active = self._colors
        b.setIcon(icons.icon(name, normal, active))

    def set_colors(self, normal: str, active: str) -> None:
        """Recolorea los iconos al cambiar de tema."""
        self._colors = (normal, active)
        for _w, name, _l, b in self._tabs:
            self._apply_icon(b, name)
        for name, b in self._actions:
            self._apply_icon(b, name)
        self._apply_icon(self.toggle_btn, "expand" if self._collapsed else "collapse")
