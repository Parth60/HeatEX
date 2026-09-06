from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FluidProperties:
    cp_j_kgk: float
    rho_kg_m3: float
    mu_pa_s: float
    k_w_mk: float
    source: str


FALLBACK_PROPERTIES = {
    "Water": FluidProperties(4180.0, 997.0, 0.00089, 0.600, "HX-RACE fallback database"),
    "Ethanol": FluidProperties(2550.0, 789.0, 0.00120, 0.171, "HX-RACE fallback database"),
    "Butanol": FluidProperties(2450.0, 810.0, 0.00260, 0.155, "HX-RACE fallback database"),
    "Acetone": FluidProperties(2160.0, 784.0, 0.00032, 0.160, "HX-RACE fallback database"),
    "Thermal oil": FluidProperties(2100.0, 850.0, 0.01200, 0.125, "HX-RACE fallback database"),
    "Light hydrocarbon": FluidProperties(2200.0, 680.0, 0.00055, 0.130, "HX-RACE fallback database"),
}


COOLPROP_NAMES = {
    "Water": "Water",
    "Ethanol": "Ethanol",
    "Acetone": "Acetone",
}


def get_properties(
    fluid: str,
    temperature_c: float,
    pressure_bar: float = 1.01325,
    package: str = "Fallback database",
) -> FluidProperties:
    """
    Return single-phase properties at the requested state.

    CoolProp is used when selected and available. Unsupported fluids/packages
    fall back to the internal screening database so the app remains usable.
    """
    if package == "CoolProp":
        try:
            import CoolProp.CoolProp as CP

            cp_name = COOLPROP_NAMES.get(fluid)
            if cp_name is not None:
                t_k = temperature_c + 273.15
                p_pa = pressure_bar * 1e5

                cp = CP.PropsSI("C", "T", t_k, "P", p_pa, cp_name)
                rho = CP.PropsSI("D", "T", t_k, "P", p_pa, cp_name)
                mu = CP.PropsSI("V", "T", t_k, "P", p_pa, cp_name)
                k = CP.PropsSI("L", "T", t_k, "P", p_pa, cp_name)

                return FluidProperties(
                    cp_j_kgk=float(cp),
                    rho_kg_m3=float(rho),
                    mu_pa_s=float(mu),
                    k_w_mk=float(k),
                    source="CoolProp",
                )
        except Exception:
            pass

    if fluid not in FALLBACK_PROPERTIES:
        raise ValueError(f"Fluid '{fluid}' is not available in the current property database.")

    return FALLBACK_PROPERTIES[fluid]
