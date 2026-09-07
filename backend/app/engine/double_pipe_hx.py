from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .single_phase_common import ServiceStream, solve_energy_balance
from .correlations import (
    darcy_friction_factor,
    nusselt_internal,
)
from .heat_transfer import lmtd


@dataclass
class DoublePipeGeometry:
    inner_tube_od_m: float = 0.0483
    inner_tube_id_m: float = 0.0409
    outer_pipe_id_m: float = 0.0779
    hairpin_length_m: float = 6.0
    hairpins: int = 4
    inner_wall_k_w_mk: float = 16.0
    inner_roughness_m: float = 4.5e-5
    outer_roughness_m: float = 4.5e-5

    def validate(self):
        if min(
            self.inner_tube_od_m,
            self.inner_tube_id_m,
            self.outer_pipe_id_m,
            self.hairpin_length_m,
        ) <= 0:
            raise ValueError("Double-pipe dimensions must be positive.")
        if self.inner_tube_id_m >= self.inner_tube_od_m:
            raise ValueError("Inner-tube ID must be below OD.")
        if self.outer_pipe_id_m <= self.inner_tube_od_m:
            raise ValueError("Outer-pipe ID must exceed inner-tube OD.")
        if self.hairpins <= 0:
            raise ValueError("Hairpin count must be positive.")

    @property
    def total_flow_length_m(self) -> float:
        return 2.0 * self.hairpin_length_m * self.hairpins

    @property
    def installed_area_m2(self) -> float:
        return (
            math.pi
            * self.inner_tube_od_m
            * self.total_flow_length_m
        )

    @property
    def annulus_hydraulic_diameter_m(self) -> float:
        return self.outer_pipe_id_m - self.inner_tube_od_m

    @property
    def annulus_flow_area_m2(self) -> float:
        return (
            math.pi / 4.0
            * (
                self.outer_pipe_id_m**2
                - self.inner_tube_od_m**2
            )
        )


@dataclass
class DoublePipeHXResult:
    duty_kw: float
    hot_outlet_c: float
    cold_outlet_c: float

    inner_velocity_m_s: float
    annulus_velocity_m_s: float

    inner_reynolds: float
    annulus_reynolds: float

    inner_h_w_m2k: float
    annulus_h_w_m2k: float

    inner_dp_kpa: float
    annulus_dp_kpa: float

    overall_u_w_m2k: float
    lmtd_c: float
    required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _flow_side(
    mass_flow_kg_s: float,
    props: dict,
    diameter_m: float,
    area_m2: float,
    length_m: float,
    roughness_m: float,
):
    rho = props["density_kg_m3"]
    mu = props["viscosity_pa_s"]
    cp = props["cp_j_kgk"]
    k = props["thermal_conductivity_w_mk"]

    velocity = mass_flow_kg_s / (rho * area_m2)
    re = rho * velocity * diameter_m / mu
    pr = cp * mu / k

    nu = nusselt_internal(max(re, 1e-9), max(pr, 1e-9))
    h = nu * k / diameter_m

    f = darcy_friction_factor(
        max(re, 1e-9),
        max(0.0, roughness_m / diameter_m),
    )

    dp = (
        f * length_m / diameter_m + 2.5
    ) * rho * velocity**2 / 2.0

    return {
        "velocity": velocity,
        "re": re,
        "pr": pr,
        "nu": nu,
        "h": h,
        "dp_kpa": dp / 1000.0,
    }


def simulate_double_pipe_hx(
    hot: ServiceStream,
    cold: ServiceStream,
    hot_outlet_target_c: float,
    geometry: DoublePipeGeometry,
    package: str = "Ideal mixture",
    interaction_parameters: dict | None = None,
    flow_arrangement: str = "Counter-current",
    hot_in_inner: bool = True,
    hot_fouling_m2k_w: float = 0.0002,
    cold_fouling_m2k_w: float = 0.0002,
    allowable_inner_dp_kpa: float = 100.0,
    allowable_annulus_dp_kpa: float = 100.0,
) -> DoublePipeHXResult:
    geometry.validate()

    eb = solve_energy_balance(
        hot, cold, hot_outlet_target_c, package, interaction_parameters
    )

    inner_area = math.pi * geometry.inner_tube_id_m**2 / 4.0
    annulus_area = geometry.annulus_flow_area_m2
    length = geometry.total_flow_length_m

    if hot_in_inner:
        inner_stream, inner_props = hot, eb.hot_mean_state
        ann_stream, ann_props = cold, eb.cold_mean_state
        rf_inner, rf_ann = hot_fouling_m2k_w, cold_fouling_m2k_w
    else:
        inner_stream, inner_props = cold, eb.cold_mean_state
        ann_stream, ann_props = hot, eb.hot_mean_state
        rf_inner, rf_ann = cold_fouling_m2k_w, hot_fouling_m2k_w

    inner = _flow_side(
        inner_stream.mass_flow_kg_s,
        inner_props,
        geometry.inner_tube_id_m,
        inner_area,
        length,
        geometry.inner_roughness_m,
    )

    annulus = _flow_side(
        ann_stream.mass_flow_kg_s,
        ann_props,
        geometry.annulus_hydraulic_diameter_m,
        annulus_area,
        length,
        geometry.outer_roughness_m,
    )

    do = geometry.inner_tube_od_m
    di = geometry.inner_tube_id_m

    resistance_outside_basis = (
        1.0 / annulus["h"]
        + rf_ann
        + do * math.log(do / di)
        / (2.0 * geometry.inner_wall_k_w_mk)
        + (do / di) * (rf_inner + 1.0 / inner["h"])
    )
    u = 1.0 / resistance_outside_basis

    counter = flow_arrangement.lower().startswith("counter")
    dtlm = lmtd(
        hot.inlet_temperature_c,
        eb.hot_outlet_c,
        cold.inlet_temperature_c,
        eb.cold_outlet_c,
        counter,
    )

    required = eb.duty_w / (u * dtlm)
    installed = geometry.installed_area_m2
    margin = 100.0 * (installed / required - 1.0)

    warnings = list(eb.warnings)
    if inner["dp_kpa"] > allowable_inner_dp_kpa:
        warnings.append("Inner-tube pressure drop exceeds allowable.")
    if annulus["dp_kpa"] > allowable_annulus_dp_kpa:
        warnings.append("Annulus pressure drop exceeds allowable.")
    if margin < 0:
        warnings.append("Installed double-pipe area is below required area.")

    return DoublePipeHXResult(
        duty_kw=eb.duty_w / 1000.0,
        hot_outlet_c=eb.hot_outlet_c,
        cold_outlet_c=eb.cold_outlet_c,
        inner_velocity_m_s=inner["velocity"],
        annulus_velocity_m_s=annulus["velocity"],
        inner_reynolds=inner["re"],
        annulus_reynolds=annulus["re"],
        inner_h_w_m2k=inner["h"],
        annulus_h_w_m2k=annulus["h"],
        inner_dp_kpa=inner["dp_kpa"],
        annulus_dp_kpa=annulus["dp_kpa"],
        overall_u_w_m2k=u,
        lmtd_c=dtlm,
        required_area_m2=required,
        installed_area_m2=installed,
        area_margin_percent=margin,
        warnings=warnings,
    )
