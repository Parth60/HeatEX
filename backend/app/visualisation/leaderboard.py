from __future__ import annotations
from html import escape


def _position_name(rank: int) -> str:
    if rank == 1:
        return "P1"
    if rank == 2:
        return "P2"
    if rank == 3:
        return "P3"
    return f"P{rank}"


def candidate_card(candidate: dict) -> str:
    rank = int(candidate["rank"])
    pos = _position_name(rank)

    return f"""
    <div class="hx-leader-card hx-p{rank}">
      <div class="hx-leader-head">
        <span class="hx-position">{pos}</span>
        <span class="hx-score">SCORE {candidate['objective_score']:.3f}</span>
      </div>

      <div class="hx-machine">
        {candidate['tube_count']} × {candidate['tube_od_mm']:.2f} mm
      </div>

      <div class="hx-leader-grid">
        <div>
          <span>AREA</span>
          <strong>{candidate['installed_area_m2']:.1f} m²</strong>
        </div>
        <div>
          <span>MARGIN</span>
          <strong>{candidate['area_margin_percent']:.1f}%</strong>
        </div>
        <div>
          <span>TUBE ΔP</span>
          <strong>{candidate['tube_dp_kpa']:.1f} kPa</strong>
        </div>
        <div>
          <span>SHELL ΔP</span>
          <strong>{candidate['shell_dp_kpa']:.1f} kPa</strong>
        </div>
      </div>

      <div class="hx-setup-line">
        {candidate['tube_length_m']:.1f} m tubes ·
        {candidate['tube_passes']} passes ·
        {candidate['baffle_count']} baffles ·
        {candidate['baffle_cut_percent']:.0f}% cut
      </div>
    </div>
    """


def leaderboard_css() -> str:
    return """
    <style>
    .hx-leaderboard {
        display:grid;
        grid-template-columns:repeat(3,minmax(0,1fr));
        gap:.8rem;
        margin:.6rem 0 1rem 0;
    }

    .hx-leader-card {
        border:1px solid #303640;
        border-radius:14px;
        padding:1rem;
        background:
          linear-gradient(160deg,rgba(255,255,255,.025),rgba(255,255,255,0)),
          #11151A;
        position:relative;
        overflow:hidden;
    }

    .hx-leader-card:before {
        content:"";
        position:absolute;
        left:0;
        top:0;
        height:4px;
        width:100%;
        background:#6B7280;
    }

    .hx-p1:before { background:#FFD60A; }
    .hx-p2:before { background:#AAB2BD; }
    .hx-p3:before { background:#C77D3B; }

    .hx-leader-head {
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:.5rem;
    }

    .hx-position {
        font-size:1.8rem;
        font-weight:950;
        letter-spacing:-.05em;
        color:#F5F7FA;
    }

    .hx-score {
        color:#8993A0;
        font-size:.68rem;
        font-weight:800;
        letter-spacing:.10em;
    }

    .hx-machine {
        margin-top:.55rem;
        font-size:1.02rem;
        font-weight:850;
        color:#F5F7FA;
    }

    .hx-leader-grid {
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:.55rem;
        margin-top:.85rem;
    }

    .hx-leader-grid div {
        padding:.5rem;
        border:1px solid #292F38;
        border-radius:8px;
        background:#0D1014;
    }

    .hx-leader-grid span {
        display:block;
        color:#7F8995;
        font-size:.62rem;
        font-weight:800;
        letter-spacing:.08em;
    }

    .hx-leader-grid strong {
        display:block;
        margin-top:.15rem;
        font-size:.93rem;
        color:#F5F7FA;
        font-variant-numeric:tabular-nums;
    }

    .hx-setup-line {
        margin-top:.75rem;
        color:#8993A0;
        font-size:.73rem;
        line-height:1.4;
    }

    @media(max-width:900px) {
        .hx-leaderboard { grid-template-columns:1fr; }
    }
    </style>
    """
