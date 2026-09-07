from __future__ import annotations

from dataclasses import dataclass, asdict

from .flash import flash_isothermal


@dataclass
class PhasePathPoint:
    temperature_c: float
    vapour_fraction: float
    liquid_mole_fractions: dict[str, float]
    vapour_mole_fractions: dict[str, float]
    k_values: dict[str, float]


@dataclass
class PhasePathResult:
    mode: str
    pressure_bar: float
    package: str
    points: list[PhasePathPoint]
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def build_phase_path(
    mode: str,
    pressure_bar: float,
    fractions: dict[str, float],
    composition_basis: str,
    package: str,
    interaction_parameters: dict | None,
    temperature_start_c: float,
    temperature_end_c: float,
    points: int = 25,
) -> PhasePathResult:
    mode_l = mode.strip().lower()

    if mode_l not in {"cooling / condensation", "heating / boiling"}:
        raise ValueError(
            "Mode must be 'Cooling / condensation' or 'Heating / boiling'."
        )

    if points < 3:
        points = 3
    if points > 80:
        points = 80

    if mode_l.startswith("cooling") and temperature_end_c >= temperature_start_c:
        raise ValueError(
            "Cooling/condensation path requires end temperature below start temperature."
        )

    if mode_l.startswith("heating") and temperature_end_c <= temperature_start_c:
        raise ValueError(
            "Heating/boiling path requires end temperature above start temperature."
        )

    results = []
    warnings = []

    for i in range(points):
        f = i / (points - 1)
        t = temperature_start_c + f * (
            temperature_end_c - temperature_start_c
        )

        flash = flash_isothermal(
            temperature_c=t,
            pressure_bar=pressure_bar,
            fractions=fractions,
            composition_basis=composition_basis,
            package=package,
            interaction_parameters=interaction_parameters,
            max_iter=80,
        )

        results.append(
            PhasePathPoint(
                temperature_c=t,
                vapour_fraction=flash.vapour_fraction,
                liquid_mole_fractions=flash.liquid_mole_fractions,
                vapour_mole_fractions=flash.vapour_mole_fractions,
                k_values=flash.k_values,
            )
        )

        for warning in flash.warnings:
            if warning not in warnings:
                warnings.append(warning)

    return PhasePathResult(
        mode=mode,
        pressure_bar=pressure_bar,
        package=package,
        points=results,
        warnings=warnings,
    )
