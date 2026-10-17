"""Utilidades compartidas entre pruebas que no son fixtures de pytest (se importan
directamente, a diferencia de conftest.py)."""


def linea_pdb(serial, nombre_atomo, resname, cadena, resnum, x, y, z, elemento=None, tipo="ATOM  "):
    """Construye una línea PDB campo por campo, por ÍNDICE (no por un f-string "parecido"
    cuyo desalineamiento rompe el parseo con errores crípticos de ValueError al convertir
    columnas a float). Columnas según el estándar PDB, 0-indexadas como el resto del código:
    record[0:6] serial[6:11] atom[12:16] resname[17:20] chain[21] resSeq[22:26]
    x[30:38] y[38:46] z[46:54] occ[54:60] temp[60:66] element[76:78]."""
    elemento = elemento or nombre_atomo.strip()[:1]
    buf = [" "] * 80
    buf[0:6] = list(f"{tipo:<6s}")
    buf[6:11] = list(f"{serial:>5d}")
    buf[12:16] = list(f"{nombre_atomo:<4s}")
    buf[17:20] = list(f"{resname:>3s}")
    buf[21] = cadena
    buf[22:26] = list(f"{resnum:>4d}")
    buf[30:38] = list(f"{x:8.3f}")
    buf[38:46] = list(f"{y:8.3f}")
    buf[46:54] = list(f"{z:8.3f}")
    buf[54:60] = list(f"{1.0:6.2f}")
    buf[60:66] = list(f"{0.0:6.2f}")
    buf[76:78] = list(f"{elemento:>2s}")
    l = "".join(buf).rstrip("\n") + "\n"
    assert l[21] == cadena, repr(l)
    assert l[22:26] == f"{resnum:>4d}", repr(l)
    assert abs(float(l[30:38]) - x) < 1e-6, repr(l)
    assert abs(float(l[38:46]) - y) < 1e-6, repr(l)
    assert abs(float(l[46:54]) - z) < 1e-6, repr(l)
    return l
