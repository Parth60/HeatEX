from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .components import R, get_component
from .composition import normalize_composition
from .flash import FlashResult, flash_isothermal
from .phase_change import pure_phase_enthalpy_j_kg


@dataclass(frozen=True)
class PhaseProperties:
    cp_j_kgk: float
    density_kg_m3: float
    viscosity_pa_s: float
    thermal_conductivity_w_mk: float
    mixture_mw_g_mol: float


@dataclass
class EquilibriumMixtureState:
    temperature_c: float
    pressure_bar: float
    package: str

    vapour_fraction_molar: float
    vapour_fraction_mass: float

    liquid_mole_fractions: dict[str, float]
    vapour_mole_fractions: dict[str, float]

    liquid_mass_fractions: dict[str, float]
    vapour_mass_fractions: dict[str, float]

    liquid_enthalpy_j_kg: float
    vapour_enthalpy_j_kg: float
    overall_enthalpy_j_kg: float

    liquid_properties: dict
    vapour_properties: dict

    flash: dict
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _mole_to_mass(mole: dict[str, float]) -> tuple[dict[str, float], float]:
    if not mole:
        return {}, 0.0

    numerator = {
        name: xi * get_component(name).mw_g_mol
        for name, xi in mole.items()
    }
    total = sum(numerator.values())

    if total <= 0:
        raise ValueError("Phase molecular-weight normalization failed.")

    mass = {
        name: value / total
        for name, value in numerator.items()
    }

    mw = sum(
        mole[name] * get_component(name).mw_g_mol
        for name in mole
    )

    return mass, mw


def _liquid_properties(
    temperature_c: float,
    mole: dict[str, float],
    mass: dict[str, float],
) -> PhaseProperties:
    if not mass:
        return PhaseProperties(
            cp_j_kgk=1.0,
            density_kg_m3=1.0,
            viscosity_pa_s=1e-3,
            thermal_conductivity_w_mk=0.1,
            mixture_mw_g_mol=1.0,
        )

    cp = sum(
        wi * get_component(name).cp_j_kgk(temperature_c)
        for name, wi in mass.items()
    )

    specific_volume = sum(
        wi / get_component(name).liquid_density_kg_m3(temperature_c)
        for name, wi in mass.items()
    )
    rho = 1.0 / max(specific_volume, 1e-12)

    ln_mu = sum(
        mole[name]
        * math.log(get_component(name).viscosity_pa_s(temperature_c))
        for name in mole
    )
    mu = math.exp(ln_mu)

    k = sum(
        wi * get_component(name).thermal_conductivity_w_mk(temperature_c)
        for name, wi in mass.items()
    )

    mw = sum(
        mole[name] * get_component(name).mw_g_mol
        for name in mole
    )

    return PhaseProperties(
        cp_j_kgk=cp,
        density_kg_m3=rho,
        viscosity_pa_s=mu,
        thermal_conductivity_w_mk=k,
        mixture_mw_g_mol=mw,
    )


def _vapour_properties(
    temperature_c: float,
    pressure_bar: float,
    mole: dict[str, float],
    mass: dict[str, float],
) -> PhaseProperties:
    if not mass:
        return PhaseProperties(
            cp_j_kgk=1.0,
            density_kg_m3=0.1,
            viscosity_pa_s=1e-5,
            thermal_conductivity_w_mk=0.02,
            mixture_mw_g_mol=1.0,
        )

    cp = sum(
        wi * get_component(name).vapour_cp_j_kgk(temperature_c)
        for name, wi in mass.items()
    )

    mw_g_mol = sum(
        mole[name] * get_component(name).mw_g_mol
        for name in mole
    )
    mw_kg_mol = mw_g_mol / 1000.0

    rho = (
        pressure_bar * 1e5 * mw_kg_mol
        / (R * (temperature_c + 273.15))
    )

    # Low-pressure vapour transport screening values.
    # Component dependence is retained through MW and weighting.
    mu = sum(
        mole[name]
        * max(7.0e-6, min(2.5e-5, 8.0e-6 + 5.0e-8 * get_component(name).mw_g_mol))
        for name in mole
    )

    k = sum(
        mole[name]
        * max(0.012, min(0.040, 0.014 + 5.0e-5 * get_component(name).mw_g_mol))
        for name in mole
    )

    return PhaseProperties(
        cp_j_kgk=cp,
        density_kg_m3=max(0.001, rho),
        viscosity_pa_s=mu,
        thermal_conductivity_w_mk=k,
        mixture_mw_g_mol=mw_g_mol,
    )


