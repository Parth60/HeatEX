from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .single_phase_common import ServiceStream, state
from .correlations import darcy_friction_factor, nusselt_internal
from .heat_transfer import lmtd


@dataclass
class AirCooledGeometry:
    tube_od_m: float = 0.0254
    tube_id_m: float = 0.0212
    tube_length_m: float = 8.0
    tubes_per_row: int = 40
    rows: int = 4

    fin_od_m: float = 0.057
    fin_thickness_m: float = 0.0004
    fins_per_m: float = 394.0
    fin_k_w_mk: float = 180.0

    transverse_pitch_m: float = 0.065
    longitudinal_pitch_m: float = 0.060

    air_flow_m3_s: float = 45.0
    fan_efficiency: float = 0.65

    def validate(self):
        if min(
            self.tube_od_m,
            self.tube_id_m,
            self.tube_length_m,
            self.fin_od_m,
            self.fin_thickness_m,
            self.transverse_pitch_m,
            self.longitudinal_pitch_m,
            self.air_flow_m3_s,
        ) <= 0:
            raise ValueError("Air-cooler geometry values must be positive.")
        if self.tube_id_m >= self.tube_od_m:
            raise ValueError("Tube ID must be below tube OD.")
        if self.fin_od_m <= self.tube_od_m:
            raise ValueError("Fin OD must exceed tube OD.")
        if self.tubes_per_row <= 0 or self.rows <= 0:
            raise ValueError("Tube count and rows must be positive.")

    @property
    def tube_count(self) -> int:
        return self.tubes_per_row * self.rows

    @property
    def bare_tube_area_m2(self) -> float:
        return math.pi * self.tube_od_m * self.tube_length_m * self.tube_count

    @property
    def fin_count_per_tube(self) -> float:
        return self.fins_per_m * self.tube_length_m

    @property
    def fin_area_per_fin_m2(self) -> float:
        # Two annular faces + outer edge.
        return (
            2.0
            * math.pi / 4.0
            * (self.fin_od_m**2 - self.tube_od_m**2)
            + math.pi * self.fin_od_m * self.fin_thickness_m
        )

    @property
    def total_fin_area_m2(self) -> float:
        return (
            self.fin_area_per_fin_m2
            * self.fin_count_per_tube
            * self.tube_count
        )

    @property
    def total_external_area_m2(self) -> float:
        # Screened total area includes fin area plus remaining exposed tube area.
        blocked_fraction = min(
            0.95,
            self.fins_per_m * self.fin_thickness_m,
        )
        exposed_tube = self.bare_tube_area_m2 * (1.0 - blocked_fraction)
        return self.total_fin_area_m2 + exposed_tube

    @property
    def face_area_m2(self) -> float:
        return (
            self.tubes_per_row
            * self.transverse_pitch_m
            * self.tube_length_m
        )


@dataclass
class AirCooledHXResult:
    duty_kw: float
    process_outlet_c: float
    air_outlet_c: float

    process_velocity_m_s: float
    process_reynolds: float
    process_h_w_m2k: float
    process_dp_kpa: float

    air_face_velocity_m_s: float
    air_reynolds: float
    air_h_w_m2k: float
    air_dp_pa: float

    fin_efficiency: float
    overall_surface_efficiency: float
    overall_u_external_w_m2k: float

    required_external_area_m2: float
    installed_external_area_m2: float
    area_margin_percent: float

    fan_power_kw: float
    lmtd_c: float

    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _air_properties(temperature_c: float):
    tk = temperature_c + 273.15
    rho = 101325.0 / (287.058 * tk)

    # Sutherland viscosity
    mu0 = 1.716e-5
    t0 = 273.15
    s = 111.0
    mu = mu0 * (tk / t0)**1.5 * (t0 + s) / (tk + s)

    cp = 1006.0 + 0.10 * (tk - 300.0)
    k = 0.0241 + 7.72e-5 * temperature_c
    pr = cp * mu / k

    return {"rho": rho, "mu": mu, "cp": cp, "k": k, "pr": pr}


