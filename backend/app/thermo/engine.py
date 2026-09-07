from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .components import R, get_component
from .composition import (
    NormalizedComposition,
    normalize_composition,
    pure_composition,
)
from .eos import cubic_eos
from .phase_equilibrium import phase_screening


@dataclass
class ThermoState:
    temperature_c: float
    pressure_bar: float
    package: str

    mole_fractions: dict[str, float]
    mass_fractions: dict[str, float]
    mixture_mw_g_mol: float

    cp_j_kgk: float
    density_kg_m3: float
    viscosity_pa_s: float
    thermal_conductivity_w_mk: float
    specific_enthalpy_j_kg: float

    phase: str
    bubble_point_c: float | None
    dew_point_c: float | None

    z_factor: float | None
    eos_roots: list[float] | None
    activity_coefficients: dict[str, float]

    property_source: str
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _composition(
    fluid: str,
    composition: dict[str, float] | None,
    basis: str,
) -> NormalizedComposition:
    if composition:
        return normalize_composition(composition, basis)

    if fluid == "Mixture":
        raise ValueError(
            "Stream fluid is 'Mixture' but no composition was provided."
        )

    return pure_composition(fluid)


def _internal_mixture_properties(
    temperature_c: float,
    composition: NormalizedComposition,
):
    cp = sum(
        composition.mass_fractions[name]
        * get_component(name).cp_j_kgk(temperature_c)
        for name in composition.mass_fractions
    )

    h = sum(
        composition.mass_fractions[name]
        * get_component(name).sensible_enthalpy_j_kg(temperature_c)
        for name in composition.mass_fractions
    )

    specific_volume = sum(
        composition.mass_fractions[name]
        / get_component(name).liquid_density_kg_m3(temperature_c)
        for name in composition.mass_fractions
    )
    rho = 1.0 / max(specific_volume, 1e-12)

    # Logarithmic viscosity mixing on mole fraction.
    ln_mu = sum(
        composition.mole_fractions[name]
        * math.log(get_component(name).viscosity_pa_s(temperature_c))
        for name in composition.mole_fractions
    )
    mu = math.exp(ln_mu)

    k = sum(
        composition.mass_fractions[name]
        * get_component(name).thermal_conductivity_w_mk(temperature_c)
        for name in composition.mass_fractions
    )

    return cp, h, rho, mu, k


def _coolprop_pure_state(
    component: str,
    temperature_c: float,
    pressure_bar: float,
):
    try:
        import CoolProp.CoolProp as CP
    except Exception as exc:
        raise RuntimeError("CoolProp is not installed.") from exc

    mapping = {
        "Water": "Water",
        "Ethanol": "Ethanol",
        "Acetone": "Acetone",
    }

    cp_name = mapping.get(component)
    if cp_name is None:
        raise ValueError(
            f"CoolProp pure-fluid mapping is not configured for '{component}'."
        )

    t_k = temperature_c + 273.15
    p_pa = pressure_bar * 1e5

    return {
        "cp": float(CP.PropsSI("C", "T", t_k, "P", p_pa, cp_name)),
        "rho": float(CP.PropsSI("D", "T", t_k, "P", p_pa, cp_name)),
        "mu": float(CP.PropsSI("V", "T", t_k, "P", p_pa, cp_name)),
        "k": float(CP.PropsSI("L", "T", t_k, "P", p_pa, cp_name)),
        "h": float(CP.PropsSI("H", "T", t_k, "P", p_pa, cp_name)),
    }


