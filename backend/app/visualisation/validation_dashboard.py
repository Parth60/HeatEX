from __future__ import annotations


def readiness_gauge_html(score: float, label: str) -> str:
    score = max(0.0, min(100.0, float(score)))

    return f"""
    <div style="
        background:#0B0D10;
        border:1px solid #303640;
        border-radius:16px;
        padding:18px;
        margin:4px 0 14px 0;
    ">
      <div style="
          display:flex;
          justify-content:space-between;
          align-items:end;
          gap:12px;
      ">
        <div>
          <div style="
              font-size:11px;
              letter-spacing:.12em;
              font-weight:800;
              color:#8993A0;
          ">MODEL READINESS</div>
          <div style="
              font-size:32px;
              font-weight:950;
              color:#F5F7FA;
              line-height:1.1;
          ">{score:.1f}<span style="font-size:16px;color:#8993A0"> / 100</span></div>
        </div>
        <div style="
            font-size:12px;
            font-weight:800;
            color:#F5F7FA;
            text-align:right;
        ">{label}</div>
      </div>

      <div style="
          width:100%;
          height:13px;
          border-radius:8px;
          background:#1B2027;
          overflow:hidden;
          margin-top:14px;
      ">
        <div style="
            height:100%;
            width:{score:.1f}%;
            background:linear-gradient(90deg,#64D2FF,#BF5AF2);
        "></div>
      </div>

      <div style="
          color:#7F8995;
          font-size:10px;
          margin-top:8px;
          line-height:1.4;
      ">
        Internal consistency/completeness score only - not uncertainty,
        statistical confidence, code approval or vendor guarantee.
      </div>
    </div>
    """
