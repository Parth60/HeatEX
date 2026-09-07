import math

from backend.app.thermo.composition import normalize_composition
from backend.app.thermo.eos import cubic_eos
from backend.app.thermo.activity import nrtl_activity_coefficients
from backend.app.thermo.engine import evaluate_state
from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.simulator import (
    StreamInput,
    HXSimulationInput,
    simulate_shell_and_tube,
)
from backend.app.engine.temperature_profile import build_temperature_profile


def test_mass_mole_conversion_normalises():
    comp = normalize_composition(
        {"Ethanol": 0.70, "Water": 0.30},
        "mass",
    )

    assert abs(sum(comp.mole_fractions.values()) - 1.0) < 1e-12
    assert abs(sum(comp.mass_fractions.values()) - 1.0) < 1e-12
    assert 18.0 < comp.mixture_mw_g_mol < 46.1


def test_peng_robinson_returns_finite_root():
    comp = normalize_composition(
        {"Ethanol": 0.8, "Water": 0.2},
        "mole",
    )

    result = cubic_eos(
        "Peng-Robinson",
        temperature_c=120.0,
        pressure_bar=5.0,
        composition=comp,
    )

    assert len(result.roots) >= 1
    assert result.z_vapor > 0
    assert math.isfinite(result.z_vapor)


def test_nrtl_zero_parameters_is_near_ideal():
    comp = normalize_composition(
        {"Ethanol": 0.5, "Water": 0.5},
        "mole",
    )

    result = nrtl_activity_coefficients(
        60.0,
        comp,
        parameters=None,
    )

    for gamma in result.activity_coefficients.values():
        assert abs(gamma - 1.0) < 1e-10


def test_multicomponent_enthalpy_simulation_and_profile():
    geometry = ShellTubeGeometry(
        shell_id_m=0.80,
        tube_od_m=0.01905,
        tube_id_m=0.01575,
        tube_length_m=6.0,
        tube_count=420,
        tube_passes=2,
        tube_pitch_m=0.025,
        tube_layout="triangular",
        baffle_count=12,
        baffle_cut_fraction=0.25,
    )

    inp = HXSimulationInput(
        hot=StreamInput(
            fluid="Mixture",
            mass_flow_kg_s=12.0,
            inlet_temperature_c=110.0,
            pressure_bar=5.0,
            composition={
                "Ethanol": 0.70,
                "Water": 0.20,
                "Butanol": 0.10,
            },
            composition_basis="mass",
        ),
        cold=StreamInput(
            fluid="Water",
            mass_flow_kg_s=22.0,
            inlet_temperature_c=20.0,
            pressure_bar=4.0,
        ),
        geometry=geometry,
        hot_outlet_target_c=65.0,
        thermo_package="Ideal mixture",
        allowable_tube_dp_kpa=200.0,
        allowable_shell_dp_kpa=200.0,
    )

    result = simulate_shell_and_tube(inp)

    assert result.duty_kw > 0
    assert result.cold_outlet_c > inp.cold.inlet_temperature_c
    assert result.hot_in_thermo["mixture_mw_g_mol"] > 0

    profile = build_temperature_profile(inp, result, segments=8)

    assert len(profile.points) == 9
    assert math.isfinite(profile.minimum_approach_c)
