from __future__ import annotations


def mechanical_cutaway_svg(
    tema_code: str,
    shell_thickness_mm: float,
    head_thickness_mm: float,
    tube_wall_mm: float,
    shell_dn_mm: int,
    tube_dn_mm: int,
    width: int = 960,
    height: int = 330,
) -> str:
    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%"
         role="img" aria-label="Mechanical heat exchanger screening cutaway">
      <rect width="{width}" height="{height}" rx="20" fill="#0B0D10"/>

      <text x="{width/2}" y="32" text-anchor="middle"
            font-family="Arial" font-size="17" font-weight="800"
            fill="#F5F7FA">
        {tema_code} // MECHANICAL SCREEN
      </text>

      <rect x="155" y="92" width="650" height="120" rx="58"
            fill="#15191F" stroke="#AAB2BD" stroke-width="8"/>

      <path d="M215 113 H744" stroke="#FF453A"
            stroke-width="4" stroke-dasharray="12 8"/>
      <path d="M215 135 H744" stroke="#FF453A"
            stroke-width="4" stroke-dasharray="12 8"/>
      <path d="M215 169 H744" stroke="#64D2FF"
            stroke-width="4" stroke-dasharray="12 8"/>
      <path d="M215 191 H744" stroke="#64D2FF"
            stroke-width="4" stroke-dasharray="12 8"/>

      <path d="M245 78 V53 H180" stroke="#BF5AF2" stroke-width="8"/>
      <path d="M715 78 V53 H780" stroke="#BF5AF2" stroke-width="8"/>

      <path d="M130 126 H95" stroke="#FF9F0A" stroke-width="8"/>
      <path d="M830 178 H865" stroke="#FF9F0A" stroke-width="8"/>

      <text x="480" y="244" text-anchor="middle"
            font-family="Arial" font-size="12" fill="#AAB2BD">
        Shell t ≈ {shell_thickness_mm:.1f} mm · Head t ≈ {head_thickness_mm:.1f} mm · Tube wall {tube_wall_mm:.2f} mm
      </text>

      <text x="480" y="268" text-anchor="middle"
            font-family="Arial" font-size="12" fill="#AAB2BD">
        Shell nozzles DN{shell_dn_mm} · Tube nozzles DN{tube_dn_mm}
      </text>

      <text x="480" y="302" text-anchor="middle"
            font-family="Arial" font-size="10" fill="#7F8995">
        Preliminary mechanical visualisation only — not an ASME/TEMA fabrication drawing.
      </text>
    </svg>
    """
