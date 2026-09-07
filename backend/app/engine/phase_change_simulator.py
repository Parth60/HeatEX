from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from backend.app.thermo.components import get_component
from backend.app.thermo.phase_change import (
    get_saturation_state,
    pure_phase_enthalpy_j_kg,
)

from .geometry import ShellTubeGeometry
from .heat_transfer import overall_u_outside_basis, required_area_m2, lmtd
from .tube_side import calculate_tube_side
from .bell_delaware import calculate_bell_delaware, BellDelawareInputs
from .two_phase import (
    nusselt_horizontal_tube_condensation,
    cooper_pool_boiling,
    lockhart_martinelli_screening,
)


@dataclass
class PhaseChangeStream:
    fluid: str
    mass_flow_kg_s: float
    pressure_bar: float
    inlet_temperature_c: float
    outlet_temperature_c: float


@dataclass
class UtilityStream:
    fluid: str
    mass_flow_kg_s: float
    pressure_bar: float
    inlet_temperature_c: float


@dataclass
class PhaseChangeHXInput:
    operation: str  # Condenser or Reboiler
    process: PhaseChangeStream
    utility: UtilityStream
    geometry: ShellTubeGeometry

    front_head: str = "B"
    shell_type: str = "E"
    rear_head: str = "M"

    process_on_tube_side: bool = True
    flow_arrangement: str = "Counter-current"

    tube_wall_k_w_mk: float = 16.0
    process_fouling_m2k_w: float = 0.0002
    utility_fouling_m2k_w: float = 0.0002

    wall_subcooling_k: float = 8.0
    boiling_surface_roughness_um: float = 1.0

    allowable_process_dp_kpa: float = 70.0
    allowable_utility_dp_kpa: float = 50.0

    bell_clearances: BellDelawareInputs | None = None


@dataclass
class ZoneResult:
    name: str
    phase: str
    duty_kw: float
    duty_fraction: float
    process_in_c: float
    process_out_c: float
    utility_in_c: float
    utility_out_c: float
    process_h_w_m2k: float
    utility_h_w_m2k: float
    overall_u_w_m2k: float
    lmtd_c: float
    required_area_m2: float
    correlation: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PhaseChangeHXResult:
    operation: str
    tema_code: str
    saturation_temperature_c: float
    latent_heat_kj_kg: float

    total_duty_kw: float
    sensible_duty_kw: float
    latent_duty_kw: float

    total_required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    utility_outlet_c: float

    process_pressure_drop_kpa: float
    utility_pressure_drop_kpa: float
    two_phase_pressure_drop_kpa: float | None
    two_phase_multiplier: float | None

    zones: list[ZoneResult]
    warnings: list[str]

    def as_dict(self) -> dict:
        data = asdict(self)
        data["zones"] = [z.as_dict() for z in self.zones]
        return data


def _cp_integral(component, t1_c: float, t2_c: float, phase: str) -> float:
    h1 = component.sensible_enthalpy_j_kg(
        t1_c,
        reference_temperature_c=25.0,
        phase=phase,
    )
    h2 = component.sensible_enthalpy_j_kg(
        t2_c,
        reference_temperature_c=25.0,
        phase=phase,
    )
    return h2 - h1


def _utility_properties(component, temperature_c: float):
    return {
        "cp": component.cp_j_kgk(temperature_c),
        "rho": component.liquid_density_kg_m3(temperature_c),
        "mu": component.viscosity_pa_s(temperature_c),
        "k": component.thermal_conductivity_w_mk(temperature_c),
    }


def _zone_lmtd(
    process_in_c: float,
    process_out_c: float,
    utility_in_c: float,
    utility_out_c: float,
    counter_current: bool,
) -> float:
    # If process side is isothermal, perturbing is unnecessary: regular LMTD
    # handles equal process temperatures as long as terminal deltas differ.
    return lmtd(
        hot_in_c=max(process_in_c, utility_out_c),
        hot_out_c=max(process_out_c, utility_in_c),
        cold_in_c=min(process_in_c, utility_in_c),
        cold_out_c=min(process_out_c, utility_out_c),
        counter_current=counter_current,
    )


def _safe_lmtd_hot_process(
    hot_in: float,
    hot_out: float,
    cold_in: float,
    cold_out: float,
    counter: bool,
) -> float:
    return lmtd(hot_in, hot_out, cold_in, cold_out, counter)


def _safe_lmtd_cold_process(
    cold_in: float,
    cold_out: float,
    hot_in: float,
    hot_out: float,
    counter: bool,
) -> float:
    return lmtd(hot_in, hot_out, cold_in, cold_out, counter)


