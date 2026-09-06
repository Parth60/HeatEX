from __future__ import annotations
from .tube_bundle import generate_tube_bundle


def cross_section_svg(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    tube_layout: str,
    baffle_cut_fraction: float,
    tube_count: int,
    size_px: int = 520,
) -> str:
    r = size_px * 0.42
    cx = cy = size_px / 2.0

    scale = r / (shell_id_m / 2.0)
    tube_r = max(1.5, tube_od_m / 2.0 * scale)

    pts = generate_tube_bundle(
        shell_radius=shell_id_m / 2.0,
        pitch=tube_pitch_m,
        tube_radius=tube_od_m / 2.0,
        layout=tube_layout,
        max_tubes=tube_count,
    )

    cut_y = cy - r + 2.0 * r * baffle_cut_fraction

    circles = []
    for i, p in enumerate(pts):
        fill = "#ff453a" if i % 2 == 0 else "#64d2ff"
        circles.append(
            f"<circle cx='{cx + p.x*scale:.2f}' cy='{cy - p.y*scale:.2f}' "
            f"r='{tube_r:.2f}' fill='{fill}' fill-opacity='0.72' "
            "stroke='#0b0d10' stroke-width='0.55'/>"
        )

    return f"""
    <svg viewBox="0 0 {size_px} {size_px}" width="100%" role="img"
         aria-label="Shell and tube exchanger cross section">
      <rect width="{size_px}" height="{size_px}" rx="22" fill="#0b0d10"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="#15191f"
              stroke="#7d8590" stroke-width="4"/>
      <line x1="{cx-r}" y1="{cut_y}" x2="{cx+r}" y2="{cut_y}"
            stroke="#ffd60a" stroke-width="5" stroke-dasharray="10 8"/>
      {''.join(circles)}
      <text x="{cx}" y="{size_px-18}" text-anchor="middle"
            font-family="Arial" font-size="14" fill="#aab2bd">
        {len(pts)} tubes shown • {tube_layout} layout
      </text>
    </svg>
    """
