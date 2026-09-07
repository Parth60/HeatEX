from __future__ import annotations

from dataclasses import dataclass

from .components import get_component


@dataclass(frozen=True)
class NormalizedComposition:
    mole_fractions: dict[str, float]
    mass_fractions: dict[str, float]
    mixture_mw_g_mol: float


def _clean_fractions(fractions: dict[str, float]) -> dict[str, float]:
    combined: dict[str, float] = {}

    for name, value in fractions.items():
        if name is None:
            continue

        name = str(name).strip()
        if not name:
            continue

        get_component(name)

        value = float(value)
        if value < 0:
            raise ValueError("Composition fractions cannot be negative.")

        combined[name] = combined.get(name, 0.0) + value

    total = sum(combined.values())
    if total <= 0:
        raise ValueError("At least one positive composition fraction is required.")

    return {k: v / total for k, v in combined.items() if v > 0}


def normalize_composition(
    fractions: dict[str, float],
    basis: str = "mole",
) -> NormalizedComposition:
    cleaned = _clean_fractions(fractions)
    basis_l = basis.strip().lower()

    if basis_l.startswith("mole"):
        x = cleaned

        mw_mix = sum(
            xi * get_component(name).mw_g_mol
            for name, xi in x.items()
        )

        w_unnormalized = {
            name: xi * get_component(name).mw_g_mol
            for name, xi in x.items()
        }
        w_total = sum(w_unnormalized.values())
        w = {name: value / w_total for name, value in w_unnormalized.items()}

    elif basis_l.startswith("mass"):
        w = cleaned

        mole_amounts = {
            name: wi / get_component(name).mw_g_mol
            for name, wi in w.items()
        }
        n_total = sum(mole_amounts.values())
        x = {name: value / n_total for name, value in mole_amounts.items()}

        mw_mix = sum(
            xi * get_component(name).mw_g_mol
            for name, xi in x.items()
        )

    else:
        raise ValueError("Composition basis must be 'mole' or 'mass'.")

    return NormalizedComposition(
        mole_fractions=x,
        mass_fractions=w,
        mixture_mw_g_mol=mw_mix,
    )


def pure_composition(component: str) -> NormalizedComposition:
    return normalize_composition({component: 1.0}, "mole")
