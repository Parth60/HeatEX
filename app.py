from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
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
from backend.app.visualization.leaderboard import leaderboard_css, candidate_card
from backend.app.engine.optimizer import OptimizationSettings, optimize_shell_and_tube
from backend.app.engine.temperature_profile import build_temperature_profile
from backend.app.thermo.components import component_names


st.set_page_config(
    page_title="HX//RACE",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(cockpit_css(), unsafe_allow_html=True)
st.markdown(leaderboard_css(), unsafe_allow_html=True)

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

FLUIDS = component_names()


def fmt(x: float, decimals: int = 1) -> str:
    return f"{x:,.{decimals}f}"


def composition_from_editor(df: pd.DataFrame) -> dict[str, float]:
    composition: dict[str, float] = {}

    if df is None:
        return composition

    for _, row in df.iterrows():
        component = str(row.get("Component", "")).strip()

        try:
            fraction = float(row.get("Fraction", 0.0))
        except Exception:
            fraction = 0.0

        if component and component in FLUIDS and fraction > 0:
            composition[component] = composition.get(component, 0.0) + fraction

    return composition


def composition_editor(
    label: str,
    default_rows: list[dict],
    key: str,
):
    st.caption(label)

    df = pd.DataFrame(default_rows)

    edited = st.data_editor(
        df,
        key=key,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Component": st.column_config.SelectboxColumn(
                "Component",
                options=FLUIDS,
                required=True,
            ),
            "Fraction": st.column_config.NumberColumn(
                "Fraction",
                min_value=0.0,
                step=0.01,
                format="%.4f",
                required=True,
            ),
        },
    )

    composition = composition_from_editor(edited)
    total = sum(composition.values())

    st.caption(
        f"Entered fraction total: {total:.4f} — HX//RACE normalises positive fractions automatically."
    )

    return composition


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
        "Thermodynamic package",
        [
            "Ideal mixture",
            "Peng-Robinson",
            "SRK",
            "NRTL",
            "UNIQUAC",
            "CoolProp (pure only)",
        ],
        help=(
            "v0.5 uses enthalpy-based stream balances. PR/SRK add cubic-EOS "
            "diagnostics; NRTL/UNIQUAC accept data-driven interaction parameters."
        ),
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
        <span>v0.5 THERMO PRO</span>
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

tab_run, tab_thermo, tab_geometry, tab_bell, tab_optimizer, tab_export = st.tabs(
    [
        "🏁 LIVE RUN",
        "🧪 THERMODYNAMICS",
        "🧩 GEOMETRY",
        "📡 BELL–DELAWARE",
        "🏎️ OPTIMISER",
        "📄 TECH PACK",
    ]
)

with tab_run:
    c_hot, c_cold = st.columns(2)

    with c_hot:
        st.markdown(
            '<div class="hx-panel-title">HOT / TUBE SIDE</div>',
            unsafe_allow_html=True,
        )

        hot_mode = st.radio(
            "Hot-stream definition",
            ["Pure fluid", "Mixture"],
            horizontal=True,
            key="hot_stream_definition",
        )

        if hot_mode == "Pure fluid":
            hot_fluid = st.selectbox("Hot fluid", FLUIDS, index=1)
            hot_composition = None
            hot_basis = "mole"
        else:
            hot_fluid = "Mixture"
            hot_basis = st.radio(
                "Hot composition basis",
                ["mass", "mole"],
                horizontal=True,
                key="hot_basis",
            )
            hot_composition = composition_editor(
                "Hot-stream composition",
                [
                    {"Component": "Ethanol", "Fraction": 0.70},
                    {"Component": "Water", "Fraction": 0.20},
                    {"Component": "Butanol", "Fraction": 0.10},
                ],
                "hot_composition_editor",
            )

        h1, h2 = st.columns(2)

        with h1:
            hot_tin = st.number_input(
                "Hot inlet [°C]",
                value=110.0 if hot_mode == "Mixture" else 140.0,
                step=1.0,
            )
            hot_p = st.number_input(
                "Hot pressure [bar]",
                min_value=0.1,
                value=5.0,
                step=0.1,
            )

        with h2:
            hot_flow = st.number_input(
                "Hot flow [kg/s]",
                min_value=0.01,
                value=12.0,
                step=0.1,
            )
            hot_tout = st.number_input(
                "Target hot outlet [°C]",
                value=65.0 if hot_mode == "Mixture" else 70.0,
                step=1.0,
            )

        tube_fouling = st.number_input(
            "Tube fouling [m²·K/W]",
            min_value=0.0,
            value=0.0002,
            format="%.5f",
        )

    with c_cold:
        st.markdown(
            '<div class="hx-panel-title">COLD / SHELL SIDE</div>',
            unsafe_allow_html=True,
        )

        cold_mode = st.radio(
            "Cold-stream definition",
            ["Pure fluid", "Mixture"],
            horizontal=True,
            key="cold_stream_definition",
        )

        if cold_mode == "Pure fluid":
            cold_fluid = st.selectbox("Cold fluid", FLUIDS, index=0)
            cold_composition = None
            cold_basis = "mole"
        else:
            cold_fluid = "Mixture"
            cold_basis = st.radio(
                "Cold composition basis",
                ["mass", "mole"],
                horizontal=True,
                key="cold_basis",
            )
            cold_composition = composition_editor(
                "Cold-stream composition",
                [
                    {"Component": "Water", "Fraction": 0.95},
                    {"Component": "Ethanol", "Fraction": 0.05},
                ],
                "cold_composition_editor",
            )

        c1, c2 = st.columns(2)

        with c1:
            cold_tin = st.number_input(
                "Cold inlet [°C]",
                value=25.0,
                step=1.0,
            )
            cold_p = st.number_input(
                "Cold pressure [bar]",
                min_value=0.1,
                value=4.0,
                step=0.1,
            )

        with c2:
            cold_flow = st.number_input(
                "Cold flow [kg/s]",
                min_value=0.01,
                value=22.0 if hot_mode == "Mixture" else 18.0,
                step=0.1,
            )
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


