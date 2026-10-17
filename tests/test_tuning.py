"""axd/tuning.py: presupuesto de núcleos, confirmación de elección de CPU, plan de
recursos (con y sin el override de Fase 6) y ThermalPolicy."""
from axd import tuning


class HW:
    def __init__(self, usable_cores=1, mem_available_mb=0, physical_cores=None):
        self.usable_cores = usable_cores
        self.mem_available_mb = mem_available_mb
        self.physical_cores = physical_cores if physical_cores is not None else usable_cores


# ---------------------------------------------------------------- core_budget
def test_core_budget_un_solo_nucleo():
    assert tuning.core_budget(1) == 1


def test_core_budget_reserva_al_menos_uno():
    assert tuning.core_budget(4, max_fraction=1.0) == 3  # siempre reserva >= 1 si hay más de 1
    assert tuning.core_budget(16, max_fraction=0.90) == 14  # round(16*0.10)=2 reservados


def test_core_budget_arimetica_exacta():
    # reservado = max(1, round(usable*(1-max_fraction)))
    assert tuning.core_budget(10, 0.90) == 9     # reservado = round(1.0) = 1
    assert tuning.core_budget(20, 0.90) == 18    # reservado = round(2.0) = 2


# ---------------------------------------------------------------- confirm_core_choice
def test_confirm_core_choice_eleccion_razonable_sin_aviso():
    allowed, warning = tuning.confirm_core_choice(4, 16)
    assert allowed == 4 and warning is None


def test_confirm_core_choice_cero_significa_todos_y_limita():
    allowed, warning = tuning.confirm_core_choice(0, 16)
    assert warning is not None and "congelar" in warning
    assert allowed == tuning.core_budget(16, tuning.HARD_MAX_FRACTION)
    assert allowed < 16


def test_confirm_core_choice_pide_casi_todos_tambien_limita():
    # usable=20: hard_cap de near_all = ceil(20*0.95) = 19; pedir 19 (sin llegar a "todos") también avisa.
    allowed, warning = tuning.confirm_core_choice(19, 20)
    assert warning is not None
    assert allowed == tuning.core_budget(20, tuning.HARD_MAX_FRACTION)


def test_confirm_core_choice_un_solo_nucleo_no_falla():
    allowed, warning = tuning.confirm_core_choice(0, 1)
    assert allowed == 1


# ---------------------------------------------------------------- plan()
def test_plan_heuristico_sin_override_reparte_el_budget():
    rp = tuning.plan(HW(usable_cores=16, mem_available_mb=100_000))
    budget = tuning.core_budget(16)
    assert rp.max_workers * rp.cpu_per_worker <= budget
    assert rp.cores_used == rp.max_workers * rp.cpu_per_worker
    assert rp.reserved_cores == 16 - budget


def test_plan_con_override_respeta_nucleos_por_corrida():
    rp = tuning.plan(HW(usable_cores=16, mem_available_mb=100_000), cpu_per_worker=8)
    budget = tuning.core_budget(16)
    assert rp.cpu_per_worker == 8
    assert rp.max_workers == budget // 8


def test_plan_override_mayor_al_budget_se_recorta():
    rp = tuning.plan(HW(usable_cores=8, mem_available_mb=100_000), cpu_per_worker=100)
    budget = tuning.core_budget(8)
    assert rp.cpu_per_worker == budget
    assert rp.max_workers == 1


def test_plan_no_crea_mas_trabajadores_que_trabajo():
    rp = tuning.plan(HW(usable_cores=16, mem_available_mb=100_000), n_jobs=1)
    assert rp.max_workers == 1


def test_plan_limita_por_memoria():
    rp = tuning.plan(HW(usable_cores=16, mem_available_mb=2000))  # poca RAM
    by_mem = max(1, 2000 // tuning._MB_PER_WORKER)
    assert rp.max_workers <= by_mem
    assert any("Memoria disponible" in n for n in rp.notes)


def test_plan_avisa_hyperthreading():
    rp = tuning.plan(HW(usable_cores=16, physical_cores=8, mem_available_mb=100_000))
    assert any("hyperthreading" in n for n in rp.notes)


# ---------------------------------------------------------------- ThermalPolicy
def test_thermal_policy_default():
    pol = tuning.ThermalPolicy.from_config(None)
    assert pol.enabled is True and pol.cpu_pause_c == 92


def test_thermal_policy_roundtrip_parcial():
    pol = tuning.ThermalPolicy.from_config({"cpu_pause_c": 80, "enabled": False})
    assert pol.cpu_pause_c == 80 and pol.enabled is False
    assert pol.cpu_throttle_c == 85  # resto queda en su default
    cfg = pol.to_config()
    assert cfg["cpu_pause_c"] == 80 and cfg["enabled"] is False
    assert set(cfg) == set(tuning.ThermalPolicy().__dataclass_fields__)
