"""El aviso de 'terminó de inmediato' debe mostrar los ✘ de pasos tempranos,
no sólo las últimas líneas del log (caso real: 3OG7 en macOS)."""
from axd.runner import resumen_problemas

LOG = """\
━━ 2 · Receptores y cajas de docking ━━━━━━━━━━
  ▸ 3OG7
    automático → cadena A, docking ciego (no hay ligando co-cristalizado)
    ✘ prepare_receptor falló (ver 04_Docking/logs/prep_receptor_3OG7.log)
  Receptores: 0/1 listos
━━ 3 · Ligandos ━━━━━━━━━━
  Ligandos: 1/1 listos
━━ 5 · Docking (matriz ligandos × dianas) ━━━━━━━━━━
  ✘ 3OG7: falta receptor o caja (corre 'receptores'); se omite
""".splitlines(keepends=True)


def test_incluye_fallo_temprano_con_su_paso_y_diana():
    texto = "".join(resumen_problemas(LOG))
    assert "2 · Receptores y cajas de docking" in texto
    assert "▸ 3OG7" in texto
    assert "prepare_receptor falló" in texto
    assert "5 · Docking" in texto and "falta receptor o caja" in texto
    assert texto.index("prepare_receptor") < texto.index("falta receptor")


def test_sin_errores_no_devuelve_nada():
    assert resumen_problemas(["━━ 1 · Descarga ━━\n", "  ✔ todo bien\n"]) == []
