from __future__ import annotations

from dataclasses import dataclass
import math

from .components import R, get_component
from .composition import NormalizedComposition


@dataclass
class ActivityResult:
    model: str
    activity_coefficients: dict[str, float]
    warnings: list[str]


def _pair_data(parameters: dict | None, model: str) -> dict:
    if not parameters:
        return {}

    return parameters.get(model, parameters.get(model.upper(), {})) or {}


def nrtl_activity_coefficients(
    temperature_c: float,
    composition: NormalizedComposition,
    parameters: dict | None = None,
) -> ActivityResult:
    """
    NRTL calculation with pair-wise dimensionless tau_ij values.

    Expected JSON pair entry:
      "Ethanol|Water": {
          "tau_ij": ...,
          "tau_ji": ...,
          "alpha": 0.30
      }

    If a pair is not supplied, tau=0 is used and the model approaches ideality.
    """
    names = list(composition.mole_fractions)
    xs = [composition.mole_fractions[n] for n in names]
    pairs = _pair_data(parameters, "NRTL")

    n = len(names)
    tau = [[0.0] * n for _ in range(n)]
    alpha = [[0.30] * n for _ in range(n)]
    missing_pairs = []

    for i, ni in enumerate(names):
        for j, nj in enumerate(names):
            if i == j:
                alpha[i][j] = 0.0
                continue

            forward = f"{ni}|{nj}"
            reverse = f"{nj}|{ni}"

            if forward in pairs:
                entry = pairs[forward]
                tau[i][j] = float(entry.get("tau_ij", 0.0))
                tau[j][i] = float(entry.get("tau_ji", tau[j][i]))
                a = float(entry.get("alpha", 0.30))
                alpha[i][j] = alpha[j][i] = a
            elif reverse not in pairs and i < j:
                missing_pairs.append(f"{ni}|{nj}")

    G = [
        [
            math.exp(-alpha[i][j] * tau[i][j])
            for j in range(n)
        ]
        for i in range(n)
    ]

    gammas = {}

    for i, ni in enumerate(names):
        first = 0.0
        for j in range(n):
            denominator = sum(xs[k] * G[k][j] for k in range(n))
            if denominator > 0:
                first += xs[j] * tau[j][i] * G[j][i] / sum(
                    xs[k] * G[k][i] for k in range(n)
                )

        second = 0.0
        for j in range(n):
            denominator_j = sum(xs[k] * G[k][j] for k in range(n))
            if denominator_j <= 0:
                continue

            weighted_tau = sum(
                xs[m] * tau[m][j] * G[m][j]
                for m in range(n)
            ) / denominator_j

            second += (
                xs[j]
                * G[i][j]
                / denominator_j
                * (tau[i][j] - weighted_tau)
            )

        ln_gamma = first + second
        gammas[ni] = math.exp(max(-20.0, min(20.0, ln_gamma)))

    warnings = []
    if missing_pairs:
        warnings.append(
            "NRTL parameters missing for: "
            + ", ".join(missing_pairs)
            + ". Missing pairs use tau = 0."
        )

    return ActivityResult(
        model="NRTL",
        activity_coefficients=gammas,
        warnings=warnings,
    )


def uniquac_activity_coefficients(
    temperature_c: float,
    composition: NormalizedComposition,
    parameters: dict | None = None,
) -> ActivityResult:
    """
    UNIQUAC calculation.

    Pair JSON entry:
      "Ethanol|Water": {
          "u_ij_j_mol": ...,
          "u_ji_j_mol": ...
      }

    tau_ij = exp(-u_ij / RT)
    """
    names = list(composition.mole_fractions)
    xs = [composition.mole_fractions[n] for n in names]
    pairs = _pair_data(parameters, "UNIQUAC")
    t = temperature_c + 273.15

    rs = []
    qs = []

    for name in names:
        c = get_component(name)
        if c.uniquac_r is None or c.uniquac_q is None:
            return ActivityResult(
                model="UNIQUAC",
                activity_coefficients={n: 1.0 for n in names},
                warnings=[
                    f"UNIQUAC structural parameters are unavailable for '{name}'. "
                    "Activity coefficients were set to unity."
                ],
            )
        rs.append(c.uniquac_r)
        qs.append(c.uniquac_q)

    n = len(names)
    u = [[0.0] * n for _ in range(n)]
    missing_pairs = []

    for i, ni in enumerate(names):
        for j, nj in enumerate(names):
            if i == j:
                continue

            forward = f"{ni}|{nj}"
            reverse = f"{nj}|{ni}"

            if forward in pairs:
                entry = pairs[forward]
                u[i][j] = float(entry.get("u_ij_j_mol", 0.0))
                u[j][i] = float(entry.get("u_ji_j_mol", u[j][i]))
            elif reverse not in pairs and i < j:
                missing_pairs.append(f"{ni}|{nj}")

    tau = [
        [
            math.exp(-u[i][j] / (R * t))
            for j in range(n)
        ]
        for i in range(n)
    ]

    z = 10.0
    sum_rx = sum(rs[i] * xs[i] for i in range(n))
    sum_qx = sum(qs[i] * xs[i] for i in range(n))

    phi = [rs[i] * xs[i] / sum_rx for i in range(n)]
    theta = [qs[i] * xs[i] / sum_qx for i in range(n)]
    l = [(z / 2.0) * (rs[i] - qs[i]) - (rs[i] - 1.0) for i in range(n)]
    sum_x_l = sum(xs[i] * l[i] for i in range(n))

    gammas = {}

    for i, name in enumerate(names):
        xi = max(xs[i], 1e-15)
        phi_i = max(phi[i], 1e-15)
        theta_i = max(theta[i], 1e-15)

        ln_gamma_c = (
            math.log(phi_i / xi)
            + (z / 2.0) * qs[i] * math.log(theta_i / phi_i)
            + l[i]
            - (phi_i / xi) * sum_x_l
        )

        sum_theta_tau_ji = sum(theta[j] * tau[j][i] for j in range(n))
        residual_sum = 0.0

        for j in range(n):
            denominator = sum(theta[k] * tau[k][j] for k in range(n))
            if denominator > 0:
                residual_sum += theta[j] * tau[i][j] / denominator

        ln_gamma_r = qs[i] * (
            1.0
            - math.log(max(sum_theta_tau_ji, 1e-15))
            - residual_sum
        )

        ln_gamma = ln_gamma_c + ln_gamma_r
        gammas[name] = math.exp(max(-20.0, min(20.0, ln_gamma)))

    warnings = []
    if missing_pairs:
        warnings.append(
            "UNIQUAC interaction energies missing for: "
            + ", ".join(missing_pairs)
            + ". Missing pairs use u_ij = 0."
        )

    return ActivityResult(
        model="UNIQUAC",
        activity_coefficients=gammas,
        warnings=warnings,
    )
