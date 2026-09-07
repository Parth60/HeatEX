from __future__ import annotations


def multicomponent_hx_svg(
    segments: list[dict],
    mode: str,
    tema_code: str,
    width: int = 980,
    height: int = 320,
) -> str:
    if not segments:
        return "<div>No integrated segments.</div>"

    x0 = 58.0
    y0 = 92.0
    usable = width - 116.0
    h = 115.0
    seg_w = usable / len(segments)

    bodies = []

    for idx, seg in enumerate(segments):
        x = x0 + idx * seg_w
        beta = max(
            0.0,
            min(1.0, float(seg.get("beta_mean", 0.0))),
        )

        # beta=0 -> blue liquid, beta=1 -> purple vapour.
        r = int(100 + 91 * beta)
        g = int(210 - 120 * beta)
        b = int(255 - 13 * beta)
        colour = f"rgb({r},{g},{b})"

        regime = str(seg.get("regime", ""))

        bodies.append(
            f"""
            <rect x="{x:.2f}" y="{y0}" width="{seg_w+0.5:.2f}" height="{h}"
                  fill="{colour}" fill-opacity="0.28"
                  stroke="#2C333D" stroke-width="1"/>
            <text x="{x+seg_w/2:.2f}" y="{y0+38}"
                  text-anchor="middle" font-family="Arial" font-size="10"
                  fill="#F5F7FA">S{idx+1}</text>
            <text x="{x+seg_w/2:.2f}" y="{y0+59}"
                  text-anchor="middle" font-family="Arial" font-size="10"
                  fill="#AAB2BD">β {beta:.2f}</text>
            <text x="{x+seg_w/2:.2f}" y="{y0+81}"
                  text-anchor="middle" font-family="Arial" font-size="9"
                  fill="#AAB2BD">{regime}</text>
            """
        )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%"
         role="img" aria-label="Multicomponent phase-change exchanger segmentation">
      <defs>
        <linearGradient id="legendGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#64D2FF"/>
          <stop offset="100%" stop-color="#BF5AF2"/>
        </linearGradient>
      </defs>

      <rect width="{width}" height="{height}" rx="20" fill="#0B0D10"/>

      <text x="{width/2}" y="34" text-anchor="middle"
            font-family="Arial" font-size="17" font-weight="800"
            fill="#F5F7FA">
        {tema_code} // MULTICOMPONENT {mode.upper()}
      </text>

      <path d="M28 {y0+h/2} H{x0}" stroke="#FF9F0A"
            stroke-width="7" stroke-linecap="round"/>

      {''.join(bodies)}

      <path d="M{x0+usable} {y0+h/2} H{width-28}"
            stroke="#FF453A" stroke-width="7" stroke-linecap="round"/>

      <rect x="{width/2-130}" y="246" width="260" height="13"
            rx="6" fill="url(#legendGrad)"/>

      <text x="{width/2-140}" y="258" text-anchor="end"
            font-family="Arial" font-size="11" fill="#64D2FF">
        LIQUID β=0
      </text>

      <text x="{width/2+140}" y="258"
            font-family="Arial" font-size="11" fill="#BF5AF2">
        β=1 VAPOUR
      </text>

      <text x="{width/2}" y="294" text-anchor="middle"
            font-family="Arial" font-size="11" fill="#7F8995">
        Colour represents local equilibrium vapour fraction; segments are computational cells.
      </text>
    </svg>
    """
