from __future__ import annotations

from dataclasses import dataclass, asdict

from .materials import get_material
from .pressure_design import (
    cylindrical_shell_thickness_mm,
    elliptical_head_thickness_mm,
    cylindrical_shell_mawp_bar,
    tube_wall_screen_mm,
    round_up_nominal_mm,
)
from .nozzles import size_nozzle
from .tema_checks import run_tema_geometry_checks


@dataclass
class MechanicalDesignInput:
    tema_code: str

    shell_inside_diameter_m: float
    tube_od_m: float
    tube_id_m: float
    tube_length_m: float
    tube_pitch_m: float
    tube_passes: int
    baffle_count: int
    baffle_cut_fraction: float

    front_head: str
    shell_type: str
    rear_head: str

    shell_design_pressure_bar: float
    tube_design_pressure_bar: float

    shell_design_temperature_c: float
    tube_design_temperature_c: float

    shell_material: str
    tube_material: str

    shell_joint_efficiency: float = 0.85
    tube_joint_efficiency: float = 1.00

    shell_corrosion_allowance_mm: float = 1.5
    tube_corrosion_allowance_mm: float = 0.0

    selected_shell_nominal_thickness_mm: float | None = None
    selected_head_nominal_thickness_mm: float | None = None

    shell_mass_flow_kg_s: float = 10.0
    shell_density_kg_m3: float = 900.0
    tube_mass_flow_kg_s: float = 10.0
    tube_density_kg_m3: float = 900.0

    shell_nozzle_target_velocity_m_s: float = 2.0
    tube_nozzle_target_velocity_m_s: float = 2.0

    tema_class: str = "R"


