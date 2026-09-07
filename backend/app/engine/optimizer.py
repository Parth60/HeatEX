from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from itertools import product
from math import isfinite
from typing import Iterable

from .geometry import ShellTubeGeometry
from .simulator import HXSimulationInput, HXSimulationResult, simulate_shell_and_tube


@dataclass(frozen=True)
class OptimizationSettings:
    objective: str = "Balanced"

    tube_od_options_mm: tuple[float, ...] = (15.88, 19.05, 25.40)
    tube_length_options_m: tuple[float, ...] = (4.0, 6.0, 8.0)
    tube_pass_options: tuple[int, ...] = (1, 2, 4)
    baffle_cut_options_percent: tuple[int, ...] = (20, 25, 30, 35)
    pitch_ratio_options: tuple[float, ...] = (1.25, 1.33)

    tube_count_min: int = 240
    tube_count_max: int = 720
    tube_count_step: int = 40

    baffle_count_min: int = 6
    baffle_count_max: int = 20
    baffle_count_step: int = 2

    minimum_area_margin_percent: float = 10.0
    maximum_area_margin_percent: float = 35.0

    minimum_tube_velocity_m_s: float = 0.5
    maximum_tube_velocity_m_s: float = 3.0

    maximum_candidates: int = 3500


@dataclass
class OptimizationCandidate:
    rank: int
    feasible: bool
    objective_score: float

    tube_od_mm: float
    tube_id_mm: float
    tube_length_m: float
    tube_count: int
    tube_passes: int
    tube_pitch_mm: float
    baffle_count: int
    baffle_cut_percent: float

    duty_kw: float
    overall_u_w_m2k: float
    required_area_m2: float
    installed_area_m2: float
    area_margin_percent: float

    tube_velocity_m_s: float
    tube_dp_kpa: float
    shell_dp_kpa: float

    hydraulic_utilisation: float
    area_efficiency: float
    relative_cost_index: float

    rejection_reasons: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class OptimizationReport:
    objective: str
    evaluated_candidates: int
    feasible_candidates: int
    rejected_candidates: int
    truncated: bool
    winners: list[OptimizationCandidate]

    def as_dict(self) -> dict:
        return {
            "objective": self.objective,
            "evaluated_candidates": self.evaluated_candidates,
            "feasible_candidates": self.feasible_candidates,
            "rejected_candidates": self.rejected_candidates,
            "truncated": self.truncated,
            "winners": [c.as_dict() for c in self.winners],
        }


def _tube_id_from_od_mm(od_mm: float) -> float:
    """
    Development tube-wall mapping for the optimiser.

    The final version will select standard tube gauges explicitly from a
    mechanical tube database. For now this keeps optimisation geometrically
    consistent without allowing tube ID >= tube OD.
    """
    wall_mm = 1.65 if od_mm <= 19.05 else 2.11
    return max(4.0, od_mm - 2.0 * wall_mm)


def _relative_cost_index(result: HXSimulationResult, geometry: ShellTubeGeometry) -> float:
    """
    Dimensionless screening index, NOT a currency estimate.

    It combines installed area, tube count, exchanger length and hydraulic
    loading so the optimiser can distinguish similarly sized candidates.
    """
    area_term = result.installed_area_m2
    bundle_term = 0.035 * geometry.tube_count
    length_term = 3.0 * geometry.tube_length_m
    hydraulic_term = 0.30 * (result.tube_dp_kpa + result.shell_dp_kpa)

    return area_term + bundle_term + length_term + hydraulic_term


def _candidate_metrics(
    result: HXSimulationResult,
    geometry: ShellTubeGeometry,
    base_input: HXSimulationInput,
) -> tuple[float, float, float]:
    tube_util = result.tube_dp_kpa / max(base_input.allowable_tube_dp_kpa, 1e-9)
    shell_util = result.shell_dp_kpa / max(base_input.allowable_shell_dp_kpa, 1e-9)
    hydraulic_utilisation = max(tube_util, shell_util)

    if result.installed_area_m2 <= 0:
        area_efficiency = 0.0
    else:
        area_efficiency = result.required_area_m2 / result.installed_area_m2

    cost_index = _relative_cost_index(result, geometry)

    return hydraulic_utilisation, area_efficiency, cost_index


def _rejection_reasons(
    result: HXSimulationResult,
    settings: OptimizationSettings,
    base_input: HXSimulationInput,
) -> list[str]:
    reasons: list[str] = []

    if result.area_margin_percent < settings.minimum_area_margin_percent:
        reasons.append("area margin below minimum")

    if result.area_margin_percent > settings.maximum_area_margin_percent:
        reasons.append("area margin above maximum")

    if result.tube_dp_kpa > base_input.allowable_tube_dp_kpa:
        reasons.append("tube pressure drop exceeds limit")

    if result.shell_dp_kpa > base_input.allowable_shell_dp_kpa:
        reasons.append("shell pressure drop exceeds limit")

    if result.tube_velocity_m_s < settings.minimum_tube_velocity_m_s:
        reasons.append("tube velocity below minimum")

    if result.tube_velocity_m_s > settings.maximum_tube_velocity_m_s:
        reasons.append("tube velocity above maximum")

    if not all(
        isfinite(v)
        for v in (
            result.overall_u_w_m2k,
            result.required_area_m2,
            result.installed_area_m2,
            result.tube_dp_kpa,
            result.shell_dp_kpa,
        )
    ):
        reasons.append("non-finite simulation result")

    return reasons


