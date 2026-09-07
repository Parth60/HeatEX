from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from backend.app.thermo.components import get_component
from backend.app.thermo.composition import normalize_composition
from backend.app.thermo.mixture_phase import (
    equilibrium_mixture_state,
    effective_latent_heat_j_kg,
)

from .geometry import ShellTubeGeometry
from .heat_transfer import overall_u_outside_basis, required_area_m2, lmtd
from .tube_side import calculate_tube_side
from .bell_delaware import calculate_bell_delaware, BellDelawareInputs
from .two_phase import lockhart_martinelli_screening
from .two_phase_multicomponent import (
    shah_tube_condensation_screening,
    shell_side_condensation_screening,
    multicomponent_boiling_screening,
)


@dataclass
class MulticomponentPhaseHXInput:
    mode: str  # Cooling / condensation OR Heating / boiling

    fractions: dict[str, float]
    composition_basis: str
    package: str
    interaction_parameters: dict | None

    process_mass_flow_kg_s: float
    process_pressure_bar: float
    process_inlet_temperature_c: float
    process_outlet_temperature_c: float

    utility_fluid: str
    utility_mass_flow_kg_s: float
    utility_pressure_bar: float
    utility_inlet_temperature_c: float

    geometry: ShellTubeGeometry

    front_head: str = "B"
    shell_type: str = "E"
    rear_head: str = "M"

    process_on_tube_side: bool = True
    flow_arrangement: str = "Counter-current"

    segments: int = 16

    tube_wall_k_w_mk: float = 16.0
    process_fouling_m2k_w: float = 0.0002
    utility_fouling_m2k_w: float = 0.0002

    wall_subcooling_k: float = 8.0
    boiling_surface_roughness_um: float = 1.0

    allowable_process_dp_kpa: float = 70.0
    allowable_utility_dp_kpa: float = 50.0

    bell_clearances: BellDelawareInputs | None = None


@dataclass
class MulticomponentSegment:
    index: int

    process_in_c: float
    process_out_c: float
    utility_in_c: float
    utility_out_c: float

    beta_in: float
    beta_out: float
    beta_mean: float

    mass_quality_mean: float

    enthalpy_in_kj_kg: float
    enthalpy_out_kj_kg: float
    duty_kw: float

    process_h_w_m2k: float
    utility_h_w_m2k: float
    overall_u_w_m2k: float
    lmtd_c: float
    required_area_m2: float

    process_dp_kpa: float
    utility_dp_kpa: float

    liquid_x_mean: dict[str, float]
    vapour_y_mean: dict[str, float]

    regime: str
    correlation: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class MulticomponentPhaseHXResult:
    mode: str
    tema_code: str

    total_duty_kw: float
    total_required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    utility_outlet_c: float
    process_dp_kpa: float
    utility_dp_kpa: float

    inlet_vapour_fraction: float
    outlet_vapour_fraction: float

    segments: list[MulticomponentSegment]
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _utility_props(fluid: str, temperature_c: float):
    c = get_component(fluid)

    return {
        "cp": c.cp_j_kgk(temperature_c),
        "rho": c.liquid_density_kg_m3(temperature_c),
        "mu": c.viscosity_pa_s(temperature_c),
        "k": c.thermal_conductivity_w_mk(temperature_c),
    }


def _pseudo_critical_pressure_pa(
    composition_mole: dict[str, float],
) -> float:
    pcs = []

    for name, xi in composition_mole.items():
        pc = get_component(name).pc_pa
        if pc is not None:
            pcs.append((xi, pc))

    if not pcs:
        return 5e6

    total_x = sum(xi for xi, _ in pcs)

    return sum(xi * pc for xi, pc in pcs) / max(total_x, 1e-12)


