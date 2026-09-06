from __future__ import annotations
from dataclasses import dataclass
import math

from .geometry import ShellTubeGeometry
from .correlations import reynolds_number, prandtl_number


@dataclass
class BellDelawareInputs:
    shell_to_baffle_clearance_m: float = 0.003
    tube_to_baffle_clearance_m: float = 0.0008
    bundle_to_shell_clearance_m: float = 0.012
    sealing_strip_pairs: int = 0


@dataclass
class BellDelawareResult:
    shell_velocity_m_s: float
    reynolds: float
    prandtl: float
    ideal_h_w_m2k: float
    j_c: float
    j_l: float
    j_b: float
    j_r: float
    j_s: float
    corrected_h_w_m2k: float
    shell_pressure_drop_kpa: float
    notes: list[str]


def _window_fraction(baffle_cut_fraction: float) -> float:
    """
    Geometric approximation of baffle-window fraction for a circular shell.
    """
    c = max(0.05, min(0.50, baffle_cut_fraction))
    h = 1.0 - 2.0 * c
    h = max(-0.999999, min(0.999999, h))
    theta = math.acos(h)
    segment = (theta - h * math.sqrt(1.0 - h*h)) / math.pi
    return max(0.05, min(0.95, segment))


def calculate_bell_delaware(
    mass_flow_kg_s: float,
    rho_kg_m3: float,
    mu_pa_s: float,
    cp_j_kgk: float,
    k_w_mk: float,
    geometry: ShellTubeGeometry,
    clearances: BellDelawareInputs | None = None,
) -> BellDelawareResult:
    """
    Development-stage Bell-Delaware framework.

    This implementation includes the five classical Bell correction-factor
    concepts (Jc, Jl, Jb, Jr, Js) using engineering screening approximations.
    It is deliberately modular so validated published correlations and exact
    leakage/bypass geometries can replace the approximations without changing
    the application interface.
    """
    geometry.validate()
    clearances = clearances or BellDelawareInputs()

    area_cross = max(1e-9, geometry.shell_crossflow_area_m2())
    velocity = mass_flow_kg_s / (rho_kg_m3 * area_cross)
    de = geometry.equivalent_shell_diameter_m()

    re = reynolds_number(rho_kg_m3, velocity, de, mu_pa_s)
    pr = prandtl_number(cp_j_kgk, mu_pa_s, k_w_mk)

    # Ideal crossflow tube-bank screening correlation.
    if re < 100:
        nu_ideal = 0.90 * max(re, 1.0) ** 0.40 * pr ** (1.0 / 3.0)
    elif re < 1000:
        nu_ideal = 0.52 * re ** 0.50 * pr ** (1.0 / 3.0)
    else:
        nu_ideal = 0.27 * re ** 0.63 * pr ** (1.0 / 3.0)

    h_ideal = nu_ideal * k_w_mk / de

    # Jc: baffle configuration/window correction.
    window_fraction = _window_fraction(geometry.baffle_cut_fraction)
    crossflow_fraction = max(0.15, 1.0 - window_fraction)
    j_c = max(0.55, min(1.15, 0.55 + 0.72 * crossflow_fraction))

    # Jl: baffle leakage correction.
    shell_leak_area = math.pi * geometry.shell_id_m * clearances.shell_to_baffle_clearance_m
    tube_leak_area = (
        geometry.tube_count
        * math.pi
        * geometry.tube_od_m
        * clearances.tube_to_baffle_clearance_m
    )
    leakage_ratio = (shell_leak_area + tube_leak_area) / max(area_cross, 1e-12)
    j_l = max(0.40, min(1.0, math.exp(-1.20 * leakage_ratio)))

    # Jb: bundle bypass correction.
    bypass_area = clearances.bundle_to_shell_clearance_m * geometry.baffle_spacing_m
    bypass_ratio = bypass_area / max(area_cross, 1e-12)
    strip_bonus = min(0.20, 0.04 * clearances.sealing_strip_pairs)
    j_b = max(0.45, min(1.0, math.exp(-1.35 * bypass_ratio) + strip_bonus))

    # Jr: adverse laminar temperature-gradient correction.
    if re >= 100:
        j_r = 1.0
    elif re <= 20:
        j_r = 0.70
    else:
        j_r = 0.70 + 0.30 * (re - 20.0) / 80.0

    # Js: unequal inlet/outlet baffle-spacing correction.
    # Current geometry assumes equal spacing, so unity is correct.
    j_s = 1.0

    h_corrected = h_ideal * j_c * j_l * j_b * j_r * j_s

    # Development shell-side pressure-drop model:
    # base tube-bank loss scaled by Bell-style leakage/bypass penalties.
    dynamic_pressure = rho_kg_m3 * velocity**2 / 2.0
    if re <= 0:
        f_shell = 1.0
    else:
        f_shell = 0.20 * max(re, 1.0) ** -0.15

    n_crossings = max(1, geometry.baffle_count + 1)
    base_dp = f_shell * (geometry.shell_id_m / de) * n_crossings * dynamic_pressure

    correction_dp = 1.0 / max(0.25, j_l * j_b)
    dp_pa = base_dp * correction_dp

    notes = [
        "Bell-Delaware correction framework active.",
        "Jc/Jl/Jb/Jr/Js are development-stage screening approximations.",
        "Replace screening leakage/bypass geometry with validated project-specific correlations before design release.",
    ]

    return BellDelawareResult(
        shell_velocity_m_s=velocity,
        reynolds=re,
        prandtl=pr,
        ideal_h_w_m2k=h_ideal,
        j_c=j_c,
        j_l=j_l,
        j_b=j_b,
        j_r=j_r,
        j_s=j_s,
        corrected_h_w_m2k=h_corrected,
        shell_pressure_drop_kpa=dp_pa / 1000.0,
        notes=notes,
    )