with tab_thermo:
    st.markdown("### Thermodynamic Garage")

    package_notes = {
        "Ideal mixture": (
            "Temperature-dependent internal mixture properties + sensible enthalpy "
            "+ ideal VLE screening."
        ),
        "Peng-Robinson": (
            "Internal PR cubic EOS with mixture roots, Z-factor and fugacity "
            "diagnostics. kij can be supplied through JSON."
        ),
        "SRK": (
            "Internal Soave–Redlich–Kwong EOS with mixture roots and fugacity "
            "diagnostics."
        ),
        "NRTL": (
            "Internal NRTL activity-coefficient engine. Valid binary tau/alpha "
            "parameters should be supplied for non-ideal predictions."
        ),
        "UNIQUAC": (
            "Internal UNIQUAC activity-coefficient engine. Binary interaction "
            "energies can be supplied through JSON."
        ),
        "CoolProp (pure only)": (
            "Attempts real pure-fluid Cp, density, viscosity, conductivity and "
            "enthalpy. Mixtures fall back transparently to the internal engine."
        ),
    }

    st.info(package_notes[thermo_package])

    parameter_file = st.file_uploader(
        "Optional interaction-parameter JSON",
        type=["json"],
        help=(
            "Supports KIJ, NRTL and UNIQUAC sections. Use validated parameters "
            "from an appropriate source."
        ),
    )

    interaction_parameters = None

    if parameter_file is not None:
        try:
            interaction_parameters = json.loads(
                parameter_file.getvalue().decode("utf-8")
            )
            st.success("Interaction-parameter file loaded.")
            with st.expander("Show loaded parameter JSON"):
                st.json(interaction_parameters)
        except Exception as exc:
            st.error(f"Could not parse interaction JSON: {exc}")
            interaction_parameters = None
    else:
        st.caption(
            "No custom parameter file loaded. Missing kij/NRTL/UNIQUAC pairs "
            "use documented fallback values and generate warnings."
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


with tab_optimizer:
    st.markdown("### P1 / P2 / P3 Design Search")
    st.caption(
        "Search multiple geometries using the same thermal-hydraulic engine as the live cockpit."
    )

    o1, o2, o3 = st.columns(3)

    with o1:
        opt_objective = st.selectbox(
            "Objective",
            [
                "Balanced",
                "Minimum installed area",
                "Minimum pressure drop",
                "Maximum overall U",
                "Minimum relative cost",
                "Maximum area efficiency",
            ],
        )

        opt_tube_count_min = st.number_input(
            "Tube count minimum",
            min_value=40,
            value=280,
            step=20,
        )

        opt_tube_count_max = st.number_input(
            "Tube count maximum",
            min_value=40,
            value=720,
            step=20,
        )

        opt_tube_count_step = st.number_input(
            "Tube count step",
            min_value=10,
            value=40,
            step=10,
        )

    with o2:
        opt_baffle_min = st.number_input(
            "Baffle minimum",
            min_value=0,
            value=6,
            step=1,
        )

        opt_baffle_max = st.number_input(
            "Baffle maximum",
            min_value=0,
            value=20,
            step=1,
        )

        opt_baffle_step = st.number_input(
            "Baffle step",
            min_value=1,
            value=2,
            step=1,
        )

        opt_min_margin = st.number_input(
            "Minimum area margin [%]",
            min_value=0.0,
            value=10.0,
            step=1.0,
        )

    with o3:
        opt_max_margin = st.number_input(
            "Maximum area margin [%]",
            min_value=1.0,
            value=35.0,
            step=1.0,
        )

        opt_min_velocity = st.number_input(
            "Minimum tube velocity [m/s]",
            min_value=0.05,
            value=0.50,
            step=0.05,
        )

        opt_max_velocity = st.number_input(
            "Maximum tube velocity [m/s]",
            min_value=0.10,
            value=3.00,
            step=0.10,
        )

        opt_max_candidates = st.selectbox(
            "Search budget",
            [500, 1000, 2000, 3500],
            index=2,
            help="Higher values search more combinations but take longer.",
        )

    st.markdown("#### Search envelope")

    e1, e2, e3 = st.columns(3)

    with e1:
        opt_od = st.multiselect(
            "Tube OD options [mm]",
            [12.70, 15.88, 19.05, 25.40, 31.75],
            default=[15.88, 19.05, 25.40],
        )

    with e2:
        opt_lengths = st.multiselect(
            "Tube lengths [m]",
            [3.0, 4.0, 5.0, 6.0, 8.0, 10.0],
            default=[4.0, 6.0, 8.0],
        )

    with e3:
        opt_passes = st.multiselect(
            "Tube passes",
            [1, 2, 4, 6],
            default=[1, 2, 4],
        )

    e4, e5 = st.columns(2)

    with e4:
        opt_cuts = st.multiselect(
            "Baffle cut options [%]",
            [15, 20, 25, 30, 35, 40],
            default=[20, 25, 30, 35],
        )

    with e5:
        opt_pitch_ratios = st.multiselect(
            "Pitch / OD ratios",
            [1.20, 1.25, 1.33, 1.40, 1.50],
            default=[1.25, 1.33],
        )

    run_optimizer = st.button(
        "🏁 RUN DESIGN SEARCH",
        type="primary",
        use_container_width=True,
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
        composition=hot_composition,
        composition_basis=hot_basis,
    ),
    cold=StreamInput(
        fluid=cold_fluid,
        mass_flow_kg_s=float(cold_flow),
        inlet_temperature_c=float(cold_tin),
        pressure_bar=float(cold_p),
        composition=cold_composition,
        composition_basis=cold_basis,
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
    interaction_parameters=interaction_parameters,
)


if run_optimizer:
    if not opt_od or not opt_lengths or not opt_passes or not opt_cuts or not opt_pitch_ratios:
        st.session_state["hx_opt_error"] = "Select at least one value in every optimisation search-envelope control."
        st.session_state.pop("hx_opt_report", None)
    elif int(opt_tube_count_max) < int(opt_tube_count_min):
        st.session_state["hx_opt_error"] = "Tube-count maximum must be greater than or equal to the minimum."
        st.session_state.pop("hx_opt_report", None)
    elif int(opt_baffle_max) < int(opt_baffle_min):
        st.session_state["hx_opt_error"] = "Baffle maximum must be greater than or equal to the minimum."
        st.session_state.pop("hx_opt_report", None)
    elif float(opt_max_margin) < float(opt_min_margin):
        st.session_state["hx_opt_error"] = "Maximum area margin must be greater than or equal to the minimum."
        st.session_state.pop("hx_opt_report", None)
    else:
        settings = OptimizationSettings(
            objective=opt_objective,
            tube_od_options_mm=tuple(float(v) for v in opt_od),
            tube_length_options_m=tuple(float(v) for v in opt_lengths),
            tube_pass_options=tuple(int(v) for v in opt_passes),
            baffle_cut_options_percent=tuple(int(v) for v in opt_cuts),
            pitch_ratio_options=tuple(float(v) for v in opt_pitch_ratios),
            tube_count_min=int(opt_tube_count_min),
            tube_count_max=int(opt_tube_count_max),
            tube_count_step=int(opt_tube_count_step),
            baffle_count_min=int(opt_baffle_min),
            baffle_count_max=int(opt_baffle_max),
            baffle_count_step=int(opt_baffle_step),
            minimum_area_margin_percent=float(opt_min_margin),
            maximum_area_margin_percent=float(opt_max_margin),
            minimum_tube_velocity_m_s=float(opt_min_velocity),
            maximum_tube_velocity_m_s=float(opt_max_velocity),
            maximum_candidates=int(opt_max_candidates),
        )

        try:
            with st.spinner("Searching the design space…"):
                opt_report = optimize_shell_and_tube(
                    sim_input,
                    settings,
                    top_n=10,
                )
            st.session_state["hx_opt_report"] = opt_report.as_dict()
            st.session_state.pop("hx_opt_error", None)
        except Exception as exc:
            st.session_state["hx_opt_error"] = str(exc)
            st.session_state.pop("hx_opt_report", None)


with tab_optimizer:
    if "hx_opt_error" in st.session_state:
        st.error(st.session_state["hx_opt_error"])

    report_data = st.session_state.get("hx_opt_report")

    if report_data:
        r1, r2, r3, r4 = st.columns(4)

        r1.metric("Evaluated", f"{report_data['evaluated_candidates']:,}")
        r2.metric("Feasible", f"{report_data['feasible_candidates']:,}")
        r3.metric("Rejected", f"{report_data['rejected_candidates']:,}")
        r4.metric(
            "Search status",
            "CAPPED" if report_data["truncated"] else "COMPLETE",
        )

        winners = report_data["winners"]

        if winners:
            podium = winners[:3]
            podium_html = '<div class="hx-leaderboard">' + "".join(
                candidate_card(c) for c in podium
            ) + "</div>"
            st.markdown(podium_html, unsafe_allow_html=True)

            table_rows = []
            for c in winners:
                table_rows.append(
                    {
                        "Pos": f"P{c['rank']}",
                        "Tube OD [mm]": c["tube_od_mm"],
                        "Length [m]": c["tube_length_m"],
                        "Tubes": c["tube_count"],
                        "Passes": c["tube_passes"],
                        "Pitch [mm]": c["tube_pitch_mm"],
                        "Baffles": c["baffle_count"],
                        "Cut [%]": c["baffle_cut_percent"],
                        "Area [m²]": c["installed_area_m2"],
                        "Margin [%]": c["area_margin_percent"],
                        "U [W/m²K]": c["overall_u_w_m2k"],
                        "Tube ΔP [kPa]": c["tube_dp_kpa"],
                        "Shell ΔP [kPa]": c["shell_dp_kpa"],
                        "Cost index": c["relative_cost_index"],
                        "Score": c["objective_score"],
                    }
                )

            opt_df = pd.DataFrame(table_rows)

            st.dataframe(
                opt_df.style.format(
                    {
                        "Tube OD [mm]": "{:.2f}",
                        "Length [m]": "{:.1f}",
                        "Pitch [mm]": "{:.2f}",
                        "Area [m²]": "{:.1f}",
                        "Margin [%]": "{:.1f}",
                        "U [W/m²K]": "{:.0f}",
                        "Tube ΔP [kPa]": "{:.1f}",
                        "Shell ΔP [kPa]": "{:.1f}",
                        "Cost index": "{:.1f}",
                        "Score": "{:.4f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            p1 = winners[0]

            st.markdown("#### P1 machine visualization")

            p1_svg = tema_longitudinal_svg(
                front=front,
                shell=shell,
                rear=rear,
                baffle_count=int(p1["baffle_count"]),
                tube_passes=int(p1["tube_passes"]),
                animated=True,
            )

            components.html(p1_svg, height=335, scrolling=False)

            dl1, dl2 = st.columns(2)

            with dl1:
                st.download_button(
                    "↓ Download optimiser leaderboard CSV",
                    data=opt_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"{tema_code}_HX-RACE_optimizer.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with dl2:
                st.download_button(
                    "↓ Download optimiser report JSON",
                    data=json.dumps(report_data, indent=2).encode("utf-8"),
                    file_name=f"{tema_code}_HX-RACE_optimizer.json",
                    mime="application/json",
                    use_container_width=True,
                )

            st.caption(
                "P1/P2/P3 are the best feasible candidates within the selected discrete search envelope, not universal global optima."
            )
        else:
            st.warning(
                "No feasible geometry was found inside the current search envelope. "
                "Increase the search range or relax one or more limits."
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
    with tab_thermo:
        st.markdown("### Stream-state telemetry")

        hot_state = result.hot_in_thermo
        hot_out_state = result.hot_out_thermo
        cold_state = result.cold_in_thermo
        cold_out_state = result.cold_out_thermo

        s1, s2, s3, s4 = st.columns(4)

        with s1:
            st.metric("Hot-in phase", hot_state["phase"])
            st.metric(
                "Hot mixture MW",
                f"{hot_state['mixture_mw_g_mol']:.2f} g/mol",
            )

        with s2:
            st.metric("Hot-out phase", hot_out_state["phase"])
            z_hot = hot_state.get("z_factor")
            st.metric(
                "Hot-in Z",
                "—" if z_hot is None else f"{z_hot:.4f}",
            )

        with s3:
            st.metric("Cold-in phase", cold_state["phase"])
            st.metric(
                "Cold mixture MW",
                f"{cold_state['mixture_mw_g_mol']:.2f} g/mol",
            )

        with s4:
            st.metric("Cold-out phase", cold_out_state["phase"])
            z_cold = cold_state.get("z_factor")
            st.metric(
                "Cold-in Z",
                "—" if z_cold is None else f"{z_cold:.4f}",
            )

        state_rows = []

        for label, state in [
            ("Hot inlet", hot_state),
            ("Hot outlet", hot_out_state),
            ("Cold inlet", cold_state),
            ("Cold outlet", cold_out_state),
        ]:
            state_rows.append(
                {
                    "State": label,
                    "T [°C]": state["temperature_c"],
                    "P [bar]": state["pressure_bar"],
                    "Phase": state["phase"],
                    "Cp [J/kgK]": state["cp_j_kgk"],
                    "ρ [kg/m³]": state["density_kg_m3"],
                    "μ [mPa·s]": state["viscosity_pa_s"] * 1000,
                    "k [W/mK]": state["thermal_conductivity_w_mk"],
                    "h [kJ/kg]": state["specific_enthalpy_j_kg"] / 1000,
                    "Bubble [°C]": state["bubble_point_c"],
                    "Dew [°C]": state["dew_point_c"],
                }
            )

        state_df = pd.DataFrame(state_rows)

        st.dataframe(
            state_df.style.format(
                {
                    "T [°C]": "{:.2f}",
                    "P [bar]": "{:.2f}",
                    "Cp [J/kgK]": "{:.0f}",
                    "ρ [kg/m³]": "{:.2f}",
                    "μ [mPa·s]": "{:.4f}",
                    "k [W/mK]": "{:.4f}",
                    "h [kJ/kg]": "{:.2f}",
                    "Bubble [°C]": lambda v: "—" if pd.isna(v) else f"{v:.2f}",
                    "Dew [°C]": lambda v: "—" if pd.isna(v) else f"{v:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### T–Q / temperature-approach profile")

        try:
            profile = build_temperature_profile(
                sim_input,
                result,
                segments=24,
            )

            profile_df = pd.DataFrame(profile.points)

            fig = go.Figure()

            fig.add_trace(
                go.Scatter(
                    x=profile_df["fraction"],
                    y=profile_df["hot_temperature_c"],
                    mode="lines+markers",
                    name="Hot stream",
                )
            )

            fig.add_trace(
                go.Scatter(
                    x=profile_df["fraction"],
                    y=profile_df["cold_temperature_c"],
                    mode="lines+markers",
                    name="Cold stream",
                )
            )

            fig.update_layout(
                template="plotly_dark",
                height=430,
                margin=dict(l=25, r=20, t=30, b=35),
                xaxis_title="Normalised exchanger / duty coordinate",
                yaxis_title="Temperature [°C]",
                legend=dict(orientation="h"),
            )

            st.plotly_chart(fig, use_container_width=True)

            p1, p2 = st.columns(2)
            p1.metric(
                "Minimum approach",
                f"{profile.minimum_approach_c:.2f} °C",
            )
            p2.metric(
                "Energy-balance basis",
                "ENTHALPY",
                help="Q = m(h_in − h_out), not constant Cp ΔT.",
            )

            if profile.minimum_approach_c <= 0:
                st.error(
                    "Temperature cross detected in the segmented enthalpy profile."
                )

        except Exception as exc:
            st.warning(f"T–Q profile could not be generated: {exc}")

        with st.expander("Composition / activity telemetry"):
            hot_comp_df = pd.DataFrame(
                {
                    "Component": list(hot_state["mole_fractions"]),
                    "Hot x": list(hot_state["mole_fractions"].values()),
                    "Hot w": [
                        hot_state["mass_fractions"][name]
                        for name in hot_state["mole_fractions"]
                    ],
                    "γ hot-in": [
                        hot_state["activity_coefficients"].get(name, 1.0)
                        for name in hot_state["mole_fractions"]
                    ],
                }
            )

            st.dataframe(
                hot_comp_df.style.format(
                    {
                        "Hot x": "{:.5f}",
                        "Hot w": "{:.5f}",
                        "γ hot-in": "{:.5f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

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
        st.markdown("### Technical Pack — v0.5")

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
    "HX//RACE v0.5 · Thermodynamics Pro · "
    "Development-stage Bell–Delaware screening model"
)