def _blend_dict(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    names = set(a) | set(b)

    values = {
        name: 0.5 * (a.get(name, 0.0) + b.get(name, 0.0))
        for name in names
    }

    total = sum(values.values())

    if total <= 0:
        return {name: 0.0 for name in names}

    return {
        name: value / total
        for name, value in values.items()
    }


def _single_phase_process_h_dp(
    inp: MulticomponentPhaseHXInput,
    state,
    phase: str,
):
    if phase == "Vapour":
        props = state.vapour_properties
    else:
        props = state.liquid_properties

    if inp.process_on_tube_side:
        result = calculate_tube_side(
            mass_flow_kg_s=inp.process_mass_flow_kg_s,
            rho_kg_m3=props["density_kg_m3"],
            mu_pa_s=props["viscosity_pa_s"],
            cp_j_kgk=props["cp_j_kgk"],
            k_w_mk=props["thermal_conductivity_w_mk"],
            geometry=inp.geometry,
        )
        return result.h_w_m2k, result.pressure_drop_kpa

    result = calculate_bell_delaware(
        mass_flow_kg_s=inp.process_mass_flow_kg_s,
        rho_kg_m3=props["density_kg_m3"],
        mu_pa_s=props["viscosity_pa_s"],
        cp_j_kgk=props["cp_j_kgk"],
        k_w_mk=props["thermal_conductivity_w_mk"],
        geometry=inp.geometry,
        clearances=inp.bell_clearances,
    )

    return result.corrected_h_w_m2k, result.shell_pressure_drop_kpa


def simulate_multicomponent_phase_hx(
    inp: MulticomponentPhaseHXInput,
) -> MulticomponentPhaseHXResult:
    inp.geometry.validate()

    mode = inp.mode.strip().lower()

    if mode not in {
        "cooling / condensation",
        "heating / boiling",
    }:
        raise ValueError(
            "Mode must be Cooling / condensation or Heating / boiling."
        )

    if inp.process_mass_flow_kg_s <= 0 or inp.utility_mass_flow_kg_s <= 0:
        raise ValueError("Mass flow rates must be positive.")

    if mode.startswith("cooling"):
        if inp.process_outlet_temperature_c >= inp.process_inlet_temperature_c:
            raise ValueError(
                "Condensation mode requires process outlet below process inlet."
            )
    else:
        if inp.process_outlet_temperature_c <= inp.process_inlet_temperature_c:
            raise ValueError(
                "Boiling mode requires process outlet above process inlet."
            )

    comp_norm = normalize_composition(
        inp.fractions,
        inp.composition_basis,
    )

    # Restrict rigorous phase-change integration to components with real
    # saturation / latent fallback data.
    for name in comp_norm.mole_fractions:
        c = get_component(name)
        if (
            c.tc_k is None
            or c.pc_pa is None
            or c.latent_heat_nbp_j_kg is None
        ):
            raise ValueError(
                f"Multicomponent phase-change mode cannot yet use pseudo-component '{name}'."
            )

    nseg = max(4, min(40, int(inp.segments)))

    states = []

    for i in range(nseg + 1):
        f = i / nseg
        t = (
            inp.process_inlet_temperature_c
            + f
            * (
                inp.process_outlet_temperature_c
                - inp.process_inlet_temperature_c
            )
        )

        states.append(
            equilibrium_mixture_state(
                temperature_c=t,
                pressure_bar=inp.process_pressure_bar,
                fractions=inp.fractions,
                composition_basis=inp.composition_basis,
                package=inp.package,
                interaction_parameters=inp.interaction_parameters,
            )
        )

    # Process duty from equilibrium-mixture enthalpy difference.
    q_segments = []

    for i in range(nseg):
        dh = (
            states[i].overall_enthalpy_j_kg
            - states[i + 1].overall_enthalpy_j_kg
        )

        if mode.startswith("heating"):
            dh = -dh

        q = inp.process_mass_flow_kg_s * dh

        if q < -1e-6:
            raise ValueError(
                "Segment enthalpy progression is inconsistent with selected mode."
            )

        q_segments.append(max(0.0, q))

    total_q = sum(q_segments)

    if total_q <= 0:
        raise ValueError("Integrated multicomponent duty is not positive.")

    # Utility sensible-energy balance.
    utility_c = get_component(inp.utility_fluid)

    mean_guess = (
        inp.utility_inlet_temperature_c
        + (15.0 if mode.startswith("cooling") else -15.0)
    )

    utility_cp = utility_c.cp_j_kgk(mean_guess)

    if mode.startswith("cooling"):
        overall_utility_out = (
            inp.utility_inlet_temperature_c
            + total_q / (inp.utility_mass_flow_kg_s * utility_cp)
        )
    else:
        overall_utility_out = (
            inp.utility_inlet_temperature_c
            - total_q / (inp.utility_mass_flow_kg_s * utility_cp)
        )

    counter = inp.flow_arrangement.lower().startswith("counter")

    if counter:
        utility_coordinate = overall_utility_out
    else:
        utility_coordinate = inp.utility_inlet_temperature_c

    segments: list[MulticomponentSegment] = []

    process_dp_total = 0.0
    utility_dp_total = 0.0

    installed_area = inp.geometry.installed_area_m2
    heat_flux_screen = total_q / max(installed_area, 1e-12)

    for i, q in enumerate(q_segments):
        s0 = states[i]
        s1 = states[i + 1]

        p_t0 = s0.temperature_c
        p_t1 = s1.temperature_c

        beta_molar_mean = 0.5 * (
            s0.vapour_fraction_molar
            + s1.vapour_fraction_molar
        )
        quality_mass = 0.5 * (
            s0.vapour_fraction_mass
            + s1.vapour_fraction_mass
        )

        x_mean = _blend_dict(
            s0.liquid_mole_fractions,
            s1.liquid_mole_fractions,
        )
        y_mean = _blend_dict(
            s0.vapour_mole_fractions,
            s1.vapour_mole_fractions,
        )

        mean_state = equilibrium_mixture_state(
            temperature_c=0.5 * (p_t0 + p_t1),
            pressure_bar=inp.process_pressure_bar,
            fractions=inp.fractions,
            composition_basis=inp.composition_basis,
            package=inp.package,
            interaction_parameters=inp.interaction_parameters,
        )

        # Utility temperature at the two process-coordinate endpoints.
        delta_u = q / (
            inp.utility_mass_flow_kg_s * utility_cp
        )

        if counter:
            if mode.startswith("cooling"):
                u_start = utility_coordinate
                u_end = utility_coordinate - delta_u
            else:
                u_start = utility_coordinate
                u_end = utility_coordinate + delta_u
        else:
            if mode.startswith("cooling"):
                u_start = utility_coordinate
                u_end = utility_coordinate + delta_u
            else:
                u_start = utility_coordinate
                u_end = utility_coordinate - delta_u

        utility_coordinate = u_end

        utility_mean_t = 0.5 * (u_start + u_end)
        up = _utility_props(
            inp.utility_fluid,
            utility_mean_t,
        )

        # Utility coefficient / full-length DP.
        if inp.process_on_tube_side:
            ucalc = calculate_bell_delaware(
                mass_flow_kg_s=inp.utility_mass_flow_kg_s,
                rho_kg_m3=up["rho"],
                mu_pa_s=up["mu"],
                cp_j_kgk=up["cp"],
                k_w_mk=up["k"],
                geometry=inp.geometry,
                clearances=inp.bell_clearances,
            )
            utility_h = ucalc.corrected_h_w_m2k
            utility_dp_full = ucalc.shell_pressure_drop_kpa
        else:
            ucalc = calculate_tube_side(
                mass_flow_kg_s=inp.utility_mass_flow_kg_s,
                rho_kg_m3=up["rho"],
                mu_pa_s=up["mu"],
                cp_j_kgk=up["cp"],
                k_w_mk=up["k"],
                geometry=inp.geometry,
            )
            utility_h = ucalc.h_w_m2k
            utility_dp_full = ucalc.pressure_drop_kpa

        # Process-side h / DP by local phase regime.
        if quality_mass <= 0.01:
            regime = "Liquid"
            process_h, process_dp_full = _single_phase_process_h_dp(
                inp,
                mean_state,
                "Liquid",
            )
            correlation = "Single-phase liquid convection"

        elif quality_mass >= 0.99:
            regime = "Vapour"
            process_h, process_dp_full = _single_phase_process_h_dp(
                inp,
                mean_state,
                "Vapour",
            )
            correlation = "Single-phase vapour convection"

        else:
            regime = "Two-phase"

            liquid_h, liquid_dp_full = _single_phase_process_h_dp(
                inp,
                mean_state,
                "Liquid",
            )

            if mode.startswith("cooling"):
                pseudo_pc = _pseudo_critical_pressure_pa(x_mean)
                pr = inp.process_pressure_bar * 1e5 / pseudo_pc

                if inp.process_on_tube_side:
                    htp = shah_tube_condensation_screening(
                        liquid_only_h_w_m2k=liquid_h,
                        vapour_quality_mass=quality_mass,
                        reduced_pressure=pr,
                    )
                else:
                    lp = mean_state.liquid_properties
                    vp = mean_state.vapour_properties
                    hfg = effective_latent_heat_j_kg(
                        mean_state.temperature_c,
                        inp.process_pressure_bar,
                        mean_state.vapour_mass_fractions,
                    )

                    htp = shell_side_condensation_screening(
                        rho_l_kg_m3=lp["density_kg_m3"],
                        rho_v_kg_m3=vp["density_kg_m3"],
                        mu_l_pa_s=lp["viscosity_pa_s"],
                        k_l_w_mk=lp["thermal_conductivity_w_mk"],
                        latent_heat_j_kg=hfg,
                        tube_od_m=inp.geometry.tube_od_m,
                        wall_subcooling_k=inp.wall_subcooling_k,
                    )
            else:
                pseudo_pc = _pseudo_critical_pressure_pa(x_mean)
                pr = inp.process_pressure_bar * 1e5 / pseudo_pc

                htp = multicomponent_boiling_screening(
                    heat_flux_w_m2=heat_flux_screen,
                    mixture_mw_g_mol=mean_state.liquid_properties[
                        "mixture_mw_g_mol"
                    ],
                    pseudo_reduced_pressure=pr,
                    surface_roughness_um=inp.boiling_surface_roughness_um,
                )

            process_h = htp.h_w_m2k
            correlation = htp.correlation

            if inp.process_on_tube_side:
                lp = mean_state.liquid_properties
                vp = mean_state.vapour_properties

                try:
                    dp_tp = lockhart_martinelli_screening(
                        liquid_only_dp_kpa=max(1e-9, liquid_dp_full),
                        quality=quality_mass,
                        rho_l_kg_m3=lp["density_kg_m3"],
                        rho_v_kg_m3=vp["density_kg_m3"],
                        mu_l_pa_s=lp["viscosity_pa_s"],
                        mu_v_pa_s=vp["viscosity_pa_s"],
                    )
                    process_dp_full = dp_tp.pressure_drop_kpa
                except Exception:
                    process_dp_full = liquid_dp_full
            else:
                process_dp_full = liquid_dp_full

        # Segment fraction used only to distribute full-length screening DP.
        q_fraction = q / total_q
        process_dp_seg = process_dp_full * q_fraction
        utility_dp_seg = utility_dp_full * q_fraction

        process_dp_total += process_dp_seg
        utility_dp_total += utility_dp_seg

        if mode.startswith("cooling"):
            # Process hot, utility cold.
            if counter:
                cold_in = u_end
                cold_out = u_start
            else:
                cold_in = u_start
                cold_out = u_end

            dtlm = lmtd(
                hot_in_c=p_t0,
                hot_out_c=p_t1,
                cold_in_c=cold_in,
                cold_out_c=cold_out,
                counter_current=counter,
            )
        else:
            # Utility hot, process cold.
            if counter:
                hot_in = u_end
                hot_out = u_start
            else:
                hot_in = u_start
                hot_out = u_end

            dtlm = lmtd(
                hot_in_c=hot_in,
                hot_out_c=hot_out,
                cold_in_c=p_t0,
                cold_out_c=p_t1,
                counter_current=counter,
            )

        if inp.process_on_tube_side:
            hi = process_h
            ho = utility_h
            rf_i = inp.process_fouling_m2k_w
            rf_o = inp.utility_fouling_m2k_w
        else:
            hi = utility_h
            ho = process_h
            rf_i = inp.utility_fouling_m2k_w
            rf_o = inp.process_fouling_m2k_w

        uo = overall_u_outside_basis(
            hi_w_m2k=hi,
            ho_w_m2k=ho,
            tube_id_m=inp.geometry.tube_id_m,
            tube_od_m=inp.geometry.tube_od_m,
            tube_k_w_mk=inp.tube_wall_k_w_mk,
            rf_inside_m2k_w=rf_i,
            rf_outside_m2k_w=rf_o,
        )

        area = required_area_m2(
            duty_w=max(q, 1e-9),
            u_w_m2k=uo,
            lmtd_k=dtlm,
            correction_factor=0.95,
        )

        segments.append(
            MulticomponentSegment(
                index=i + 1,
                process_in_c=p_t0,
                process_out_c=p_t1,
                utility_in_c=u_start,
                utility_out_c=u_end,
                beta_in=s0.vapour_fraction_molar,
                beta_out=s1.vapour_fraction_molar,
                beta_mean=beta_molar_mean,
                mass_quality_mean=quality_mass,
                enthalpy_in_kj_kg=s0.overall_enthalpy_j_kg / 1000.0,
                enthalpy_out_kj_kg=s1.overall_enthalpy_j_kg / 1000.0,
                duty_kw=q / 1000.0,
                process_h_w_m2k=process_h,
                utility_h_w_m2k=utility_h,
                overall_u_w_m2k=uo,
                lmtd_c=dtlm,
                required_area_m2=area,
                process_dp_kpa=process_dp_seg,
                utility_dp_kpa=utility_dp_seg,
                liquid_x_mean=x_mean,
                vapour_y_mean=y_mean,
                regime=regime,
                correlation=correlation,
            )
        )

    total_area = sum(s.required_area_m2 for s in segments)
    area_margin = 100.0 * (
        installed_area / total_area - 1.0
    )

    warnings: list[str] = []

    if area_margin < 0:
        warnings.append(
            f"Installed area is {abs(area_margin):.1f}% below integrated required area."
        )

    if process_dp_total > inp.allowable_process_dp_kpa:
        warnings.append(
            f"Integrated process ΔP {process_dp_total:.1f} kPa exceeds "
            f"allowable {inp.allowable_process_dp_kpa:.1f} kPa."
        )

    if utility_dp_total > inp.allowable_utility_dp_kpa:
        warnings.append(
            f"Integrated utility ΔP {utility_dp_total:.1f} kPa exceeds "
            f"allowable {inp.allowable_utility_dp_kpa:.1f} kPa."
        )

    warnings.append(
        "v0.8 is a coupled multicomponent VLE/exchanger screening model. "
        "Mixture latent enthalpy, two-phase h and two-phase ΔP remain approximations "
        "and should be benchmarked before design release."
    )

    if inp.package in {"NRTL", "UNIQUAC"}:
        warnings.append(
            f"{inp.package} flash path uses gamma-Raoult with ideal vapour fugacity in v0.8."
        )

    return MulticomponentPhaseHXResult(
        mode=inp.mode,
        tema_code=f"{inp.front_head}{inp.shell_type}{inp.rear_head}",
        total_duty_kw=total_q / 1000.0,
        total_required_area_m2=total_area,
        installed_area_m2=installed_area,
        area_margin_percent=area_margin,
        utility_outlet_c=overall_utility_out,
        process_dp_kpa=process_dp_total,
        utility_dp_kpa=utility_dp_total,
        inlet_vapour_fraction=states[0].vapour_fraction_molar,
        outlet_vapour_fraction=states[-1].vapour_fraction_molar,
        segments=segments,
        warnings=warnings,
    )
