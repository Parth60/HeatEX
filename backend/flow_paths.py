from __future__ import annotations


def shell_flow_path_points(
    x0: float,
    x1: float,
    y_top: float,
    y_bottom: float,
    baffle_count: int,
) -> list[tuple[float, float]]:
    if baffle_count < 0:
        raise ValueError("Baffle count cannot be negative.")

    pts = [(x0, (y_top + y_bottom) / 2.0)]
    if baffle_count == 0:
        pts.append((x1, (y_top + y_bottom) / 2.0))
        return pts

    dx = (x1 - x0) / (baffle_count + 1)

    for i in range(baffle_count):
        x = x0 + dx * (i + 1)
        y = y_bottom if i % 2 == 0 else y_top
        pts.append((x, y))

    pts.append((x1, (y_top + y_bottom) / 2.0))
    return pts


def svg_polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
