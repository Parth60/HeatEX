from __future__ import annotations

import math

from app.models import FlowArrangement, SimulationRequest, SimulationResult, ThermalSpec
from app.engine.properties import properties
from app.engine.tema import SHELL_F_SCREENING, TemaConfiguration


def _lmtd(thi: float, tho: float, tci: float, tco: float, arrangement: FlowArrangement) -> float:
    if arrangement == FlowArrangement.counter_current:
        d1, d2 = thi - tco, tho - tci
    else:
        d1, d2 = thi - tci, tho - tco
    if d1 <= 0 or d2 <= 0:
        raise ValueError("Temperature cross or invalid terminal temperature difference")
    if abs(d1 - d2) < 1e-9:
        return d1
    return (d1 - d2) / math.log(d1 / d2)


def _darcy_friction_factor(re: float) -> float:
    if re <= 0:
        return 1.0
    if re < 2300:
        return 64.0 / re
    # Blasius screening relation for smooth turbulent tube flow.
    return 0.3164 / re ** 0.25


def _tube_nusselt(re: float, pr: float) -> float:
    if re < 2300:
        return 3.66
    # Dittus-Boelter screening relation.
    return 0.023 * re ** 0.8 * pr ** 0.4


def _shell_equivalent_diameter(pitch: float, do: float, layout: str) -> float:
    if "triangular" in layout:
        return max(0.002, 1.10 * (pitch * pitch - 0.917 * do * do) / do)
    return max(0.002, 1.27 * (pitch * pitch - 0.785 * do * do) / do)


