from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .components import R, get_component
from .composition import NormalizedComposition, normalize_composition
from .eos import cubic_eos
from .activity import (
    nrtl_activity_coefficients,
    uniquac_activity_coefficients,
)


@dataclass
class FlashResult:
    package: str
    temperature_c: float
    pressure_bar: float
    feed_mole_fractions: dict[str, float]

    phase: str
    vapour_fraction: float

    liquid_mole_fractions: dict[str, float]
    vapour_mole_fractions: dict[str, float]
    k_values: dict[str, float]

    liquid_z: float | None
    vapour_z: float | None

    liquid_fugacity_coefficients: dict[str, float] | None
    vapour_fugacity_coefficients: dict[str, float] | None
    activity_coefficients: dict[str, float]

    iterations: int
    converged: bool
    residual: float
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def wilson_k_values(
    temperature_c: float,
    pressure_bar: float,
    composition: NormalizedComposition,
) -> dict[str, float]:
    """
    Wilson K-value estimate:

        ln Ki = ln(Pci/P) + 5.373(1+omega_i)(1-Tci/T)

    Used as an initial estimate for cubic-EOS flash calculations.
    """
    t = temperature_c + 273.15
    p = pressure_bar * 1e5

    if t <= 0 or p <= 0:
        raise ValueError("Temperature and pressure must be positive.")

    result = {}

    for name in composition.mole_fractions:
        c = get_component(name)

        if c.tc_k is None or c.pc_pa is None or c.acentric_factor is None:
            raise ValueError(
                f"Wilson K calculation requires Tc/Pc/omega; '{name}' "
                "is currently a pseudo-component."
            )

        ln_k = (
            math.log(c.pc_pa / p)
            + 5.373
            * (1.0 + c.acentric_factor)
            * (1.0 - c.tc_k / t)
        )

        result[name] = max(1e-12, min(1e12, math.exp(ln_k)))

    return result


def rachford_rice_residual(
    beta: float,
    z: dict[str, float],
    k: dict[str, float],
) -> float:
    value = 0.0

    for name, zi in z.items():
        ki = k[name]
        denominator = 1.0 + beta * (ki - 1.0)

        if denominator <= 0:
            raise ValueError(
                "Rachford-Rice denominator became non-positive."
            )

        value += zi * (ki - 1.0) / denominator

    return value


def solve_rachford_rice(
    z: dict[str, float],
    k: dict[str, float],
    tol: float = 1e-12,
    max_iter: int = 200,
) -> tuple[float, str, float]:
    """
    Solve vapour fraction beta in [0,1].

    Returns:
        beta, phase_label, residual
    """
    f0 = rachford_rice_residual(0.0, z, k)
    f1 = rachford_rice_residual(1.0, z, k)

    if f0 <= 0.0:
        return 0.0, "Liquid", f0

    if f1 >= 0.0:
        return 1.0, "Vapour", f1

    low = 0.0
    high = 1.0
    f_low = f0

    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        f_mid = rachford_rice_residual(mid, z, k)

        if abs(f_mid) < tol:
            return mid, "Two-phase", f_mid

        if f_low * f_mid <= 0:
            high = mid
        else:
            low = mid
            f_low = f_mid

    beta = 0.5 * (low + high)
    return beta, "Two-phase", rachford_rice_residual(beta, z, k)


def phase_compositions(
    z: dict[str, float],
    k: dict[str, float],
    beta: float,
) -> tuple[dict[str, float], dict[str, float]]:
    x = {}
    y = {}

    for name, zi in z.items():
        denominator = 1.0 + beta * (k[name] - 1.0)
        xi = zi / denominator
        yi = k[name] * xi

        x[name] = max(0.0, xi)
        y[name] = max(0.0, yi)

    sx = sum(x.values())
    sy = sum(y.values())

    if sx <= 0 or sy <= 0:
        raise ValueError("Invalid phase-composition normalization.")

    x = {name: value / sx for name, value in x.items()}
    y = {name: value / sy for name, value in y.items()}

    return x, y


def _ideal_or_gamma_k(
    package: str,
    temperature_c: float,
    pressure_bar: float,
    feed: NormalizedComposition,
    liquid_composition: dict[str, float] | None,
    interaction_parameters: dict | None,
) -> tuple[dict[str, float], dict[str, float], list[str]]:
    p = pressure_bar * 1e5
    warnings = []

    if liquid_composition is None:
        liquid_composition = feed.mole_fractions

    liquid_norm = normalize_composition(
        liquid_composition,
        "mole",
    )

    if package == "NRTL":
        activity = nrtl_activity_coefficients(
            temperature_c,
            liquid_norm,
            interaction_parameters,
        )
    elif package == "UNIQUAC":
        activity = uniquac_activity_coefficients(
            temperature_c,
            liquid_norm,
            interaction_parameters,
        )
    else:
        class Ideal:
            activity_coefficients = {
                name: 1.0
                for name in liquid_norm.mole_fractions
            }
            warnings = []

        activity = Ideal()

    warnings.extend(activity.warnings)

    k = {}

    for name in feed.mole_fractions:
        psat = get_component(name).saturation_pressure_pa(
            temperature_c
        )

        if psat is None:
            raise ValueError(
                f"Saturation-pressure data are unavailable for '{name}'."
            )

        gamma = activity.activity_coefficients.get(name, 1.0)
        k[name] = max(
            1e-12,
            min(1e12, gamma * psat / p),
        )

    return k, activity.activity_coefficients, warnings