@dataclass
class MechanicalDesignResult:
    tema_code: str
    tema_class: str

    shell_allowable_stress_mpa: float
    tube_allowable_stress_mpa: float

    required_shell_thickness_mm: float
    suggested_shell_nominal_mm: float
    required_head_thickness_mm: float
    suggested_head_nominal_mm: float

    selected_shell_nominal_mm: float
    shell_mawp_bar: float
    shell_pressure_margin_bar: float

    required_tube_wall_mm: float
    actual_tube_wall_mm: float
    tube_wall_margin_mm: float

    shell_nozzle: dict
    tube_nozzle: dict

    differential_design_pressure_bar: float

    geometry_checks: list[dict]
    warnings: list[str]
    design_notes: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def run_mechanical_design(
    inp: MechanicalDesignInput,
) -> MechanicalDesignResult:
    shell_mat = get_material(inp.shell_material)
    tube_mat = get_material(inp.tube_material)

    shell_s = shell_mat.allowable_stress_mpa(
        inp.shell_design_temperature_c
    )
    tube_s = tube_mat.allowable_stress_mpa(
        inp.tube_design_temperature_c
    )

    shell_required = cylindrical_shell_thickness_mm(
        design_pressure_bar=inp.shell_design_pressure_bar,
        inside_diameter_mm=inp.shell_inside_diameter_m * 1000.0,
        allowable_stress_mpa=shell_s,
        joint_efficiency=inp.shell_joint_efficiency,
        corrosion_allowance_mm=inp.shell_corrosion_allowance_mm,
    )

    head_required = elliptical_head_thickness_mm(
        design_pressure_bar=inp.shell_design_pressure_bar,
        inside_diameter_mm=inp.shell_inside_diameter_m * 1000.0,
        allowable_stress_mpa=shell_s,
        joint_efficiency=inp.shell_joint_efficiency,
        corrosion_allowance_mm=inp.shell_corrosion_allowance_mm,
    )

    shell_suggested = round_up_nominal_mm(shell_required)
    head_suggested = round_up_nominal_mm(head_required)

    selected_shell = (
        float(inp.selected_shell_nominal_thickness_mm)
        if inp.selected_shell_nominal_thickness_mm is not None
        else shell_suggested
    )

    shell_mawp = cylindrical_shell_mawp_bar(
        nominal_thickness_mm=selected_shell,
        inside_diameter_mm=inp.shell_inside_diameter_m * 1000.0,
        allowable_stress_mpa=shell_s,
        joint_efficiency=inp.shell_joint_efficiency,
        corrosion_allowance_mm=inp.shell_corrosion_allowance_mm,
    )

    required_tube_wall = tube_wall_screen_mm(
        design_pressure_bar=inp.tube_design_pressure_bar,
        tube_od_mm=inp.tube_od_m * 1000.0,
        allowable_stress_mpa=tube_s,
        joint_efficiency=inp.tube_joint_efficiency,
        corrosion_allowance_mm=inp.tube_corrosion_allowance_mm,
    )

    actual_tube_wall = (
        inp.tube_od_m - inp.tube_id_m
    ) * 1000.0 / 2.0

    shell_nozzle = size_nozzle(
        mass_flow_kg_s=inp.shell_mass_flow_kg_s,
        density_kg_m3=inp.shell_density_kg_m3,
        target_velocity_m_s=inp.shell_nozzle_target_velocity_m_s,
    )

    tube_nozzle = size_nozzle(
        mass_flow_kg_s=inp.tube_mass_flow_kg_s,
        density_kg_m3=inp.tube_density_kg_m3,
        target_velocity_m_s=inp.tube_nozzle_target_velocity_m_s,
    )

    checks = run_tema_geometry_checks(
        shell_id_m=inp.shell_inside_diameter_m,
        tube_od_m=inp.tube_od_m,
        tube_pitch_m=inp.tube_pitch_m,
        tube_length_m=inp.tube_length_m,
        tube_passes=inp.tube_passes,
        baffle_count=inp.baffle_count,
        baffle_cut_fraction=inp.baffle_cut_fraction,
        shell_type=inp.shell_type,
        front_head=inp.front_head,
        rear_head=inp.rear_head,
    )

    warnings: list[str] = []

    if selected_shell < shell_required:
        warnings.append(
            "Selected shell nominal thickness is below the pressure-screening requirement."
        )

    if actual_tube_wall < required_tube_wall:
        warnings.append(
            "Actual tube wall is below the preliminary internal-pressure screen."
        )

    if shell_mawp < inp.shell_design_pressure_bar:
        warnings.append(
            "Calculated shell MAWP screen is below the entered shell design pressure."
        )

    if shell_nozzle.warning:
        warnings.append(shell_nozzle.warning)
    if tube_nozzle.warning:
        warnings.append(tube_nozzle.warning)

    if any(c.status == "REVIEW" for c in checks):
        warnings.append(
            "One or more TEMA-style geometry screening checks require review."
        )

    delta_p = abs(
        inp.tube_design_pressure_bar - inp.shell_design_pressure_bar
    )

    design_notes = [
        (
            f"TEMA class {inp.tema_class} is recorded as a design-basis input only; "
            "HX-RACE does not certify compliance with a TEMA class."
        ),
        (
            "Tubesheet thickness, flange design, gasket seating, nozzle reinforcement, "
            "external pressure/buckling, wind/seismic, lifting lugs, saddles, fatigue, "
            "thermal stress and vibration require dedicated mechanical calculations."
        ),
        (
            "Material allowable stresses in HX-RACE are screening anchors. "
            "Use the governing code material tables for final design."
        ),
    ]

    return MechanicalDesignResult(
        tema_code=inp.tema_code,
        tema_class=inp.tema_class,
        shell_allowable_stress_mpa=shell_s,
        tube_allowable_stress_mpa=tube_s,
        required_shell_thickness_mm=shell_required,
        suggested_shell_nominal_mm=shell_suggested,
        required_head_thickness_mm=head_required,
        suggested_head_nominal_mm=head_suggested,
        selected_shell_nominal_mm=selected_shell,
        shell_mawp_bar=shell_mawp,
        shell_pressure_margin_bar=shell_mawp - inp.shell_design_pressure_bar,
        required_tube_wall_mm=required_tube_wall,
        actual_tube_wall_mm=actual_tube_wall,
        tube_wall_margin_mm=actual_tube_wall - required_tube_wall,
        shell_nozzle=shell_nozzle.as_dict(),
        tube_nozzle=tube_nozzle.as_dict(),
        differential_design_pressure_bar=delta_p,
        geometry_checks=[c.as_dict() for c in checks],
        warnings=warnings,
        design_notes=design_notes,
    )