def _phase_enthalpy(
    temperature_c: float,
    pressure_bar: float,
    mass_fractions: dict[str, float],
    phase: str,
) -> float:
    if not mass_fractions:
        return 0.0

    return sum(
        wi
        * pure_phase_enthalpy_j_kg(
            component=name,
            temperature_c=temperature_c,
            pressure_bar=pressure_bar,
            phase=phase,
        )
        for name, wi in mass_fractions.items()
    )


def equilibrium_mixture_state(
    temperature_c: float,
    pressure_bar: float,
    fractions: dict[str, float],
    composition_basis: str,
    package: str,
    interaction_parameters: dict | None = None,
) -> EquilibriumMixtureState:
    flash = flash_isothermal(
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        fractions=fractions,
        composition_basis=composition_basis,
        package=package,
        interaction_parameters=interaction_parameters,
    )

    x = flash.liquid_mole_fractions
    y = flash.vapour_mole_fractions

    w_l, mw_l = _mole_to_mass(x)
    w_v, mw_v = _mole_to_mass(y)

    beta = flash.vapour_fraction

    liquid_molar_share = max(0.0, 1.0 - beta)
    vapour_molar_share = max(0.0, beta)

    liquid_mass_basis = liquid_molar_share * mw_l
    vapour_mass_basis = vapour_molar_share * mw_v
    total_mass_basis = liquid_mass_basis + vapour_mass_basis

    if total_mass_basis <= 0:
        vapour_mass_fraction = beta
    else:
        vapour_mass_fraction = vapour_mass_basis / total_mass_basis

    h_l = _phase_enthalpy(
        temperature_c,
        pressure_bar,
        w_l,
        "liquid",
    )
    h_v = _phase_enthalpy(
        temperature_c,
        pressure_bar,
        w_v,
        "vapour",
    )

    h_overall = (
        (1.0 - vapour_mass_fraction) * h_l
        + vapour_mass_fraction * h_v
    )

    lp = _liquid_properties(temperature_c, x, w_l)
    vp = _vapour_properties(temperature_c, pressure_bar, y, w_v)

    warnings = list(flash.warnings)
    warnings.append(
        "Mixture phase enthalpy is an HX-RACE screening model built from "
        "component sensible enthalpies plus pure-component Watson latent heats."
    )

    return EquilibriumMixtureState(
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        package=package,
        vapour_fraction_molar=beta,
        vapour_fraction_mass=vapour_mass_fraction,
        liquid_mole_fractions=x,
        vapour_mole_fractions=y,
        liquid_mass_fractions=w_l,
        vapour_mass_fractions=w_v,
        liquid_enthalpy_j_kg=h_l,
        vapour_enthalpy_j_kg=h_v,
        overall_enthalpy_j_kg=h_overall,
        liquid_properties=asdict(lp),
        vapour_properties=asdict(vp),
        flash=flash.as_dict(),
        warnings=warnings,
    )


def effective_latent_heat_j_kg(
    temperature_c: float,
    pressure_bar: float,
    vapour_mass_fractions: dict[str, float],
) -> float:
    total = 0.0
    weight = 0.0

    for name, wi in vapour_mass_fractions.items():
        c = get_component(name)
        try:
            # Use the pure-component latent heat at its pure saturation
            # temperature at the system pressure.
            from .phase_change import get_saturation_state

            sat = get_saturation_state(name, pressure_bar)
            hfg = sat.latent_heat_j_kg
        except Exception:
            hfg = c.latent_heat_nbp_j_kg or 0.0

        total += wi * hfg
        weight += wi

    if weight <= 0:
        return 1.0

    return max(1.0, total / weight)
