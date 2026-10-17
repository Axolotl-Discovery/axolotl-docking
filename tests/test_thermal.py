"""axd/thermal.py: ThermalGuard — lectura de sensores (parcheada) + decisión con histéresis.
No depende de sensores reales: read_cpu_temp_c/read_gpu_temps_c se monkeypatchean."""
import axd.thermal as T
from axd.thermal import Decision
from axd.tuning import ThermalPolicy


def _guard(monkeypatch, cpu=None, gpu=(), **policy_kwargs):
    monkeypatch.setattr(T, "read_cpu_temp_c", lambda: cpu)
    monkeypatch.setattr(T, "read_gpu_temps_c", lambda: list(gpu))
    pol = ThermalPolicy(**policy_kwargs)
    return T.ThermalGuard(pol)


def test_run_cuando_todo_esta_frio(monkeypatch):
    g = _guard(monkeypatch, cpu=40, gpu=[35])
    r = g.read()
    assert r.decision == Decision.RUN and r.reason == ""


def test_throttle_entre_throttle_y_pause(monkeypatch):
    g = _guard(monkeypatch, cpu=87, gpu=[50])  # entre cpu_throttle_c(85) y cpu_pause_c(92)
    r = g.read()
    assert r.decision == Decision.THROTTLE
    assert "87" in r.reason or "CPU 87" in r.reason


def test_pause_por_encima_del_umbral(monkeypatch):
    g = _guard(monkeypatch, cpu=95, gpu=[50])
    r = g.read()
    assert r.decision == Decision.PAUSE


def test_gpu_tambien_dispara_pause(monkeypatch):
    g = _guard(monkeypatch, cpu=40, gpu=[91])  # gpu_pause_c=90
    assert g.read().decision == Decision.PAUSE


def test_histeresis_se_queda_pausado_hasta_el_umbral_de_reanudar(monkeypatch):
    monkeypatch.setattr(T, "read_gpu_temps_c", lambda: [])
    temps = iter([95, 80, 80, 74])  # pause -> aún caliente (no reanuda a 80, resume_c=75) -> reanuda a 74
    monkeypatch.setattr(T, "read_cpu_temp_c", lambda: next(temps))
    g = T.ThermalGuard(ThermalPolicy())
    assert g.read().decision == Decision.PAUSE   # 95
    assert g.read().decision == Decision.PAUSE   # 80: sigue por encima de cpu_resume_c (75) -> sticky
    assert g.read().decision == Decision.PAUSE   # 80 otra vez
    assert g.read().decision == Decision.RUN     # 74 <= 75 -> reanuda


def test_desactivado_siempre_run(monkeypatch):
    g = _guard(monkeypatch, cpu=120, gpu=[99], enabled=False)
    r = g.read()
    assert r.decision == Decision.RUN
    assert "desactivado" in r.reason


def test_sin_sensores_disponibles_es_run(monkeypatch):
    g = _guard(monkeypatch, cpu=None, gpu=[])  # ningún sensor disponible
    r = g.read()
    assert r.decision == Decision.RUN
    assert r.cpu_c is None and r.gpu_c is None


def test_sensor_available_refleja_la_lectura(monkeypatch):
    monkeypatch.setattr(T, "read_cpu_temp_c", lambda: None)
    monkeypatch.setattr(T, "read_gpu_temps_c", lambda: [])
    assert T.cpu_sensor_available() is False and T.gpu_sensor_available() is False
    monkeypatch.setattr(T, "read_cpu_temp_c", lambda: 42.0)
    monkeypatch.setattr(T, "read_gpu_temps_c", lambda: [55.0])
    assert T.cpu_sensor_available() is True and T.gpu_sensor_available() is True
