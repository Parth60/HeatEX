from backend.app.engine.single_phase_common import ServiceStream
from backend.app.engine.plate_hx import PlateGeometry, simulate_plate_hx
from backend.app.engine.double_pipe_hx import DoublePipeGeometry, simulate_double_pipe_hx
from backend.app.engine.air_cooled_hx import AirCooledGeometry, simulate_air_cooled_hx
from backend.app.engine.exchanger_selector import SelectionCase, rank_exchangers


def streams():
    hot = ServiceStream(
        fluid="Ethanol",
        mass_flow_kg_s=3.0,
        inlet_temperature_c=120.0,
        pressure_bar=4.0,
    )
    cold = ServiceStream(
        fluid="Water",
        mass_flow_kg_s=8.0,
        inlet_temperature_c=25.0,
        pressure_bar=3.0,
    )
    return hot, cold


def test_plate_runs():
    hot, cold = streams()
    result = simulate_plate_hx(
        hot, cold, 70.0,
        PlateGeometry(
            plate_length_m=1.0,
            plate_width_m=0.4,
            plate_gap_m=0.003,
            plate_count=100,
        ),
    )
    assert result.duty_kw > 0
    assert result.required_area_m2 > 0
    assert result.overall_u_w_m2k > 0


def test_double_pipe_runs():
    hot, cold = streams()
    result = simulate_double_pipe_hx(
        hot, cold, 80.0,
        DoublePipeGeometry(
            hairpin_length_m=6.0,
            hairpins=12,
        ),
    )
    assert result.duty_kw > 0
    assert result.required_area_m2 > 0


def test_air_cooler_runs():
    hot = ServiceStream(
        fluid="Thermal oil",
        mass_flow_kg_s=2.0,
        inlet_temperature_c=160.0,
        pressure_bar=5.0,
    )
    result = simulate_air_cooled_hx(
        hot,
        process_outlet_target_c=110.0,
        air_inlet_temperature_c=30.0,
        geometry=AirCooledGeometry(
            tube_length_m=8.0,
            tubes_per_row=40,
            rows=4,
            air_flow_m3_s=70.0,
        ),
    )
    assert result.duty_kw > 0
    assert result.fan_power_kw > 0
    assert result.installed_external_area_m2 > 0


def test_selector_ranks_four_types():
    result = rank_exchangers(
        SelectionCase(
            duty_kw=200.0,
            hot_viscosity_mpa_s=1.0,
            cold_viscosity_mpa_s=1.0,
            hot_pressure_bar=5.0,
            cold_pressure_bar=3.0,
            phase_change=False,
            solids_or_heavy_fouling=False,
            close_temperature_approach=True,
            cooling_water_available=True,
            compactness_priority=True,
        )
    )
    assert len(result) == 4
    assert result[0].score >= result[-1].score
