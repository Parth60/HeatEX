from __future__ import annotations


def plate_hx_svg(plates: int, passes_hot: int, passes_cold: int) -> str:
    n = max(8, min(24, int(plates // 4)))
    x0 = 130
    plate_w = 12
    gap = 8
    rects = []
    for i in range(n):
        x = x0 + i * (plate_w + gap)
        rects.append(
            f"<rect x='{x}' y='72' width='{plate_w}' height='150' rx='3' "
            f"fill='none' stroke='#AAB2BD' stroke-width='2'/>"
        )
    return f"""
    <svg viewBox="0 0 760 290" width="100%">
      <rect width="760" height="290" rx="20" fill="#0B0D10"/>
      <text x="380" y="32" text-anchor="middle" font-family="Arial"
            font-size="16" font-weight="800" fill="#F5F7FA">
        PLATE & FRAME // {plates} PLATES
      </text>
      <path d="M45 110 H120" stroke="#FF453A" stroke-width="7"/>
      <path d="M640 110 H715" stroke="#FF453A" stroke-width="7"/>
      <path d="M715 185 H640" stroke="#64D2FF" stroke-width="7"/>
      <path d="M120 185 H45" stroke="#64D2FF" stroke-width="7"/>
      {''.join(rects)}
      <text x="380" y="258" text-anchor="middle" font-family="Arial"
            font-size="12" fill="#8E99A6">
        Hot passes {passes_hot} · Cold passes {passes_cold}
      </text>
    </svg>
    """


def double_pipe_svg(hairpins: int) -> str:
    loops = max(1, min(8, int(hairpins)))
    y0 = 80
    paths = []
    for i in range(loops):
        y = y0 + i * 22
        paths.append(
            f"<path d='M110 {y} H610 Q655 {y} 655 {y+11} "
            f"Q655 {y+22} 610 {y+22} H110' fill='none' "
            f"stroke='#7D8590' stroke-width='8'/>"
        )
    return f"""
    <svg viewBox="0 0 760 320" width="100%">
      <rect width="760" height="320" rx="20" fill="#0B0D10"/>
      <text x="380" y="32" text-anchor="middle" font-family="Arial"
            font-size="16" font-weight="800" fill="#F5F7FA">
        DOUBLE PIPE // {hairpins} HAIRPINS
      </text>
      {''.join(paths)}
      <path d="M65 92 H650" stroke="#FF453A" stroke-width="4"
            stroke-dasharray="12 8"/>
      <path d="M650 118 H65" stroke="#64D2FF" stroke-width="4"
            stroke-dasharray="12 8"/>
      <text x="380" y="292" text-anchor="middle" font-family="Arial"
            font-size="12" fill="#8E99A6">
        Modular counter-current hairpin service
      </text>
    </svg>
    """


def air_cooler_svg(rows: int, tubes_per_row: int, fan_power_kw: float) -> str:
    fans = []
    for cx in [270, 490]:
        fans.append(
            f"""
            <circle cx="{cx}" cy="225" r="48" fill="none"
                    stroke="#64D2FF" stroke-width="4"/>
            <path d="M{cx} 225 l32 -9 l-22 25 z" fill="#64D2FF" opacity=".55"/>
            <path d="M{cx} 225 l-11 -31 l-13 30 z" fill="#64D2FF" opacity=".55"/>
            <path d="M{cx} 225 l-20 26 l34 -6 z" fill="#64D2FF" opacity=".55"/>
            """
        )
    return f"""
    <svg viewBox="0 0 760 320" width="100%">
      <rect width="760" height="320" rx="20" fill="#0B0D10"/>
      <text x="380" y="32" text-anchor="middle" font-family="Arial"
            font-size="16" font-weight="800" fill="#F5F7FA">
        AIR COOLED // {rows} ROWS × {tubes_per_row} TUBES
      </text>
      <rect x="100" y="70" width="560" height="95" rx="14"
            fill="#15191F" stroke="#7D8590" stroke-width="3"/>
      <g stroke="#FF9F0A" stroke-width="3">
        {''.join(
            f"<line x1='120' y1='{88+i*18}' x2='640' y2='{88+i*18}'/>"
            for i in range(4)
        )}
      </g>
      {''.join(fans)}
      <text x="380" y="304" text-anchor="middle" font-family="Arial"
            font-size="12" fill="#8E99A6">
        Fan power {fan_power_kw:.1f} kW · forced-draft screening layout
      </text>
    </svg>
    """
