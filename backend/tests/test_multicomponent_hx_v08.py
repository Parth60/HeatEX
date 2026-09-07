import math

from backend.app.thermo.mixture_phase import equilibrium_mixture_state
from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.multicomponent_phase_hx import (
    MulticomponentPhaseHXInput,
    simulate_multicomponent_phase_hx,
)


def geometry():
    return ShellTubeGeometry(
        shell_id_m=0.90,
        tube_od_m=0.01905,
        tube_id_m=0.01575,
        tube_length_m=6.0,
        tube_count=650,
        tube_passes=2,
        tube_pitch_m=0.025,
        tube_layout="triangular",
        baffle_count=12,
        baffle_cut_fraction=0.25,
    )


def test_equilibrium_mixture_enthalpy_changes_with_phase_fraction():
    feed = {
        "Ethanol": 0.70,
        "Water": 0.20,
        "Butanol": 0.10,
    }

    hot = equilibrium_mixture_state(
        125.0,
        1.2,
        feed,
        "mole",
        "Ideal mixture",
    )

    cold = equilibrium_mixture_state(
        55.0,
        1.2,
        feed,
        "mole",
        "Ideal mixture",
    )

    assert hot.vapour_fraction_molar >= cold.vapour_fraction_molar
    assert hot.overall_enthalpy_j_kg > cold.overall_enthalpy_j_kg


def test_multicomponent_condenser_integrates_area_and_duty():
    result = simulate_multicomponent_phase_hx(
        MulticomponentPhaseHXInput(
            mode="Cooling / condensation",
            fractions={
                "Ethanol": 0.70,
                "Water": 0.20,
                "Butanol": 0.10,
            },
            composition_basis="mole",
            package="Ideal mixture",
            interaction_parameters=None,
            process_mass_flow_kg_s=2.0,
            process_pressure_bar=1.2,
            process_inlet_temperature_c=125.0,
            process_outlet_temperature_c=55.0,
            utility_fluid="Water",
            utility_mass_flow_kg_s=30.0,
            utility_pressure_bar=3.0,
            utility_inlet_temperature_c=20.0,
            geometry=geometry(),
            process_on_tube_side=True,
            flow_arrangement="Counter-current",
            segments=10,
            allowable_process_dp_kpa=500.0,
            allowable_utility_dp_kpa=500.0,
        )
    )

    assert result.total_duty_kw > 0
    assert result.total_required_area_m2 > 0
    assert len(result.segments) == 10
    assert result.inlet_vapour_fraction > result.outlet_vapour_fraction


def test_multicomponent_reboiler_runs():
    result = simulate_multicomponent_phase_hx(
        MulticomponentPhaseHXInput(
            mode="Heating / boiling",
            fractions={
                "Ethanol": 0.50,
                "Water": 0.40,
                "Butanol": 0.10,
            },
            composition_basis="mole",
            package="Ideal mixture",
            interaction_parameters=None,
            process_mass_flow_kg_s=1.0,
            process_pressure_bar=1.2,
            process_inlet_temperature_c=55.0,
            process_outlet_temperature_c=120.0,
            utility_fluid="Thermal oil",
            utility_mass_flow_kg_s=35.0,
            utility_pressure_bar=5.0,
            utility_inlet_temperature_c=220.0,
            geometry=geometry(),
            process_on_tube_side=False,
            flow_arrangement="Counter-current",
            segments=10,
            allowable_process_dp_kpa=500.0,
            allowable_utility_dp_kpa=500.0,
        )
    )

    assert result.total_duty_kw > 0
    assert result.total_required_area_m2 > 0
    assert result.outlet_vapour_fraction > result.inlet_vapour_fraction