def simulate(req: SimulationRequest) -> SimulationResult:
    tema = TemaConfiguration(req.tema.front, req.tema.shell, req.tema.rear)
    tema.validate()
    g = req.geometry

    # Mean-temperature properties for the current single-phase screening engine.
    hot_guess = 0.5 * (req.hot_stream.inlet_temp_c + (req.thermal_target if req.thermal_spec == ThermalSpec.hot_outlet else req.hot_stream.inlet_temp_c - 25))
    cold_guess = 0.5 * (req.cold_stream.inlet_temp_c + (req.thermal_target if req.thermal_spec == ThermalSpec.cold_outlet else req.cold_stream.inlet_temp_c + 20))
    hp = properties(req.hot_stream.fluid, hot_guess, req.hot_stream.pressure_bar, req.thermo_package)
    cp = properties(req.cold_stream.fluid, cold_guess, req.cold_stream.pressure_bar, req.thermo_package)

    thi = req.hot_stream.inlet_temp_c
    tci = req.cold_stream.inlet_temp_c
    mh = req.hot_stream.mass_flow_kg_s
    mc = req.cold_stream.mass_flow_kg_s

    if req.thermal_spec == ThermalSpec.hot_outlet:
        tho = req.thermal_target
        duty_w = mh * hp.cp_j_kgk * (thi - tho)
        tco = tci + duty_w / (mc * cp.cp_j_kgk)
    elif req.thermal_spec == ThermalSpec.cold_outlet:
        tco = req.thermal_target
        duty_w = mc * cp.cp_j_kgk * (tco - tci)
        tho = thi - duty_w / (mh * hp.cp_j_kgk)
    else:
        duty_w = req.thermal_target * 1000.0
        tho = thi - duty_w / (mh * hp.cp_j_kgk)
        tco = tci + duty_w / (mc * cp.cp_j_kgk)

    if duty_w <= 0:
        raise ValueError("Calculated heat duty must be positive")

    do = g.tube_od_mm / 1000.0
    di = g.tube_id_mm / 1000.0
    pitch = g.tube_pitch_mm / 1000.0
    n_per_pass = max(1.0, g.tube_count / g.tube_passes)
    tube_flow_area = n_per_pass * math.pi * di * di / 4.0
    vt = mh / (hp.rho_kg_m3 * tube_flow_area)
    re_t = hp.rho_kg_m3 * vt * di / hp.mu_pa_s
    pr_t = hp.cp_j_kgk * hp.mu_pa_s / hp.k_w_mk
    nu_t = _tube_nusselt(re_t, pr_t)
    hi = nu_t * hp.k_w_mk / di

    baffle_spacing = g.tube_length_m / max(1, g.baffle_count + 1)
    shell_crossflow_area = max(1e-6, g.shell_id_m * baffle_spacing * (pitch - do) / pitch)
    vs = mc / (cp.rho_kg_m3 * shell_crossflow_area)
    de = _shell_equivalent_diameter(pitch, do, g.tube_layout)
    re_s = cp.rho_kg_m3 * vs * de / cp.mu_pa_s
    pr_s = cp.cp_j_kgk * cp.mu_pa_s / cp.k_w_mk
    # Kern-style screening correlation only; Bell-Delaware is the production target.
    nu_s = 1.8 if re_s < 100 else 0.36 * re_s ** 0.55 * pr_s ** (1 / 3)
    ho = nu_s * cp.k_w_mk / de

    wall = do * math.log(do / di) / (2 * g.tube_wall_k_w_mk)
    resistance = (
        1 / max(10.0, ho)
        + g.shell_fouling_m2k_w
        + wall
        + (do / di) * (g.tube_fouling_m2k_w + 1 / max(10.0, hi))
    )
    uo = 1 / resistance

    lmtd = _lmtd(thi, tho, tci, tco, req.flow_arrangement)
    f_corr = SHELL_F_SCREENING[req.tema.shell]
    effective_dt = lmtd * f_corr
    required_area = duty_w / (uo * effective_dt)
    installed_area = math.pi * do * g.tube_length_m * g.tube_count

    f_t = _darcy_friction_factor(re_t)
    tube_dp = (f_t * (g.tube_length_m * g.tube_passes / di) + 1.5 * g.tube_passes) * (hp.rho_kg_m3 * vt * vt / 2) / 1000
    shell_f = 0.20 / max(100.0, re_s) ** 0.15
    shell_dp = shell_f * (g.shell_id_m / de) * (g.baffle_count + 1) * (cp.rho_kg_m3 * vs * vs / 2) / 1000

    # Rating mode caps achieved duty if installed area cannot support the specified target.
    if req.mode.value == "rating" and installed_area < required_area:
        ratio = max(0.01, installed_area / required_area)
        duty_w *= ratio
        tho = thi - duty_w / (mh * hp.cp_j_kgk)
        tco = tci + duty_w / (mc * cp.cp_j_kgk)
        lmtd = _lmtd(thi, tho, tci, tco, req.flow_arrangement)
        effective_dt = lmtd * f_corr
        required_area = installed_area

    margin = 100.0 * (installed_area / required_area - 1.0)
    warnings: list[str] = []
    if vt < 0.5:
        warnings.append("Tube-side velocity is below the current screening target of 0.5 m/s.")
    if vt > 3.0:
        warnings.append("Tube-side velocity exceeds the current screening target of 3.0 m/s.")
    if tube_dp > req.tube_dp_limit_kpa:
        warnings.append("Tube-side pressure drop exceeds the user limit.")
    if shell_dp > req.shell_dp_limit_kpa:
        warnings.append("Shell-side pressure drop exceeds the user limit.")
    if margin < 0:
        warnings.append("Installed heat-transfer area is below the calculated required area.")
    if "fallback" in hp.source or "fallback" in cp.source:
        warnings.append("At least one stream is using fallback properties; do not treat the result as a validated thermodynamic-package calculation.")

    hydraulic_penalty = max(0, tube_dp / req.tube_dp_limit_kpa - 0.75) * 25 + max(0, shell_dp / req.shell_dp_limit_kpa - 0.75) * 25
    area_penalty = abs(max(-50, min(100, margin)) - 15) * 0.15
    score = max(0.0, min(100.0, 100.0 - hydraulic_penalty - area_penalty - 5.0 * len(warnings)))

    return SimulationResult(
        tema_code=tema.code,
        tema_description=tema.description(),
        duty_kw=duty_w / 1000,
        hot_outlet_c=tho,
        cold_outlet_c=tco,
        lmtd_c=lmtd,
        correction_factor=f_corr,
        effective_delta_t_c=effective_dt,
        overall_u_w_m2k=uo,
        required_area_m2=required_area,
        installed_area_m2=installed_area,
        area_margin_pct=margin,
        tube_velocity_m_s=vt,
        tube_reynolds=re_t,
        tube_prandtl=pr_t,
        tube_nusselt=nu_t,
        tube_h_w_m2k=hi,
        tube_dp_kpa=tube_dp,
        shell_velocity_m_s=vs,
        shell_reynolds=re_s,
        shell_prandtl=pr_s,
        shell_nusselt=nu_s,
        shell_h_w_m2k=ho,
        shell_dp_kpa=shell_dp,
        hot_properties=hp,
        cold_properties=cp,
        screening_score=score,
        warnings=warnings,
        methodology=[
            "Energy balance using mean-temperature stream properties",
            "Tube-side Dittus-Boelter / laminar Nu=3.66 screening model",
            "Shell-side Kern-style screening model",
            "Overall U including tube-wall and fouling resistances",
            "LMTD method with a provisional shell-type correction factor",
            "Darcy/Blasius-style tube-side pressure-drop screening",
            "Shell-side pressure-drop screening pending Bell-Delaware production implementation",
        ],
    )
