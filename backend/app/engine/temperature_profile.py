from __future__ import annotations

from dataclasses import dataclass, asdict

from backend.app.thermo.engine import evaluate_state, solve_temperature_for_enthalpy
from .simulator import HXSimulationInput, HXSimulationResult


@dataclass
class TemperatureProfile:
    points: list[dict]
    minimum_approach_c: float

    def as_dict(self) -> dict:
        return asdict(self)


def build_temperature_profile(
    inp: HXSimulationInput,
    result: HXSimulationResult,
    segments: int = 20,
) -> TemperatureProfile:
    segments = max(4, min(100, int(segments)))

    h_hot_in = result.hot_in_thermo["specific_enthalpy_j_kg"]
    h_hot_out = result.hot_out_thermo["specific_enthalpy_j_kg"]
    h_cold_in = result.cold_in_thermo["specific_enthalpy_j_kg"]
    h_cold_out = result.cold_out_thermo["specific_enthalpy_j_kg"]

    counter = inp.flow_arrangement.lower().startswith("counter")

    points = []

    for i in range(segments + 1):
        x = i / segments

        h_hot = h_hot_in + x * (h_hot_out - h_hot_in)

        if counter:
            # At hot inlet end, cold stream is at its outlet state.
            h_cold = h_cold_out + x * (h_cold_in - h_cold_out)
        else:
            h_cold = h_cold_in + x * (h_cold_out - h_cold_in)

        t_hot = solve_temperature_for_enthalpy(
            h_hot,
            inp.hot.fluid,
            inp.hot.pressure_bar,
            inp.thermo_package,
            inp.hot.composition,
            inp.hot.composition_basis,
            inp.interaction_parameters,
        )

        t_cold = solve_temperature_for_enthalpy(
            h_cold,
            inp.cold.fluid,
            inp.cold.pressure_bar,
            inp.thermo_package,
            inp.cold.composition,
            inp.cold.composition_basis,
            inp.interaction_parameters,
        )

        points.append(
            {
                "fraction": x,
                "hot_temperature_c": t_hot,
                "cold_temperature_c": t_cold,
                "approach_c": t_hot - t_cold,
            }
        )

    minimum = min(p["approach_c"] for p in points)

    return TemperatureProfile(
        points=points,
        minimum_approach_c=minimum,
    )
