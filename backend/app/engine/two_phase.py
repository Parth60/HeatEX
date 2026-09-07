from __future__ import annotations

from dataclasses import dataclass
import math


G = 9.80665


@dataclass(frozen=True)
class TwoPhaseHTResult:
    mode: str
    h_w_m2k: float
    correlation: str
    notes: list[str]


@dataclass(frozen=True)
class TwoPhaseDPResult:
    pressure_drop_kpa: float
    multiplier: float
    quality: float
    correlation: str
    notes: list[str]


def nusselt_horizontal_tube_condensation(
    rho_l_kg_m3: float,
    rho_v_kg_m3: float,
    mu_l_pa_s: float,
    k_l_w_mk: float,
    latent_heat_j_kg: float,
    tube_od_m: float,
    wall_subcooling_k: float,
) -> TwoPhaseHTResult:
    """
    Nusselt laminar film-condensation screening correlation for a horizontal tube.

    h = 0.725 [rho_l(rho_l-rho_v) g h_fg k_l^3 /
               (mu_l D deltaT)]^0.25
    """
    if min(
        rho_l_kg_m3,
        mu_l_pa_s,
        k_l_w_mk,
        latent_heat_j_kg,
        tube_od_m,
        wall_subcooling_k,
    ) <= 0:
        raise ValueError("Condensation-correlation inputs must be positive.")

    density_term = max(1e-9, rho_l_kg_m3 - rho_v_kg_m3)

    h = 0.725 * (
        rho_l_kg_m3
        * density_term
        * G
        * latent_heat_j_kg
        * k_l_w_mk**3
        / (mu_l_pa_s * tube_od_m * wall_subcooling_k)
    ) ** 0.25

    return TwoPhaseHTResult(
        mode="Condensation",
        h_w_m2k=h,
        correlation="Nusselt horizontal-tube laminar film condensation",
        notes=[
            "Pure-fluid screening correlation.",
            "Wall subcooling is an explicit design input.",
            "Tube-bank inundation and shear effects are not yet included.",
        ],
    )


def cooper_pool_boiling(
    heat_flux_w_m2: float,
    molecular_weight_g_mol: float,
    reduced_pressure: float,
    surface_roughness_um: float = 1.0,
) -> TwoPhaseHTResult:
    """
    Cooper pool-boiling screening correlation.

    Form implemented in kW/m² heat-flux basis and converted to W/m²K.
    This is suitable as a screening model, not a final vendor design basis.
    """
    if heat_flux_w_m2 <= 0:
        raise ValueError("Heat flux must be positive.")
    if molecular_weight_g_mol <= 0:
        raise ValueError("Molecular weight must be positive.")

    pr = max(1e-5, min(0.999, reduced_pressure))
    q_kw_m2 = heat_flux_w_m2 / 1000.0
    rp = max(0.1, surface_roughness_um)

    # Cooper-style nucleate boiling coefficient in kW/m²K.
    h_kw_m2k = (
        55.0
        * pr ** (0.12 - 0.20 * math.log10(rp))
        * (-math.log10(pr)) ** -0.55
        * molecular_weight_g_mol ** -0.50
        * q_kw_m2 ** 0.67
    )

    return TwoPhaseHTResult(
        mode="Boiling",
        h_w_m2k=max(50.0, h_kw_m2k * 1000.0),
        correlation="Cooper nucleate pool-boiling screening correlation",
        notes=[
            "Screening correlation for nucleate pool boiling.",
            "Surface roughness and heat flux materially affect the result.",
            "Critical heat flux / dryout is checked separately.",
        ],
    )


def lockhart_martinelli_screening(
    liquid_only_dp_kpa: float,
    quality: float,
    rho_l_kg_m3: float,
    rho_v_kg_m3: float,
    mu_l_pa_s: float,
    mu_v_pa_s: float,
    c_parameter: float = 20.0,
) -> TwoPhaseDPResult:
    """
    Lockhart-Martinelli turbulent/turbulent screening multiplier.
    """
    x = max(1e-4, min(0.9999, quality))

    if min(
        liquid_only_dp_kpa,
        rho_l_kg_m3,
        rho_v_kg_m3,
        mu_l_pa_s,
        mu_v_pa_s,
    ) <= 0:
        raise ValueError("Two-phase pressure-drop inputs must be positive.")

    x_tt = (
        ((1.0 - x) / x) ** 0.9
        * (rho_v_kg_m3 / rho_l_kg_m3) ** 0.5
        * (mu_l_pa_s / mu_v_pa_s) ** 0.1
    )

    phi_l_sq = 1.0 + c_parameter / max(x_tt, 1e-9) + 1.0 / max(x_tt, 1e-9) ** 2

    return TwoPhaseDPResult(
        pressure_drop_kpa=liquid_only_dp_kpa * phi_l_sq,
        multiplier=phi_l_sq,
        quality=x,
        correlation="Lockhart-Martinelli screening multiplier",
        notes=[
            "Frictional component only.",
            "Acceleration and static-head terms are not included in v0.6.",
        ],
    )