def flash_isothermal(
    temperature_c: float,
    pressure_bar: float,
    fractions: dict[str, float],
    composition_basis: str = "mole",
    package: str = "Peng-Robinson",
    interaction_parameters: dict | None = None,
    max_iter: int = 100,
    tol: float = 1e-8,
    damping: float = 0.50,
) -> FlashResult:
    """
    Isothermal-isobaric multicomponent flash.

    Supported paths:
      - Peng-Robinson: phi-phi iteration
      - SRK: phi-phi iteration
      - NRTL: gamma-Psat / P
      - UNIQUAC: gamma-Psat / P
      - Ideal mixture: Raoult-law K values

    The NRTL/UNIQUAC path uses ideal vapour fugacity in v0.7.
    """
    feed = normalize_composition(
        fractions,
        composition_basis,
    )

    z = feed.mole_fractions
    package = package.strip()

    warnings: list[str] = []
    activity_coefficients = {name: 1.0 for name in z}
    phi_l = None
    phi_v = None
    z_l = None
    z_v = None

    if package in {"Peng-Robinson", "SRK"}:
        k = wilson_k_values(
            temperature_c,
            pressure_bar,
            feed,
        )
    elif package in {"NRTL", "UNIQUAC", "Ideal mixture"}:
        k, activity_coefficients, act_warnings = _ideal_or_gamma_k(
            package,
            temperature_c,
            pressure_bar,
            feed,
            None,
            interaction_parameters,
        )
        warnings.extend(act_warnings)
    else:
        raise ValueError(
            "Flash package must be Peng-Robinson, SRK, NRTL, UNIQUAC, "
            "or Ideal mixture."
        )

    beta, phase, rr = solve_rachford_rice(z, k)
    x, y = phase_compositions(z, k, beta)

    if phase != "Two-phase":
        # For a stable single-phase feed, still return normalized x/y
        # diagnostics based on the current K estimates.
        return FlashResult(
            package=package,
            temperature_c=temperature_c,
            pressure_bar=pressure_bar,
            feed_mole_fractions=z,
            phase=phase,
            vapour_fraction=beta,
            liquid_mole_fractions=x,
            vapour_mole_fractions=y,
            k_values=k,
            liquid_z=None,
            vapour_z=None,
            liquid_fugacity_coefficients=None,
            vapour_fugacity_coefficients=None,
            activity_coefficients=activity_coefficients,
            iterations=0,
            converged=True,
            residual=rr,
            warnings=warnings,
        )

    converged = False
    last_change = float("inf")

    for iteration in range(1, max_iter + 1):
        beta, phase, rr = solve_rachford_rice(z, k)
        x, y = phase_compositions(z, k, beta)

        if package in {"Peng-Robinson", "SRK"}:
            liquid = normalize_composition(x, "mole")
            vapor = normalize_composition(y, "mole")

            kij = None
            if interaction_parameters:
                kij = interaction_parameters.get("KIJ")

            eos_l = cubic_eos(
                package,
                temperature_c,
                pressure_bar,
                liquid,
                kij=kij,
            )
            eos_v = cubic_eos(
                package,
                temperature_c,
                pressure_bar,
                vapor,
                kij=kij,
            )

            phi_l = eos_l.fugacity_coefficients_liquid
            phi_v = eos_v.fugacity_coefficients_vapor
            z_l = eos_l.z_liquid
            z_v = eos_v.z_vapor

            new_k = {}

            for name in z:
                numerator = max(
                    1e-12,
                    (phi_l or {}).get(name, 1.0),
                )
                denominator = max(
                    1e-12,
                    (phi_v or {}).get(name, 1.0),
                )
                new_k[name] = max(
                    1e-12,
                    min(1e12, numerator / denominator),
                )

        else:
            new_k, activity_coefficients, act_warnings = _ideal_or_gamma_k(
                package,
                temperature_c,
                pressure_bar,
                feed,
                x,
                interaction_parameters,
            )
            for warning in act_warnings:
                if warning not in warnings:
                    warnings.append(warning)

        changes = []

        for name in z:
            old_ln = math.log(max(k[name], 1e-30))
            new_ln = math.log(max(new_k[name], 1e-30))

            mixed_ln = (
                (1.0 - damping) * old_ln
                + damping * new_ln
            )

            k[name] = math.exp(
                max(-40.0, min(40.0, mixed_ln))
            )

            changes.append(abs(new_ln - old_ln))

        last_change = max(changes) if changes else 0.0

        # Re-evaluate the phase split using the UPDATED K values.
        beta_check, phase_check, rr_check = solve_rachford_rice(z, k)

        if last_change < tol:
            if phase_check != "Two-phase" or abs(rr_check) < 1e-8:
                beta = beta_check
                phase = phase_check
                rr = rr_check
                converged = True
                break

    beta, phase, rr = solve_rachford_rice(z, k)
    x, y = phase_compositions(z, k, beta)

    if package in {"NRTL", "UNIQUAC"}:
        warnings.append(
            f"{package} v0.7 flash uses gamma-Raoult with ideal vapour fugacity. "
            "A later gamma-phi build will add non-ideal vapour fugacity."
        )

    if not converged:
        warnings.append(
            f"Flash iteration reached {max_iter} iterations; "
            f"maximum ln(K) change = {last_change:.3e}."
        )

    return FlashResult(
        package=package,
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        feed_mole_fractions=z,
        phase=phase,
        vapour_fraction=beta,
        liquid_mole_fractions=x,
        vapour_mole_fractions=y,
        k_values=k,
        liquid_z=z_l,
        vapour_z=z_v,
        liquid_fugacity_coefficients=phi_l,
        vapour_fugacity_coefficients=phi_v,
        activity_coefficients=activity_coefficients,
        iterations=iteration,
        converged=converged,
        residual=rr,
        warnings=warnings,
    )
