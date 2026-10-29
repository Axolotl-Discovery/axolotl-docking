"""Estado por paso de una corrida del pipeline, para la lista de pasos de la GUI.

pipeline/run.py marca cada paso como pendiente → en_curso → ok | error y guarda
04_Docking/logs/steps.json de forma atómica en cada cambio. Mientras un paso
corre, se copian aparte las líneas con ✘ (y los tracebacks) que imprime, para
poder mostrar "qué falló" sin que el usuario tenga que buscar en el log."""
import io
import json
import os
import sys
import time

MAX_LINEAS_ERROR = 200


class _Tee(io.TextIOBase):
    """Escribe en la salida real y, a la vez, guarda las líneas de error del paso actual."""

    def __init__(self, real, sink):
        self.real, self.sink, self._buf = real, sink, ""

    def write(self, s):
        self.real.write(s)
        self._buf += s
        while "\n" in self._buf:
            linea, self._buf = self._buf.split("\n", 1)
            self.sink(linea)
        return len(s)

    def flush(self):
        self.real.flush()

    def reconfigure(self, **kw):  # run.py llama sys.stdout.reconfigure(...)
        if hasattr(self.real, "reconfigure"):
            self.real.reconfigure(**kw)


class StepTracker:
    def __init__(self, ruta, pasos, titulos, log=None):
        self.ruta = ruta
        self.data = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S"), "log": log, "terminado": False,
                     "pasos": [{"id": p, "titulo": titulos.get(p, p), "estado": "pendiente", "inicio": None,
                                "fin": None, "segundos": None, "fallos": 0, "errores": []} for p in pasos]}
        self._actual = None
        self._en_traceback = False
        self._t0 = None
        self._stdout = sys.stdout
        sys.stdout = _Tee(self._stdout, self._linea)
        self._guardar()

    # ---------------------------------------------------------------- captura
    def _linea(self, linea):
        if self._actual is None:
            return
        errores = self._actual["errores"]
        s = linea.rstrip()
        if s.startswith("Traceback"):
            self._en_traceback = True
        if self._en_traceback or "✘" in s:
            if len(errores) < MAX_LINEAS_ERROR:
                errores.append(s)
        if self._en_traceback and s and not s.startswith((" ", "Traceback")):
            self._en_traceback = False  # la última línea del traceback es la del tipo de error

    # ---------------------------------------------------------------- transiciones
    def _paso(self, pid):
        return next(p for p in self.data["pasos"] if p["id"] == pid)

    def iniciar(self, pid):
        self._actual = self._paso(pid)
        self._actual.update(estado="en_curso", inicio=time.strftime("%H:%M:%S"))
        self._t0 = time.time()
        self._guardar()

    def terminar(self, pid, fallos, excepcion=False):
        p = self._paso(pid)
        p.update(fin=time.strftime("%H:%M:%S"), segundos=round(time.time() - (self._t0 or time.time()), 1),
                 fallos=int(fallos), estado="error" if (fallos or excepcion) else "ok")
        if (fallos or excepcion) and not p["errores"]:
            p["errores"].append(f"El paso terminó con {fallos} problema(s); revisa el log completo.")
        self._actual, self._en_traceback = None, False
        self._guardar()

    def cerrar(self):
        self.data["terminado"] = True
        self.data["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._guardar()
        sys.stdout = self._stdout

    def _guardar(self):
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        tmp = self.ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.ruta)
