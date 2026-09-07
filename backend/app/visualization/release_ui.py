from __future__ import annotations


def final_release_css() -> str:
    return """
    <style>
      .hx-final-pill {
        display:inline-flex;
        align-items:center;
        gap:8px;
        padding:6px 10px;
        border:1px solid #3B4350;
        border-radius:999px;
        background:linear-gradient(90deg,rgba(100,210,255,.10),rgba(191,90,242,.10));
        color:#F5F7FA;
        font-size:11px;
        font-weight:900;
        letter-spacing:.09em;
      }
      .hx-release-grid {
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:10px;
        margin:10px 0 18px 0;
      }
      .hx-release-card {
        border:1px solid #2E3540;
        border-radius:14px;
        background:#101318;
        padding:12px 13px;
      }
      .hx-release-kicker {
        font-size:10px;
        font-weight:850;
        letter-spacing:.10em;
        color:#7F8995;
      }
      .hx-release-value {
        font-size:18px;
        font-weight:900;
        color:#F5F7FA;
        margin-top:3px;
      }
      @media(max-width:900px){
        .hx-release-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
      }
    </style>
    """


def release_banner_html(version: str, tema_code: str, package: str, units: str) -> str:
    return f"""
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
      <span class="hx-final-pill">🏁 HX//RACE v{version} FINAL</span>
      <span class="hx-final-pill">CONFIG {tema_code}</span>
      <span class="hx-final-pill">{package}</span>
      <span class="hx-final-pill">{units}</span>
    </div>
    """
