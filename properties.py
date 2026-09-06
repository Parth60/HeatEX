from __future__ import annotations

from dataclasses import dataclass

try:
    from CoolProp.CoolProp import PropsSI  # type: ignore
except Exception:  # pragma: no cover
    PropsSI = None

from app.models import PropertyState, ThermoPackage


FALLBACK = {
    "Water": (4180.0, 997.0, 0.00089, 0.60),
    "Ethanol": (2550.0, 789.0, 0.00120, 0.171),
    "n-Butanol": (2450.0, 810.0, 0.00260, 0.155),
    "Butanol": (2450.0, 810.0, 0.00260, 0.155),
    "Toluene": (1710.0, 867.0, 0.00059, 0.130),
}

COOLPROP_NAMES = {
    "Water": "Water",
    "Ethanol": "Ethanol",
    "Butanol": "n-Butanol",
    "n-Butanol": "n-Butanol",
    "Toluene": "Toluene",
}


def _fallback(fluid: str) -> PropertyState:
    cp, rho, mu, k = FALLBACK.get(fluid, FALLBACK["Water"])
    return PropertyState(cp_j_kgk=cp, rho_kg_m3=rho, mu_pa_s=mu, k_w_mk=k, source="fallback-property-database")


def properties(fluid: str, temp_c: float, pressure_bar: float, package: ThermoPackage) -> PropertyState:
    # IAPWS is represented via CoolProp's IF97 backend for water.
    if package == ThermoPackage.iapws and fluid == "Water" and PropsSI is not None:
        cp = PropsSI("C", "T", temp_c + 273.15, "P", pressure_bar * 1e5, "IF97::Water")
        rho = PropsSI("D", "T", temp_c + 273.15, "P", pressure_bar * 1e5, "IF97::Water")
        mu = PropsSI("V", "T", temp_c + 273.15, "P", pressure_bar * 1e5, "IF97::Water")
        k = PropsSI("L", "T", temp_c + 273.15, "P", pressure_bar * 1e5, "IF97::Water")
        return PropertyState(cp_j_kgk=cp, rho_kg_m3=rho, mu_pa_s=mu, k_w_mk=k, source="CoolProp IF97")

    if package == ThermoPackage.coolprop and PropsSI is not None:
        cp_name = COOLPROP_NAMES.get(fluid)
        if cp_name:
            try:
                cp = PropsSI("C", "T", temp_c + 273.15, "P", pressure_bar * 1e5, cp_name)
                rho = PropsSI("D", "T", temp_c + 273.15, "P", pressure_bar * 1e5, cp_name)
                mu = PropsSI("V", "T", temp_c + 273.15, "P", pressure_bar * 1e5, cp_name)
                k = PropsSI("L", "T", temp_c + 273.15, "P", pressure_bar * 1e5, cp_name)
                return PropertyState(cp_j_kgk=cp, rho_kg_m3=rho, mu_pa_s=mu, k_w_mk=k, source="CoolProp PropsSI")
            except Exception:
                pass

    # EOS/activity-coefficient package selection is wired into the API now, but a
    # proper multicomponent flash/property layer is a separate engine module.
    # Until enabled, provide a clearly tagged fallback instead of pretending the
    # named package has been solved.
    state = _fallback(fluid)
    if package not in (ThermoPackage.ideal, ThermoPackage.coolprop):
        state.source = f"fallback (selected {package.value}; mixture engine not enabled yet)"
    return state
