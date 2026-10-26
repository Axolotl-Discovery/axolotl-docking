"""Inspección de estructuras PDB y heurísticas de dominio compartidas entre los asistentes
interactivos (axd/wizards) y el pipeline (pipeline/receptors.py). Sin dependencias externas."""
from collections import OrderedDict

WATERS = {"HOH", "WAT", "DOD", "H2O"}
ADDITIVES = {"SO4", "PO4", "GOL", "EDO", "PEG", "PG4", "ACT", "CL", "NA", "K", "DMS", "FMT", "MPD", "BME",
             "TRS", "EPE", "IOD", "NO3", "IMD", "CIT", "MES", "ACY", "1PE", "P6G", "BR"}
COFACTOR_CODES = {"HEM", "HEC", "HEA", "FAD", "FMN", "NAD", "NAI", "NAP", "NDP", "SAM", "SAH", "PLP", "COA", "TPP",
                  "SF4", "FES", "F3S", "CLA", "BCL"}
METAL_CODES = {"ZN", "MG", "MN", "FE", "FE2", "CU", "CU1", "CO", "NI", "CA"}
UNIPROT_RE = r"[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}"


def inspect_pdb(path):
    """Devuelve (cadenas{cadena: n_residuos}, heteros[(resname, cadena, resseq, n_atomos)])."""
    chains, het = OrderedDict(), OrderedDict()
    if not path.lower().endswith(".pdb"):
        return chains, []
    seen = set()
    with open(path, errors="ignore") as fh:
        for l in fh:
            if l.startswith("ENDMDL"):
                break
            if l[:6] == "ATOM  ":
                k = (l[21], l[22:27])
                if k not in seen:
                    seen.add(k); chains[l[21]] = chains.get(l[21], 0) + 1
            elif l[:6] == "HETATM":
                rn = l[17:20].strip()
                if rn in WATERS:
                    continue
                k = (rn, l[21], l[22:26].strip())
                het[k] = het.get(k, 0) + 1
    return chains, [(k[0], k[1], k[2], n) for k, n in het.items()]


def auto_decision(het, chains):
    """Elige ligando de referencia (el más grande que no sea aditivo/cofactor/ion) y su cadena.
    Devuelve (ref 'RES:CAD' o None, cadena)."""
    cand = sorted([h for h in het if h[0] not in ADDITIVES | COFACTOR_CODES | METAL_CODES and h[3] >= 8],
                  key=lambda h: -h[3])
    if cand:
        return f"{cand[0][0]}:{cand[0][1]}", cand[0][1]
    return None, (list(chains)[0] if chains else "")
