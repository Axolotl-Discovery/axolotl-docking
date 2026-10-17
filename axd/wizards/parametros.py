"""Asistente de modo avanzado: ajustar los parámetros de docking (semillas, exhaustiveness,
número de poses, núcleos de CPU y, si aplica, AutoDock4)."""
from .. import config as C
from .. import ui


def asistente_parametros(ruta, p):
    d = p["docking"]
    ui.titulo("Parámetros de docking (smina)")
    n = ui.preguntar_int("Número de semillas (réplicas independientes)", len(d["semillas"]), 1, 10)
    base = [42, 2026, 777, 1234, 31415, 2718, 1618, 4242, 9001, 1337]
    d["semillas"] = (d["semillas"] + [s for s in base if s not in d["semillas"]])[:n]
    d["exhaustiveness"] = ui.preguntar_int("Exhaustiveness (8 rápido · 32 estándar · 64+ ciego)", d["exhaustiveness"], 1, 512)
    d["num_modes"] = ui.preguntar_int("Número de poses por corrida", d["num_modes"], 1, 50)
    d["energy_range"] = ui.preguntar_int("Rango de energía (kcal/mol)", d["energy_range"], 1, 20)
    d["cpu"] = ui.preguntar_int("Núcleos de CPU (0 = todos)", d["cpu"], 0, 512)
    if d.get("motor") == "ad4":
        d["ad4_runs"] = ui.preguntar_int("AutoDock4: corridas GA por semilla", d.get("ad4_runs", 20), 1, 500)
        d["ad4_evals"] = ui.preguntar_int("AutoDock4: evaluaciones por corrida", d.get("ad4_evals", 2500000), 10000, 100000000)
    C.guardar_proyecto(ruta, p)
    ui.ok("Parámetros guardados.")
