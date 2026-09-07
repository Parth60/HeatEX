from __future__ import annotations


def telemetry_card(label: str, value: str, subtitle: str = "") -> str:
    return f"""
    <div class="hx-kpi">
      <div class="hx-kpi-label">{label}</div>
      <div class="hx-kpi-value">{value}</div>
      <div class="hx-kpi-sub">{subtitle}</div>
    </div>
    """


def cockpit_css() -> str:
    return """
    <style>
    .stApp {
        background:
          radial-gradient(circle at 15% 10%, rgba(255,59,48,0.08), transparent 30%),
          radial-gradient(circle at 85% 20%, rgba(100,210,255,0.06), transparent 25%),
          #0B0D10;
    }

    .block-container {
        max-width: 1500px;
        padding-top: 1.6rem;
        padding-bottom: 3rem;
    }

    h1, h2, h3 {
        letter-spacing: -0.02em;
    }

    .hx-topline {
        display:flex;
        align-items:center;
        gap:.65rem;
        flex-wrap:wrap;
        color:#AAB2BD;
        font-size:.78rem;
        font-weight:800;
        text-transform:uppercase;
        letter-spacing:.18em;
        margin-bottom:.4rem;
    }

    .hx-brand {
        font-size:2rem;
        line-height:1;
        font-weight:900;
        color:#F5F7FA;
        letter-spacing:-.04em;
    }

    .hx-code {
        display:inline-block;
        border:1px solid #3C434D;
        border-left:4px solid #FF3B30;
        padding:.38rem .7rem;
        font-size:.85rem;
        font-weight:800;
        color:#F5F7FA;
        background:#15191F;
        transform:skew(-5deg);
    }

    .hx-kpi-grid {
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:.75rem;
        margin:.7rem 0 1rem 0;
    }

    .hx-kpi {
        position:relative;
        overflow:hidden;
        border:1px solid #303640;
        background:linear-gradient(145deg,#171B21,#101318);
        border-radius:12px;
        padding:.85rem .9rem;
        min-height:105px;
    }

    .hx-kpi:before {
        content:"";
        position:absolute;
        top:0; left:0;
        width:44%;
        height:3px;
        background:#FF3B30;
    }

    .hx-kpi-label {
        color:#9EA7B2;
        font-size:.70rem;
        font-weight:800;
        text-transform:uppercase;
        letter-spacing:.12em;
    }

    .hx-kpi-value {
        color:#F5F7FA;
        font-size:1.62rem;
        font-weight:900;
        margin-top:.25rem;
        font-variant-numeric:tabular-nums;
    }

    .hx-kpi-sub {
        color:#7F8995;
        font-size:.72rem;
        margin-top:.25rem;
    }

    .hx-panel-title {
        color:#AAB2BD;
        font-size:.72rem;
        font-weight:800;
        text-transform:uppercase;
        letter-spacing:.15em;
        margin-bottom:.2rem;
    }

    .hx-status-ok {
        padding:.6rem .75rem;
        border:1px solid #276749;
        background:rgba(39,103,73,.12);
        border-radius:10px;
        color:#B7F7D2;
        font-size:.86rem;
        font-weight:700;
    }

    .hx-status-warn {
        padding:.6rem .75rem;
        border:1px solid #8A5A00;
        background:rgba(138,90,0,.10);
        border-radius:10px;
        color:#FFD98A;
        font-size:.86rem;
    }

    div[data-testid="stMetric"] {
        background:#15191F;
        border:1px solid #303640;
        padding:.7rem .8rem;
        border-radius:10px;
    }

    @media (max-width:900px) {
        .hx-kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }

    @media (max-width:520px) {
        .hx-kpi-grid { grid-template-columns:1fr; }
        .hx-brand { font-size:1.55rem; }
    }
    </style>
    """
