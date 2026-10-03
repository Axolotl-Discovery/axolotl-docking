"""Utilidades de interfaz de terminal: colores, preguntas, menús y rutas.

Sólo usa la librería estándar para que la app funcione con el python3 del sistema,
aunque el entorno conda todavía no esté instalado.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

try:
    import readline  # habilita flechas, historial y autocompletado con TAB
except ImportError:  # pragma: no cover
    readline = None

COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code):
    return (lambda t: f"\033[{code}m{t}\033[0m") if COLOR else (lambda t: str(t))


rosa, verde, amarillo, rojo, gris, negrita, cian = (
    _c("38;5;205"), _c("32"), _c("33"), _c("31"), _c("90"), _c("1"), _c("36"))

ARTE = [
    "...g............................g...",
    "...gg..........................gg...",
    "...fgf........................fgf...",
    "....fgf......................fgf....",
    ".....fg.......oooooooo.......gf.....",
    "......fg...ooPPPPPPPPPPoo...gf......",
    ".......gfooPPPPPPPPPPPPPPoofg.......",
    "g.f....fooPPPPPPPPPPPPPPPPoof....f.g",
    "gggff..ooPPPPPPPPPPPPPPPPPPoo..ffggg",
    "f.fgggfoPPPWKKPPPPPPPPWKKPPPofgggf.f",
    "...ffggoPPPKKKPPPPPPPPKKKPPPoggff...",
    "......ooPPPKKKPPPPPPPPKKKPPPoo......",
    ".......oPPPPPPPPPPPPPPPPPPPPo.......",
    "....f.foPCCPLLLmLLLLmLLLCCPPof.f....",
    ".f.fgggooPPLLLLLmmmmLLLLLPPoogggf.f.",
    ".gggg.ffooLLLLLLLLLLLLLLLLooff.gggg.",
    ".g.f.....ooLLLLLLLLLLLLLLoo.....f.g.",
    "...........ooLLLLLLLLLLoo...........",
    "..............oooooooo..............",
    "....................................",
]

# colores del ajolote (RGB)
PALETA = {"P": (246, 166, 193), "o": (184, 67, 111), "L": (253, 217, 230), "g": (233, 87, 142),
          "f": (255, 156, 194), "K": (43, 27, 46), "W": (255, 255, 255), "C": (255, 111, 156),
          "m": (142, 47, 87)}

ARTE_ASCII = r"""
   \\  \\                 //  //
    \\__\\   .-------.   //__//
   ===   ) /  o     o  \ (   ===
    //‾‾// |    \___/    | \\‾‾\\
   //  //   '._________.'   \\  \\
"""


def _arte_color():
    """Dibuja el pixel art con medios bloques (▀): cada celda = 2 píxeles verticales, color verdadero."""
    lineas = []
    for y in range(0, len(ARTE), 2):
        sup, inf = ARTE[y], ARTE[y + 1] if y + 1 < len(ARTE) else "." * len(ARTE[y])
        l = ""
        for a, b in zip(sup, inf):
            ca, cb = PALETA.get(a), PALETA.get(b)
            if ca and cb:
                l += f"\033[38;2;{ca[0]};{ca[1]};{ca[2]}m\033[48;2;{cb[0]};{cb[1]};{cb[2]}m▀\033[0m"
            elif ca:
                l += f"\033[38;2;{ca[0]};{ca[1]};{ca[2]}m▀\033[0m"
            elif cb:
                l += f"\033[38;2;{cb[0]};{cb[1]};{cb[2]}m▄\033[0m"
            else:
                l += " "
        lineas.append(l)
    return lineas


class Cancelado(Exception):
    """El usuario canceló (Ctrl+C o escribió 'q')."""


def banner(version=""):
    texto = ["", "", "", negrita(rosa("A X O L O T L   D O C K I N G")),
             gris("docking molecular sin tanto show"), "",
             gris(f"v{version}  ·  por Axolotl Discovery") if version else gris("por Axolotl Discovery")]
    if not COLOR:
        print(ARTE_ASCII)
        print("  AXOLOTL DOCKING" + (f"  v{version}" if version else ""))
        print()
        return
    arte = _arte_color()
    ancho = shutil.get_terminal_size((100, 30)).columns
    print()
    if ancho >= len(ARTE[0]) + 42:
        for i, l in enumerate(arte):
            print("  " + l + "    " + (texto[i] if i < len(texto) else ""))
    else:
        for l in arte:
            print("  " + l)
        for t in texto[3:]:
            print("  " + t)
    print()


def titulo(t):
    print()
    print(negrita(rosa(f"── {t} ")) + rosa("─" * max(2, 60 - len(t))))


def ok(t):
    print(verde("  ✔ ") + t)


def aviso(t):
    print(amarillo("  ⚠ ") + t)


def error(t):
    print(rojo("  ✘ ") + t)


def info(t):
    print(gris("  · ") + t)


# ---------------------------------------------------------------- autocompletado
def _completar_rutas(texto, estado):
    t = os.path.expanduser(texto.strip("'\""))
    opciones = []
    for p in sorted(glob.glob(t + "*")):
        opciones.append(p + ("/" if os.path.isdir(p) else ""))
    return opciones[estado] if estado < len(opciones) else None


def _modo_rutas(activo):
    if not readline:
        return
    if activo:
        readline.set_completer_delims("\t\n;")
        readline.set_completer(_completar_rutas)
        readline.parse_and_bind("tab: complete")
    else:
        readline.set_completer(None)


def _input(prompt, prefill=""):
    if readline and prefill:
        readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        print()
        raise Cancelado()
    finally:
        if readline:
            readline.set_startup_hook(None)


# ---------------------------------------------------------------- preguntas
def preguntar(texto, defecto=None, obligatorio=False, valida=None, editable=False):
    """Pregunta texto libre. Con editable=True el valor por defecto aparece ya escrito."""
    while True:
        sufijo = "" if (defecto in (None, "") or editable) else gris(f" [{defecto}]")
        r = _input(f"  {cian('?')} {texto}{sufijo}: ", prefill=str(defecto) if (editable and defecto) else "").strip()
        if r.lower() == "q":
            raise Cancelado()
        if not r and defecto is not None:
            r = str(defecto)
        if not r and obligatorio:
            aviso("Este dato es obligatorio (escribe q para cancelar).")
            continue
        if valida and r:
            msg = valida(r)
            if msg:
                aviso(msg)
                continue
        return r


def preguntar_int(texto, defecto, minimo=None, maximo=None):
    def v(x):
        if not re.fullmatch(r"-?\d+", x):
            return "Escribe un número entero."
        n = int(x)
        if minimo is not None and n < minimo:
            return f"Mínimo {minimo}."
        if maximo is not None and n > maximo:
            return f"Máximo {maximo}."
    return int(preguntar(texto, defecto, valida=v))


def preguntar_float(texto, defecto):
    def v(x):
        try:
            float(x)
        except ValueError:
            return "Escribe un número."
    return float(preguntar(texto, defecto, valida=v))


def si_no(texto, defecto=True):
    op = "S/n" if defecto else "s/N"
    while True:
        r = _input(f"  {cian('?')} {texto} {gris('(' + op + ')')}: ").strip().lower()
        if r == "q":
            raise Cancelado()
        if not r:
            return defecto
        if r in ("s", "si", "sí", "y", "yes"):
            return True
        if r in ("n", "no"):
            return False


def menu(titulo_menu, opciones, defecto=None, salir="Volver"):
    """opciones: lista de (clave, texto). Devuelve la clave elegida o None para salir."""
    titulo(titulo_menu)
    for i, (_, txt) in enumerate(opciones, 1):
        print(f"   {rosa(str(i).rjust(2))}) {txt}")
    if salir:
        print(f"   {gris(' 0) ' + salir)}")
    while True:
        r = _input(f"  {cian('›')} Opción{gris(f' [{defecto}]') if defecto else ''}: ").strip().lower()
        if not r and defecto:
            r = str(defecto)
        if r in ("0", "q") and salir:
            return None
        if r.isdigit() and 1 <= int(r) <= len(opciones):
            return opciones[int(r) - 1][0]
        aviso("Opción no válida.")


# ---------------------------------------------------------------- rutas
def a_ruta_linux(p):
    """Acepta rutas de Windows (C:\\...), rutas arrastradas con comillas y ~."""
    p = p.strip().strip("'\"").strip()
    if re.match(r"^[A-Za-z]:[\\/]", p) or p.startswith("\\\\"):
        if shutil.which("wslpath"):
            try:
                return subprocess.check_output(["wslpath", "-u", p], text=True).strip()
            except subprocess.CalledProcessError:
                pass
        if re.match(r"^[A-Za-z]:", p):
            return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    p = p.replace("\\ ", " ")
    return os.path.abspath(os.path.expanduser(p))


def preguntar_ruta(texto, defecto=None, debe_existir=True, tipo="cualquiera"):
    """tipo: 'archivo', 'carpeta' o 'cualquiera'. TAB autocompleta. Acepta rutas de Windows."""
    _modo_rutas(True)
    try:
        while True:
            r = preguntar(texto + gris(" (TAB autocompleta)"), defecto, obligatorio=defecto is None)
            p = a_ruta_linux(r)
            if debe_existir and not os.path.exists(p):
                aviso(f"No existe: {p}")
                continue
            if debe_existir and tipo == "archivo" and not os.path.isfile(p):
                aviso("Eso es una carpeta; necesito un archivo.")
                continue
            if debe_existir and tipo == "carpeta" and not os.path.isdir(p):
                aviso("Eso es un archivo; necesito una carpeta.")
                continue
            return p
    finally:
        _modo_rutas(False)


def pausa():
    try:
        _input(gris("  (Enter para continuar) "))
    except Cancelado:
        pass


def nombre_seguro(t):
    """Convierte un nombre en algo válido para archivos (sin espacios ni acentos raros)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9._+-]+", "_", t.strip()).strip("_")
    return t or "sin_nombre"
