from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.simulator import (
    StreamInput,
    HXSimulationInput,
    simulate_shell_and_tube,
)


def test_v03_integrated_simulation():
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
            fluid="Ethanol",
            mass_flow_kg_s=12.0,
            inlet_temperature_c=140.0,
            pressure_bar=4.0,
        ),
        cold=StreamInput(
            fluid="Water",
            mass_flow_kg_s=18.0,
            inlet_temperature_c=25.0,
            pressure_bar=3.0,
        ),
        geometry=geometry,
        hot_outlet_target_c=70.0,
        thermo_package="Fallback database",
    )

    result = simulate_shell_and_tube(inp)

    assert result.tema_code == "BEM"
    assert result.duty_kw > 0
    assert result.required_area_m2 > 0
    assert result.overall_u_w_m2k > 0
    assert result.tube_dp_kpa >= 0
    assert result.shell_dp_kpa >= 0
