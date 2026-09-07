from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class SelectionCase:
    duty_kw: float
    hot_viscosity_mpa_s: float
    cold_viscosity_mpa_s: float
    hot_pressure_bar: float
    cold_pressure_bar: float
    phase_change: bool
    solids_or_heavy_fouling: bool
    close_temperature_approach: bool
    cooling_water_available: bool
    compactness_priority: bool


@dataclass
class SelectionCandidate:
    exchanger_type: str
    score: float
    reasons: list[str]
    cautions: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def rank_exchangers(case: SelectionCase) -> list[SelectionCandidate]:
    scores = {
        "Shell & Tube": 70.0,
        "Plate & Frame": 70.0,
        "Double Pipe": 50.0,
        "Air-Cooled": 55.0,
    }
    reasons = {k: [] for k in scores}
    cautions = {k: [] for k in scores}

    max_p = max(case.hot_pressure_bar, case.cold_pressure_bar)
    max_mu = max(case.hot_viscosity_mpa_s, case.cold_viscosity_mpa_s)

    if case.phase_change:
        scores["Shell & Tube"] += 18
        scores["Air-Cooled"] += 8
        scores["Plate & Frame"] += 5
        reasons["Shell & Tube"].append("Strong fit for condenser/reboiler service.")
        cautions["Double Pipe"].append("Phase-change service is possible but usually niche/small-duty.")

    if case.solids_or_heavy_fouling:
        scores["Shell & Tube"] += 15
        scores["Plate & Frame"] -= 18
        scores["Air-Cooled"] -= 5
        reasons["Shell & Tube"].append("Mechanical cleaning and robust geometry suit fouling service.")
        cautions["Plate & Frame"].append("Narrow plate channels can plug or foul.")
    else:
        scores["Plate & Frame"] += 8
        reasons["Plate & Frame"].append("Clean-fluid service suits compact plate channels.")

    if case.close_temperature_approach:
        scores["Plate & Frame"] += 18
        scores["Double Pipe"] += 7
        reasons["Plate & Frame"].append("High U and near-countercurrent flow suit close approaches.")

    if case.compactness_priority:
        scores["Plate & Frame"] += 14
        scores["Shell & Tube"] -= 4
        reasons["Plate & Frame"].append("Very high area density.")
        reasons["Air-Cooled"].append("Avoids cooling-water system but needs plot area.")

    if not case.cooling_water_available:
        scores["Air-Cooled"] += 24
        reasons["Air-Cooled"].append("Does not require a cooling-water loop.")
    else:
        scores["Air-Cooled"] -= 4

    if case.duty_kw < 300:
        scores["Double Pipe"] += 24
        reasons["Double Pipe"].append("Small duty fits simple modular hairpin service.")
    elif case.duty_kw > 5000:
        scores["Double Pipe"] -= 22
        cautions["Double Pipe"].append("Large duty can require excessive hairpins/footprint.")
        scores["Shell & Tube"] += 8

    if max_p > 30:
        scores["Shell & Tube"] += 14
        scores["Plate & Frame"] -= 8
        reasons["Shell & Tube"].append("High-pressure service generally favours robust tubular construction.")
        cautions["Plate & Frame"].append("Pressure capability depends strongly on plate/frame construction.")

    if max_mu > 20:
        scores["Plate & Frame"] += 6
        scores["Air-Cooled"] -= 6
        reasons["Plate & Frame"].append("High shear can help viscous clean liquids.")
        cautions["Air-Cooled"].append("Tube-side viscous flow can produce high pumping losses.")

    if case.phase_change and not case.cooling_water_available:
        scores["Air-Cooled"] += 8

    result = []
    for hx_type, score in scores.items():
        score = max(0.0, min(100.0, score))
        result.append(
            SelectionCandidate(
                exchanger_type=hx_type,
                score=score,
                reasons=reasons[hx_type],
                cautions=cautions[hx_type],
            )
        )

    result.sort(key=lambda x: x.score, reverse=True)
    return result
