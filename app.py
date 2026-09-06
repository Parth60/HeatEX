from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.bell_delaware import BellDelawareInputs
from backend.app.engine.simulator import (
    StreamInput,
    HXSimulationInput,
    simulate_shell_and_tube,
)
from backend.app.visualization.tema_svg import tema_longitudinal_svg
from backend.app.visualization.cross_section import cross_section_svg
from backend.app.visualization.telemetry import cockpit_css


st.set_page_config(
    page_title="HX//RACE",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(cockpit_css(), unsafe_allow_html=True)

FRONT = {
    "A": "Channel + removable cover",
    "B": "Bonnet",
    "C": "Integral channel + removable cover",
    "N": "Integral channel",
    "D": "High-pressure closure",
}

SHELL = {
    "E": "One-pass shell",
    "F": "Two-pass shell",
    "G": "Split flow",
    "H": "Double split flow",
    "J": "Divided flow",
    "K": "Kettle reboiler",
    "X": "Cross flow",
}

REAR = {
    "L": "Fixed tubesheet / A style",
    "M": "Fixed tubesheet / bonnet",
    "N": "Fixed tubesheet / N style",
    "P": "Outside-packed floating",
    "S": "Floating head + backing device",
    "T": "Pull-through floating head",
    "U": "U-tube bundle",
    "W": "Externally sealed floating tubesheet",
}

FLUIDS = [
    "Water",
    "Ethanol",
    "Butanol",
    "Acetone",
    "Thermal oil",
    "Light hydrocarbon",
]


def fmt(x: float, decimals: int = 1) -> str:
    return f"{x:,.{decimals}f}"


with st.sidebar:
    st.markdown("### MACHINE SETUP")

    mode = st.radio(
        "Mode",
        ["Design", "Rating"],
        horizontal=True,
        help="v0.3 calculates a design case. Full independent rating-mode solving comes in a later batch.",
    )

    st.divider()

    st.markdown("#### TEMA CONFIGURATION")

    front = st.selectbox(
        "Front head",
        list(FRONT),
        index=list(FRONT).index("B"),
        format_func=lambda x: f"{x} — {FRONT[x]}",
    )

    shell = st.selectbox(
        "Shell",
        list(SHELL),
        index=list(SHELL).index("E"),
        format_func=lambda x: f"{x} — {SHELL[x]}",
    )

    rear = st.selectbox(
        "Rear head",
        list(REAR),
        index=list(REAR).index("M"),
        format_func=lambda x: f"{x} — {REAR[x]}",
    )

    tema_code = f"{front}{shell}{rear}"

    st.divider()

    st.markdown("#### THERMODYNAMICS")

    thermo_package = st.selectbox(
        "Property engine",
        ["Fallback database", "CoolProp"],
        help="CoolProp is used where a current supported pure-fluid mapping is available.",
    )

    flow_arrangement = st.selectbox(
        "Flow arrangement",
        ["Counter-current", "Co-current"],
    )

    st.divider()

    st.markdown("#### DESIGN LIMITS")

    allowable_tube_dp = st.number_input(
        "Max tube ΔP [kPa]",
        min_value=1.0,
        value=70.0,
        step=5.0,
    )

    allowable_shell_dp = st.number_input(
        "Max shell ΔP [kPa]",
        min_value=1.0,
        value=50.0,
        step=5.0,
    )


st.markdown(
    f"""
    <div class="hx-topline">
        <span>HX//RACE</span>
        <span>•</span>
        <span>THERMAL-HYDRAULIC ENGINE</span>
        <span>•</span>
        <span>v0.3 COCKPIT</span>
    </div>
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:8px;">
        <div class="hx-brand">HEAT EXCHANGER TELEMETRY</div>
        <div class="hx-code">{tema_code}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    f"{FRONT[front]}  /  {SHELL[shell]}  /  {REAR[rear]}  ·  "
    f"{thermo_package}  ·  {flow_arrangement}"
)

tab_run, tab_geometry, tab_bell, tab_export = st.tabs(
    ["🏁 LIVE RUN", "🧩 GEOMETRY", "📡 BELL–DELAWARE", "📄 TECH PACK"]
)

with tab_run:
    c_hot, c_cold = st.columns(2)

    with c_hot:
        st.markdown('<div class="hx-panel-title">HOT / TUBE SIDE</div>', unsafe_allow_html=True)
        h1, h2 = st.columns(2)
        with h1:
            hot_fluid = st.selectbox("Hot fluid", FLUIDS, index=1)
            hot_tin = st.number_input("Hot inlet [°C]", value=140.0, step=1.0)
            hot_p = st.number_input("Hot pressure [bar]", min_value=0.1, value=4.0, step=0.1)
        with h2:
            hot_flow = st.number_input("Hot flow [kg/s]", min_value=0.01, value=12.0, step=0.1)
            hot_tout = st.number_input("Target hot outlet [°C]", value=70.0, step=1.0)
            tube_fouling = st.number_input(
                "Tube fouling [m²·K/W]",
                min_value=0.0,
                value=0.0002,
                format="%.5f",
            )

    with c_cold:
        st.markdown('<div class="hx-panel-title">COLD / SHELL SIDE</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            cold_fluid = st.selectbox("Cold fluid", FLUIDS, index=0)
            cold_tin = st.number_input("Cold inlet [°C]", value=25.0, step=1.0)
            cold_p = st.number_input("Cold pressure [bar]", min_value=0.1, value=3.0, step=0.1)
        with c2:
            cold_flow = st.number_input("Cold flow [kg/s]", min_value=0.01, value=18.0, step=0.1)
            shell_fouling = st.number_input(
                "Shell fouling [m²·K/W]",
                min_value=0.0,
                value=0.0002,
                format="%.5f",
            )
            wall_k = st.number_input(
                "Tube-wall k [W/m·K]",
                min_value=1.0,
                value=16.0,
                step=1.0,
            )

with tab_geometry:
    st.markdown("### Chassis / Geometry")

    g1, g2, g3, g4 = st.columns(4)

    with g1:
        shell_id = st.number_input("Shell ID [m]", min_value=0.15, value=0.80, step=0.01)
        tube_od_mm = st.number_input("Tube OD [mm]", min_value=6.0, value=19.05, step=0.1)

    with g2:
        tube_id_mm = st.number_input("Tube ID [mm]", min_value=4.0, value=15.75, step=0.1)
        tube_length = st.number_input("Tube length [m]", min_value=0.5, value=6.0, step=0.1)

    with g3:
        tube_count = st.number_input("Tube count", min_value=4, value=420, step=1)
        tube_passes = st.selectbox("Tube passes", [1, 2, 4, 6, 8], index=1)

    with g4:
        tube_pitch_mm = st.number_input("Tube pitch [mm]", min_value=8.0, value=25.0, step=0.1)
        tube_layout = st.selectbox(
            "Tube layout",
            ["triangular", "square", "rotated square"],
        )

    b1, b2 = st.columns(2)

    with b1:
        baffle_count = st.slider("Number of baffles", 0, 30, 12, 1)

    with b2:
        baffle_cut = st.slider("Baffle cut [%]", 10, 50, 25, 1)


with tab_bell:
    st.markdown("### Bell–Delaware clearance inputs")

    bd1, bd2 = st.columns(2)

    with bd1:
        shell_baffle_clearance_mm = st.number_input(
            "Shell-to-baffle clearance [mm]",
            min_value=0.0,
            value=3.0,
            step=0.1,
        )
        tube_baffle_clearance_mm = st.number_input(
            "Tube-to-baffle diametral clearance [mm]",
            min_value=0.0,
            value=0.8,
            step=0.1,
        )

    with bd2:
        bundle_shell_clearance_mm = st.number_input(
            "Bundle-to-shell clearance [mm]",
            min_value=0.0,
            value=12.0,
            step=0.5,
        )
        sealing_strip_pairs = st.number_input(
            "Sealing-strip pairs",
            min_value=0,
            value=0,
            step=1,
        )

    st.info(
        "v0.3 exposes Bell–Delaware geometry directly so the correction factors "
        "can be inspected. The current coefficients remain development-stage "
        "screening correlations and must be validated before design release."
    )


# Build geometry and simulation after all tab widgets exist.
geometry = ShellTubeGeometry(
    shell_id_m=float(shell_id),
    tube_od_m=float(tube_od_mm) / 1000.0,
    tube_id_m=float(tube_id_mm) / 1000.0,
    tube_length_m=float(tube_length),
    tube_count=int(tube_count),
    tube_passes=int(tube_passes),
    tube_pitch_m=float(tube_pitch_mm) / 1000.0,
    tube_layout=str(tube_layout),
    baffle_count=int(baffle_count),
    baffle_cut_fraction=float(baffle_cut) / 100.0,
)

clearances = BellDelawareInputs(
    shell_to_baffle_clearance_m=float(shell_baffle_clearance_mm) / 1000.0,
    tube_to_baffle_clearance_m=float(tube_baffle_clearance_mm) / 1000.0,
    bundle_to_shell_clearance_m=float(bundle_shell_clearance_mm) / 1000.0,
    sealing_strip_pairs=int(sealing_strip_pairs),
)

sim_input = HXSimulationInput(
    hot=StreamInput(
        fluid=hot_fluid,
        mass_flow_kg_s=float(hot_flow),
        inlet_temperature_c=float(hot_tin),
        pressure_bar=float(hot_p),
    ),
    cold=StreamInput(
        fluid=cold_fluid,
        mass_flow_kg_s=float(cold_flow),
        inlet_temperature_c=float(cold_tin),
        pressure_bar=float(cold_p),
    ),
    geometry=geometry,
    front_head=front,
    shell_type=shell,
    rear_head=rear,
    thermo_package=thermo_package,
    flow_arrangement=flow_arrangement,
    hot_outlet_target_c=float(hot_tout),
    tube_wall_k_w_mk=float(wall_k),
    tube_fouling_m2k_w=float(tube_fouling),
    shell_fouling_m2k_w=float(shell_fouling),
    allowable_tube_dp_kpa=float(allowable_tube_dp),
    allowable_shell_dp_kpa=float(allowable_shell_dp),
    bell_clearances=clearances,
)

try:
    result = simulate_shell_and_tube(sim_input)
    sim_error = None
except Exception as exc:
    result = None
    sim_error = str(exc)


# Results are rendered below the tabs so the cockpit remains visible on every tab.
st.divider()

if sim_error:
    st.error(f"Simulation could not run: {sim_error}")
else:
    st.markdown(
        f"""
        <div class="hx-kpi-grid">
            <div class="hx-kpi">
              <div class="hx-kpi-label">HEAT DUTY</div>
              <div class="hx-kpi-value">{fmt(result.duty_kw/1000,2)} MW</div>
              <div class="hx-kpi-sub">Hot-side energy balance</div>
            </div>
            <div class="hx-kpi">
              <div class="hx-kpi-label">REQUIRED AREA</div>
              <div class="hx-kpi-value">{fmt(result.required_area_m2,1)} m²</div>
              <div class="hx-kpi-sub">Installed {fmt(result.installed_area_m2,1)} m²</div>
            </div>
            <div class="hx-kpi">
              <div class="hx-kpi-label">OVERALL U</div>
              <div class="hx-kpi-value">{fmt(result.overall_u_w_m2k,0)}</div>
              <div class="hx-kpi-sub">W/m²·K outside-area basis</div>
            </div>
            <div class="hx-kpi">
              <div class="hx-kpi-label">AREA MARGIN</div>
              <div class="hx-kpi-value">{fmt(result.area_margin_percent,1)}%</div>
              <div class="hx-kpi-sub">Installed vs required</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    vis_left, vis_right = st.columns([1.5, 1.0])

    with vis_left:
        st.markdown('<div class="hx-panel-title">LONGITUDINAL / FLOW TELEMETRY</div>', unsafe_allow_html=True)
        tema_svg = tema_longitudinal_svg(
            front=front,
            shell=shell,
            rear=rear,
            baffle_count=int(baffle_count),
            tube_passes=int(tube_passes),
            animated=True,
        )
        components.html(tema_svg, height=335, scrolling=False)

    with vis_right:
        st.markdown('<div class="hx-panel-title">CROSS SECTION / TUBE BUNDLE</div>', unsafe_allow_html=True)
        cs_svg = cross_section_svg(
            shell_id_m=float(shell_id),
            tube_od_m=float(tube_od_mm) / 1000.0,
            tube_pitch_m=float(tube_pitch_mm) / 1000.0,
            tube_layout=str(tube_layout),
            baffle_cut_fraction=float(baffle_cut) / 100.0,
            tube_count=int(tube_count),
            size_px=520,
        )
        components.html(cs_svg, height=420, scrolling=False)

    st.markdown("### Live telemetry")

    t1, t2, t3, t4 = st.columns(4)

    with t1:
        st.metric("Hot outlet", f"{fmt(result.hot_outlet_c,1)} °C")
        st.metric("Cold outlet", f"{fmt(result.cold_outlet_c,1)} °C")
        st.metric("LMTD", f"{fmt(result.lmtd_c,1)} °C")

    with t2:
        st.metric("Tube h", f"{fmt(result.tube_h_w_m2k,0)} W/m²K")
        st.metric("Tube velocity", f"{fmt(result.tube_velocity_m_s,2)} m/s")
        st.metric("Tube ΔP", f"{fmt(result.tube_dp_kpa,1)} kPa")

    with t3:
        st.metric("Shell h", f"{fmt(result.shell_h_w_m2k,0)} W/m²K")
        st.metric("Shell velocity", f"{fmt(result.shell_velocity_m_s,2)} m/s")
        st.metric("Shell ΔP", f"{fmt(result.shell_dp_kpa,1)} kPa")

    with t4:
        st.metric("Tube Re", f"{result.tube_reynolds:,.0f}")
        st.metric("Shell Re", f"{result.shell_reynolds:,.0f}")
        st.metric("F correction", f"{result.correction_factor:.3f}")

    bell_df = pd.DataFrame(
        {
            "Bell factor": ["Jc", "Jl", "Jb", "Jr", "Js"],
            "Value": [
                result.j_c,
                result.j_l,
                result.j_b,
                result.j_r,
                result.j_s,
            ],
            "Meaning": [
                "Baffle configuration/window",
                "Leakage",
                "Bundle bypass",
                "Laminar adverse-gradient",
                "Unequal baffle spacing",
            ],
        }
    )

    with st.expander("Bell–Delaware correction-factor telemetry"):
        st.dataframe(
            bell_df.style.format({"Value": "{:.4f}"}),
            use_container_width=True,
            hide_index=True,
        )

    if result.warnings:
        st.markdown('<div class="hx-panel-title">RACE ENGINEER / DESIGN NOTES</div>', unsafe_allow_html=True)
        for warning in result.warnings:
            st.markdown(
                f'<div class="hx-status-warn">⚠ {warning}</div>',
                unsafe_allow_html=True,
            )
            st.write("")
    else:
        st.markdown(
            '<div class="hx-status-ok">✓ No current thermal/hydraulic screening warnings.</div>',
            unsafe_allow_html=True,
        )

    with tab_export:
        st.markdown("### Technical Pack — v0.3")

        payload = result.as_dict()
        payload["generated_utc"] = datetime.utcnow().isoformat() + "Z"
        payload["status"] = (
            "HX-RACE engineering simulation output. "
            "Not TEMA certification, ASME code stamping, or fabrication approval."
        )

        component_rows = [
            ["TEMA configuration", result.tema_code, "Configuration"],
            ["Shell ID", f"{shell_id:.3f} m", "Geometry"],
            ["Tube OD", f"{tube_od_mm:.2f} mm", "Geometry"],
            ["Tube ID", f"{tube_id_mm:.2f} mm", "Geometry"],
            ["Tube length", f"{tube_length:.2f} m", "Geometry"],
            ["Tube count", str(int(tube_count)), "Geometry"],
            ["Tube passes", str(int(tube_passes)), "Geometry"],
            ["Baffles", str(int(baffle_count)), "Geometry"],
            ["Baffle cut", f"{int(baffle_cut)}%", "Geometry"],
            ["Thermo package", thermo_package, "Thermodynamics"],
            ["Heat duty", f"{result.duty_kw:.2f} kW", "Performance"],
            ["Required area", f"{result.required_area_m2:.2f} m²", "Performance"],
            ["Overall U", f"{result.overall_u_w_m2k:.2f} W/m²K", "Performance"],
            ["Tube ΔP", f"{result.tube_dp_kpa:.2f} kPa", "Hydraulics"],
            ["Shell ΔP", f"{result.shell_dp_kpa:.2f} kPa", "Hydraulics"],
        ]

        component_df = pd.DataFrame(
            component_rows,
            columns=["Item", "Value", "Section"],
        )

        st.dataframe(component_df, use_container_width=True, hide_index=True)

        json_bytes = json.dumps(payload, indent=2).encode("utf-8")
        csv_bytes = component_df.to_csv(index=False).encode("utf-8")

        d1, d2 = st.columns(2)

        with d1:
            st.download_button(
                "↓ Download simulation JSON",
                data=json_bytes,
                file_name=f"{result.tema_code}_HX-RACE_simulation.json",
                mime="application/json",
                use_container_width=True,
            )

        with d2:
            st.download_button(
                "↓ Download component register CSV",
                data=csv_bytes,
                file_name=f"{result.tema_code}_HX-RACE_component_register.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.warning(
            "These downloads are engineering-simulation records only. "
            "Formal TEMA/ASME certification requires the applicable manufacturer, "
            "code calculations, review, approval, and documentation."
        )


st.caption(
    "HX//RACE v0.3 · Shell-and-tube integration build · "
    "Development-stage Bell–Delaware screening model"
)
