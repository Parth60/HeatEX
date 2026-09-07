from __future__ import annotations

from dataclasses import dataclass
import math

from .components import get_component
from .composition import NormalizedComposition
from .activity import (
    nrtl_activity_coefficients,
    uniquac_activity_coefficients,
)


@dataclass
class PhaseScreeningResult:
    phase: str
    bubble_point_c: float | None
    dew_point_c: float | None
    activity_coefficients: dict[str, float]
    warnings: list[str]


def _gammas(
    package: str,
    temperature_c: float,
    composition: NormalizedComposition,
    interaction_parameters: dict | None,
):
    if package == "NRTL":
        return nrtl_activity_coefficients(
            temperature_c,
            composition,
            interaction_parameters,
        )

    if package == "UNIQUAC":
        return uniquac_activity_coefficients(
            temperature_c,
            composition,
            interaction_parameters,
        )

    class Ideal:
        activity_coefficients = {
            name: 1.0 for name in composition.mole_fractions
        }
        warnings = []

    return Ideal()


def _bubble_residual(
    temperature_c: float,
    pressure_pa: float,
    composition: NormalizedComposition,
    package: str,
    interaction_parameters: dict | None,
) -> float | None:
    gammas = _gammas(
        package,
        temperature_c,
        composition,
        interaction_parameters,
    ).activity_coefficients

    total = 0.0

    for name, xi in composition.mole_fractions.items():
        psat = get_component(name).saturation_pressure_pa(temperature_c)
        if psat is None:
            return None
        total += xi * gammas.get(name, 1.0) * psat

    return total - pressure_pa


def _dew_residual_ideal(
    temperature_c: float,
    pressure_pa: float,
    composition: NormalizedComposition,
) -> float | None:
    total = 0.0

    for name, yi in composition.mole_fractions.items():
        psat = get_component(name).saturation_pressure_pa(temperature_c)
        if psat is None or psat <= 0:
            return None
        total += yi * pressure_pa / psat

    return total - 1.0


def _bisect(function, low: float, high: float) -> float | None:
    f_low = function(low)
    f_high = function(high)

    if f_low is None or f_high is None:
        return None

    if f_low == 0:
        return low
    if f_high == 0:
        return high

    if f_low * f_high > 0:
        return None

    for _ in range(90):
        mid = 0.5 * (low + high)
        f_mid = function(mid)

        if f_mid is None:
            return None

        if abs(f_mid) < 1e-6:
            return mid

        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return 0.5 * (low + high)


def phase_screening(
    temperature_c: float,
    pressure_bar: float,
    composition: NormalizedComposition,
    package: str,
    interaction_parameters: dict | None = None,
) -> PhaseScreeningResult:
    pressure_pa = pressure_bar * 1e5
    warnings: list[str] = []

    real_components = []
    for name in composition.mole_fractions:
        c = get_component(name)
        if c.tc_k is None or c.pc_pa is None or c.acentric_factor is None:
            warnings.append(
                f"VLE screening unavailable for pseudo-component '{name}'."
            )
        else:
            real_components.append(c)

    gamma_result = _gammas(
        package,
        temperature_c,
        composition,
        interaction_parameters,
    )
    warnings.extend(gamma_result.warnings)

    if len(real_components) != len(composition.mole_fractions):
        return PhaseScreeningResult(
            phase="Unknown",
            bubble_point_c=None,
            dew_point_c=None,
            activity_coefficients=gamma_result.activity_coefficients,
            warnings=warnings,
        )

    tc_min_c = min(c.tc_k for c in real_components) - 273.15
    upper = min(450.0, tc_min_c - 0.5)
    lower = -100.0

    bubble = _bisect(
        lambda t: _bubble_residual(
            t,
            pressure_pa,
            composition,
            package,
            interaction_parameters,
        ),
        lower,
        upper,
    )

    # Dew-point diagnostic remains ideal in v0.5.
    dew = _bisect(
        lambda t: _dew_residual_ideal(
            t,
            pressure_pa,
            composition,
        ),
        lower,
        upper,
    )

    if package in {"NRTL", "UNIQUAC"} and len(composition.mole_fractions) > 1:
        warnings.append(
            "v0.5 dew-point diagnostic uses an ideal-vapour/ideal-dew screening "
            "solver; rigorous gamma-phi dew solving is reserved for the phase-change build."
        )

    if bubble is None or dew is None:
        phase = "Unknown"
    else:
        low_boundary = min(bubble, dew)
        high_boundary = max(bubble, dew)

        if temperature_c < low_boundary - 0.2:
            phase = "Liquid"
        elif temperature_c > high_boundary + 0.2:
            phase = "Vapour"
        else:
            phase = "Two-phase screening region"

    return PhaseScreeningResult(
        phase=phase,
        bubble_point_c=bubble,
        dew_point_c=dew,
        activity_coefficients=gamma_result.activity_coefficients,
        warnings=warnings,
    )
