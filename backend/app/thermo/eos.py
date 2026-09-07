from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .components import R, get_component
from .composition import NormalizedComposition


@dataclass
class EOSResult:
    model: str
    roots: list[float]
    z_liquid: float
    z_vapor: float
    fugacity_coefficients_liquid: dict[str, float] | None
    fugacity_coefficients_vapor: dict[str, float] | None
    warnings: list[str]


def _real_positive_roots(coefficients: list[float]) -> list[float]:
    raw = np.roots(coefficients)
    roots = sorted(
        float(r.real)
        for r in raw
        if abs(r.imag) < 1e-8 and r.real > 1e-10
    )
    if not roots:
        raise ValueError("Cubic EOS produced no positive real compressibility roots.")
    return roots


def _mixing_terms(
    temperature_k: float,
    composition: NormalizedComposition,
    model: str,
    kij: dict[str, dict[str, float]] | None = None,
):
    names = list(composition.mole_fractions)
    x = np.array([composition.mole_fractions[n] for n in names], dtype=float)

    ai = []
    bi = []

    for name in names:
        c = get_component(name)
        if c.tc_k is None or c.pc_pa is None or c.acentric_factor is None:
            raise ValueError(
                f"{model} requires critical properties and acentric factor; "
                f"'{name}' is a pseudo-component in the current database."
            )

        tr = temperature_k / c.tc_k
        if tr <= 0:
            raise ValueError("Reduced temperature must be positive.")

        if model == "Peng-Robinson":
            kappa = (
                0.37464
                + 1.54226 * c.acentric_factor
                - 0.26992 * c.acentric_factor**2
            )
            alpha = (1.0 + kappa * (1.0 - math.sqrt(tr))) ** 2
            a = 0.45724 * R**2 * c.tc_k**2 / c.pc_pa * alpha
            b = 0.07780 * R * c.tc_k / c.pc_pa
        elif model == "SRK":
            m = (
                0.480
                + 1.574 * c.acentric_factor
                - 0.176 * c.acentric_factor**2
            )
            alpha = (1.0 + m * (1.0 - math.sqrt(tr))) ** 2
            a = 0.42747 * R**2 * c.tc_k**2 / c.pc_pa * alpha
            b = 0.08664 * R * c.tc_k / c.pc_pa
        else:
            raise ValueError(f"Unsupported cubic EOS '{model}'.")

        ai.append(a)
        bi.append(b)

    ai = np.array(ai)
    bi = np.array(bi)

    aij = np.zeros((len(names), len(names)))

    for i, ni in enumerate(names):
        for j, nj in enumerate(names):
            kij_value = 0.0
            if kij:
                kij_value = float(
                    kij.get(ni, {}).get(
                        nj,
                        kij.get(nj, {}).get(ni, 0.0),
                    )
                )
            aij[i, j] = math.sqrt(ai[i] * ai[j]) * (1.0 - kij_value)

    a_mix = float(x @ aij @ x)
    b_mix = float(x @ bi)

    return names, x, ai, bi, aij, a_mix, b_mix


def _phi_pr(
    z: float,
    a: float,
    b: float,
    A: float,
    B: float,
    names: list[str],
    x: np.ndarray,
    bi: np.ndarray,
    aij: np.ndarray,
) -> dict[str, float]:
    if b <= 0 or A <= 0 or B <= 0 or z <= B:
        return {name: 1.0 for name in names}

    sqrt2 = math.sqrt(2.0)
    log_term = math.log(
        (z + (1.0 + sqrt2) * B)
        / (z + (1.0 - sqrt2) * B)
    )

    result = {}

    for i, name in enumerate(names):
        sum_aij = float(np.dot(x, aij[i]))
        bracket = 2.0 * sum_aij / a - bi[i] / b

        ln_phi = (
            bi[i] / b * (z - 1.0)
            - math.log(z - B)
            - A / (2.0 * sqrt2 * B) * bracket * log_term
        )
        result[name] = math.exp(max(-50.0, min(50.0, ln_phi)))

    return result


def _phi_srk(
    z: float,
    a: float,
    b: float,
    A: float,
    B: float,
    names: list[str],
    x: np.ndarray,
    bi: np.ndarray,
    aij: np.ndarray,
) -> dict[str, float]:
    if b <= 0 or A <= 0 or B <= 0 or z <= B:
        return {name: 1.0 for name in names}

    result = {}

    for i, name in enumerate(names):
        sum_aij = float(np.dot(x, aij[i]))
        bracket = 2.0 * sum_aij / a - bi[i] / b

        ln_phi = (
            bi[i] / b * (z - 1.0)
            - math.log(z - B)
            - A / B * bracket * math.log(1.0 + B / z)
        )
        result[name] = math.exp(max(-50.0, min(50.0, ln_phi)))

    return result


def cubic_eos(
    model: str,
    temperature_c: float,
    pressure_bar: float,
    composition: NormalizedComposition,
    kij: dict[str, dict[str, float]] | None = None,
) -> EOSResult:
    model_alias = {
        "PR": "Peng-Robinson",
        "Peng-Robinson": "Peng-Robinson",
        "SRK": "SRK",
        "Soave-Redlich-Kwong": "SRK",
    }
    model = model_alias.get(model, model)

    t = temperature_c + 273.15
    p = pressure_bar * 1e5

    names, x, ai, bi, aij, a, b = _mixing_terms(
        t,
        composition,
        model,
        kij,
    )

    A = a * p / (R**2 * t**2)
    B = b * p / (R * t)

    if model == "Peng-Robinson":
        coefficients = [
            1.0,
            -(1.0 - B),
            A - 3.0 * B**2 - 2.0 * B,
            -(A * B - B**2 - B**3),
        ]
    elif model == "SRK":
        coefficients = [
            1.0,
            -1.0,
            A - B - B**2,
            -A * B,
        ]
    else:
        raise ValueError(f"Unsupported cubic EOS '{model}'.")

    roots = _real_positive_roots(coefficients)
    z_l = roots[0]
    z_v = roots[-1]

    if model == "Peng-Robinson":
        phi_l = _phi_pr(z_l, a, b, A, B, names, x, bi, aij)
        phi_v = _phi_pr(z_v, a, b, A, B, names, x, bi, aij)
    else:
        phi_l = _phi_srk(z_l, a, b, A, B, names, x, bi, aij)
        phi_v = _phi_srk(z_v, a, b, A, B, names, x, bi, aij)

    warnings: list[str] = []
    if kij is None:
        warnings.append(
            f"{model} binary interaction coefficients defaulted to kij = 0."
        )

    return EOSResult(
        model=model,
        roots=roots,
        z_liquid=z_l,
        z_vapor=z_v,
        fugacity_coefficients_liquid=phi_l,
        fugacity_coefficients_vapor=phi_v,
        warnings=warnings,
    )
