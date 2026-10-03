"""Paso 'resumen': tabla de afinidades (media ± DE), eficiencia de ligando, Δ vs control y mejores poses."""
import os
import re

from comun import afinidad, completo, log, modelo1, pesados_pdbqt, titulo


def ejecutar(P, rehacer=False):
    titulo("6 · Resumen de afinidades")
    import pandas as pd
    filas = []
    for diana in P.cfg["dianas"]:
        carpeta = P.r("04_Docking", "Resultados", diana["id"])
        for lig, ctrl in P.ligandos_para(diana["id"]):
            for s in P.cfg["docking"]["semillas"]:
                f = os.path.join(carpeta, f"{lig['id']}_s{s}.pdbqt")
                if not completo(f):
                    continue
                lp = P.ligando_pdbqt(lig, ctrl)
                filas.append(dict(diana=diana["id"], ligando=lig["id"], nombre=lig.get("nombre", lig["id"]),
                                  tipo="control" if ctrl else "ligando", semilla=s, afinidad=afinidad(f),
                                  n_pesados=pesados_pdbqt(lp) if os.path.exists(lp) else None, archivo=f))
    if not filas:
        log("  Aún no hay resultados de docking.")
        return 0
    df = pd.DataFrame(filas)
    df.drop(columns=["archivo"]).to_csv(P.r("05_Analisis", "afinidades_corridas.csv"), index=False)

    res = (df.groupby(["diana", "ligando", "nombre", "tipo"], sort=False)
             .agg(afinidad_media=("afinidad", "mean"), afinidad_de=("afinidad", "std"), mejor=("afinidad", "min"),
                  n_semillas=("afinidad", "size"), n_pesados=("n_pesados", "first")).reset_index())
    res["LE"] = -res["afinidad_media"] / res["n_pesados"]
    ctrl = res[res.tipo == "control"].sort_values("afinidad_media").groupby("diana").first()
    res["control_ref"] = res.diana.map(ctrl["ligando"]) if len(ctrl) else None
    res["afinidad_control"] = res.diana.map(ctrl["afinidad_media"]) if len(ctrl) else None
    res["delta_vs_control"] = res["afinidad_media"] - res["afinidad_control"]
    res = res.sort_values(["diana", "afinidad_media"]).round(3)
    res.to_csv(P.r("05_Analisis", "afinidades_resumen.csv"), index=False)
    mat = res.pivot(index="ligando", columns="diana", values="afinidad_media")
    mat.to_csv(P.r("05_Analisis", "matriz_afinidad.csv"))

    xlsx_nombre = re.sub(r"[^A-Za-z0-9._-]+", "_", P.cfg["nombre"]) + "_afinidades.xlsx"
    try:
        with pd.ExcelWriter(P.r("05_Analisis", xlsx_nombre)) as xw:
            res.to_excel(xw, sheet_name="Resumen", index=False)
            mat.to_excel(xw, sheet_name="Matriz")
            df.drop(columns=["archivo"]).to_excel(xw, sheet_name="Corridas", index=False)
            rd = P.r("05_Analisis", "redocking_resumen.csv")
            if os.path.exists(rd):
                pd.read_csv(rd).to_excel(xw, sheet_name="Redocking", index=False)
        xlsx = True
    except Exception:  # noqa: BLE001  (openpyxl no instalado)
        xlsx = False

    # mejor pose de cada par → MejoresPoses/<diana>__<ligando>.pdbqt
    mejores = df.loc[df.groupby(["diana", "ligando"])["afinidad"].idxmin()]
    for r in mejores.itertuples():
        open(P.r("04_Docking", "MejoresPoses", f"{r.diana}__{r.ligando}.pdbqt"), "w").write(modelo1(r.archivo))

    for diana, g in res.groupby("diana", sort=False):
        log(f"\n  ▸ {diana}")
        log(f"    {'ligando':34s} {'ΔG media':>9s} {'DE':>5s} {'mejor':>7s} {'LE':>5s} {'Δ ctrl':>7s}")
        for r in g.itertuples():
            de = 0 if r.afinidad_de != r.afinidad_de else r.afinidad_de
            dc = "" if r.delta_vs_control != r.delta_vs_control else f"{r.delta_vs_control:+7.2f}"
            log(f"    {r.ligando[:34]:34s} {r.afinidad_media:9.2f} {de:5.2f} {r.mejor:7.2f} {r.LE:5.2f} {dc:>7s}"
                + ("  ◆ control" if r.tipo == "control" else ""))
    log("\n  Archivos:")
    log("    05_Analisis/afinidades_resumen.csv · matriz_afinidad.csv · afinidades_corridas.csv"
        + (f" · {xlsx_nombre}" if xlsx else ""))
    log(f"    04_Docking/MejoresPoses/  ({len(mejores)} poses)")
    log("  (Δ ctrl negativo = el ligando supera al control en afinidad predicha)")
    return 0
