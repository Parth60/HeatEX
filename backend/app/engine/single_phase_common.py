from __future__ import annotations

from dataclasses import dataclass, asdict
from backend.app.thermo.engine import evaluate_state, solve_temperature_for_enthalpy


@dataclass
class ServiceStream:
    fluid: str
    mass_flow_kg_s: float
    inlet_temperature_c: float
    pressure_bar: float
    composition: dict[str, float] | None = None
    composition_basis: str = "mole"


@dataclass
class EnergyBalanceResult:
    duty_w: float
    hot_outlet_c: float
    cold_outlet_c: float
    hot_mean_state: dict
    cold_mean_state: dict
    warnings: list[str]


def state(
    stream: ServiceStream,
    temperature_c: float,
    package: str,
    interaction_parameters: dict | None = None,
):
    return evaluate_state(
        fluid=stream.fluid,
        temperature_c=temperature_c,
        pressure_bar=stream.pressure_bar,
        package=package,
        composition=stream.composition,
        composition_basis=stream.composition_basis,
        interaction_parameters=interaction_parameters,
    )


def solve_energy_balance(
    hot: ServiceStream,
    cold: ServiceStream,
    hot_outlet_target_c: float,
    package: str,
    interaction_parameters: dict | None = None,
) -> EnergyBalanceResult:
    if hot.mass_flow_kg_s <= 0 or cold.mass_flow_kg_s <= 0:
        raise ValueError("Mass flow rates must be positive.")
    if hot_outlet_target_c >= hot.inlet_temperature_c:
        raise ValueError("Hot outlet target must be below hot inlet temperature.")

    h_hi = state(hot, hot.inlet_temperature_c, package, interaction_parameters)
    h_ho = state(hot, hot_outlet_target_c, package, interaction_parameters)

    specific_drop = h_hi.specific_enthalpy_j_kg - h_ho.specific_enthalpy_j_kg
    if specific_drop <= 0:
        raise ValueError("Hot-side enthalpy drop must be positive.")

    duty_w = hot.mass_flow_kg_s * specific_drop

    h_ci = state(cold, cold.inlet_temperature_c, package, interaction_parameters)
    target_h_co = h_ci.specific_enthalpy_j_kg + duty_w / cold.mass_flow_kg_s

    cold_outlet_c = solve_temperature_for_enthalpy(
        target_h_j_kg=target_h_co,
        fluid=cold.fluid,
        pressure_bar=cold.pressure_bar,
        package=package,
        composition=cold.composition,
        composition_basis=cold.composition_basis,
        interaction_parameters=interaction_parameters,
    )

    hot_mean_t = 0.5 * (hot.inlet_temperature_c + hot_outlet_target_c)
    cold_mean_t = 0.5 * (cold.inlet_temperature_c + cold_outlet_c)

    hot_mean = state(hot, hot_mean_t, package, interaction_parameters)
    cold_mean = state(cold, cold_mean_t, package, interaction_parameters)

    warnings = []
    for label, st in [("Hot mean", hot_mean), ("Cold mean", cold_mean)]:
        for w in st.warnings:
            warnings.append(f"{label}: {w}")

    return EnergyBalanceResult(
        duty_w=duty_w,
        hot_outlet_c=hot_outlet_target_c,
        cold_outlet_c=cold_outlet_c,
        hot_mean_state=hot_mean.as_dict(),
        cold_mean_state=cold_mean.as_dict(),
        warnings=list(dict.fromkeys(warnings)),
    )
