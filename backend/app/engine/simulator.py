from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from .geometry import ShellTubeGeometry
from .tube_side import calculate_tube_side
from .bell_delaware import calculate_bell_delaware, BellDelawareInputs
from .heat_transfer import lmtd, overall_u_outside_basis, required_area_m2

from backend.app.thermo.engine import (
    evaluate_state,
    solve_temperature_for_enthalpy,
)


@dataclass
class StreamInput:
    fluid: str
    mass_flow_kg_s: float
    inlet_temperature_c: float
    pressure_bar: float
    composition: dict[str, float] | None = None
    composition_basis: str = "mole"


@dataclass
class HXSimulationInput:
    hot: StreamInput
    cold: StreamInput
    geometry: ShellTubeGeometry

    front_head: str = "B"
    shell_type: str = "E"
    rear_head: str = "M"

    thermo_package: str = "Ideal mixture"
    flow_arrangement: str = "Counter-current"

    hot_outlet_target_c: float = 70.0

    tube_wall_k_w_mk: float = 16.0
    tube_fouling_m2k_w: float = 0.0002
    shell_fouling_m2k_w: float = 0.0002

    allowable_tube_dp_kpa: float = 70.0
    allowable_shell_dp_kpa: float = 50.0

    bell_clearances: Optional[BellDelawareInputs] = None

    interaction_parameters: dict | None = None


@dataclass
class HXSimulationResult:
    tema_code: str

    duty_kw: float
    hot_outlet_c: float
    cold_outlet_c: float

    lmtd_c: float
    correction_factor: float
    effective_delta_t_c: float

    tube_h_w_m2k: float
    shell_h_w_m2k: float
    overall_u_w_m2k: float

    required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    tube_velocity_m_s: float
    tube_reynolds: float
    tube_prandtl: float
    tube_nusselt: float
    tube_dp_kpa: float

    shell_velocity_m_s: float
    shell_reynolds: float
    shell_prandtl: float
    shell_dp_kpa: float

    j_c: float
    j_l: float
    j_b: float
    j_r: float
    j_s: float

    hot_property_source: str
    cold_property_source: str

    hot_in_thermo: dict
    hot_out_thermo: dict
    cold_in_thermo: dict
    cold_out_thermo: dict

    phase_change_flag: bool
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


SHELL_F_CORRECTION = {
    "E": 0.95,
    "F": 0.87,
    "G": 0.90,
    "H": 0.88,
    "J": 0.91,
    "K": 0.93,
    "X": 0.96,
}


def _state(stream: StreamInput, temperature_c: float, inp: HXSimulationInput):
    return evaluate_state(
        fluid=stream.fluid,
        temperature_c=temperature_c,
        pressure_bar=stream.pressure_bar,
        package=inp.thermo_package,
        composition=stream.composition,
        composition_basis=stream.composition_basis,
        interaction_parameters=inp.interaction_parameters,
    )


