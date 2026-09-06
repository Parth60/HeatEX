from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass
class TubePoint:
    x: float
    y: float


def generate_tube_bundle(
    shell_radius: float,
    pitch: float,
    tube_radius: float,
    layout: str = "triangular",
    max_tubes: int | None = None,
) -> list[TubePoint]:
    if shell_radius <= 0 or pitch <= 0 or tube_radius <= 0:
        raise ValueError("Geometry dimensions must be positive.")

    usable_radius = shell_radius - tube_radius - 0.02 * shell_radius
    if usable_radius <= 0:
        return []

    pts: list[TubePoint] = []
    n = int(math.ceil(usable_radius / pitch)) + 2
    layout_l = layout.lower()

    for row in range(-n, n + 1):
        for col in range(-n, n + 1):
            if "tri" in layout_l:
                x = col * pitch + (0.5 * pitch if row % 2 else 0.0)
                y = row * pitch * math.sqrt(3.0) / 2.0
            elif "rotated" in layout_l:
                x = (col - row) * pitch / math.sqrt(2.0)
                y = (col + row) * pitch / math.sqrt(2.0)
            else:
                x = col * pitch
                y = row * pitch

            if x*x + y*y <= usable_radius*usable_radius:
                pts.append(TubePoint(x=x, y=y))
                if max_tubes and len(pts) >= max_tubes:
                    return pts

    return pts
