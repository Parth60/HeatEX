from __future__ import annotations

from copy import deepcopy
from itertools import product

from app.models import SimulationRequest
from app.engine.shell_tube import simulate


def optimise(req: SimulationRequest, objective: str = "balanced") -> dict:
    """Bounded discrete search suitable for the first working build.

    Production version can replace this with scipy differential_evolution / NSGA-II,
    while keeping the API response contract unchanged.
    """
    candidates = []
    ods = [15.88, 19.05, 25.4]
    passes = [1, 2, 4]
    baffles = sorted(set([max(2, req.geometry.baffle_count - 4), req.geometry.baffle_count, min(30, req.geometry.baffle_count + 4)]))
    tube_counts = sorted(set([max(80, req.geometry.tube_count - 120), req.geometry.tube_count, min(2000, req.geometry.tube_count + 120)]))

    for od, p, b, nt in product(ods, passes, baffles, tube_counts):
        trial = deepcopy(req)
        trial.geometry.tube_od_mm = od
        trial.geometry.tube_id_mm = od * 0.82
        trial.geometry.tube_pitch_mm = max(od * 1.25, od + 3)
        trial.geometry.tube_passes = p
        trial.geometry.baffle_count = b
        trial.geometry.tube_count = nt
        try:
            res = simulate(trial)
        except Exception:
            continue
        if res.tube_dp_kpa > req.tube_dp_limit_kpa or res.shell_dp_kpa > req.shell_dp_limit_kpa:
            continue
        if res.area_margin_pct < 5:
            continue

        if objective == "minimum-area":
            metric = res.installed_area_m2
        elif objective == "minimum-pressure-drop":
            metric = res.tube_dp_kpa + res.shell_dp_kpa
        else:
            metric = res.installed_area_m2 + 0.8 * (res.tube_dp_kpa + res.shell_dp_kpa) - 0.15 * res.screening_score
        candidates.append((metric, trial, res))

    if not candidates:
        return {"found": False, "message": "No candidate satisfied the current screening constraints."}
    candidates.sort(key=lambda x: x[0])
    metric, best_req, best_res = candidates[0]
    return {
        "found": True,
        "objective": objective,
        "metric": metric,
        "request": best_req.model_dump(mode="json"),
        "result": best_res.model_dump(mode="json"),
        "evaluated_candidates": len(candidates),
    }
