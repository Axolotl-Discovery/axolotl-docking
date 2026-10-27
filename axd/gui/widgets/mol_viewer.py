"""Visor 3D embebido para la pestaña Visualización: 3Dmol.js (copia local en
axd/gui/vendor/3dmol, sin CDN) dentro de un QWebEngineView.

Si QtWebEngine no está disponible en el entorno, el widget muestra un aviso
en su lugar y la pestaña sigue funcionando con "Abrir en PyMOL"."""
from __future__ import annotations

import base64
import json
import os
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

VENDOR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor", "3dmol")
LIGAND_RESN = "LIG"  # nombre de residuo del ligando en los complejos (pipeline/interactions.py)

try:  # QtWebEngine viene en PySide6 de PyPI; en algunos builds de conda puede faltar
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_ERROR = ""
except ImportError as e:  # pragma: no cover — depende del entorno
    QWebEngineView = None
    WEBENGINE_ERROR = str(e)

BG = {"dark": "#000000", "light": "#FFFFFF"}

_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;overflow:hidden;background:__BG__}#v{position:absolute;inset:0}</style>
<script src="3Dmol-min.js"></script></head>
<body><div id="v"></div>
<script>
let viewer = null;
try {
  viewer = $3Dmol.createViewer("v", {backgroundColor: "__BG__"});
} catch (e) {
  viewer = null;
}
if (!viewer) {
  document.getElementById("v").innerHTML =
    '<div style="font:13px -apple-system,Segoe UI,sans-serif;color:#9A9A9A;padding:24px;max-width:520px">' +
    'El visor 3D no pudo iniciar: este equipo no ofrece WebGL a la app (pasa en algunas ' +
    'm&aacute;quinas virtuales o sin aceleraci&oacute;n gr&aacute;fica). Usa &laquo;Abrir en PyMOL&raquo;.</div>';
}
let st = {mode: "cartoon", data: null, ref: null};
const LIG = "__LIG__";
function noLig(){ return {not: {resn: [LIG, "HOH", "WAT"]}}; }
function apply(){
  if (!viewer) return;
  viewer.setStyle({}, {});
  viewer.removeAllSurfaces();
  const d = st.data; if (!d) { viewer.render(); return; }
  const prot = {hetflag: false};
  if (st.mode === "sticks") viewer.setStyle(prot, {stick: {radius: 0.12, colorscheme: "grayCarbon"}});
  else viewer.setStyle(prot, {cartoon: {color: "#B8B8B8"}});
  if (st.mode === "surface")
    viewer.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.7, color: "#E8E8E8"}, prot);
  viewer.setStyle({hetflag: true, and: [noLig()]}, {stick: {radius: 0.2, colorscheme: "yellowCarbon"}});
  for (const h of d.highlight || [])
    viewer.addStyle({resi: h.resi, chain: h.chain, hetflag: false}, {stick: {radius: 0.18, colorscheme: "greenCarbon"}});
  viewer.setStyle({resn: LIG}, {stick: {radius: 0.28, colorscheme: "magentaCarbon"}});
  if (st.ref) st.ref.setStyle({}, {stick: {radius: 0.28, colorscheme: "magentaCarbon"}});
  viewer.render();
}
function center(){
  if (!viewer) return;
  const d = st.data;
  // Ligando con ~10 Å de bolsillo alrededor; en una diana, su ligando de
  // referencia si lo hay; si no, la proteína entera.
  if (d && d.focus_ligand) viewer.zoomTo({within: {distance: 10, sel: {resn: LIG}}});
  else if (st.ref) viewer.zoomTo({within: {distance: 12, sel: {model: st.ref}}});
  else viewer.zoomTo();
  viewer.render();
}
function load(d){
  st.data = d; st.ref = null;
  if (!viewer) return;
  viewer.clear();
  if (!d) { viewer.render(); return; }
  viewer.addModel(d.pdb, "pdb");
  st.ref = d.ref ? viewer.addModel(d.ref, "pdb") : null;
  if (d.box) viewer.addBox({center: {x: d.box.center[0], y: d.box.center[1], z: d.box.center[2]},
                            dimensions: {w: d.box.size[0], h: d.box.size[1], d: d.box.size[2]},
                            color: "#FF5FAF", wireframe: true});
  apply(); center();
}
function setMode(m){ st.mode = m; apply(); }
function png(){ return viewer ? viewer.pngURI() : null; }
function setBg(c){ document.body.style.background = c; if (viewer) { viewer.setBackgroundColor(c); viewer.render(); } }
</script></body></html>"""


def residues_from_interactions(rows):
    """[{'resi': 532, 'chain': 'A'}, ...] únicos, desde filas de interactions_detail.csv
    ('residuo' tipo 'CYS532', 'cadena' 'A')."""
    out, seen = [], set()
    for r in rows:
        m = re.search(r"(-?\d+)[A-Za-z]?$", str(r.get("residuo", "")).strip())
        if not m:
            continue
        key = (int(m.group(1)), (r.get("cadena") or "").strip())
        if key not in seen:
            seen.add(key)
            out.append({"resi": key[0], "chain": key[1]} if key[1] else {"resi": key[0]})
    return out


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


class MolViewer(QWidget):
    """Visor con barra de herramientas (Cartoon / Superficie / Sticks, Centrar, Captura)."""

    def __init__(self, theme: str = "dark", figures_dir_fn=None, parent=None):
        super().__init__(parent)
        self._theme = theme if theme in BG else "dark"
        self._ready = False
        self._pending: list[str] = []
        self._figures_dir_fn = figures_dir_fn
        self._name = "estructura"

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        bar = QHBoxLayout()
        self._mode_buttons = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for mode, label in (("cartoon", "Cartoon"), ("surface", "Superficie"), ("sticks", "Sticks")):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setChecked(mode == "cartoon")
            b.clicked.connect(lambda _c=False, m=mode: self.set_mode(m))
            self._mode_group.addButton(b)
            self._mode_buttons[mode] = b
            bar.addWidget(b)
        bar.addSpacing(12)
        self.center_btn = QPushButton("Centrar")
        self.center_btn.clicked.connect(lambda: self._js("center()"))
        self.snap_btn = QPushButton("Captura")
        self.snap_btn.clicked.connect(self.snapshot)
        bar.addWidget(self.center_btn)
        bar.addWidget(self.snap_btn)
        bar.addStretch(1)
        v.addLayout(bar)

        if QWebEngineView is None:
            self.view = None
            msg = QLabel("El visor 3D necesita QtWebEngine, que no está en este entorno de PySide6.\n"
                         "Puedes seguir usando «Abrir en PyMOL».\n\nDetalle: " + WEBENGINE_ERROR)
            msg.setObjectName("Muted")
            msg.setWordWrap(True)
            v.addWidget(msg, 1)
            for b in self._mode_group.buttons() + [self.center_btn, self.snap_btn]:
                b.setEnabled(False)
        else:
            self.view = QWebEngineView(self)
            s = self.view.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            self.view.loadFinished.connect(self._on_loaded)
            html = (_HTML.replace("__BG__", BG[self._theme]).replace("__LIG__", LIGAND_RESN))
            self.view.setHtml(html, QUrl.fromLocalFile(VENDOR_DIR + os.sep))
            v.addWidget(self.view, 1)

        legend = QLabel('<span style="color:#FF00FF">■</span> ligando &nbsp;&nbsp; '
                        '<span style="color:#33CC33">■</span> residuos en contacto &nbsp;&nbsp; '
                        '<span style="color:#E6C14D">■</span> cofactores &nbsp;&nbsp; '
                        '<span style="color:#FF5FAF">□</span> caja de docking')
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setObjectName("Muted")
        v.addWidget(legend)

    @property
    def available(self) -> bool:
        return self.view is not None

    # ---------------------------------------------------------------- JS
    def _on_loaded(self, ok: bool) -> None:
        self._ready = bool(ok)
        if ok:
            for code in self._pending:
                self.view.page().runJavaScript(code)
        self._pending.clear()

    def _js(self, code: str, callback=None) -> None:
        if self.view is None:
            return
        if self._ready:
            if callback:
                self.view.page().runJavaScript(code, 0, callback)
            else:
                self.view.page().runJavaScript(code)
        elif callback is None:
            self._pending.append(code)

    # ---------------------------------------------------------------- API
    def clear(self) -> None:
        self._name = "estructura"
        self._js("load(null)")

    def show_complex(self, pdb_path: str, interactions=None, name: str = "complejo") -> None:
        self._name = name
        self._js("load(%s)" % json.dumps({"pdb": _read(pdb_path), "focus_ligand": True,
                                          "highlight": residues_from_interactions(interactions or [])}))

    def show_target(self, receptor_path: str, box: dict | None = None, ref_path: str | None = None,
                    name: str = "diana") -> None:
        self._name = name
        payload = {"pdb": _read(receptor_path), "focus_ligand": False}
        if box and box.get("center") and box.get("size"):
            payload["box"] = {"center": box["center"], "size": box["size"]}
        if ref_path and os.path.isfile(ref_path):
            payload["ref"] = _read(ref_path)
        self._js("load(%s)" % json.dumps(payload))

    def set_mode(self, mode: str) -> None:
        if mode in self._mode_buttons and not self._mode_buttons[mode].isChecked():
            self._mode_buttons[mode].setChecked(True)
        self._js("setMode(%s)" % json.dumps(mode))

    def set_theme(self, theme: str) -> None:
        self._theme = theme if theme in BG else "dark"
        self._js("setBg(%s)" % json.dumps(BG[self._theme]))

    def snapshot(self) -> None:
        if self.view is None:
            return
        base = self._figures_dir_fn() if self._figures_dir_fn else ""
        if base:
            os.makedirs(base, exist_ok=True)
        dest, _ = QFileDialog.getSaveFileName(self, "Guardar captura",
                                              os.path.join(base, f"{self._name}.png"), "Imagen PNG (*.png)")
        if not dest:
            return

        def _save(uri):
            if isinstance(uri, str) and "," in uri:
                with open(dest, "wb") as fh:
                    fh.write(base64.b64decode(uri.split(",", 1)[1]))
            else:  # respaldo: captura del widget tal cual se ve
                self.view.grab().save(dest)

        self._js("png()", _save)
