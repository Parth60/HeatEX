from __future__ import annotations

import math


def _validate_pressure_inputs(
    design_pressure_bar: float,
    diameter_mm: float,
    allowable_stress_mpa: float,
    joint_efficiency: float,
    corrosion_allowance_mm: float,
):
    if design_pressure_bar <= 0:
        raise ValueError("Design pressure must be positive.")
    if diameter_mm <= 0:
        raise ValueError("Diameter must be positive.")
    if allowable_stress_mpa <= 0:
        raise ValueError("Allowable stress must be positive.")
    if not (0.1 <= joint_efficiency <= 1.0):
        raise ValueError("Joint efficiency must be between 0.1 and 1.0.")
    if corrosion_allowance_mm < 0:
        raise ValueError("Corrosion allowance cannot be negative.")


def cylindrical_shell_thickness_mm(
    design_pressure_bar: float,
    inside_diameter_mm: float,
    allowable_stress_mpa: float,
    joint_efficiency: float = 1.0,
    corrosion_allowance_mm: float = 1.5,
) -> float:
    """
    ASME-style internal-pressure screening for a cylindrical shell:

        t = P D / (2 S E - 1.2 P) + CA

    P and S in MPa.

    IMPORTANT:
    This is a preliminary screening equation only. It does not include all
    governing-code requirements, external pressure, wind/seismic loads,
    nozzle reinforcement, tolerances, forming allowance, MDMT, fatigue,
    cyclic service, local stresses or manufacturer rules.
    """
    _validate_pressure_inputs(
        design_pressure_bar,
        inside_diameter_mm,
        allowable_stress_mpa,
        joint_efficiency,
        corrosion_allowance_mm,
    )

    p = design_pressure_bar * 0.1  # bar -> MPa
    denominator = 2.0 * allowable_stress_mpa * joint_efficiency - 1.2 * p

    if denominator <= 0:
        raise ValueError("Pressure equation denominator is non-positive.")

    pressure_t = p * inside_diameter_mm / denominator
    return pressure_t + corrosion_allowance_mm


def elliptical_head_thickness_mm(
    design_pressure_bar: float,
    inside_diameter_mm: float,
    allowable_stress_mpa: float,
    joint_efficiency: float = 1.0,
    corrosion_allowance_mm: float = 1.5,
) -> float:
    """
    2:1 elliptical-head pressure-screening equation:

        t = P D / (2 S E - 0.2 P) + CA

    Preliminary only; not code certification.
    """
    _validate_pressure_inputs(
        design_pressure_bar,
        inside_diameter_mm,
        allowable_stress_mpa,
        joint_efficiency,
        corrosion_allowance_mm,
    )

    p = design_pressure_bar * 0.1
    denominator = 2.0 * allowable_stress_mpa * joint_efficiency - 0.2 * p

    if denominator <= 0:
        raise ValueError("Head pressure equation denominator is non-positive.")

    return p * inside_diameter_mm / denominator + corrosion_allowance_mm


def cylindrical_shell_mawp_bar(
    nominal_thickness_mm: float,
    inside_diameter_mm: float,
    allowable_stress_mpa: float,
    joint_efficiency: float = 1.0,
    corrosion_allowance_mm: float = 1.5,
) -> float:
    """
    Inversion of the shell screening equation.

        P = 2 S E t / (D + 1.2 t)

    Uses effective thickness after corrosion allowance.
    """
    if nominal_thickness_mm <= corrosion_allowance_mm:
        return 0.0

    t = nominal_thickness_mm - corrosion_allowance_mm

    p_mpa = (
        2.0 * allowable_stress_mpa * joint_efficiency * t
        / (inside_diameter_mm + 1.2 * t)
    )

    return p_mpa * 10.0


def tube_wall_screen_mm(
    design_pressure_bar: float,
    tube_od_mm: float,
    allowable_stress_mpa: float,
    joint_efficiency: float = 1.0,
    corrosion_allowance_mm: float = 0.0,
) -> float:
    """
    Preliminary Barlow-style tube-wall pressure screen:

        t = P Do / (2 S E) + CA

    This is intentionally conservative/simple and does not replace tube
    specification, manufacturing tolerance, external-pressure collapse,
    vibration/erosion allowance, rolling/grooving requirements or code design.
    """
    _validate_pressure_inputs(
        design_pressure_bar,
        tube_od_mm,
        allowable_stress_mpa,
        joint_efficiency,
        corrosion_allowance_mm,
    )

    p = design_pressure_bar * 0.1

    return (
        p * tube_od_mm
        / (2.0 * allowable_stress_mpa * joint_efficiency)
        + corrosion_allowance_mm
    )


def round_up_nominal_mm(required_mm: float) -> float:
    """
    Round to a practical preliminary plate-thickness ladder.
    """
    nominal = [
        1.0, 1.2, 1.5, 1.6, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0,
        8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 25.0,
        28.0, 30.0, 32.0, 36.0, 40.0, 45.0, 50.0, 60.0,
    ]

    for value in nominal:
        if value >= required_mm:
            return value

    return math.ceil(required_mm / 5.0) * 5.0
