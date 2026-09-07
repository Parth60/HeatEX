import math

from backend.app.thermo.phase_change import (
    saturation_temperature_c,
    get_saturation_state,
)
from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.phase_change_simulator import (
    PhaseChangeStream,
    UtilityStream,
    PhaseChangeHXInput,
    simulate_phase_change,
)


def geometry():
    return ShellTubeGeometry(
        shell_id_m=0.80,
        tube_od_m=0.01905,
        tube_id_m=0.01575,
        tube_length_m=6.0,
        tube_count=520,
        tube_passes=2,
        tube_pitch_m=0.025,
        tube_layout="triangular",
        baffle_count=12,
        baffle_cut_fraction=0.25,
    )


def test_water_saturation_near_100c_at_1atm_screening():
    t = saturation_temperature_c("Water", 1.01325)
    assert 95.0 < t < 105.0


def test_ethanol_latent_heat_is_positive():
    sat = get_saturation_state("Ethanol", 1.5)
    assert sat.latent_heat_j_kg > 0
    assert sat.saturation_temperature_c > 50


def test_condenser_zone_split_runs():
    sat = get_saturation_state("Ethanol", 1.5)

    inp = PhaseChangeHXInput(
        operation="Condenser",
        process=PhaseChangeStream(
            fluid="Ethanol",
            mass_flow_kg_s=2.0,
            pressure_bar=1.5,
            inlet_temperature_c=sat.saturation_temperature_c + 20.0,
            outlet_temperature_c=sat.saturation_temperature_c - 10.0,
        ),
        utility=UtilityStream(
            fluid="Water",
            mass_flow_kg_s=30.0,
            pressure_bar=3.0,
            inlet_temperature_c=20.0,
        ),
        geometry=geometry(),
        process_on_tube_side=True,
        allowable_process_dp_kpa=200.0,
        allowable_utility_dp_kpa=200.0,
    )

    result = simulate_phase_change(inp)

    assert result.total_duty_kw > 0
    assert result.latent_duty_kw > 0
    assert result.total_required_area_m2 > 0
    assert len(result.zones) >= 2


def test_reboiler_zone_split_runs():
    sat = get_saturation_state("Water", 2.0)

    inp = PhaseChangeHXInput(
        operation="Reboiler",
        process=PhaseChangeStream(
            fluid="Water",
            mass_flow_kg_s=1.0,
            pressure_bar=2.0,
            inlet_temperature_c=sat.saturation_temperature_c - 15.0,
            outlet_temperature_c=sat.saturation_temperature_c + 8.0,
        ),
        utility=UtilityStream(
            fluid="Thermal oil",
            mass_flow_kg_s=25.0,
            pressure_bar=5.0,
            inlet_temperature_c=220.0,
        ),
        geometry=geometry(),
        process_on_tube_side=False,
        allowable_process_dp_kpa=500.0,
        allowable_utility_dp_kpa=500.0,
    )

    result = simulate_phase_change(inp)

    assert result.total_duty_kw > 0
    assert result.latent_duty_kw > 0
    assert result.utility_outlet_c < inp.utility.inlet_temperature_c
