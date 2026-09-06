from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from app.engine.optimizer import optimize
    from app.engine.shell_tube import simulate
    from app.models import (
        FlowArrangement,
        GeometryInput,
        Mode,
        SimulationRequest,
        StreamInput,
        TemaInput,
        ThermalSpec,
        ThermoPackage,
    )
except Exception as exc:  # Friendly repo-setup error.
    st.error(
        "HX//RACE backend could not be imported. Keep this `streamlit_app` folder "
        "beside the existing `backend` folder from HX-RACE v0.1."
    )
    st.exception(exc)
    st.stop()

st.set_page_config(
    page_title="HX//RACE",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
.hxr-title {font-size: clamp(2rem, 4vw, 4.4rem); font-weight: 950; line-height: .92; letter-spacing:-.055em;}
.hxr-kicker {font-size:.75rem; letter-spacing:.22em; font-weight:800; opacity:.7; text-transform:uppercase;}
.hxr-rule {height:3px; border-radius:99px; background:linear-gradient(90deg,#ff3b30,#e7e7e7,#71717a); margin:.7rem 0 1rem;}
.hxr-tag {display:inline-block; padding:.2rem .55rem; border:1px solid #424750; border-radius:999px; font-size:.72rem; margin-right:.35rem;}
.hxr-note {padding:.75rem 1rem; border:1px solid #333842; border-radius:.8rem; background:#11151a; font-size:.82rem;}
[data-testid="stMetric"] {border:1px solid #2c3138; padding:.75rem; border-radius:.75rem; background:#11151a;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="hxr-kicker">Heat Exchanger Engineering Telemetry</div>', unsafe_allow_html=True)
st.markdown('<div class="hxr-title">HX//RACE</div>', unsafe_allow_html=True)
st.markdown('<div class="hxr-rule"></div>', unsafe_allow_html=True)
st.markdown(
    '<span class="hxr-tag">DESIGN</span><span class="hxr-tag">RATING</span>'
    '<span class="hxr-tag">TEMA CONFIGURATION</span><span class="hxr-tag">OPTIMISATION</span>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("CONTROL WALL")
    mode = st.radio("Operating mode", ["design", "rating"], horizontal=True)
    thermo = st.selectbox(
        "Thermodynamic package",
        ["CoolProp", "Ideal", "Peng-Robinson", "SRK", "NRTL", "UNIQUAC", "IAPWS"],
        index=0,
    )
    flow = st.selectbox("Flow arrangement", ["counter-current", "co-current"])
    st.divider()
    st.subheader("TEMA")
    front = st.selectbox("Front head", ["A", "B", "C", "N", "D"], index=1)
    shell = st.selectbox("Shell", ["E", "F", "G", "H", "J", "K", "X"], index=0)
    rear = st.selectbox("Rear head", ["L", "M", "N", "P", "S", "T", "U", "W"], index=1)
    tema_code = f"{front}{shell}{rear}"
    st.success(f"Selected: {tema_code}")

left, center, right = st.columns([1.0, 1.35, 1.0], gap="large")

with left:
    st.subheader("01 / STREAMS")
    with st.container(border=True):
        st.caption("HOT SIDE")
        hot_fluid = st.selectbox("Hot fluid", ["Ethanol", "Water", "Butanol", "Thermal oil", "Light hydrocarbon"])
        c1, c2 = st.columns(2)
        hot_t = c1.number_input("T in / °C", value=140.0, step=1.0)
        hot_m = c2.number_input("Flow / kg s⁻¹", min_value=0.01, value=12.0, step=0.1)
        hot_p = st.number_input("Hot pressure / bar", min_value=0.1, value=4.0, step=0.1)

        st.caption("COLD SIDE")
        cold_fluid = st.selectbox("Cold fluid", ["Water", "Ethanol", "Butanol", "Thermal oil", "Light hydrocarbon"])
        c3, c4 = st.columns(2)
        cold_t = c3.number_input("Cold T in / °C", value=25.0, step=1.0)
        cold_m = c4.number_input("Cold flow / kg s⁻¹", min_value=0.01, value=18.0, step=0.1)
        cold_p = st.number_input("Cold pressure / bar", min_value=0.1, value=3.0, step=0.1)

    st.subheader("02 / THERMAL TARGET")
    spec_label = st.selectbox("Specification", ["Hot outlet temperature", "Cold outlet temperature", "Heat duty"])
    if spec_label == "Hot outlet temperature":
        thermal_spec = "hot-outlet"
        target = st.number_input("Target hot outlet / °C", value=70.0, step=1.0)
    elif spec_label == "Cold outlet temperature":
        thermal_spec = "cold-outlet"
        target = st.number_input("Target cold outlet / °C", value=65.0, step=1.0)
    else:
        thermal_spec = "duty"
        target = st.number_input("Specified duty / kW", min_value=1.0, value=2500.0, step=50.0)

with center:
    st.subheader("03 / LIVE MACHINE")
    g1, g2, g3 = st.columns(3)
    shell_id = g1.number_input("Shell ID / m", min_value=0.11, value=0.80, step=0.01)
    tube_od = g2.selectbox("Tube OD / mm", [15.88, 19.05, 25.40, 31.75], index=1)
    tube_id_default = {15.88: 12.7, 19.05: 15.75, 25.40: 21.18, 31.75: 27.86}[tube_od]
    tube_id = g3.number_input("Tube ID / mm", min_value=3.1, max_value=float(tube_od - 0.1), value=float(tube_id_default), step=0.1)
    g4, g5, g6 = st.columns(3)
    tube_length = g4.number_input("Tube length / m", min_value=0.5, value=6.0, step=0.5)
    tube_count = g5.number_input("Tube count", min_value=4, max_value=10000, value=420, step=10)
    tube_passes = g6.selectbox("Tube passes", [1, 2, 4, 6, 8], index=1)
    g7, g8, g9 = st.columns(3)
    pitch = g7.number_input("Tube pitch / mm", min_value=float(tube_od + 0.1), value=max(25.0, float(tube_od * 1.25)), step=0.5)
    layout = g8.selectbox("Layout", ["triangular-30", "triangular-60", "square-90", "square-45"])
    baffles = g9.slider("Baffles", min_value=0, max_value=40, value=12)
    baffle_cut = st.slider("Baffle cut / %", min_value=10, max_value=50, value=25)

    # Lightweight schematic. The engineering result remains in Python.
    baffle_svg = []
    n_show = min(baffles, 18)
    for i in range(n_show):
        x = 160 + (430 * (i + 1) / (n_show + 1))
        y1, y2 = (70, 145) if i % 2 == 0 else (110, 190)
        baffle_svg.append(f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" stroke="#6b7280" stroke-width="3"/>')
    schematic = f"""
    <div style='font-family:Inter,Arial;background:#0d1117;border:1px solid #30363d;border-radius:14px;padding:10px'>
      <div style='display:flex;justify-content:space-between;color:#d6d9df;font-size:12px;font-weight:700;letter-spacing:.12em'><span>{tema_code}</span><span>{baffles} BAFFLES // {tube_passes} PASSES</span></div>
      <svg viewBox='0 0 720 245' style='width:100%;margin-top:5px'>
        <defs><marker id='a' markerWidth='8' markerHeight='8' refX='7' refY='3' orient='auto'><path d='M0 0L0 6L7 3Z' fill='#ff5b52'/></marker><marker id='b' markerWidth='8' markerHeight='8' refX='7' refY='3' orient='auto'><path d='M0 0L0 6L7 3Z' fill='#67b7ff'/></marker></defs>
        <rect x='125' y='55' width='480' height='145' rx='28' fill='#131820' stroke='#49515c' stroke-width='2'/>
        <path d='M125 70Q75 90 75 128Q75 170 125 187M605 70Q655 90 655 128Q655 170 605 187' fill='none' stroke='#d6d9df' stroke-width='3'/>
        {''.join(baffle_svg)}
        <g stroke='#38414b' stroke-width='2'><line x1='115' y1='102' x2='615' y2='102'/><line x1='115' y1='126' x2='615' y2='126'/><line x1='115' y1='150' x2='615' y2='150'/></g>
        <path d='M88 103H630' fill='none' stroke='#ff5b52' stroke-width='5' stroke-linecap='round' marker-end='url(#a)'/>
        <path d='M590 185C550 185 535 78 495 78S445 185 405 185S355 78 315 78S265 185 225 185S175 78 125 78' fill='none' stroke='#67b7ff' stroke-width='5' stroke-linecap='round' marker-end='url(#b)'/>
      </svg>
    </div>
    """
    components.html(schematic, height=270)

with right:
    st.subheader("04 / LIMITS")
    with st.container(border=True):
        tube_dp_limit = st.number_input("Tube ΔP limit / kPa", min_value=1.0, value=70.0)
        shell_dp_limit = st.number_input("Shell ΔP limit / kPa", min_value=1.0, value=50.0)
        wall_k = st.number_input("Tube wall k / W m⁻¹ K⁻¹", min_value=0.1, value=16.0)
        tube_foul = st.number_input("Tube fouling / m²K W⁻¹", min_value=0.0, value=0.0002, format="%.5f")
        shell_foul = st.number_input("Shell fouling / m²K W⁻¹", min_value=0.0, value=0.0002, format="%.5f")

request = SimulationRequest(
    mode=Mode(mode),
    thermo_package=ThermoPackage(thermo),
    flow_arrangement=FlowArrangement(flow),
    thermal_spec=ThermalSpec(thermal_spec),
    thermal_target=target,
    hot_stream=StreamInput(fluid=hot_fluid, mass_flow_kg_s=hot_m, inlet_temp_c=hot_t, pressure_bar=hot_p),
    cold_stream=StreamInput(fluid=cold_fluid, mass_flow_kg_s=cold_m, inlet_temp_c=cold_t, pressure_bar=cold_p),
    geometry=GeometryInput(
        shell_id_m=shell_id,
        tube_od_mm=tube_od,
        tube_id_mm=tube_id,
        tube_length_m=tube_length,
        tube_count=int(tube_count),
        tube_passes=int(tube_passes),
        tube_pitch_mm=pitch,
        tube_layout=layout,
        baffle_count=int(baffles),
        baffle_cut_pct=baffle_cut,
        tube_wall_k_w_mk=wall_k,
        tube_fouling_m2k_w=tube_foul,
        shell_fouling_m2k_w=shell_foul,
    ),
    tema=TemaInput(front=front, shell=shell, rear=rear),
    tube_dp_limit_kpa=tube_dp_limit,
    shell_dp_limit_kpa=shell_dp_limit,
)

st.divider()
st.subheader("05 / LIVE TELEMETRY")
try:
    result = simulate(request)
except Exception as exc:
    st.error(str(exc))
    st.stop()

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Duty", f"{result.duty_kw/1000:.3f} MW")
m2.metric("Required A", f"{result.required_area_m2:.1f} m²")
m3.metric("Installed A", f"{result.installed_area_m2:.1f} m²")
m4.metric("Overall U", f"{result.overall_u_w_m2k:.0f} W/m²K")
m5.metric("Tube ΔP", f"{result.tube_dp_kpa:.1f} kPa")
m6.metric("Score", f"{result.screening_score:.1f}/100")

p1, p2 = st.columns([1.2, 1])
with p1:
    st.markdown("#### Thermal / hydraulic detail")
    table = pd.DataFrame(
        [
            ["Hot outlet", result.hot_outlet_c, "°C"],
            ["Cold outlet", result.cold_outlet_c, "°C"],
            ["LMTD", result.lmtd_c, "°C"],
            ["Correction factor", result.correction_factor, "—"],
            ["Area margin", result.area_margin_pct, "%"],
            ["Tube velocity", result.tube_velocity_m_s, "m/s"],
            ["Tube Reynolds", result.tube_reynolds, "—"],
            ["Tube h", result.tube_h_w_m2k, "W/m²K"],
            ["Shell velocity", result.shell_velocity_m_s, "m/s"],
            ["Shell Reynolds", result.shell_reynolds, "—"],
            ["Shell h", result.shell_h_w_m2k, "W/m²K"],
            ["Shell ΔP", result.shell_dp_kpa, "kPa"],
        ],
        columns=["Parameter", "Value", "Unit"],
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
with p2:
    st.markdown("#### Race engineer")
    if result.warnings:
        for warning in result.warnings:
            st.warning(warning)
    else:
        st.success("No current screening warnings.")
    st.progress(min(100, max(0, int(result.screening_score))))
    st.caption("Score is a screening indicator, not a code-compliance certificate.")

st.subheader("06 / TECHNICAL PACK")
export_obj = {
    "request": request.model_dump(mode="json"),
    "result": result.model_dump(mode="json"),
}
json_bytes = json.dumps(export_obj, indent=2).encode("utf-8")
st.download_button(
    "Download simulation JSON",
    data=json_bytes,
    file_name=f"{tema_code}_HX_simulation.json",
    mime="application/json",
    use_container_width=True,
)

st.markdown(
    """
<div class='hxr-note'><b>Engineering boundary:</b> the current backend is a screening engine. Keep the wording <b>TEMA-aligned / TEMA configuration</b>, not “TEMA certified”. Production work should replace the provisional shell-side model and F-factor logic with validated implementations before design sign-off.</div>
""",
    unsafe_allow_html=True,
)