def simulate_shell_and_tube(inp: HXSimulationInput) -> HXSimulationResult:
    g = inp.geometry
    g.validate()

    if inp.hot.mass_flow_kg_s <= 0 or inp.cold.mass_flow_kg_s <= 0:
        raise ValueError("Mass flow rates must be positive.")

    if inp.hot_outlet_target_c >= inp.hot.inlet_temperature_c:
        raise ValueError("Hot outlet target must be below hot inlet temperature.")

    # -------------------------------------------------------------
    # Enthalpy-based energy balance
    # -------------------------------------------------------------
    hot_in = _state(inp.hot, inp.hot.inlet_temperature_c, inp)
    hot_out = _state(inp.hot, inp.hot_outlet_target_c, inp)

    specific_hot_drop = (
        hot_in.specific_enthalpy_j_kg
        - hot_out.specific_enthalpy_j_kg
    )

    if specific_hot_drop <= 0:
        raise ValueError(
            "Hot-stream enthalpy did not decrease across the specified temperature interval."
        )

    duty_w = inp.hot.mass_flow_kg_s * specific_hot_drop

    cold_in = _state(inp.cold, inp.cold.inlet_temperature_c, inp)
    target_cold_h = (
        cold_in.specific_enthalpy_j_kg
        + duty_w / inp.cold.mass_flow_kg_s
    )

    cold_out_temperature = solve_temperature_for_enthalpy(
        target_h_j_kg=target_cold_h,
        fluid=inp.cold.fluid,
        pressure_bar=inp.cold.pressure_bar,
        package=inp.thermo_package,
        composition=inp.cold.composition,
        composition_basis=inp.cold.composition_basis,
        interaction_parameters=inp.interaction_parameters,
    )

    cold_out = _state(inp.cold, cold_out_temperature, inp)

    # -------------------------------------------------------------
    # Mean states for single-phase transport correlations
    # -------------------------------------------------------------
    hot_mean_temperature = 0.5 * (
        inp.hot.inlet_temperature_c
        + inp.hot_outlet_target_c
    )
    cold_mean_temperature = 0.5 * (
        inp.cold.inlet_temperature_c
        + cold_out_temperature
    )

    hot_mean = _state(inp.hot, hot_mean_temperature, inp)
    cold_mean = _state(inp.cold, cold_mean_temperature, inp)

    tube = calculate_tube_side(
        mass_flow_kg_s=inp.hot.mass_flow_kg_s,
        rho_kg_m3=hot_mean.density_kg_m3,
        mu_pa_s=hot_mean.viscosity_pa_s,
        cp_j_kgk=hot_mean.cp_j_kgk,
        k_w_mk=hot_mean.thermal_conductivity_w_mk,
        geometry=g,
    )

    shell = calculate_bell_delaware(
        mass_flow_kg_s=inp.cold.mass_flow_kg_s,
        rho_kg_m3=cold_mean.density_kg_m3,
        mu_pa_s=cold_mean.viscosity_pa_s,
        cp_j_kgk=cold_mean.cp_j_kgk,
        k_w_mk=cold_mean.thermal_conductivity_w_mk,
        geometry=g,
        clearances=inp.bell_clearances,
    )

    counter = inp.flow_arrangement.lower().startswith("counter")

    lmtd_value = lmtd(
        hot_in_c=inp.hot.inlet_temperature_c,
        hot_out_c=inp.hot_outlet_target_c,
        cold_in_c=inp.cold.inlet_temperature_c,
        cold_out_c=cold_out_temperature,
        counter_current=counter,
    )

    correction = SHELL_F_CORRECTION.get(inp.shell_type, 0.90)

    uo = overall_u_outside_basis(
        hi_w_m2k=tube.h_w_m2k,
        ho_w_m2k=shell.corrected_h_w_m2k,
        tube_id_m=g.tube_id_m,
        tube_od_m=g.tube_od_m,
        tube_k_w_mk=inp.tube_wall_k_w_mk,
        rf_inside_m2k_w=inp.tube_fouling_m2k_w,
        rf_outside_m2k_w=inp.shell_fouling_m2k_w,
    )

    a_req = required_area_m2(
        duty_w=duty_w,
        u_w_m2k=uo,
        lmtd_k=lmtd_value,
        correction_factor=correction,
    )

    a_inst = g.installed_area_m2
    margin = 100.0 * (a_inst / a_req - 1.0)

    warnings: list[str] = []

    for state_name, state in (
        ("hot inlet", hot_in),
        ("hot outlet", hot_out),
        ("cold inlet", cold_in),
        ("cold outlet", cold_out),
    ):
        for warning in state.warnings:
            tagged = f"{state_name}: {warning}"
            if tagged not in warnings:
                warnings.append(tagged)

    phase_change_flag = (
        hot_in.phase != hot_out.phase
        or cold_in.phase != cold_out.phase
        or "Two-phase" in hot_in.phase
        or "Two-phase" in hot_out.phase
        or "Two-phase" in cold_in.phase
        or "Two-phase" in cold_out.phase
    )

    if phase_change_flag:
        warnings.append(
            "Phase-boundary change detected. v0.5 uses enthalpy-based sensible "
            "stream calculations but does not yet apply rigorous latent-heat/two-phase "
            "heat-transfer correlations. Treat this case as diagnostic only."
        )

    if tube.pressure_drop_kpa > inp.allowable_tube_dp_kpa:
        warnings.append(
            f"Tube-side ΔP {tube.pressure_drop_kpa:.1f} kPa exceeds "
            f"allowable {inp.allowable_tube_dp_kpa:.1f} kPa."
        )

    if shell.shell_pressure_drop_kpa > inp.allowable_shell_dp_kpa:
        warnings.append(
            f"Shell-side ΔP {shell.shell_pressure_drop_kpa:.1f} kPa exceeds "
            f"allowable {inp.allowable_shell_dp_kpa:.1f} kPa."
        )

    if margin < 0:
        warnings.append(
            f"Installed area is {abs(margin):.1f}% below calculated required area."
        )

    if tube.velocity_m_s < 0.5:
        warnings.append("Tube-side velocity is low; fouling risk may increase.")
    elif tube.velocity_m_s > 3.0:
        warnings.append("Tube-side velocity is high; review erosion and pressure drop.")

    warnings.extend(shell.notes)

    # De-duplicate while preserving order.
    warnings = list(dict.fromkeys(warnings))

    return HXSimulationResult(
        tema_code=f"{inp.front_head}{inp.shell_type}{inp.rear_head}",
        duty_kw=duty_w / 1000.0,
        hot_outlet_c=inp.hot_outlet_target_c,
        cold_outlet_c=cold_out_temperature,
        lmtd_c=lmtd_value,
        correction_factor=correction,
        effective_delta_t_c=lmtd_value * correction,
        tube_h_w_m2k=tube.h_w_m2k,
        shell_h_w_m2k=shell.corrected_h_w_m2k,
        overall_u_w_m2k=uo,
        required_area_m2=a_req,
        installed_area_m2=a_inst,
        area_margin_percent=margin,
        tube_velocity_m_s=tube.velocity_m_s,
        tube_reynolds=tube.reynolds,
        tube_prandtl=tube.prandtl,
        tube_nusselt=tube.nusselt,
        tube_dp_kpa=tube.pressure_drop_kpa,
        shell_velocity_m_s=shell.shell_velocity_m_s,
        shell_reynolds=shell.reynolds,
        shell_prandtl=shell.prandtl,
        shell_dp_kpa=shell.shell_pressure_drop_kpa,
        j_c=shell.j_c,
        j_l=shell.j_l,
        j_b=shell.j_b,
        j_r=shell.j_r,
        j_s=shell.j_s,
        hot_property_source=hot_mean.property_source,
        cold_property_source=cold_mean.property_source,
        hot_in_thermo=hot_in.as_dict(),
        hot_out_thermo=hot_out.as_dict(),
        cold_in_thermo=cold_in.as_dict(),
        cold_out_thermo=cold_out.as_dict(),
        phase_change_flag=phase_change_flag,
        warnings=warnings,
    )
