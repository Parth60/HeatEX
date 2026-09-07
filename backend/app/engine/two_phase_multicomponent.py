from __future__ import annotations

from dataclasses import dataclass
import math

from .two_phase import (
    nusselt_horizontal_tube_condensation,
    cooper_pool_boiling,
)


@dataclass(frozen=True)
class MulticomponentHTResult:
    h_w_m2k: float
    correlation: str
    notes: list[str]


def shah_tube_condensation_screening(
    liquid_only_h_w_m2k: float,
    vapour_quality_mass: float,
    reduced_pressure: float,
) -> MulticomponentHTResult:
    """
    Shah-style in-tube condensation enhancement screening.

    h_tp / h_l =
      (1-x)^0.8 +
      3.8 x^0.76 (1-x)^0.04 / Pr^0.38
    """
    if liquid_only_h_w_m2k <= 0:
        raise ValueError("Liquid-only heat-transfer coefficient must be positive.")

    x = max(1e-5, min(0.99999, vapour_quality_mass))
    pr = max(1e-5, min(0.999, reduced_pressure))

    multiplier = (
        (1.0 - x) ** 0.8
        + 3.8
        * x**0.76
        * (1.0 - x) ** 0.04
        / pr**0.38
    )

    return MulticomponentHTResult(
        h_w_m2k=liquid_only_h_w_m2k * multiplier,
        correlation="Shah-style in-tube condensation screening",
        notes=[
            "Applied using a pseudo-reduced pressure for the mixture.",
            "Use as screening only for multicomponent condensation.",
        ],
    )


def shell_side_condensation_screening(
    rho_l_kg_m3: float,
    rho_v_kg_m3: float,
    mu_l_pa_s: float,
    k_l_w_mk: float,
    latent_heat_j_kg: float,
    tube_od_m: float,
    wall_subcooling_k: float,
) -> MulticomponentHTResult:
    base = nusselt_horizontal_tube_condensation(
        rho_l_kg_m3=rho_l_kg_m3,
        rho_v_kg_m3=rho_v_kg_m3,
        mu_l_pa_s=mu_l_pa_s,
        k_l_w_mk=k_l_w_mk,
        latent_heat_j_kg=latent_heat_j_kg,
        tube_od_m=tube_od_m,
        wall_subcooling_k=wall_subcooling_k,
    )

    return MulticomponentHTResult(
        h_w_m2k=base.h_w_m2k,
        correlation=base.correlation + " / mixture-property screening",
        notes=base.notes + [
            "Mixture transport and effective latent heat are composition-weighted."
        ],
    )


def multicomponent_boiling_screening(
    heat_flux_w_m2: float,
    mixture_mw_g_mol: float,
    pseudo_reduced_pressure: float,
    surface_roughness_um: float,
) -> MulticomponentHTResult:
    base = cooper_pool_boiling(
        heat_flux_w_m2=heat_flux_w_m2,
        molecular_weight_g_mol=mixture_mw_g_mol,
        reduced_pressure=pseudo_reduced_pressure,
        surface_roughness_um=surface_roughness_um,
    )

    return MulticomponentHTResult(
        h_w_m2k=base.h_w_m2k,
        correlation=base.correlation + " / mixture screening",
        notes=base.notes + [
            "Mixture molecular weight and pseudo-critical pressure are used."
        ],
    )
