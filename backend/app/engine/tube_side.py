from __future__ import annotations
from dataclasses import dataclass
import math

from .correlations import (
    reynolds_number,
    prandtl_number,
    nusselt_internal,
    darcy_friction_factor,
)
from .geometry import ShellTubeGeometry


@dataclass
class TubeSideResult:
    velocity_m_s: float
    reynolds: float
    prandtl: float
    nusselt: float
    h_w_m2k: float
    friction_factor: float
    pressure_drop_kpa: float


def calculate_tube_side(
    mass_flow_kg_s: float,
    rho_kg_m3: float,
    mu_pa_s: float,
    cp_j_kgk: float,
    k_w_mk: float,
    geometry: ShellTubeGeometry,
    roughness_m: float = 4.5e-5,
    minor_loss_coefficient_per_pass: float = 1.5,
) -> TubeSideResult:
    geometry.validate()

    flow_area = geometry.tube_flow_area_m2
    velocity = mass_flow_kg_s / (rho_kg_m3 * flow_area)

    re = reynolds_number(rho_kg_m3, velocity, geometry.tube_id_m, mu_pa_s)
    pr = prandtl_number(cp_j_kgk, mu_pa_s, k_w_mk)
    nu = nusselt_internal(re, pr)
    h = nu * k_w_mk / geometry.tube_id_m

    rr = roughness_m / geometry.tube_id_m
    f = darcy_friction_factor(re, rr)

    total_length = geometry.tube_length_m * geometry.tube_passes
    dynamic_pressure = rho_kg_m3 * velocity**2 / 2.0

    k_minor = minor_loss_coefficient_per_pass * geometry.tube_passes
    dp_pa = (
        f * total_length / geometry.tube_id_m + k_minor
    ) * dynamic_pressure

    return TubeSideResult(
        velocity_m_s=velocity,
        reynolds=re,
        prandtl=pr,
        nusselt=nu,
        h_w_m2k=h,
        friction_factor=f,
        pressure_drop_kpa=dp_pa / 1000.0,
    )
