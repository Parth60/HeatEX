import io
import zipfile

from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.simulator import (
    StreamInput,
    HXSimulationInput,
    simulate_shell_and_tube,
)
from backend.app.validation.validation_engine import validate_shell_and_tube
from backend.app.validation.benchmarks import run_benchmark_suite
from backend.app.validation.trace import build_calculation_trace
from backend.app.validation.assumptions import build_assumptions_register
from backend.app.reporting.technical_pack import (
    build_report_payload,
    build_technical_pack_zip,
)
from backend.app.reporting.engineering_report import build_engineering_report_pdf


def case():
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
            mass_flow_kg_s=3.0,
            inlet_temperature_c=120.0,
            pressure_bar=4.0,
        ),
        cold=StreamInput(
            fluid="Water",
            mass_flow_kg_s=8.0,
            inlet_temperature_c=25.0,
            pressure_bar=3.0,
        ),
        geometry=geometry,
        hot_outlet_target_c=70.0,
        thermo_package="Ideal mixture",
        allowable_tube_dp_kpa=200.0,
        allowable_shell_dp_kpa=200.0,
    )

    result = simulate_shell_and_tube(inp)
    return inp, result


def test_benchmark_suite_passes():
    benchmarks = run_benchmark_suite()
    assert len(benchmarks) >= 4
    assert all(x.status == "PASS" for x in benchmarks)


def test_validation_energy_and_area_close():
    inp, result = case()
    validation = validate_shell_and_tube(inp, result)

    assert validation.energy_balance_residual_percent < 1e-6
    assert validation.area_closure_residual_percent < 1e-6
    assert validation.failed_checks == 0


def test_pdf_and_zip_generate():
    inp, result = case()

    validation = validate_shell_and_tube(inp, result)
    benchmarks = run_benchmark_suite()
    trace = build_calculation_trace(inp, result)
    assumptions = build_assumptions_register(inp, result)

    payload = build_report_payload(
        inp,
        result,
        validation,
        benchmarks,
        assumptions,
        trace,
    )

    pdf = build_engineering_report_pdf(payload)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 5000

    pack = build_technical_pack_zip(payload)

    with zipfile.ZipFile(io.BytesIO(pack), "r") as z:
        names = z.namelist()

    assert any(name.endswith(".pdf") for name in names)
    assert any("Validation.csv" in name for name in names)
    assert any("Design_Data" in name for name in names)
