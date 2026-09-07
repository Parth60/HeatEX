from __future__ import annotations

from dataclasses import dataclass
import math

from .components import get_component


@dataclass(frozen=True)
class SaturationState:
    component: str
    pressure_bar: float
    saturation_temperature_c: float
    latent_heat_j_kg: float
    liquid_density_kg_m3: float
    vapour_density_kg_m3: float
    liquid_viscosity_pa_s: float
    liquid_k_w_mk: float
    liquid_cp_j_kgk: float
    vapour_cp_j_kgk: float
    source: str


def saturation_temperature_c(
    component: str,
    pressure_bar: float,
) -> float:
    if pressure_bar <= 0:
        raise ValueError("Pressure must be positive.")

    c = get_component(component)

    if c.tc_k is None or c.pc_pa is None:
        raise ValueError(
            f"Saturation calculation is unavailable for '{component}'."
        )

    target = pressure_bar * 1e5

    low = -120.0
    high = min(450.0, c.tc_k - 273.15 - 0.01)

    def residual(t_c: float) -> float:
        psat = c.saturation_pressure_pa(t_c)
        if psat is None:
            raise ValueError("Saturation-pressure model unavailable.")
        return psat - target

    f_low = residual(low)
    f_high = residual(high)

    if f_low * f_high > 0:
        raise ValueError(
            "Requested pressure is outside the component saturation-model range."
        )

    for _ in range(100):
        mid = 0.5 * (low + high)
        f_mid = residual(mid)

        if abs(f_mid) < 1e-3:
            return mid

        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return 0.5 * (low + high)


def get_saturation_state(
    component: str,
    pressure_bar: float,
) -> SaturationState:
    c = get_component(component)

    t_sat = saturation_temperature_c(component, pressure_bar)
    hfg = c.latent_heat_j_kg(t_sat)

    if hfg is None or hfg <= 0:
        raise ValueError(
            f"Latent-heat fallback data are unavailable for '{component}'."
        )

    rho_l = c.liquid_density_kg_m3(t_sat)
    mu_l = c.viscosity_pa_s(t_sat)
    k_l = c.thermal_conductivity_w_mk(t_sat)
    cp_l = c.cp_j_kgk(t_sat)
    cp_v = c.vapour_cp_j_kgk(t_sat)

    # Ideal-gas vapour-density screening at saturation.
    rho_v = (
        pressure_bar
        * 1e5
        * c.mw_kg_mol
        / (8.31446261815324 * (t_sat + 273.15))
    )

    return SaturationState(
        component=component,
        pressure_bar=pressure_bar,
        saturation_temperature_c=t_sat,
        latent_heat_j_kg=hfg,
        liquid_density_kg_m3=rho_l,
        vapour_density_kg_m3=max(0.001, rho_v),
        liquid_viscosity_pa_s=mu_l,
        liquid_k_w_mk=k_l,
        liquid_cp_j_kgk=cp_l,
        vapour_cp_j_kgk=cp_v,
        source="HX-RACE Watson + corresponding-states saturation fallback",
    )


def pure_phase_enthalpy_j_kg(
    component: str,
    temperature_c: float,
    pressure_bar: float,
    phase: str,
    quality: float | None = None,
) -> float:
    """
    Phase-aware fallback enthalpy on an arbitrary 25 °C liquid reference.

    It is internally consistent for phase-change duty calculations:
      saturated vapour = saturated liquid + h_fg
    """
    c = get_component(component)
    sat = get_saturation_state(component, pressure_bar)

    t_sat = sat.saturation_temperature_c

    h_liq_sat = c.sensible_enthalpy_j_kg(
        t_sat,
        reference_temperature_c=25.0,
        phase="liquid",
    )

    h_vap_sat = h_liq_sat + sat.latent_heat_j_kg

    phase_l = phase.lower()

    if phase_l.startswith("liq"):
        return c.sensible_enthalpy_j_kg(
            temperature_c,
            reference_temperature_c=25.0,
            phase="liquid",
        )

    if phase_l.startswith("vap"):
        superheat = c.sensible_enthalpy_j_kg(
            temperature_c,
            reference_temperature_c=t_sat,
            phase="vapour",
        )
        return h_vap_sat + superheat

    if phase_l.startswith("two") or phase_l.startswith("sat"):
        x = 0.0 if quality is None else max(0.0, min(1.0, quality))
        return h_liq_sat + x * sat.latent_heat_j_kg

    raise ValueError(f"Unsupported phase '{phase}'.")
