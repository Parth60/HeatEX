from __future__ import annotations

from dataclasses import dataclass, asdict

from backend.app.thermo.flash import flash_isothermal


@dataclass
class FlashDrumResult:
    feed_mol_s: float
    vapour_mol_s: float
    liquid_mol_s: float
    vapour_fraction: float
    vapour_composition: dict[str, float]
    liquid_composition: dict[str, float]
    package: str
    temperature_c: float
    pressure_bar: float
    converged: bool
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def simulate_flash_drum(
    feed_mol_s: float,
    temperature_c: float,
    pressure_bar: float,
    fractions: dict[str, float],
    composition_basis: str,
    package: str,
    interaction_parameters: dict | None = None,
) -> FlashDrumResult:
    if feed_mol_s <= 0:
        raise ValueError("Feed molar flow must be positive.")

    flash = flash_isothermal(
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        fractions=fractions,
        composition_basis=composition_basis,
        package=package,
        interaction_parameters=interaction_parameters,
    )

    vapor = feed_mol_s * flash.vapour_fraction
    liquid = feed_mol_s - vapor

    return FlashDrumResult(
        feed_mol_s=feed_mol_s,
        vapour_mol_s=vapor,
        liquid_mol_s=liquid,
        vapour_fraction=flash.vapour_fraction,
        vapour_composition=flash.vapour_mole_fractions,
        liquid_composition=flash.liquid_mole_fractions,
        package=package,
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        converged=flash.converged,
        warnings=flash.warnings,
    )
