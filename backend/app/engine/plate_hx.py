from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .single_phase_common import ServiceStream, solve_energy_balance
from .heat_transfer import lmtd


@dataclass
class PlateGeometry:
    plate_length_m: float = 1.0
    plate_width_m: float = 0.40
    plate_gap_m: float = 0.003
    plate_thickness_m: float = 0.0006
    plate_count: int = 80
    passes_hot: int = 1
    passes_cold: int = 1
    chevron_angle_deg: float = 45.0
    enlargement_factor: float = 1.18
    plate_k_w_mk: float = 15.0
    port_diameter_m: float = 0.10

    def validate(self):
        if self.plate_length_m <= 0 or self.plate_width_m <= 0:
            raise ValueError("Plate dimensions must be positive.")
        if self.plate_gap_m <= 0 or self.plate_thickness_m <= 0:
            raise ValueError("Plate gap/thickness must be positive.")
        if self.plate_count < 4:
            raise ValueError("Plate count must be at least 4.")
        if self.passes_hot <= 0 or self.passes_cold <= 0:
            raise ValueError("Pass counts must be positive.")

    @property
    def effective_plate_count(self) -> int:
        return max(1, self.plate_count - 2)

    @property
    def installed_area_m2(self) -> float:
        return (
            self.effective_plate_count
            * self.plate_length_m
            * self.plate_width_m
            * self.enlargement_factor
        )

    def channels_per_pass(self, side: str) -> float:
        total_channels = max(2, self.plate_count - 1)
        side_channels = total_channels / 2.0
        passes = self.passes_hot if side == "hot" else self.passes_cold
        return max(1.0, side_channels / passes)


@dataclass
class PlateHXResult:
    duty_kw: float
    hot_outlet_c: float
    cold_outlet_c: float

    hot_velocity_m_s: float
    cold_velocity_m_s: float
    hot_reynolds: float
    cold_reynolds: float
    hot_h_w_m2k: float
    cold_h_w_m2k: float

    hot_dp_kpa: float
    cold_dp_kpa: float

    overall_u_w_m2k: float
    lmtd_c: float
    required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _plate_side(
    mass_flow_kg_s: float,
    props: dict,
    geometry: PlateGeometry,
    side: str,
):
    channels = geometry.channels_per_pass(side)
    flow_area = geometry.plate_width_m * geometry.plate_gap_m * channels

    rho = props["density_kg_m3"]
    mu = props["viscosity_pa_s"]
    cp = props["cp_j_kgk"]
    k = props["thermal_conductivity_w_mk"]

    velocity = mass_flow_kg_s / (rho * flow_area)
    dh = 2.0 * geometry.plate_gap_m

    re = rho * velocity * dh / mu
    pr = cp * mu / k

    beta = math.radians(geometry.chevron_angle_deg)
    angle_factor = max(0.75, min(1.35, 0.80 + 0.70 * math.sin(beta)))

    # Screening chevron-plate correlation.
    if re < 100:
        nu = 3.66
        f = 24.0 / max(re, 1e-9)
    else:
        nu = 0.30 + 0.62 * re**0.67 * pr**(1.0/3.0) * angle_factor
        f = 3.5 * re**-0.30 * (1.0 + 0.75 * math.sin(beta))

    h = nu * k / dh

    passes = geometry.passes_hot if side == "hot" else geometry.passes_cold
    friction_dp = (
        4.0 * f * geometry.plate_length_m / dh
        * rho * velocity**2 / 2.0
        * passes
    )

    port_area = math.pi * geometry.port_diameter_m**2 / 4.0
    port_velocity = mass_flow_kg_s / (rho * port_area)
    port_dp = 1.5 * passes * rho * port_velocity**2 / 2.0

    return {
        "velocity": velocity,
        "re": re,
        "pr": pr,
        "nu": nu,
        "h": h,
        "dp_kpa": (friction_dp + port_dp) / 1000.0,
    }


def simulate_plate_hx(
    hot: ServiceStream,
    cold: ServiceStream,
    hot_outlet_target_c: float,
    geometry: PlateGeometry,
    package: str = "Ideal mixture",
    interaction_parameters: dict | None = None,
    flow_arrangement: str = "Counter-current",
    hot_fouling_m2k_w: float = 0.0002,
    cold_fouling_m2k_w: float = 0.0002,
    allowable_hot_dp_kpa: float = 70.0,
    allowable_cold_dp_kpa: float = 70.0,
) -> PlateHXResult:
    geometry.validate()

    eb = solve_energy_balance(
        hot, cold, hot_outlet_target_c, package, interaction_parameters
    )

    hs = _plate_side(
        hot.mass_flow_kg_s, eb.hot_mean_state, geometry, "hot"
    )
    cs = _plate_side(
        cold.mass_flow_kg_s, eb.cold_mean_state, geometry, "cold"
    )

    wall_r = geometry.plate_thickness_m / geometry.plate_k_w_mk

    resistance = (
        1.0 / hs["h"]
        + hot_fouling_m2k_w
        + wall_r
        + cold_fouling_m2k_w
        + 1.0 / cs["h"]
    )
    u = 1.0 / resistance

    counter = flow_arrangement.lower().startswith("counter")
    dtlm = lmtd(
        hot.inlet_temperature_c,
        eb.hot_outlet_c,
        cold.inlet_temperature_c,
        eb.cold_outlet_c,
        counter,
    )

    required_area = eb.duty_w / (u * dtlm)
    installed = geometry.installed_area_m2
    margin = 100.0 * (installed / required_area - 1.0)

    warnings = list(eb.warnings)

    if hs["dp_kpa"] > allowable_hot_dp_kpa:
        warnings.append("Hot-side plate pressure drop exceeds allowable.")
    if cs["dp_kpa"] > allowable_cold_dp_kpa:
        warnings.append("Cold-side plate pressure drop exceeds allowable.")
    if margin < 0:
        warnings.append("Installed plate area is below required area.")
    if hs["velocity"] > 4.0 or cs["velocity"] > 4.0:
        warnings.append("High plate-channel velocity; review erosion and port losses.")

    warnings.append(
        "Plate-side heat transfer/friction are screening chevron correlations; "
        "vendor plate geometry is required for final rating."
    )

    return PlateHXResult(
        duty_kw=eb.duty_w / 1000.0,
        hot_outlet_c=eb.hot_outlet_c,
        cold_outlet_c=eb.cold_outlet_c,
        hot_velocity_m_s=hs["velocity"],
        cold_velocity_m_s=cs["velocity"],
        hot_reynolds=hs["re"],
        cold_reynolds=cs["re"],
        hot_h_w_m2k=hs["h"],
        cold_h_w_m2k=cs["h"],
        hot_dp_kpa=hs["dp_kpa"],
        cold_dp_kpa=cs["dp_kpa"],
        overall_u_w_m2k=u,
        lmtd_c=dtlm,
        required_area_m2=required_area,
        installed_area_m2=installed,
        area_margin_percent=margin,
        warnings=warnings,
    )
