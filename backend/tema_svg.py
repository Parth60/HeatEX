from __future__ import annotations
from .flow_paths import shell_flow_path_points, svg_polyline


FRONT_NAMES = {
    "A": "Channel + removable cover",
    "B": "Bonnet",
    "C": "Integral channel + removable cover",
    "N": "Integral channel",
    "D": "High-pressure closure",
}

SHELL_NAMES = {
    "E": "One-pass shell",
    "F": "Two-pass shell",
    "G": "Split flow",
    "H": "Double split flow",
    "J": "Divided flow",
    "K": "Kettle reboiler shell",
    "X": "Cross flow",
}

REAR_NAMES = {
    "L": "Fixed tubesheet / A style",
    "M": "Fixed tubesheet / bonnet",
    "N": "Fixed tubesheet / N style",
    "P": "Outside-packed floating head",
    "S": "Floating head with backing device",
    "T": "Pull-through floating head",
    "U": "U-tube bundle",
    "W": "Externally sealed floating tubesheet",
}


def _front_path(code: str) -> str:
    if code == "D":
        return "M130 65 L80 65 L58 95 L58 205 L80 235 L130 235"
    if code in {"A", "C", "N"}:
        return "M130 65 L90 65 Q67 150 90 235 L130 235"
    return "M130 70 Q78 94 78 150 Q78 206 130 230"


def _rear_path(code: str) -> str:
    if code == "U":
        return "M630 70 Q705 95 670 150 Q705 205 630 230"
    if code in {"P", "S", "T", "W"}:
        return "M630 65 L675 65 Q700 150 675 235 L630 235"
    return "M630 70 Q682 94 682 150 Q682 206 630 230"


def tema_longitudinal_svg(
    front: str = "B",
    shell: str = "E",
    rear: str = "M",
    baffle_count: int = 12,
    tube_passes: int = 2,
    animated: bool = True,
) -> str:
    code = f"{front}{shell}{rear}"
    baffles = []
    for i in range(baffle_count):
        x = 150 + 455 * (i + 1) / (baffle_count + 1)
        if i % 2 == 0:
            y1, y2 = 78, 188
        else:
            y1, y2 = 112, 222
        baffles.append(
            f"<line x1='{x:.2f}' x2='{x:.2f}' y1='{y1}' y2='{y2}' "
            "stroke='#8e8e93' stroke-width='3'/>"
        )

    pts = shell_flow_path_points(120, 642, 92, 208, baffle_count)
    shell_poly = svg_polyline(pts)

    animation_css = """
    .hx-flow{stroke-dasharray:15 11;animation:hxmove 1.05s linear infinite}
    @keyframes hxmove{to{stroke-dashoffset:-52}}
    """ if animated else ""

    title = (
        f"{code} • {FRONT_NAMES.get(front, front)} • "
        f"{SHELL_NAMES.get(shell, shell)} • {REAR_NAMES.get(rear, rear)}"
    )

    tube_paths = []
    if tube_passes <= 1:
        tube_paths.append(
            "<path class='hx-flow' d='M92 123 H665' stroke='#ff453a' "
            "stroke-width='6' fill='none' stroke-linecap='round'/>"
        )
    else:
        y0 = 112
        spacing = 28
        for p in range(min(tube_passes, 6)):
            y = y0 + p * spacing
            if p % 2 == 0:
                d = f"M92 {y} H655"
            else:
                d = f"M655 {y} H92"
            tube_paths.append(
                f"<path class='hx-flow' d='{d}' stroke='#ff453a' "
                "stroke-width='5' fill='none' stroke-linecap='round'/>"
            )

    return f"""
    <svg viewBox="0 0 760 300" width="100%" role="img"
         aria-label="TEMA {code} longitudinal exchanger schematic">
      <style>{animation_css}</style>
      <rect width="760" height="300" rx="18" fill="#0b0d10"/>
      <text x="380" y="29" text-anchor="middle" font-family="Arial"
            font-size="15" font-weight="700" fill="#f5f7fa">{title}</text>
      <rect x="130" y="58" width="500" height="185" rx="30"
            fill="#15191f" stroke="#7d8590" stroke-width="3"/>
      <path d="{_front_path(front)}" fill="none" stroke="#f5f7fa" stroke-width="4"/>
      <path d="{_rear_path(rear)}" fill="none" stroke="#f5f7fa" stroke-width="4"/>
      {''.join(baffles)}
      {''.join(tube_paths)}
      <polyline class="hx-flow" points="{shell_poly}" fill="none"
                stroke="#64d2ff" stroke-width="6" stroke-linecap="round"
                stroke-linejoin="round"/>
      <text x="92" y="272" font-family="Arial" font-size="13"
            font-weight="700" fill="#ff453a">TUBE-SIDE FLOW</text>
      <text x="552" y="272" font-family="Arial" font-size="13"
            font-weight="700" fill="#64d2ff">SHELL-SIDE FLOW</text>
    </svg>
    """