def _objective_score(
    objective: str,
    result: HXSimulationResult,
    hydraulic_utilisation: float,
    area_efficiency: float,
    cost_index: float,
    settings: OptimizationSettings,
) -> float:
    """
    Smaller score is better.
    """
    name = objective.strip().lower()

    area_target_margin = settings.minimum_area_margin_percent
    area_margin_error = abs(result.area_margin_percent - area_target_margin)

    velocity_target = 1.5
    velocity_error = abs(result.tube_velocity_m_s - velocity_target)

    if name == "minimum installed area":
        return result.installed_area_m2

    if name == "minimum pressure drop":
        return result.tube_dp_kpa + result.shell_dp_kpa

    if name == "maximum overall u":
        return -result.overall_u_w_m2k

    if name == "minimum relative cost":
        return cost_index

    if name == "maximum area efficiency":
        return -area_efficiency

    # Balanced multi-objective score. Feasibility is handled separately.
    # Terms are scaled so one variable does not dominate purely by units.
    return (
        0.36 * (result.installed_area_m2 / 100.0)
        + 0.25 * hydraulic_utilisation
        + 0.18 * (area_margin_error / 10.0)
        + 0.11 * (velocity_error / 1.5)
        + 0.10 * (cost_index / 150.0)
    )


def _integer_range(start: int, stop: int, step: int) -> list[int]:
    if step <= 0:
        raise ValueError("Optimisation range step must be positive.")
    if stop < start:
        raise ValueError("Optimisation maximum must be >= minimum.")

    values = list(range(start, stop + 1, step))
    if values[-1] != stop and stop not in values:
        values.append(stop)
    return values


def optimize_shell_and_tube(
    base_input: HXSimulationInput,
    settings: OptimizationSettings,
    top_n: int = 10,
) -> OptimizationReport:
    """
    Bounded discrete geometry search.

    The optimiser reuses the same engineering simulation function as the live
    cockpit. This avoids having separate 'display' and 'optimisation' physics.
    """
    tube_counts = _integer_range(
        settings.tube_count_min,
        settings.tube_count_max,
        settings.tube_count_step,
    )
    baffle_counts = _integer_range(
        settings.baffle_count_min,
        settings.baffle_count_max,
        settings.baffle_count_step,
    )

    design_space = product(
        settings.tube_od_options_mm,
        settings.tube_length_options_m,
        tube_counts,
        settings.tube_pass_options,
        baffle_counts,
        settings.baffle_cut_options_percent,
        settings.pitch_ratio_options,
    )

    candidates: list[OptimizationCandidate] = []
    evaluated = 0
    truncated = False

    for (
        od_mm,
        length_m,
        tube_count,
        tube_passes,
        baffle_count,
        baffle_cut_percent,
        pitch_ratio,
    ) in design_space:
        if evaluated >= settings.maximum_candidates:
            truncated = True
            break

        evaluated += 1

        id_mm = _tube_id_from_od_mm(float(od_mm))
        pitch_mm = float(od_mm) * float(pitch_ratio)

        geometry = replace(
            base_input.geometry,
            tube_od_m=float(od_mm) / 1000.0,
            tube_id_m=id_mm / 1000.0,
            tube_length_m=float(length_m),
            tube_count=int(tube_count),
            tube_passes=int(tube_passes),
            tube_pitch_m=pitch_mm / 1000.0,
            baffle_count=int(baffle_count),
            baffle_cut_fraction=float(baffle_cut_percent) / 100.0,
        )

        try:
            result = simulate_shell_and_tube(
                replace(base_input, geometry=geometry)
            )
        except Exception:
            continue

        reasons = _rejection_reasons(result, settings, base_input)
        feasible = len(reasons) == 0

        hyd_util, area_eff, cost_index = _candidate_metrics(
            result,
            geometry,
            base_input,
        )

        score = _objective_score(
            settings.objective,
            result,
            hyd_util,
            area_eff,
            cost_index,
            settings,
        )

        candidates.append(
            OptimizationCandidate(
                rank=0,
                feasible=feasible,
                objective_score=float(score),
                tube_od_mm=float(od_mm),
                tube_id_mm=float(id_mm),
                tube_length_m=float(length_m),
                tube_count=int(tube_count),
                tube_passes=int(tube_passes),
                tube_pitch_mm=float(pitch_mm),
                baffle_count=int(baffle_count),
                baffle_cut_percent=float(baffle_cut_percent),
                duty_kw=result.duty_kw,
                overall_u_w_m2k=result.overall_u_w_m2k,
                required_area_m2=result.required_area_m2,
                installed_area_m2=result.installed_area_m2,
                area_margin_percent=result.area_margin_percent,
                tube_velocity_m_s=result.tube_velocity_m_s,
                tube_dp_kpa=result.tube_dp_kpa,
                shell_dp_kpa=result.shell_dp_kpa,
                hydraulic_utilisation=hyd_util,
                area_efficiency=area_eff,
                relative_cost_index=cost_index,
                rejection_reasons=reasons,
            )
        )

    feasible = [c for c in candidates if c.feasible]
    feasible.sort(key=lambda c: c.objective_score)

    winners = feasible[: max(1, top_n)]

    for rank, candidate in enumerate(winners, start=1):
        candidate.rank = rank

    return OptimizationReport(
        objective=settings.objective,
        evaluated_candidates=evaluated,
        feasible_candidates=len(feasible),
        rejected_candidates=len(candidates) - len(feasible),
        truncated=truncated,
        winners=winners,
    )
