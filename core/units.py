from __future__ import annotations

import math


UNIT_SYSTEMS = [
    "SI Engineering",
    "Metric Plant",
    "US Customary",
]


def _f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def _psi_from_kpa(kpa: float) -> float:
    return kpa * 0.1450377377


def _ft2(m2: float) -> float:
    return m2 * 10.7639104167


def _btu_h_ft2_f(u_si: float) -> float:
    return u_si * 0.1761101838


def _mmbtu_h_from_kw(kw: float) -> float:
    return kw * 0.003412141633


def _lb_h_from_kg_s(kg_s: float) -> float:
    return kg_s * 7936.641438


def build_display_summary(
    result,
    hot_mass_flow_kg_s: float,
    cold_mass_flow_kg_s: float,
    unit_system: str,
) -> list[dict]:
    """
    Convert the main result dashboard only.

    HX//RACE calculations remain internally SI. This function is deliberately
    a display layer so unit conversion cannot change the engineering solver.
    """
    if unit_system == "US Customary":
        return [
            {"Parameter": "Duty", "Value": f"{_mmbtu_h_from_kw(result.duty_kw):,.3f}", "Unit": "MMBtu/h"},
            {"Parameter": "Hot outlet", "Value": f"{_f(result.hot_outlet_c):,.2f}", "Unit": "°F"},
            {"Parameter": "Cold outlet", "Value": f"{_f(result.cold_outlet_c):,.2f}", "Unit": "°F"},
            {"Parameter": "LMTD", "Value": f"{result.lmtd_c * 9.0/5.0:,.2f}", "Unit": "°F"},
            {"Parameter": "Overall U", "Value": f"{_btu_h_ft2_f(result.overall_u_w_m2k):,.2f}", "Unit": "Btu/h·ft²·°F"},
            {"Parameter": "Required area", "Value": f"{_ft2(result.required_area_m2):,.1f}", "Unit": "ft²"},
            {"Parameter": "Installed area", "Value": f"{_ft2(result.installed_area_m2):,.1f}", "Unit": "ft²"},
            {"Parameter": "Tube ΔP", "Value": f"{_psi_from_kpa(result.tube_dp_kpa):,.2f}", "Unit": "psi"},
            {"Parameter": "Shell ΔP", "Value": f"{_psi_from_kpa(result.shell_dp_kpa):,.2f}", "Unit": "psi"},
            {"Parameter": "Hot flow", "Value": f"{_lb_h_from_kg_s(hot_mass_flow_kg_s):,.0f}", "Unit": "lb/h"},
            {"Parameter": "Cold flow", "Value": f"{_lb_h_from_kg_s(cold_mass_flow_kg_s):,.0f}", "Unit": "lb/h"},
        ]

    if unit_system == "Metric Plant":
        return [
            {"Parameter": "Duty", "Value": f"{result.duty_kw/1000.0:,.4f}", "Unit": "MW"},
            {"Parameter": "Hot outlet", "Value": f"{result.hot_outlet_c:,.2f}", "Unit": "°C"},
            {"Parameter": "Cold outlet", "Value": f"{result.cold_outlet_c:,.2f}", "Unit": "°C"},
            {"Parameter": "LMTD", "Value": f"{result.lmtd_c:,.2f}", "Unit": "°C"},
            {"Parameter": "Overall U", "Value": f"{result.overall_u_w_m2k:,.1f}", "Unit": "W/m²·K"},
            {"Parameter": "Required area", "Value": f"{result.required_area_m2:,.2f}", "Unit": "m²"},
            {"Parameter": "Installed area", "Value": f"{result.installed_area_m2:,.2f}", "Unit": "m²"},
            {"Parameter": "Tube ΔP", "Value": f"{result.tube_dp_kpa/100.0:,.3f}", "Unit": "bar"},
            {"Parameter": "Shell ΔP", "Value": f"{result.shell_dp_kpa/100.0:,.3f}", "Unit": "bar"},
            {"Parameter": "Hot flow", "Value": f"{hot_mass_flow_kg_s*3600.0:,.1f}", "Unit": "kg/h"},
            {"Parameter": "Cold flow", "Value": f"{cold_mass_flow_kg_s*3600.0:,.1f}", "Unit": "kg/h"},
        ]

    return [
        {"Parameter": "Duty", "Value": f"{result.duty_kw:,.2f}", "Unit": "kW"},
        {"Parameter": "Hot outlet", "Value": f"{result.hot_outlet_c:,.2f}", "Unit": "°C"},
        {"Parameter": "Cold outlet", "Value": f"{result.cold_outlet_c:,.2f}", "Unit": "°C"},
        {"Parameter": "LMTD", "Value": f"{result.lmtd_c:,.2f}", "Unit": "°C"},
        {"Parameter": "Overall U", "Value": f"{result.overall_u_w_m2k:,.1f}", "Unit": "W/m²·K"},
        {"Parameter": "Required area", "Value": f"{result.required_area_m2:,.2f}", "Unit": "m²"},
        {"Parameter": "Installed area", "Value": f"{result.installed_area_m2:,.2f}", "Unit": "m²"},
        {"Parameter": "Tube ΔP", "Value": f"{result.tube_dp_kpa:,.2f}", "Unit": "kPa"},
        {"Parameter": "Shell ΔP", "Value": f"{result.shell_dp_kpa:,.2f}", "Unit": "kPa"},
        {"Parameter": "Hot flow", "Value": f"{hot_mass_flow_kg_s:,.3f}", "Unit": "kg/s"},
        {"Parameter": "Cold flow", "Value": f"{cold_mass_flow_kg_s:,.3f}", "Unit": "kg/s"},
    ]