def simulate_air_cooled_hx(
    process: ServiceStream,
    process_outlet_target_c: float,
    air_inlet_temperature_c: float,
    geometry: AirCooledGeometry,
    package: str = "Ideal mixture",
    interaction_parameters: dict | None = None,
    process_fouling_m2k_w: float = 0.0002,
    tube_wall_k_w_mk: float = 16.0,
    allowable_process_dp_kpa: float = 100.0,
) -> AirCooledHXResult:
    geometry.validate()

    if process.mass_flow_kg_s <= 0:
        raise ValueError("Process flow must be positive.")
    if process_outlet_target_c >= process.inlet_temperature_c:
        raise ValueError("Process outlet target must be below inlet temperature.")

    s_in = state(process, process.inlet_temperature_c, package, interaction_parameters)
    s_out = state(process, process_outlet_target_c, package, interaction_parameters)

    duty_w = process.mass_flow_kg_s * (
        s_in.specific_enthalpy_j_kg - s_out.specific_enthalpy_j_kg
    )
    if duty_w <= 0:
        raise ValueError("Process-side duty must be positive.")

    s_mean = state(
        process,
        0.5 * (process.inlet_temperature_c + process_outlet_target_c),
        package,
        interaction_parameters,
    )

    # Tube-side process.
    flow_area = (
        geometry.tube_count
        * math.pi * geometry.tube_id_m**2 / 4.0
    )
    velocity = process.mass_flow_kg_s / (
        s_mean.density_kg_m3 * flow_area
    )
    re_p = (
        s_mean.density_kg_m3
        * velocity
        * geometry.tube_id_m
        / s_mean.viscosity_pa_s
    )
    pr_p = (
        s_mean.cp_j_kgk
        * s_mean.viscosity_pa_s
        / s_mean.thermal_conductivity_w_mk
    )
    nu_p = nusselt_internal(max(re_p, 1e-9), max(pr_p, 1e-9))
    h_p = (
        nu_p
        * s_mean.thermal_conductivity_w_mk
        / geometry.tube_id_m
    )
    f_p = darcy_friction_factor(
        max(re_p, 1e-9),
        4.5e-5 / geometry.tube_id_m,
    )
    dp_p = (
        f_p * geometry.tube_length_m / geometry.tube_id_m + 1.5
    ) * s_mean.density_kg_m3 * velocity**2 / 2.0 / 1000.0

    # Air-side iteration using mean temperature estimated from outlet.
    air0 = _air_properties(air_inlet_temperature_c)
    air_mass_flow = geometry.air_flow_m3_s * air0["rho"]
    air_out = (
        air_inlet_temperature_c
        + duty_w / (air_mass_flow * air0["cp"])
    )

    air_mean_t = 0.5 * (air_inlet_temperature_c + air_out)
    air = _air_properties(air_mean_t)
    air_mass_flow = geometry.air_flow_m3_s * air["rho"]
    air_out = (
        air_inlet_temperature_c
        + duty_w / (air_mass_flow * air["cp"])
    )

    face_velocity = geometry.air_flow_m3_s / geometry.face_area_m2

    minimum_area_ratio = max(
        0.15,
        (geometry.transverse_pitch_m - geometry.fin_od_m)
        / geometry.transverse_pitch_m,
    )
    max_velocity = face_velocity / minimum_area_ratio

    re_air = air["rho"] * max_velocity * geometry.fin_od_m / air["mu"]

    # Zukauskas-style crossflow screening correlation.
    if re_air < 40:
        c, m = 0.75, 0.40
    elif re_air < 1000:
        c, m = 0.51, 0.50
    elif re_air < 200000:
        c, m = 0.27, 0.63
    else:
        c, m = 0.021, 0.84

    nu_air = c * re_air**m * air["pr"]**0.36
    h_air = nu_air * air["k"] / geometry.fin_od_m

    fin_height = 0.5 * (geometry.fin_od_m - geometry.tube_od_m)
    m_fin = math.sqrt(
        2.0 * h_air
        / (geometry.fin_k_w_mk * geometry.fin_thickness_m)
    )
    ml = m_fin * fin_height
    fin_eff = math.tanh(ml) / max(ml, 1e-12)

    a_fin = geometry.total_fin_area_m2
    a_total = geometry.total_external_area_m2
    a_bare = max(0.0, a_total - a_fin)

    surface_eff = (
        fin_eff * a_fin + a_bare
    ) / max(a_total, 1e-12)

    # Outside-area-basis U.
    do = geometry.tube_od_m
    di = geometry.tube_id_m
    r_total = (
        1.0 / max(surface_eff * h_air, 1e-9)
        + do * math.log(do / di) / (2.0 * tube_wall_k_w_mk)
        + (do / di) * (process_fouling_m2k_w + 1.0 / h_p)
    )
    u_ext = 1.0 / r_total

    dtlm = lmtd(
        process.inlet_temperature_c,
        process_outlet_target_c,
        air_inlet_temperature_c,
        air_out,
        True,
    )

    required_area = duty_w / (u_ext * dtlm)
    installed_area = geometry.total_external_area_m2
    margin = 100.0 * (installed_area / required_area - 1.0)

    # Air DP screening through rows.
    drag_coeff = 1.2 + 18.0 / math.sqrt(max(re_air, 1.0))
    air_dp = (
        geometry.rows
        * drag_coeff
        * air["rho"] * max_velocity**2 / 2.0
    )
    fan_power_kw = (
        air_dp * geometry.air_flow_m3_s
        / max(geometry.fan_efficiency, 1e-6)
        / 1000.0
    )

    warnings = []
    if dp_p > allowable_process_dp_kpa:
        warnings.append("Process-side air-cooler pressure drop exceeds allowable.")
    if margin < 0:
        warnings.append("Installed finned area is below required area.")
    if air_out >= process_outlet_target_c:
        warnings.append("Air outlet approaches/exceeds process outlet target; review temperature approach.")
    if face_velocity > 5.0:
        warnings.append("High air face velocity; review noise, fan power and bundle pressure drop.")

    warnings.append(
        "Air-side heat transfer and pressure drop are screening crossflow/finned-tube "
        "correlations; vendor fan/bundle data are required for final design."
    )

    return AirCooledHXResult(
        duty_kw=duty_w / 1000.0,
        process_outlet_c=process_outlet_target_c,
        air_outlet_c=air_out,
        process_velocity_m_s=velocity,
        process_reynolds=re_p,
        process_h_w_m2k=h_p,
        process_dp_kpa=dp_p,
        air_face_velocity_m_s=face_velocity,
        air_reynolds=re_air,
        air_h_w_m2k=h_air,
        air_dp_pa=air_dp,
        fin_efficiency=fin_eff,
        overall_surface_efficiency=surface_eff,
        overall_u_external_w_m2k=u_ext,
        required_external_area_m2=required_area,
        installed_external_area_m2=installed_area,
        area_margin_percent=margin,
        fan_power_kw=fan_power_kw,
        lmtd_c=dtlm,
        warnings=warnings,
    )
