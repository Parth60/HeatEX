from __future__ import annotations
import math


def reynolds_number(rho: float, velocity: float, diameter: float, mu: float) -> float:
    if mu <= 0 or diameter <= 0:
        raise ValueError("Viscosity and diameter must be positive.")
    return rho * velocity * diameter / mu


def prandtl_number(cp: float, mu: float, k: float) -> float:
    if k <= 0:
        raise ValueError("Thermal conductivity must be positive.")
    return cp * mu / k


def darcy_friction_factor(reynolds: float, relative_roughness: float = 0.0) -> float:
    if reynolds <= 0:
        raise ValueError("Reynolds number must be positive.")

    if reynolds < 2300:
        return 64.0 / reynolds

    # Swamee-Jain explicit approximation
    rr = max(0.0, relative_roughness)
    return 0.25 / (
        math.log10(rr / 3.7 + 5.74 / reynolds**0.9) ** 2
    )


def nusselt_internal(
    reynolds: float,
    prandtl: float,
    heating: bool = True,
) -> float:
    """
    Screening correlation for circular-tube internal flow.

    - laminar: fully developed, constant-wall-temperature baseline
    - transition: linear blend
    - turbulent: Gnielinski correlation
    """
    if reynolds <= 0 or prandtl <= 0:
        raise ValueError("Reynolds and Prandtl numbers must be positive.")

    if reynolds <= 2300:
        return 3.66

    f = (0.79 * math.log(reynolds) - 1.64) ** -2
    nu_turb = (
        (f / 8.0) * (reynolds - 1000.0) * prandtl
        / (1.0 + 12.7 * math.sqrt(f / 8.0) * (prandtl ** (2.0 / 3.0) - 1.0))
    )

    if reynolds >= 10000:
        return nu_turb

    frac = (reynolds - 2300.0) / (10000.0 - 2300.0)
    return 3.66 + frac * (nu_turb - 3.66)
