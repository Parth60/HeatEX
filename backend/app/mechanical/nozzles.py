from __future__ import annotations

from dataclasses import dataclass, asdict
import math


STANDARD_DN_MM = [
    15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150,
    200, 250, 300, 350, 400, 450, 500, 600, 700, 800,
]


@dataclass
class NozzleSizingResult:
    required_inside_diameter_mm: float
    selected_dn_mm: int
    selected_velocity_m_s: float
    volumetric_flow_m3_s: float
    target_velocity_m_s: float
    warning: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def size_nozzle(
    mass_flow_kg_s: float,
    density_kg_m3: float,
    target_velocity_m_s: float,
) -> NozzleSizingResult:
    if mass_flow_kg_s <= 0:
        raise ValueError("Mass flow must be positive.")
    if density_kg_m3 <= 0:
        raise ValueError("Density must be positive.")
    if target_velocity_m_s <= 0:
        raise ValueError("Target velocity must be positive.")

    q = mass_flow_kg_s / density_kg_m3
    required_area = q / target_velocity_m_s
    required_diameter = math.sqrt(4.0 * required_area / math.pi)

    required_mm = required_diameter * 1000.0

    selected = STANDARD_DN_MM[-1]
    for dn in STANDARD_DN_MM:
        if dn >= required_mm:
            selected = dn
            break

    area_selected = math.pi * (selected / 1000.0) ** 2 / 4.0
    selected_velocity = q / area_selected

    warning = None
    if required_mm > STANDARD_DN_MM[-1]:
        warning = (
            "Required nozzle exceeds the largest internal HX-RACE DN ladder; "
            "manual piping/mechanical design is required."
        )

    return NozzleSizingResult(
        required_inside_diameter_mm=required_mm,
        selected_dn_mm=selected,
        selected_velocity_m_s=selected_velocity,
        volumetric_flow_m3_s=q,
        target_velocity_m_s=target_velocity_m_s,
        warning=warning,
    )
