from __future__ import annotations
from html import escape


ZONE_COLOURS = {
    "Desuperheating": "#FF453A",
    "Condensation": "#BF5AF2",
    "Subcooling": "#64D2FF",
    "Preheating": "#64D2FF",
    "Boiling": "#FF9F0A",
    "Superheating": "#FF453A",
}


def phase_zone_svg(
    zones: list[dict],
    operation: str,
    tema_code: str,
    width: int = 920,
    height: int = 310,
) -> str:
    if not zones:
        return "<div>No phase-change zones.</div>"

    x0 = 70
    y0 = 95
    usable = width - 140
    body_h = 105

    rects = []
    labels = []

    cursor = x0

    for i, zone in enumerate(zones):
        frac = max(0.035, float(zone.get("duty_fraction", 0.0)))
        zone_w = usable * frac

        # Ensure final zone ends exactly at the exchanger boundary.
        if i == len(zones) - 1:
            zone_w = x0 + usable - cursor

        name = str(zone.get("name", "Zone"))
        colour = ZONE_COLOURS.get(name, "#8E8E93")

        rects.append(
            f"""
            <rect x="{cursor:.1f}" y="{y0}" width="{zone_w:.1f}" height="{body_h}"
                  rx="8" fill="{colour}" fill-opacity="0.18"
                  stroke="{colour}" stroke-width="2"/>
            """
        )

        labels.append(
            f"""
            <text x="{cursor + zone_w/2:.1f}" y="{y0 + 35}"
                  text-anchor="middle" font-family="Arial" font-size="13"
                  font-weight="700" fill="#F5F7FA">{escape(name)}</text>
            <text x="{cursor + zone_w/2:.1f}" y="{y0 + 58}"
                  text-anchor="middle" font-family="Arial" font-size="12"
                  fill="#AAB2BD">{zone.get('duty_kw', 0):.1f} kW</text>
            <text x="{cursor + zone_w/2:.1f}" y="{y0 + 78}"
                  text-anchor="middle" font-family="Arial" font-size="11"
                  fill="#AAB2BD">{zone.get('required_area_m2', 0):.1f} m²</text>
            """
        )

        cursor += zone_w

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%"
         role="img" aria-label="{escape(operation)} phase-zone exchanger">
      <rect width="{width}" height="{height}" rx="20" fill="#0B0D10"/>
      <text x="{width/2}" y="35" text-anchor="middle"
            font-family="Arial" font-size="17" font-weight="800"
            fill="#F5F7FA">{escape(tema_code)} // {escape(operation.upper())} ZONE MAP</text>

      <path d="M45 {y0+body_h/2} H{x0}" stroke="#FF453A"
            stroke-width="6" stroke-linecap="round"/>
      <path d="M{x0+usable} {y0+body_h/2} H{width-45}" stroke="#64D2FF"
            stroke-width="6" stroke-linecap="round"/>

      {''.join(rects)}
      {''.join(labels)}

      <text x="{x0}" y="{height-50}" font-family="Arial" font-size="12"
            font-weight="700" fill="#FF453A">PROCESS IN</text>
      <text x="{x0+usable}" y="{height-50}" text-anchor="end"
            font-family="Arial" font-size="12" font-weight="700"
            fill="#64D2FF">PROCESS OUT</text>
      <text x="{width/2}" y="{height-18}" text-anchor="middle"
            font-family="Arial" font-size="11" fill="#7F8995">
        Zone length is proportional to calculated duty fraction, not fabrication length.
      </text>
    </svg>
    """
