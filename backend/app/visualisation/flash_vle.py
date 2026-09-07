from __future__ import annotations


def flash_split_svg(
    vapour_fraction: float,
    phase: str,
    width: int = 820,
    height: int = 310,
) -> str:
    beta = max(0.0, min(1.0, float(vapour_fraction)))
    vap_pct = 100.0 * beta
    liq_pct = 100.0 - vap_pct

    vapor_h = max(8.0, 150.0 * beta)
    liquid_h = max(8.0, 150.0 * (1.0 - beta))

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%"
         role="img" aria-label="Flash drum vapour liquid split">

      <rect width="{width}" height="{height}" rx="20" fill="#0B0D10"/>

      <text x="{width/2}" y="34" text-anchor="middle"
            font-family="Arial" font-size="17" font-weight="800"
            fill="#F5F7FA">
        FLASH // {phase.upper()} // VF = {beta:.4f}
      </text>

      <path d="M70 150 H270" stroke="#FF9F0A" stroke-width="7"
            stroke-linecap="round"/>

      <rect x="270" y="65" width="220" height="180" rx="58"
            fill="#15191F" stroke="#7D8590" stroke-width="3"/>

      <rect x="280" y="{235-liquid_h:.2f}" width="200" height="{liquid_h:.2f}"
            rx="20" fill="#64D2FF" fill-opacity="0.34"/>

      <rect x="280" y="75" width="200" height="{vapor_h:.2f}"
            rx="20" fill="#BF5AF2" fill-opacity="0.25"/>

      <path d="M380 65 V25 H650" stroke="#BF5AF2" stroke-width="7"
            fill="none" stroke-linecap="round"/>

      <path d="M380 245 V285 H650" stroke="#64D2FF" stroke-width="7"
            fill="none" stroke-linecap="round"/>

      <text x="665" y="32" font-family="Arial" font-size="13"
            font-weight="800" fill="#BF5AF2">
        VAPOUR {vap_pct:.1f}%
      </text>

      <text x="665" y="290" font-family="Arial" font-size="13"
            font-weight="800" fill="#64D2FF">
        LIQUID {liq_pct:.1f}%
      </text>

      <text x="82" y="136" font-family="Arial" font-size="12"
            font-weight="800" fill="#FF9F0A">FEED</text>

      <text x="380" y="160" text-anchor="middle"
            font-family="Arial" font-size="15" font-weight="800"
            fill="#F5F7FA">VLE</text>
    </svg>
    """
