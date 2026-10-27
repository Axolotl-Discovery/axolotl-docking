"""Motor GPU (Vina-GPU 2.1): selección de dispositivo, variantes por tamaño de caja,
comando, ejecución con un binario falso y no mezclar motores en un proyecto.

No necesita GPU ni Vina-GPU real: el binario es un script que imita su salida."""
import io
import os
import stat
import sys
from contextlib import redirect_stdout

import pytest

import common
import docking
import vina_gpu
from axd import config as C
from axd import device as DEV
from axd.hardware import Gpu

CAJA = {"center": [1.0, 2.0, 3.0], "size": [22.0, 22.0, 22.0]}
PARAMS = {"num_modes": 9, "energy_range": 3, "exhaustiveness": 8, "seeds": [42]}

FAKE = """#!{py}
import sys
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
open("args.txt", "w").write(" ".join(sys.argv[1:]))
with open(args["--out"], "w") as fh:
    fh.write("MODEL 1\\nREMARK VINA RESULT:      -8.2      0.000      0.000\\nTORSDOF 0\\nENDMDL\\n")
print("Using random seed: " + args["--seed"])
"""


def _instalar_falso(base, variantes=("small",)):
    for var in variantes:
        d = os.path.join(base, var)
        os.makedirs(d, exist_ok=True)
        exe = os.path.join(d, DEV.EXE)
        with open(exe, "w") as fh:
            fh.write(FAKE.format(py=sys.executable))
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        for k in DEV.KERNELS:
            open(os.path.join(d, k), "wb").write(b"bin")


@pytest.fixture
def global_gpu(tmp_path):
    g0 = C.load_global()
    base = str(tmp_path / "vina-gpu")
    g = dict(g0, **{DEV.DEVICE_KEY: DEV.GPU, DEV.VINA_GPU_DIR_KEY: base})
    C.save_global(g)
    yield base
    C.save_global(g0)


# ---------------------------------------------------------------- device
def test_variante_por_tamano_de_caja():
    v = {"small": ("a", "a"), "large": ("b", "b")}
    assert DEV.variant_for_box([22, 22, 22], v) == "small"
    assert DEV.variant_for_box([22, 45, 22], v) == "large"
    assert DEV.variant_for_box([80, 20, 20], v) is None
    assert DEV.variant_for_box([22, 22, 22], {"large": ("b", "b")}) == "large"


def test_solo_cuentan_instalaciones_completas(global_gpu):
    _instalar_falso(global_gpu, ("small",))
    os.makedirs(os.path.join(global_gpu, "large"))  # incompleta: sin binario ni kernels
    assert set(DEV.vina_gpu_variants(C.load_global())) == {"small"}


def test_fabricante_cpu():
    assert DEV.cpu_vendor("Intel(R) Core(TM) i7-12700") == "intel"
    assert DEV.cpu_vendor("AMD Ryzen 9 7950X") == "amd"
    assert DEV.cpu_vendor("Apple M2 Pro") == "apple"


def test_soporte_gpu(monkeypatch):
    class HW:
        gpus = []
    monkeypatch.setattr(DEV.platform, "system", lambda: "Linux")
    assert DEV.gpu_support(HW)[0] is False
    HW.gpus = [Gpu(name="Apple M2", vendor="apple")]
    assert DEV.gpu_support(HW)[0] is False
    HW.gpus = [Gpu(name="NVIDIA RTX 4070", vendor="nvidia")]
    ok, _, g = DEV.gpu_support(HW)
    assert ok and g.vendor == "nvidia"
    monkeypatch.setattr(DEV.platform, "system", lambda: "Darwin")
    assert DEV.gpu_support(HW)[0] is False  # no hay Vina-GPU para macOS


