from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from .flash import flash_isothermal


@dataclass
class PhaseEnvelopePoint:
    temperature_c: float
    vapour_fraction: float
    phase: str
    converged: bool


@dataclass
class PhaseEnvelopeResult:
    pressure_bar: float
    package: str
    points: list[PhaseEnvelopePoint]
    bubble_temperature_c: float | None
    dew_temperature_c: float | None
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def temperature_flash_sweep(
    pressure_bar: float,
    fractions: dict[str, float],
    composition_basis: str,
    package: str,
    interaction_parameters: dict | None = None,
    temperature_min_c: float = 20.0,
    temperature_max_c: float = 160.0,
    points: int = 35,
) -> PhaseEnvelopeResult:
    if temperature_max_c <= temperature_min_c:
        raise ValueError("Maximum temperature must exceed minimum temperature.")

    points = max(8, min(120, int(points)))

    values: list[PhaseEnvelopePoint] = []
    warnings: list[str] = []

    for i in range(points):
        frac = i / (points - 1)
        t = (
            temperature_min_c
            + frac * (temperature_max_c - temperature_min_c)
        )

        try:
            result = flash_isothermal(
                temperature_c=t,
                pressure_bar=pressure_bar,
                fractions=fractions,
                composition_basis=composition_basis,
                package=package,
                interaction_parameters=interaction_parameters,
                max_iter=60,
            )

            values.append(
                PhaseEnvelopePoint(
                    temperature_c=t,
                    vapour_fraction=result.vapour_fraction,
                    phase=result.phase,
                    converged=result.converged,
                )
            )
        except Exception as exc:
            warnings.append(
                f"Flash failed at {t:.2f} °C: {exc}"
            )

    if not values:
        raise ValueError("No valid flash points were generated.")

    bubble = None
    dew = None

    for a, b in zip(values[:-1], values[1:]):
        if bubble is None:
            if (
                a.vapour_fraction <= 1e-6
                and b.vapour_fraction > 1e-6
            ):
                bubble = 0.5 * (
                    a.temperature_c + b.temperature_c
                )

        if dew is None:
            if (
                a.vapour_fraction < 1.0 - 1e-6
                and b.vapour_fraction >= 1.0 - 1e-6
            ):
                dew = 0.5 * (
                    a.temperature_c + b.temperature_c
                )

    return PhaseEnvelopeResult(
        pressure_bar=pressure_bar,
        package=package,
        points=values,
        bubble_temperature_c=bubble,
        dew_temperature_c=dew,
        warnings=warnings,
    )
