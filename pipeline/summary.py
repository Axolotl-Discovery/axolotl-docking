"""Paso 'resumen': tabla de afinidades (media ± DE), eficiencia de ligando, Δ vs control y mejores poses."""
import os
import re

from common import affinity, is_complete, log, model1, heavy_atoms_pdbqt, title


def run(P, rehacer=False):
    title("6 · Resumen de afinidades")
    import pandas as pd
    filas = []
    for diana in P.cfg["targets"]:
        for lig, ctrl in P.ligands_for(diana["id"]):
            for s in P.cfg["docking"]["seeds"]:
                f = P.layout.result_pdbqt(diana["id"], lig["id"], s)
                if not is_complete(f):
                    continue
                lp = P.ligand_pdbqt(lig, ctrl)
                filas.append(dict(diana=diana["id"], ligando=lig["id"], nombre=lig.get("name", lig["id"]),
                                  tipo="control" if ctrl else "ligando", semilla=s, afinidad=affinity(f),
                                  n_pesados=heavy_atoms_pdbqt(lp) if os.path.exists(lp) else None, archivo=f))
    if not filas:
        log("  Aún no hay resultados de docking.")
        return 0
    df = pd.DataFrame(filas)
    df.drop(columns=["archivo"]).to_csv(P.layout.affinities_runs_csv(), index=False)

    res = (df.groupby(["diana", "ligando", "nombre", "tipo"], sort=False)
             .agg(afinidad_media=("afinidad", "mean"), afinidad_de=("afinidad", "std"), mejor=("afinidad", "min"),
                  n_semillas=("afinidad", "size"), n_pesados=("n_pesados", "first")).reset_index())
    res["LE"] = -res["afinidad_media"] / pd.to_numeric(res["n_pesados"], errors="coerce")
    ctrl = res[res.tipo == "control"].sort_values("afinidad_media").groupby("diana").first()
    res["control_ref"] = res.diana.map(ctrl["ligando"]) if len(ctrl) else None
    res["afinidad_control"] = res.diana.map(ctrl["afinidad_media"]) if len(ctrl) else None
    res["delta_vs_control"] = res["afinidad_media"] - res["afinidad_control"]
    res = res.sort_values(["diana", "afinidad_media"]).round(3)
    res.to_csv(P.layout.affinities_summary_csv(), index=False)
    mat = res.pivot_table(index="ligando", columns="diana", values="afinidad_media", aggfunc="mean")
    mat.to_csv(P.layout.affinity_matrix_csv())

    nombre_seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", P.cfg["name"])
    xlsx_path = P.layout.affinities_xlsx(nombre_seguro)
    try:
        with pd.ExcelWriter(xlsx_path) as xw:
            res.to_excel(xw, sheet_name="Resumen", index=False)
            mat.to_excel(xw, sheet_name="Matriz")
            df.drop(columns=["archivo"]).to_excel(xw, sheet_name="Corridas", index=False)
            rd = P.layout.redocking_summary_csv()
            if os.path.exists(rd):
                pd.read_csv(rd).to_excel(xw, sheet_name="Redocking", index=False)
            for hoja, f in (("Consenso", P.layout.consensus_summary_csv()),
                            ("Consenso poses", P.layout.consensus_poses_csv()),
                            ("Consenso Kendall", P.layout.consensus_tau_csv())):
                if os.path.exists(f):
                    pd.read_csv(f).to_excel(xw, sheet_name=hoja, index=False)
        xlsx = True
    except Exception:  # noqa: BLE001  (openpyxl no instalado)
        xlsx = False

    # mejor pose de cada par → BestPoses/<diana>__<ligando>.pdbqt
    mejores = df.loc[df.groupby(["diana", "ligando"])["afinidad"].idxmin()]
    for r in mejores.itertuples():
        open(P.layout.best_pose_pdbqt(r.diana, r.ligando), "w").write(model1(r.archivo))

    for diana, g in res.groupby("diana", sort=False):
        log(f"\n  ▸ {diana}")
        log(f"    {'ligando':34s} {'ΔG media':>9s} {'DE':>5s} {'mejor':>7s} {'LE':>5s} {'Δ ctrl':>7s}")
        for r in g.itertuples():
            de = 0 if r.afinidad_de != r.afinidad_de else r.afinidad_de
            dc = "" if r.delta_vs_control != r.delta_vs_control else f"{r.delta_vs_control:+7.2f}"
            log(f"    {r.ligando[:34]:34s} {r.afinidad_media:9.2f} {de:5.2f} {r.mejor:7.2f} {r.LE:5.2f} {dc:>7s}"
                + ("  ◆ control" if r.tipo == "control" else ""))
    log("\n  Archivos:")
    log("    05_Analysis/affinities_summary.csv · affinity_matrix.csv · affinities_runs.csv"
        + (f" · {os.path.basename(xlsx_path)}" if xlsx else ""))
    log(f"    04_Docking/BestPoses/  ({len(mejores)} poses)")
    log("  (Δ ctrl negativo = el ligando supera al control en afinidad predicha)")
    return 0