def evaluate_state(
    fluid: str,
    temperature_c: float,
    pressure_bar: float,
    package: str = "Ideal mixture",
    composition: dict[str, float] | None = None,
    composition_basis: str = "mole",
    interaction_parameters: dict | None = None,
) -> ThermoState:
    if pressure_bar <= 0:
        raise ValueError("Pressure must be positive.")

    comp = _composition(fluid, composition, composition_basis)
    package = package.strip()

    warnings: list[str] = []

    phase = phase_screening(
        temperature_c,
        pressure_bar,
        comp,
        package,
        interaction_parameters,
    )
    warnings.extend(phase.warnings)

    # Pure-fluid CoolProp route
    if package == "CoolProp (pure only)" and len(comp.mole_fractions) == 1:
        name = next(iter(comp.mole_fractions))

        try:
            cp_state = _coolprop_pure_state(
                name,
                temperature_c,
                pressure_bar,
            )

            return ThermoState(
                temperature_c=temperature_c,
                pressure_bar=pressure_bar,
                package=package,
                mole_fractions=comp.mole_fractions,
                mass_fractions=comp.mass_fractions,
                mixture_mw_g_mol=comp.mixture_mw_g_mol,
                cp_j_kgk=cp_state["cp"],
                density_kg_m3=cp_state["rho"],
                viscosity_pa_s=cp_state["mu"],
                thermal_conductivity_w_mk=cp_state["k"],
                specific_enthalpy_j_kg=cp_state["h"],
                phase=phase.phase,
                bubble_point_c=phase.bubble_point_c,
                dew_point_c=phase.dew_point_c,
                z_factor=None,
                eos_roots=None,
                activity_coefficients=phase.activity_coefficients,
                property_source="CoolProp",
                warnings=warnings,
            )
        except Exception as exc:
            warnings.append(
                f"CoolProp evaluation failed ({exc}); internal temperature-dependent "
                "screening properties were used instead."
            )

    elif package == "CoolProp (pure only)" and len(comp.mole_fractions) > 1:
        warnings.append(
            "CoolProp (pure only) was selected for a mixture. "
            "HX-RACE internal mixture properties were used."
        )

    cp, h, rho_liq, mu, k = _internal_mixture_properties(
        temperature_c,
        comp,
    )

    z_factor = None
    eos_roots = None

    if package in {"Peng-Robinson", "SRK"}:
        try:
            eos = cubic_eos(
                package,
                temperature_c,
                pressure_bar,
                comp,
                kij=(interaction_parameters or {}).get("KIJ"),
            )
            eos_roots = eos.roots
            warnings.extend(eos.warnings)

            if phase.phase == "Liquid":
                z_factor = eos.z_liquid
            else:
                z_factor = eos.z_vapor

            # EOS density is used only for states screened as vapour.
            if phase.phase == "Vapour" and z_factor > 0:
                mw_kg_mol = comp.mixture_mw_g_mol / 1000.0
                rho = (
                    pressure_bar * 1e5 * mw_kg_mol
                    / (z_factor * R * (temperature_c + 273.15))
                )
            else:
                rho = rho_liq

        except Exception as exc:
            rho = rho_liq
            warnings.append(
                f"{package} EOS diagnostic unavailable ({exc}); "
                "liquid-mixing density was retained."
            )
    else:
        rho = rho_liq

    if package in {"NRTL", "UNIQUAC"} and interaction_parameters is None:
        warnings.append(
            f"{package} selected without an interaction-parameter file. "
            "Missing binary parameters default toward ideal behaviour."
        )

    if phase.phase == "Two-phase screening region":
        warnings.append(
            "State lies inside the v0.5 phase-screening region. "
            "Latent heat and rigorous two-phase transport are not yet included."
        )

    return ThermoState(
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        package=package,
        mole_fractions=comp.mole_fractions,
        mass_fractions=comp.mass_fractions,
        mixture_mw_g_mol=comp.mixture_mw_g_mol,
        cp_j_kgk=cp,
        density_kg_m3=rho,
        viscosity_pa_s=mu,
        thermal_conductivity_w_mk=k,
        specific_enthalpy_j_kg=h,
        phase=phase.phase,
        bubble_point_c=phase.bubble_point_c,
        dew_point_c=phase.dew_point_c,
        z_factor=z_factor,
        eos_roots=eos_roots,
        activity_coefficients=phase.activity_coefficients,
        property_source="HX-RACE temperature-dependent mixture engine",
        warnings=warnings,
    )


def solve_temperature_for_enthalpy(
    target_h_j_kg: float,
    fluid: str,
    pressure_bar: float,
    package: str,
    composition: dict[str, float] | None,
    composition_basis: str,
    interaction_parameters: dict | None = None,
    low_c: float = -100.0,
    high_c: float = 450.0,
) -> float:
    def residual(t: float) -> float:
        return (
            evaluate_state(
                fluid=fluid,
                temperature_c=t,
                pressure_bar=pressure_bar,
                package=package,
                composition=composition,
                composition_basis=composition_basis,
                interaction_parameters=interaction_parameters,
            ).specific_enthalpy_j_kg
            - target_h_j_kg
        )

    f_low = residual(low_c)
    f_high = residual(high_c)

    if f_low * f_high > 0:
        raise ValueError(
            "Target enthalpy is outside the current sensible-temperature solver range."
        )

    for _ in range(90):
        mid = 0.5 * (low_c + high_c)
        f_mid = residual(mid)

        if abs(f_mid) < 0.1:
            return mid

        if f_low * f_mid <= 0:
            high_c = mid
            f_high = f_mid
        else:
            low_c = mid
            f_low = f_mid

    return 0.5 * (low_c + high_c)