def simulate_phase_change(inp: PhaseChangeHXInput) -> PhaseChangeHXResult:
    operation = inp.operation.strip().lower()

    if operation not in {"condenser", "reboiler"}:
        raise ValueError("Operation must be Condenser or Reboiler.")

    inp.geometry.validate()

    if inp.process.mass_flow_kg_s <= 0 or inp.utility.mass_flow_kg_s <= 0:
        raise ValueError("Mass flow rates must be positive.")

    if inp.process.fluid in {"Thermal oil", "Light hydrocarbon"}:
        raise ValueError(
            "v0.6 phase-change mode requires a real pure component with saturation data."
        )

    process_comp = get_component(inp.process.fluid)
    utility_comp = get_component(inp.utility.fluid)

    sat = get_saturation_state(
        inp.process.fluid,
        inp.process.pressure_bar,
    )

    tsat = sat.saturation_temperature_c
    hfg = sat.latent_heat_j_kg

    counter = inp.flow_arrangement.lower().startswith("counter")

    # ------------------------------------------------------------------
    # Duty split
    # ------------------------------------------------------------------
    if operation == "condenser":
        if inp.process.inlet_temperature_c < tsat:
            raise ValueError(
                "Condenser inlet temperature is below saturation temperature "
                "for the selected pressure."
            )
        if inp.process.outlet_temperature_c > tsat:
            raise ValueError(
                "Condenser outlet remains above saturation; no full condensation "
                "zone exists for the requested outlet."
            )

        q_superheat = inp.process.mass_flow_kg_s * max(
            0.0,
            _cp_integral(
                process_comp,
                tsat,
                inp.process.inlet_temperature_c,
                "vapour",
            ),
        )
        q_latent = inp.process.mass_flow_kg_s * hfg
        q_subcool = inp.process.mass_flow_kg_s * max(
            0.0,
            _cp_integral(
                process_comp,
                inp.process.outlet_temperature_c,
                tsat,
                "liquid",
            ),
        )

        # integral(out -> sat) is positive; this is cooling duty magnitude.
        q_total = q_superheat + q_latent + q_subcool

    else:
        if inp.process.inlet_temperature_c > tsat:
            raise ValueError(
                "Reboiler inlet temperature is above saturation temperature "
                "for the selected pressure."
            )
        if inp.process.outlet_temperature_c < tsat:
            raise ValueError(
                "Reboiler outlet remains below saturation; no complete boiling "
                "zone exists for the requested outlet."
            )

        q_preheat = inp.process.mass_flow_kg_s * max(
            0.0,
            _cp_integral(
                process_comp,
                inp.process.inlet_temperature_c,
                tsat,
                "liquid",
            ),
        )
        q_latent = inp.process.mass_flow_kg_s * hfg
        q_superheat = inp.process.mass_flow_kg_s * max(
            0.0,
            _cp_integral(
                process_comp,
                tsat,
                inp.process.outlet_temperature_c,
                "vapour",
            ),
        )

        q_total = q_preheat + q_latent + q_superheat

    if q_total <= 0:
        raise ValueError("Calculated phase-change duty is not positive.")

    # ------------------------------------------------------------------
    # Utility outlet from sensible enthalpy approximation
    # ------------------------------------------------------------------
    utility_mean_guess = inp.utility.inlet_temperature_c + (
        20.0 if operation == "condenser" else -20.0
    )
    utility_cp = utility_comp.cp_j_kgk(utility_mean_guess)

    if operation == "condenser":
        utility_out = (
            inp.utility.inlet_temperature_c
            + q_total / (inp.utility.mass_flow_kg_s * utility_cp)
        )
    else:
        utility_out = (
            inp.utility.inlet_temperature_c
            - q_total / (inp.utility.mass_flow_kg_s * utility_cp)
        )

    utility_mean = 0.5 * (
        inp.utility.inlet_temperature_c + utility_out
    )
    util_props = _utility_properties(utility_comp, utility_mean)

    # ------------------------------------------------------------------
    # Base single-phase coefficients
    # ------------------------------------------------------------------
    process_mean_liquid = process_comp.liquid_density_kg_m3(tsat)

    if inp.process_on_tube_side:
        # Utility on shell side.
        tube_liquid = calculate_tube_side(
            mass_flow_kg_s=inp.process.mass_flow_kg_s,
            rho_kg_m3=sat.liquid_density_kg_m3,
            mu_pa_s=sat.liquid_viscosity_pa_s,
            cp_j_kgk=sat.liquid_cp_j_kgk,
            k_w_mk=sat.liquid_k_w_mk,
            geometry=inp.geometry,
        )

        shell_utility = calculate_bell_delaware(
            mass_flow_kg_s=inp.utility.mass_flow_kg_s,
            rho_kg_m3=util_props["rho"],
            mu_pa_s=util_props["mu"],
            cp_j_kgk=util_props["cp"],
            k_w_mk=util_props["k"],
            geometry=inp.geometry,
            clearances=inp.bell_clearances,
        )

        process_single_h = tube_liquid.h_w_m2k
        utility_h = shell_utility.corrected_h_w_m2k
        process_dp = tube_liquid.pressure_drop_kpa
        utility_dp = shell_utility.shell_pressure_drop_kpa
    else:
        tube_utility = calculate_tube_side(
            mass_flow_kg_s=inp.utility.mass_flow_kg_s,
            rho_kg_m3=util_props["rho"],
            mu_pa_s=util_props["mu"],
            cp_j_kgk=util_props["cp"],
            k_w_mk=util_props["k"],
            geometry=inp.geometry,
        )

        shell_process = calculate_bell_delaware(
            mass_flow_kg_s=inp.process.mass_flow_kg_s,
            rho_kg_m3=sat.liquid_density_kg_m3,
            mu_pa_s=sat.liquid_viscosity_pa_s,
            cp_j_kgk=sat.liquid_cp_j_kgk,
            k_w_mk=sat.liquid_k_w_mk,
            geometry=inp.geometry,
            clearances=inp.bell_clearances,
        )

        process_single_h = shell_process.corrected_h_w_m2k
        utility_h = tube_utility.h_w_m2k
        process_dp = shell_process.shell_pressure_drop_kpa
        utility_dp = tube_utility.pressure_drop_kpa

    # ------------------------------------------------------------------
    # Two-phase h and DP
    # ------------------------------------------------------------------
    if operation == "condenser":
        phase_ht = nusselt_horizontal_tube_condensation(
            rho_l_kg_m3=sat.liquid_density_kg_m3,
            rho_v_kg_m3=sat.vapour_density_kg_m3,
            mu_l_pa_s=sat.liquid_viscosity_pa_s,
            k_l_w_mk=sat.liquid_k_w_mk,
            latent_heat_j_kg=sat.latent_heat_j_kg,
            tube_od_m=inp.geometry.tube_od_m,
            wall_subcooling_k=inp.wall_subcooling_k,
        )
    else:
        # Initial heat flux from installed area, then Cooper h.
        q_flux = q_total / max(inp.geometry.installed_area_m2, 1e-9)
        reduced_pressure = (
            inp.process.pressure_bar * 1e5 / process_comp.pc_pa
            if process_comp.pc_pa
            else 0.10
        )

        phase_ht = cooper_pool_boiling(
            heat_flux_w_m2=q_flux,
            molecular_weight_g_mol=process_comp.mw_g_mol,
            reduced_pressure=reduced_pressure,
            surface_roughness_um=inp.boiling_surface_roughness_um,
        )

    # Vapour viscosity fallback: much lower than liquid viscosity.
    mu_v = max(7e-6, sat.liquid_viscosity_pa_s * 0.025)

    dp_two = None
    if inp.process_on_tube_side and process_dp > 0:
        try:
            dp_two = lockhart_martinelli_screening(
                liquid_only_dp_kpa=process_dp,
                quality=0.5,
                rho_l_kg_m3=sat.liquid_density_kg_m3,
                rho_v_kg_m3=sat.vapour_density_kg_m3,
                mu_l_pa_s=sat.liquid_viscosity_pa_s,
                mu_v_pa_s=mu_v,
            )
        except Exception:
            dp_two = None

    # ------------------------------------------------------------------
    # Zone construction
    # ------------------------------------------------------------------
    zones: list[ZoneResult] = []
    remaining_utility_in = inp.utility.inlet_temperature_c

    def add_zone(
        name: str,
        phase: str,
        q_w: float,
        p_in: float,
        p_out: float,
        p_h: float,
        correlation: str,
    ):
        nonlocal remaining_utility_in

        if q_w <= 1e-6:
            return

        if operation == "condenser":
            u_out = remaining_utility_in + q_w / (
                inp.utility.mass_flow_kg_s * utility_cp
            )

            if p_in >= p_out:
                dtlm = _safe_lmtd_hot_process(
                    p_in,
                    p_out,
                    remaining_utility_in,
                    u_out,
                    counter,
                )
            else:
                dtlm = _safe_lmtd_hot_process(
                    p_out,
                    p_in,
                    remaining_utility_in,
                    u_out,
                    counter,
                )
        else:
            u_out = remaining_utility_in - q_w / (
                inp.utility.mass_flow_kg_s * utility_cp
            )

            dtlm = _safe_lmtd_cold_process(
                p_in,
                p_out,
                remaining_utility_in,
                u_out,
                counter,
            )

        uo = overall_u_outside_basis(
            hi_w_m2k=p_h if inp.process_on_tube_side else utility_h,
            ho_w_m2k=utility_h if inp.process_on_tube_side else p_h,
            tube_id_m=inp.geometry.tube_id_m,
            tube_od_m=inp.geometry.tube_od_m,
            tube_k_w_mk=inp.tube_wall_k_w_mk,
            rf_inside_m2k_w=(
                inp.process_fouling_m2k_w
                if inp.process_on_tube_side
                else inp.utility_fouling_m2k_w
            ),
            rf_outside_m2k_w=(
                inp.utility_fouling_m2k_w
                if inp.process_on_tube_side
                else inp.process_fouling_m2k_w
            ),
        )

        area = required_area_m2(
            duty_w=q_w,
            u_w_m2k=uo,
            lmtd_k=dtlm,
            correction_factor=0.95,
        )

        zones.append(
            ZoneResult(
                name=name,
                phase=phase,
                duty_kw=q_w / 1000.0,
                duty_fraction=q_w / q_total,
                process_in_c=p_in,
                process_out_c=p_out,
                utility_in_c=remaining_utility_in,
                utility_out_c=u_out,
                process_h_w_m2k=p_h,
                utility_h_w_m2k=utility_h,
                overall_u_w_m2k=uo,
                lmtd_c=dtlm,
                required_area_m2=area,
                correlation=correlation,
            )
        )

        remaining_utility_in = u_out

    if operation == "condenser":
        add_zone(
            "Desuperheating",
            "Vapour",
            q_superheat,
            inp.process.inlet_temperature_c,
            tsat,
            process_single_h,
            "Single-phase process-side convection screening",
        )
        add_zone(
            "Condensation",
            "Two-phase",
            q_latent,
            tsat,
            tsat,
            phase_ht.h_w_m2k,
            phase_ht.correlation,
        )
        add_zone(
            "Subcooling",
            "Liquid",
            q_subcool,
            tsat,
            inp.process.outlet_temperature_c,
            process_single_h,
            "Single-phase process-side convection screening",
        )
        sensible_duty = q_superheat + q_subcool

    else:
        add_zone(
            "Preheating",
            "Liquid",
            q_preheat,
            inp.process.inlet_temperature_c,
            tsat,
            process_single_h,
            "Single-phase process-side convection screening",
        )
        add_zone(
            "Boiling",
            "Two-phase",
            q_latent,
            tsat,
            tsat,
            phase_ht.h_w_m2k,
            phase_ht.correlation,
        )
        add_zone(
            "Superheating",
            "Vapour",
            q_superheat,
            tsat,
            inp.process.outlet_temperature_c,
            process_single_h,
            "Single-phase process-side convection screening",
        )
        sensible_duty = q_preheat + q_superheat

    total_area = sum(z.required_area_m2 for z in zones)
    installed = inp.geometry.installed_area_m2
    margin = 100.0 * (installed / total_area - 1.0)

    warnings: list[str] = []

    if margin < 0:
        warnings.append(
            f"Installed area is {abs(margin):.1f}% below phase-change required area."
        )

    if process_dp > inp.allowable_process_dp_kpa:
        warnings.append(
            f"Process-side single-phase screening ΔP {process_dp:.1f} kPa "
            f"exceeds the allowable {inp.allowable_process_dp_kpa:.1f} kPa."
        )

    if utility_dp > inp.allowable_utility_dp_kpa:
        warnings.append(
            f"Utility-side ΔP {utility_dp:.1f} kPa exceeds the allowable "
            f"{inp.allowable_utility_dp_kpa:.1f} kPa."
        )

    if dp_two is not None and dp_two.pressure_drop_kpa > inp.allowable_process_dp_kpa:
        warnings.append(
            f"Two-phase Lockhart-Martinelli screening ΔP "
            f"{dp_two.pressure_drop_kpa:.1f} kPa exceeds the process limit."
        )

    warnings.extend(phase_ht.notes)
    warnings.append(
        "v0.6 phase-change mode is for pure-component engineering screening. "
        "Mixture condensation/boiling requires a rigorous flash and phase-equilibrium solver."
    )

    return PhaseChangeHXResult(
        operation=inp.operation,
        tema_code=f"{inp.front_head}{inp.shell_type}{inp.rear_head}",
        saturation_temperature_c=tsat,
        latent_heat_kj_kg=hfg / 1000.0,
        total_duty_kw=q_total / 1000.0,
        sensible_duty_kw=sensible_duty / 1000.0,
        latent_duty_kw=q_latent / 1000.0,
        total_required_area_m2=total_area,
        installed_area_m2=installed,
        area_margin_percent=margin,
        utility_outlet_c=utility_out,
        process_pressure_drop_kpa=process_dp,
        utility_pressure_drop_kpa=utility_dp,
        two_phase_pressure_drop_kpa=(
            None if dp_two is None else dp_two.pressure_drop_kpa
        ),
        two_phase_multiplier=(
            None if dp_two is None else dp_two.multiplier
        ),
        zones=zones,
        warnings=warnings,
    )
