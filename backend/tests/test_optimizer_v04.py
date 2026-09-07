from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.simulator import (
    StreamInput,
    HXSimulationInput,
)
from backend.app.engine.optimizer import (
    OptimizationSettings,
    optimize_shell_and_tube,
)


def base_input():
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

    return HXSimulationInput(
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
        allowable_tube_dp_kpa=120.0,
        allowable_shell_dp_kpa=120.0,
    )


def test_optimizer_returns_ranked_feasible_candidates():
    settings = OptimizationSettings(
        objective="Balanced",
        tube_od_options_mm=(19.05,),
        tube_length_options_m=(4.0, 6.0),
        tube_pass_options=(2, 4),
        baffle_cut_options_percent=(25,),
        pitch_ratio_options=(1.25,),
        tube_count_min=300,
        tube_count_max=540,
        tube_count_step=60,
        baffle_count_min=8,
        baffle_count_max=16,
        baffle_count_step=4,
        minimum_area_margin_percent=0.0,
        maximum_area_margin_percent=200.0,
        maximum_candidates=200,
    )

    report = optimize_shell_and_tube(
        base_input(),
        settings,
        top_n=5,
    )

    assert report.evaluated_candidates > 0
    assert report.feasible_candidates > 0
    assert len(report.winners) > 0
    assert report.winners[0].rank == 1

    scores = [c.objective_score for c in report.winners]
    assert scores == sorted(scores)
