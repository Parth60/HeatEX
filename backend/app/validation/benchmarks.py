from __future__ import annotations

from dataclasses import dataclass, asdict
import math

from backend.app.engine.heat_transfer import lmtd
from backend.app.thermo.composition import normalize_composition
from backend.app.thermo.flash import solve_rachford_rice
from backend.app.mechanical.pressure_design import (
    cylindrical_shell_thickness_mm,
    cylindrical_shell_mawp_bar,
)


@dataclass
class BenchmarkResult:
    name: str
    status: str
    calculated: float
    expected: float
    relative_error_percent: float
    note: str

    def as_dict(self) -> dict:
        return asdict(self)


def _result(
    name: str,
    calculated: float,
    expected: float,
    tolerance_percent: float,
    note: str,
) -> BenchmarkResult:
    error = (
        abs(calculated - expected)
        / max(abs(expected), 1e-12)
        * 100.0
    )
    return BenchmarkResult(
        name=name,
        status="PASS" if error <= tolerance_percent else "FAIL",
        calculated=calculated,
        expected=expected,
        relative_error_percent=error,
        note=note,
    )


def run_benchmark_suite() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    # 1. LMTD analytical check
    expected_lmtd = (80.0 - 70.0) / math.log(80.0 / 70.0)
    calculated_lmtd = lmtd(
        hot_in_c=150.0,
        hot_out_c=100.0,
        cold_in_c=30.0,
        cold_out_c=70.0,
        counter_current=True,
    )
    results.append(
        _result(
            "Counter-current LMTD analytical identity",
            calculated_lmtd,
            expected_lmtd,
            1e-8,
            "Exact algebraic reference case.",
        )
    )

    # 2. Rachford-Rice known binary solution beta = 0.5
    beta, phase, residual = solve_rachford_rice(
        {"A": 0.5, "B": 0.5},
        {"A": 2.0, "B": 0.5},
    )
    results.append(
        _result(
            "Rachford-Rice known binary vapour fraction",
            beta,
            0.5,
            1e-8,
            f"Known analytical solution; phase={phase}, residual={residual:.3e}.",
        )
    )

    # 3. Composition normalization identity
    comp = normalize_composition(
        {"Ethanol": 7.0, "Water": 2.0, "Butanol": 1.0},
        "mole",
    )
    x_sum = sum(comp.mole_fractions.values())
    results.append(
        _result(
            "Composition normalization",
            x_sum,
            1.0,
            1e-8,
            "Normalized mole fractions must sum to unity.",
        )
    )

    # 4. Shell thickness/MAWP inverse consistency
    p_design = 10.0
    ca = 1.5
    t = cylindrical_shell_thickness_mm(
        design_pressure_bar=p_design,
        inside_diameter_mm=800.0,
        allowable_stress_mpa=120.0,
        joint_efficiency=0.85,
        corrosion_allowance_mm=ca,
    )
    mawp = cylindrical_shell_mawp_bar(
        nominal_thickness_mm=t,
        inside_diameter_mm=800.0,
        allowable_stress_mpa=120.0,
        joint_efficiency=0.85,
        corrosion_allowance_mm=ca,
    )
    results.append(
        _result(
            "Shell pressure equation inverse consistency",
            mawp,
            p_design,
            1e-8,
            "Thickness equation and inverted MAWP equation must close.",
        )
    )

    return results