# ---------------------------------------------------------------- comando y corrida
def test_comando_vina_gpu():
    cmd = vina_gpu.comando("/x/vina-gpu", "/x", CAJA, 42, dict(PARAMS, gpu_threads=500))
    a = dict(zip(cmd[1::2], cmd[2::2]))
    assert a["--thread"] == "1000"  # Vina-GPU exige ≥ 1000
    assert a["--seed"] == "42" and a["--opencl_binary_path"] == "/x" and a["--size_x"] == "22.0"
    assert "--exhaustiveness" not in cmd


def test_corrida_con_binario_falso(global_gpu, tmp_path):
    _instalar_falso(global_gpu)
    rec, lig = tmp_path / "r.pdbqt", tmp_path / "l.pdbqt"
    rec.write_text("ATOM\n"); lig.write_text("ATOM\n")
    sal = str(tmp_path / "out" / "L_s42.pdbqt")
    e, previa = vina_gpu.correr(DEV.vina_gpu_variants(C.load_global()), str(rec), str(lig), CAJA, sal, 42, PARAMS)
    assert e == -8.2 and previa is False and common.is_complete(sal)
    assert vina_gpu.correr({}, str(rec), str(lig), CAJA, sal, 42, PARAMS) == (-8.2, True)  # reanudable


def test_caja_demasiado_grande(global_gpu, tmp_path):
    _instalar_falso(global_gpu, ("small",))
    buf = io.StringIO()
    with redirect_stdout(buf):
        r = vina_gpu.correr(DEV.vina_gpu_variants(C.load_global()), "r", "l",
                            {"center": [0, 0, 0], "size": [40, 40, 40]}, str(tmp_path / "o.pdbqt"), 1, PARAMS)
    assert r == (None, False) and "40 Å" in buf.getvalue()


# ---------------------------------------------------------------- Motor
@pytest.fixture
def proyecto(tmp_path):
    ruta = str(tmp_path / "p")
    p = C.new_project(ruta, "p")
    p["targets"] = [{"id": "T1", "source": "pdb", "pdb": "3OG7", "chains": "A", "cofactors": [], "box": {"mode": "auto"}}]
    C.save_project(ruta, p)
    return ruta


def test_motor_gpu_no_instalado(global_gpu, proyecto):
    P = common.Project(proyecto)
    m = docking.Motor(P, [])
    assert m.nombre == "vina-gpu"
    with redirect_stdout(io.StringIO()):
        assert m.disponible() is False


def test_motor_gpu_registra_y_va_de_uno_en_uno(global_gpu, proyecto):
    from axd.tuning import ResourcePlan
    _instalar_falso(global_gpu)
    P = common.Project(proyecto)
    m = docking.Motor(P, [])
    assert m.disponible() is True
    assert common.Project(proyecto).cfg["docking"]["motor_usado"] == "vina-gpu"
    rp = m.ajustar_plan(ResourcePlan(max_workers=4, cpu_per_worker=2, cores_used=8, reserved_cores=0))
    assert rp.max_workers == 1


def test_no_mezcla_motores(global_gpu, proyecto):
    _instalar_falso(global_gpu)
    P = common.Project(proyecto)
    P.cfg["docking"]["motor_usado"] = "smina"
    P.save()
    f = P.layout.result_pdbqt("T1", "L1", 42)
    os.makedirs(os.path.dirname(f))
    open(f, "w").write("MODEL 1\nREMARK minimizedAffinity -7.0\nENDMDL\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert docking.Motor(common.Project(proyecto), []).disponible() is False
    assert "no se mezclan motores" in buf.getvalue()
    # el redocking no bloquea: sólo cuentan los resultados de docking
    os.remove(f)
    red = P.layout.redocking_result_pdbqt("T1", 42)
    os.makedirs(os.path.dirname(red), exist_ok=True)
    open(red, "w").write("MODEL 1\nREMARK minimizedAffinity -7.0\nENDMDL\n")
    with redirect_stdout(io.StringIO()):
        assert docking.Motor(common.Project(proyecto), []).disponible() is True
