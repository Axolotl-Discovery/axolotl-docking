"""Utilidades pequeñas compartidas entre los módulos de axd/wizards."""
import re

EXT_LIGANDO = (".sdf", ".mol", ".mol2", ".pdb", ".smi", ".smiles", ".pdbqt")


def id_unico(base, existentes):
    i, x = 2, base
    while x in existentes:
        x = f"{base}_{i}"; i += 1
    return x


def parece_smiles(t):
    return " " not in t and (bool(re.search(r"[=#()\[\]@/\\]", t)) or bool(re.fullmatch(r"[BCNOSPFIcnosp0-9]+", t)))


def partir_sdf(ruta):
    """Separa un SDF de varias moléculas: [(nombre, bloque)]."""
    txt = open(ruta, errors="ignore").read()
    regs = [r.strip("\n") for r in txt.split("$$$$") if r.strip()]
    return [((r.splitlines()[0].strip() if r.splitlines() else "") or f"mol{i + 1}", r + "\n$$$$\n")
            for i, r in enumerate(regs)]
