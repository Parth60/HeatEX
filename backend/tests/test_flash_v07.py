import math

from backend.app.thermo.flash import (
    wilson_k_values,
    solve_rachford_rice,
    flash_isothermal,
)
from backend.app.thermo.composition import normalize_composition
from backend.app.thermo.phase_envelope import temperature_flash_sweep
from backend.app.thermo.two_phase_path import build_phase_path
from backend.app.engine.flash_drum import simulate_flash_drum


def test_rachford_rice_known_binary():
    z = {"A": 0.5, "B": 0.5}
    k = {"A": 2.0, "B": 0.5}

    beta, phase, residual = solve_rachford_rice(z, k)

    assert phase == "Two-phase"
    assert 0.0 < beta < 1.0
    assert abs(residual) < 1e-8


def test_pr_flash_returns_mass_balance():
    result = flash_isothermal(
        temperature_c=90.0,
        pressure_bar=1.5,
        fractions={
            "Ethanol": 0.60,
            "Water": 0.25,
            "Butanol": 0.15,
        },
        composition_basis="mole",
        package="Peng-Robinson",
    )

    assert 0.0 <= result.vapour_fraction <= 1.0
    assert abs(sum(result.liquid_mole_fractions.values()) - 1.0) < 1e-8
    assert abs(sum(result.vapour_mole_fractions.values()) - 1.0) < 1e-8


def test_nrtl_flash_runs_with_ideal_fallback_parameters():
    result = flash_isothermal(
        temperature_c=80.0,
        pressure_bar=1.0,
        fractions={
            "Ethanol": 0.50,
            "Water": 0.50,
        },
        composition_basis="mole",
        package="NRTL",
    )

    assert 0.0 <= result.vapour_fraction <= 1.0
    assert len(result.k_values) == 2


def test_flash_drum_flow_split():
    result = simulate_flash_drum(
        feed_mol_s=100.0,
        temperature_c=90.0,
        pressure_bar=1.5,
        fractions={
            "Ethanol": 0.60,
            "Water": 0.25,
            "Butanol": 0.15,
        },
        composition_basis="mole",
        package="Peng-Robinson",
    )

    assert abs(
        result.feed_mol_s
        - result.vapour_mol_s
        - result.liquid_mol_s
    ) < 1e-9


def test_temperature_sweep_and_path_run():
    envelope = temperature_flash_sweep(
        pressure_bar=1.2,
        fractions={
            "Ethanol": 0.70,
            "Water": 0.20,
            "Butanol": 0.10,
        },
        composition_basis="mole",
        package="Ideal mixture",
        temperature_min_c=50.0,
        temperature_max_c=130.0,
        points=15,
    )

    assert len(envelope.points) > 5

    path = build_phase_path(
        mode="Cooling / condensation",
        pressure_bar=1.2,
        fractions={
            "Ethanol": 0.70,
            "Water": 0.20,
            "Butanol": 0.10,
        },
        composition_basis="mole",
        package="Ideal mixture",
        interaction_parameters=None,
        temperature_start_c=130.0,
        temperature_end_c=50.0,
        points=12,
    )

    assert len(path.points) == 12
