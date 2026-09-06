from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

from .geometry import ShellTubeGeometry
from .tube_side import calculate_tube_side
from .bell_delaware import calculate_bell_delaware, BellDelawareInputs
from .heat_transfer import lmtd, overall_u_outside_basis, required_area_m2
from .thermo_provider import get_properties


@dataclass
class StreamInput:
    fluid: str
    mass_flow_kg_s: float
    inlet_temperature_c: float
    pressure_bar: float


@dataclass
class HXSimulationInput:
    hot: StreamInput
    cold: StreamInput
    geometry: ShellTubeGeometry

    front_head: str = "B"
    shell_type: str = "E"
    rear_head: str = "M"

    thermo_package: str = "Fallback database"
    flow_arrangement: str = "Counter-current"

    hot_outlet_target_c: float = 70.0

    tube_wall_k_w_mk: float = 16.0
    tube_fouling_m2k_w: float = 0.0002
    shell_fouling_m2k_w: float = 0.0002

    allowable_tube_dp_kpa: float = 70.0
    allowable_shell_dp_kpa: float = 50.0

    bell_clearances: Optional[BellDelawareInputs] = None


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


def simulate_shell_and_tube(inp: HXSimulationInput) -> HXSimulationResult:
    g = inp.geometry
    g.validate()

    if inp.hot.mass_flow_kg_s <= 0 or inp.cold.mass_flow_kg_s <= 0:
        raise ValueError("Mass flow rates must be positive.")

    if inp.hot_outlet_target_c >= inp.hot.inlet_temperature_c:
        raise ValueError("Hot outlet target must be below hot inlet temperature.")

    hot_mean = 0.5 * (inp.hot.inlet_temperature_c + inp.hot_outlet_target_c)
    cold_guess = inp.cold.inlet_temperature_c + 20.0
    cold_mean = 0.5 * (inp.cold.inlet_temperature_c + cold_guess)

    hot_p = get_properties(
        inp.hot.fluid,
        hot_mean,
        inp.hot.pressure_bar,
        inp.thermo_package,
    )
    cold_p = get_properties(
        inp.cold.fluid,
        cold_mean,
        inp.cold.pressure_bar,
        inp.thermo_package,
    )

    duty_w = (
        inp.hot.mass_flow_kg_s
        * hot_p.cp_j_kgk
        * (inp.hot.inlet_temperature_c - inp.hot_outlet_target_c)
    )

    cold_out = (
        inp.cold.inlet_temperature_c
        + duty_w / (inp.cold.mass_flow_kg_s * cold_p.cp_j_kgk)
    )

    # Re-evaluate the cold properties at the final mean temperature.
    cold_mean_final = 0.5 * (inp.cold.inlet_temperature_c + cold_out)
    cold_p = get_properties(
        inp.cold.fluid,
        cold_mean_final,
        inp.cold.pressure_bar,
        inp.thermo_package,
    )

    # Recalculate the outlet once using the updated Cp.
    cold_out = (
        inp.cold.inlet_temperature_c
        + duty_w / (inp.cold.mass_flow_kg_s * cold_p.cp_j_kgk)
    )

    tube = calculate_tube_side(
        mass_flow_kg_s=inp.hot.mass_flow_kg_s,
        rho_kg_m3=hot_p.rho_kg_m3,
        mu_pa_s=hot_p.mu_pa_s,
        cp_j_kgk=hot_p.cp_j_kgk,
        k_w_mk=hot_p.k_w_mk,
        geometry=g,
    )

    shell = calculate_bell_delaware(
        mass_flow_kg_s=inp.cold.mass_flow_kg_s,
        rho_kg_m3=cold_p.rho_kg_m3,
        mu_pa_s=cold_p.mu_pa_s,
        cp_j_kgk=cold_p.cp_j_kgk,
        k_w_mk=cold_p.k_w_mk,
        geometry=g,
        clearances=inp.bell_clearances,
    )

    counter = inp.flow_arrangement.lower().startswith("counter")
    lmtd_value = lmtd(
        hot_in_c=inp.hot.inlet_temperature_c,
        hot_out_c=inp.hot_outlet_target_c,
        cold_in_c=inp.cold.inlet_temperature_c,
        cold_out_c=cold_out,
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

    if cold_out >= inp.hot_outlet_target_c and counter is False:
        warnings.append("Co-current terminal temperatures are approaching a temperature cross.")

    warnings.extend(shell.notes)

    return HXSimulationResult(
        tema_code=f"{inp.front_head}{inp.shell_type}{inp.rear_head}",
        duty_kw=duty_w / 1000.0,
        hot_outlet_c=inp.hot_outlet_target_c,
        cold_outlet_c=cold_out,
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
        hot_property_source=hot_p.source,
        cold_property_source=cold_p.source,
        warnings=warnings,
    )
