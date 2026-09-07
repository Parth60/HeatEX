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
from backend.app.thermo.phase_change import get_saturation_state
from backend.app.engine.phase_change_simulator import (
    PhaseChangeStream,
    UtilityStream,
    PhaseChangeHXInput,
    simulate_phase_change,
)
from backend.app.visualization.phase_zones import phase_zone_svg
from backend.app.thermo.flash import flash_isothermal
from backend.app.thermo.phase_envelope import temperature_flash_sweep
from backend.app.thermo.two_phase_path import build_phase_path
from backend.app.engine.flash_drum import simulate_flash_drum
from backend.app.visualization.flash_vle import flash_split_svg
from backend.app.engine.multicomponent_phase_hx import (
    MulticomponentPhaseHXInput,
    simulate_multicomponent_phase_hx,
)
from backend.app.visualization.multicomponent_hx import multicomponent_hx_svg
from backend.app.engine.single_phase_common import ServiceStream
from backend.app.engine.plate_hx import PlateGeometry, simulate_plate_hx
from backend.app.engine.double_pipe_hx import DoublePipeGeometry, simulate_double_pipe_hx
from backend.app.engine.air_cooled_hx import AirCooledGeometry, simulate_air_cooled_hx
from backend.app.engine.exchanger_selector import SelectionCase, rank_exchangers
from backend.app.mechanical.materials import material_names
from backend.app.mechanical.mechanical_design import (
    MechanicalDesignInput,
    run_mechanical_design,
)
from backend.app.visualization.mechanical_svg import mechanical_cutaway_svg
from backend.app.validation.validation_engine import validate_shell_and_tube
from backend.app.validation.benchmarks import run_benchmark_suite
from backend.app.validation.trace import build_calculation_trace
from backend.app.validation.assumptions import build_assumptions_register
from backend.app.reporting.technical_pack import (
    build_report_payload,
    build_technical_pack_zip,
)
from backend.app.reporting.engineering_report import build_engineering_report_pdf
from backend.app.visualization.validation_dashboard import readiness_gauge_html
from backend.app.visualization.other_exchangers import (
    plate_hx_svg,
    double_pipe_svg,
    air_cooler_svg,
)


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
        <span>v0.11 VALIDATION / REPORT</span>
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

tab_run, tab_thermo, tab_flash, tab_multi, tab_alternatives, tab_phase, tab_geometry, tab_mechanical, tab_bell, tab_optimizer, tab_validation, tab_export = st.tabs(
    [
        "🏁 LIVE RUN",
        "🧪 THERMODYNAMICS",
        "⚗️ FLASH / VLE",
        "🧬 MULTICOMP HX",
        "🔀 HX TYPES",
        "🌫️ PHASE CHANGE",
        "🧩 GEOMETRY",
        "🛠️ MECHANICAL",
        "📡 BELL–DELAWARE",
        "🏎️ OPTIMISER",
        "✅ VALIDATION",
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



with tab_flash:
    st.markdown("### Rigorous Flash / VLE Garage")

    f1, f2, f3 = st.columns(3)

    with f1:
        flash_package = st.selectbox(
            "Flash package",
            [
                "Peng-Robinson",
                "SRK",
                "NRTL",
                "UNIQUAC",
                "Ideal mixture",
            ],
            key="flash_package",
        )

        flash_basis = st.radio(
            "Feed composition basis",
            ["mole", "mass"],
            horizontal=True,
            key="flash_basis",
        )

    with f2:
        flash_temperature = st.number_input(
            "Flash temperature [°C]",
            value=90.0,
            step=1.0,
            key="flash_temperature",
        )

        flash_pressure = st.number_input(
            "Flash pressure [bar]",
            min_value=0.05,
            value=1.50,
            step=0.05,
            key="flash_pressure",
        )

    with f3:
        flash_feed_mol_s = st.number_input(
            "Flash feed [mol/s]",
            min_value=0.001,
            value=100.0,
            step=5.0,
            key="flash_feed_mol_s",
        )

        flash_points = st.selectbox(
            "Path resolution",
            [12, 20, 30, 40],
            index=1,
            key="flash_points",
        )

    flash_composition = composition_editor(
        "Flash feed composition",
        [
            {"Component": "Ethanol", "Fraction": 0.60},
            {"Component": "Water", "Fraction": 0.25},
            {"Component": "Butanol", "Fraction": 0.15},
        ],
        "flash_composition_editor",
    )

    flash_run = st.button(
        "⚗️ RUN ISOTHERMAL FLASH",
        type="primary",
        use_container_width=True,
        key="run_flash_v07",
    )

    if flash_run:
        try:
            flash_result = flash_isothermal(
                temperature_c=float(flash_temperature),
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
            )

            st.session_state["flash_v07_result"] = flash_result.as_dict()
            st.session_state.pop("flash_v07_error", None)

        except Exception as exc:
            st.session_state["flash_v07_error"] = str(exc)
            st.session_state.pop("flash_v07_result", None)

    if "flash_v07_error" in st.session_state:
        st.error(st.session_state["flash_v07_error"])

    flash_data = st.session_state.get("flash_v07_result")

    if flash_data:
        q1, q2, q3, q4 = st.columns(4)

        q1.metric(
            "Vapour fraction β",
            f"{flash_data['vapour_fraction']:.5f}",
        )
        q2.metric(
            "Phase",
            flash_data["phase"],
        )
        q3.metric(
            "Iterations",
            str(flash_data["iterations"]),
        )
        q4.metric(
            "Converged",
            "YES" if flash_data["converged"] else "NO",
        )

        split_svg = flash_split_svg(
            flash_data["vapour_fraction"],
            flash_data["phase"],
        )
        components.html(split_svg, height=340, scrolling=False)

        names = list(flash_data["feed_mole_fractions"])

        phase_df = pd.DataFrame(
            {
                "Component": names,
                "Feed z": [
                    flash_data["feed_mole_fractions"][n]
                    for n in names
                ],
                "Liquid x": [
                    flash_data["liquid_mole_fractions"][n]
                    for n in names
                ],
                "Vapour y": [
                    flash_data["vapour_mole_fractions"][n]
                    for n in names
                ],
                "K = y/x": [
                    flash_data["k_values"][n]
                    for n in names
                ],
                "γ": [
                    flash_data["activity_coefficients"].get(n, 1.0)
                    for n in names
                ],
            }
        )

        st.dataframe(
            phase_df.style.format(
                {
                    "Feed z": "{:.6f}",
                    "Liquid x": "{:.6f}",
                    "Vapour y": "{:.6f}",
                    "K = y/x": "{:.5f}",
                    "γ": "{:.5f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        drum = simulate_flash_drum(
            feed_mol_s=float(flash_feed_mol_s),
            temperature_c=float(flash_temperature),
            pressure_bar=float(flash_pressure),
            fractions=flash_composition,
            composition_basis=flash_basis,
            package=flash_package,
            interaction_parameters=interaction_parameters,
        )

        d1, d2, d3 = st.columns(3)

        d1.metric(
            "Feed",
            f"{drum.feed_mol_s:.2f} mol/s",
        )
        d2.metric(
            "Vapour",
            f"{drum.vapour_mol_s:.2f} mol/s",
        )
        d3.metric(
            "Liquid",
            f"{drum.liquid_mol_s:.2f} mol/s",
        )

        with st.expander("EOS / activity diagnostics"):
            if flash_data.get("liquid_z") is not None:
                st.write(
                    f"Liquid Z: {flash_data['liquid_z']:.6f}"
                )
            if flash_data.get("vapour_z") is not None:
                st.write(
                    f"Vapour Z: {flash_data['vapour_z']:.6f}"
                )

            st.write(
                f"Rachford–Rice residual: "
                f"{flash_data['residual']:.3e}"
            )

            for warning in flash_data["warnings"]:
                st.warning(warning)

        st.markdown("### Isobaric vapour-fraction sweep")

        sw1, sw2 = st.columns(2)

        with sw1:
            sweep_tmin = st.number_input(
                "Sweep Tmin [°C]",
                value=50.0,
                step=5.0,
                key="sweep_tmin",
            )

        with sw2:
            sweep_tmax = st.number_input(
                "Sweep Tmax [°C]",
                value=140.0,
                step=5.0,
                key="sweep_tmax",
            )

        try:
            envelope = temperature_flash_sweep(
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
                temperature_min_c=float(sweep_tmin),
                temperature_max_c=float(sweep_tmax),
                points=int(flash_points),
            )

            env_df = pd.DataFrame(
                [
                    {
                        "Temperature [°C]": p.temperature_c,
                        "Vapour fraction": p.vapour_fraction,
                        "Phase": p.phase,
                    }
                    for p in envelope.points
                ]
            )

            fig_env = go.Figure()
            fig_env.add_trace(
                go.Scatter(
                    x=env_df["Temperature [°C]"],
                    y=env_df["Vapour fraction"],
                    mode="lines+markers",
                    name="β",
                )
            )
            fig_env.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=25, r=20, t=30, b=35),
                xaxis_title="Temperature [°C]",
                yaxis_title="Vapour fraction β",
                yaxis_range=[-0.03, 1.03],
            )

            st.plotly_chart(fig_env, use_container_width=True)

            e1, e2 = st.columns(2)

            e1.metric(
                "Approx. bubble T",
                "—"
                if envelope.bubble_temperature_c is None
                else f"{envelope.bubble_temperature_c:.2f} °C",
            )
            e2.metric(
                "Approx. dew T",
                "—"
                if envelope.dew_temperature_c is None
                else f"{envelope.dew_temperature_c:.2f} °C",
            )

        except Exception as exc:
            st.warning(
                f"Temperature flash sweep could not be generated: {exc}"
            )

        st.markdown("### Multicomponent phase path")

        path_mode = st.radio(
            "Path mode",
            ["Cooling / condensation", "Heating / boiling"],
            horizontal=True,
            key="flash_path_mode",
        )

        if path_mode.startswith("Cooling"):
            path_t_start_default = max(
                float(flash_temperature),
                120.0,
            )
            path_t_end_default = min(
                float(flash_temperature) - 30.0,
                55.0,
            )
        else:
            path_t_start_default = min(
                float(flash_temperature),
                55.0,
            )
            path_t_end_default = max(
                float(flash_temperature) + 30.0,
                125.0,
            )

        pp1, pp2 = st.columns(2)

        with pp1:
            path_t_start = st.number_input(
                "Path start [°C]",
                value=float(path_t_start_default),
                step=2.0,
                key=f"path_start_{path_mode}",
            )

        with pp2:
            path_t_end = st.number_input(
                "Path end [°C]",
                value=float(path_t_end_default),
                step=2.0,
                key=f"path_end_{path_mode}",
            )

        try:
            path = build_phase_path(
                mode=path_mode,
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
                temperature_start_c=float(path_t_start),
                temperature_end_c=float(path_t_end),
                points=int(flash_points),
            )

            path_rows = []

            for point in path.points:
                row = {
                    "Temperature [°C]": point.temperature_c,
                    "Vapour fraction": point.vapour_fraction,
                }

                for comp in flash_composition:
                    row[f"x {comp}"] = (
                        point.liquid_mole_fractions.get(comp, 0.0)
                    )
                    row[f"y {comp}"] = (
                        point.vapour_mole_fractions.get(comp, 0.0)
                    )

                path_rows.append(row)

            path_df = pd.DataFrame(path_rows)

            fig_path = go.Figure()
            fig_path.add_trace(
                go.Scatter(
                    x=path_df["Temperature [°C]"],
                    y=path_df["Vapour fraction"],
                    mode="lines+markers",
                    name="Vapour fraction",
                )
            )

            fig_path.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=25, r=20, t=30, b=35),
                xaxis_title="Temperature [°C]",
                yaxis_title="β",
                yaxis_range=[-0.03, 1.03],
            )

            st.plotly_chart(fig_path, use_container_width=True)

            with st.expander("Phase-composition path table"):
                st.dataframe(
                    path_df,
                    use_container_width=True,
                    hide_index=True,
                )

        except Exception as exc:
            st.warning(
                f"Multicomponent phase path could not be generated: {exc}"
            )

        flash_json = json.dumps(
            flash_data,
            indent=2,
        ).encode("utf-8")

        st.download_button(
            "↓ Download flash / VLE JSON",
            data=flash_json,
            file_name="HX-RACE_v07_flash_vle.json",
            mime="application/json",
            use_container_width=True,
        )



with tab_alternatives:
    st.markdown("### Multi-Exchanger Platform")

    alt_type = st.radio(
        "Exchanger",
        ["Plate & Frame", "Double Pipe", "Air-Cooled", "Selector"],
        horizontal=True,
        key="alt_hx_type_v09",
    )

    if alt_type in {"Plate & Frame", "Double Pipe"}:
        aa, bb = st.columns(2)

        with aa:
            alt_hot_fluid = st.selectbox(
                "Hot fluid",
                FLUIDS,
                index=1,
                key=f"alt_hot_fluid_{alt_type}",
            )
            alt_hot_flow = st.number_input(
                "Hot flow [kg/s]",
                min_value=0.01,
                value=3.0,
                step=0.1,
                key=f"alt_hot_flow_{alt_type}",
            )
            alt_hot_tin = st.number_input(
                "Hot inlet [°C]",
                value=120.0,
                step=1.0,
                key=f"alt_hot_tin_{alt_type}",
            )
            alt_hot_tout = st.number_input(
                "Target hot outlet [°C]",
                value=70.0 if alt_type == "Plate & Frame" else 80.0,
                step=1.0,
                key=f"alt_hot_tout_{alt_type}",
            )
            alt_hot_p = st.number_input(
                "Hot pressure [bar]",
                min_value=0.1,
                value=4.0,
                step=0.1,
                key=f"alt_hot_p_{alt_type}",
            )

        with bb:
            alt_cold_fluid = st.selectbox(
                "Cold fluid",
                FLUIDS,
                index=0,
                key=f"alt_cold_fluid_{alt_type}",
            )
            alt_cold_flow = st.number_input(
                "Cold flow [kg/s]",
                min_value=0.01,
                value=8.0,
                step=0.1,
                key=f"alt_cold_flow_{alt_type}",
            )
            alt_cold_tin = st.number_input(
                "Cold inlet [°C]",
                value=25.0,
                step=1.0,
                key=f"alt_cold_tin_{alt_type}",
            )
            alt_cold_p = st.number_input(
                "Cold pressure [bar]",
                min_value=0.1,
                value=3.0,
                step=0.1,
                key=f"alt_cold_p_{alt_type}",
            )
            alt_flow_arrangement = st.selectbox(
                "Flow arrangement",
                ["Counter-current", "Co-current"],
                key=f"alt_flow_arrangement_{alt_type}",
            )

        hot_service = ServiceStream(
            fluid=alt_hot_fluid,
            mass_flow_kg_s=float(alt_hot_flow),
            inlet_temperature_c=float(alt_hot_tin),
            pressure_bar=float(alt_hot_p),
        )
        cold_service = ServiceStream(
            fluid=alt_cold_fluid,
            mass_flow_kg_s=float(alt_cold_flow),
            inlet_temperature_c=float(alt_cold_tin),
            pressure_bar=float(alt_cold_p),
        )

    if alt_type == "Plate & Frame":
        st.markdown("#### Plate geometry")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            plate_count_alt = st.number_input("Plates", 4, 500, 100, 2)
            plate_length_alt = st.number_input("Plate length [m]", 0.2, 3.0, 1.0, 0.1)
        with p2:
            plate_width_alt = st.number_input("Plate width [m]", 0.1, 1.5, 0.40, 0.05)
            plate_gap_alt = st.number_input("Plate gap [mm]", 1.0, 10.0, 3.0, 0.1)
        with p3:
            chevron_alt = st.slider("Chevron angle [°]", 20, 70, 45, 1)
            enlargement_alt = st.number_input("Enlargement factor", 1.0, 1.6, 1.18, 0.01)
        with p4:
            plate_hot_passes = st.selectbox("Hot passes", [1,2,3,4], index=0)
            plate_cold_passes = st.selectbox("Cold passes", [1,2,3,4], index=0)

        try:
            plate_result = simulate_plate_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                PlateGeometry(
                    plate_length_m=float(plate_length_alt),
                    plate_width_m=float(plate_width_alt),
                    plate_gap_m=float(plate_gap_alt)/1000.0,
                    plate_count=int(plate_count_alt),
                    passes_hot=int(plate_hot_passes),
                    passes_cold=int(plate_cold_passes),
                    chevron_angle_deg=float(chevron_alt),
                    enlargement_factor=float(enlargement_alt),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
            )

            components.html(
                plate_hx_svg(int(plate_count_alt), int(plate_hot_passes), int(plate_cold_passes)),
                height=315,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{plate_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{plate_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{plate_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{plate_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": plate_result.hot_outlet_c,
                    "Cold outlet [°C]": plate_result.cold_outlet_c,
                    "Hot velocity [m/s]": plate_result.hot_velocity_m_s,
                    "Cold velocity [m/s]": plate_result.cold_velocity_m_s,
                    "Hot Re": plate_result.hot_reynolds,
                    "Cold Re": plate_result.cold_reynolds,
                    "Hot h [W/m²K]": plate_result.hot_h_w_m2k,
                    "Cold h [W/m²K]": plate_result.cold_h_w_m2k,
                    "Hot ΔP [kPa]": plate_result.hot_dp_kpa,
                    "Cold ΔP [kPa]": plate_result.cold_dp_kpa,
                    "LMTD [°C]": plate_result.lmtd_c,
                    "Installed area [m²]": plate_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in plate_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Plate HX calculation failed: {exc}")

    elif alt_type == "Double Pipe":
        st.markdown("#### Double-pipe geometry")
        d1,d2,d3,d4 = st.columns(4)
        with d1:
            dp_inner_od = st.number_input("Inner tube OD [mm]", 10.0, 100.0, 48.3, 0.1)
            dp_inner_id = st.number_input("Inner tube ID [mm]", 8.0, 95.0, 40.9, 0.1)
        with d2:
            dp_outer_id = st.number_input("Outer pipe ID [mm]", 20.0, 200.0, 77.9, 0.1)
            dp_length = st.number_input("Hairpin length [m]", 1.0, 12.0, 6.0, 0.5)
        with d3:
            dp_hairpins = st.number_input("Hairpins", 1, 50, 12, 1)
            dp_hot_inner = st.checkbox("Hot stream in inner tube", value=True)
        with d4:
            st.metric("Total flow length", f"{2*float(dp_length)*int(dp_hairpins):.1f} m")

        try:
            dp_result = simulate_double_pipe_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                DoublePipeGeometry(
                    inner_tube_od_m=float(dp_inner_od)/1000.0,
                    inner_tube_id_m=float(dp_inner_id)/1000.0,
                    outer_pipe_id_m=float(dp_outer_id)/1000.0,
                    hairpin_length_m=float(dp_length),
                    hairpins=int(dp_hairpins),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
                hot_in_inner=dp_hot_inner,
            )

            components.html(
                double_pipe_svg(int(dp_hairpins)),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{dp_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{dp_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{dp_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{dp_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": dp_result.hot_outlet_c,
                    "Cold outlet [°C]": dp_result.cold_outlet_c,
                    "Inner velocity [m/s]": dp_result.inner_velocity_m_s,
                    "Annulus velocity [m/s]": dp_result.annulus_velocity_m_s,
                    "Inner Re": dp_result.inner_reynolds,
                    "Annulus Re": dp_result.annulus_reynolds,
                    "Inner h [W/m²K]": dp_result.inner_h_w_m2k,
                    "Annulus h [W/m²K]": dp_result.annulus_h_w_m2k,
                    "Inner ΔP [kPa]": dp_result.inner_dp_kpa,
                    "Annulus ΔP [kPa]": dp_result.annulus_dp_kpa,
                    "Installed area [m²]": dp_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in dp_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Double-pipe calculation failed: {exc}")

    elif alt_type == "Air-Cooled":
        a1,a2,a3 = st.columns(3)
        with a1:
            ac_fluid = st.selectbox("Process fluid", FLUIDS, index=4, key="ac_fluid_v09")
            ac_flow = st.number_input("Process flow [kg/s]", 0.01, 500.0, 2.0, 0.1)
            ac_tin = st.number_input("Process inlet [°C]", value=160.0, step=1.0)
            ac_tout = st.number_input("Process outlet [°C]", value=110.0, step=1.0)
            ac_pressure = st.number_input("Process pressure [bar]", 0.1, 200.0, 5.0, 0.5)
        with a2:
            ac_air_tin = st.number_input("Ambient air [°C]", value=30.0, step=1.0)
            ac_air_flow = st.number_input("Air flow [m³/s]", 1.0, 500.0, 70.0, 5.0)
            ac_rows = st.number_input("Rows", 1, 12, 4, 1)
            ac_tpr = st.number_input("Tubes / row", 4, 200, 40, 2)
        with a3:
            ac_length = st.number_input("Tube length [m]", 1.0, 20.0, 8.0, 0.5)
            ac_fins = st.number_input("Fins / m", 50.0, 800.0, 394.0, 10.0)
            ac_fin_od = st.number_input("Fin OD [mm]", 30.0, 120.0, 57.0, 1.0)
            ac_fan_eff = st.slider("Fan efficiency", 0.30, 0.90, 0.65, 0.01)

        try:
            ac_result = simulate_air_cooled_hx(
                ServiceStream(
                    fluid=ac_fluid,
                    mass_flow_kg_s=float(ac_flow),
                    inlet_temperature_c=float(ac_tin),
                    pressure_bar=float(ac_pressure),
                ),
                process_outlet_target_c=float(ac_tout),
                air_inlet_temperature_c=float(ac_air_tin),
                geometry=AirCooledGeometry(
                    tube_length_m=float(ac_length),
                    tubes_per_row=int(ac_tpr),
                    rows=int(ac_rows),
                    fin_od_m=float(ac_fin_od)/1000.0,
                    fins_per_m=float(ac_fins),
                    air_flow_m3_s=float(ac_air_flow),
                    fan_efficiency=float(ac_fan_eff),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
            )

            components.html(
                air_cooler_svg(int(ac_rows), int(ac_tpr), ac_result.fan_power_kw),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{ac_result.duty_kw/1000:.3f} MW")
            c2.metric("Fan power", f"{ac_result.fan_power_kw:.1f} kW")
            c3.metric("Required area", f"{ac_result.required_external_area_m2:.0f} m²")
            c4.metric("Area margin", f"{ac_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Process outlet [°C]": ac_result.process_outlet_c,
                    "Air outlet [°C]": ac_result.air_outlet_c,
                    "Process velocity [m/s]": ac_result.process_velocity_m_s,
                    "Process Re": ac_result.process_reynolds,
                    "Process h [W/m²K]": ac_result.process_h_w_m2k,
                    "Process ΔP [kPa]": ac_result.process_dp_kpa,
                    "Air face velocity [m/s]": ac_result.air_face_velocity_m_s,
                    "Air Re": ac_result.air_reynolds,
                    "Air h [W/m²K]": ac_result.air_h_w_m2k,
                    "Air ΔP [Pa]": ac_result.air_dp_pa,
                    "Fin efficiency": ac_result.fin_efficiency,
                    "Surface efficiency": ac_result.overall_surface_efficiency,
                    "U ext [W/m²K]": ac_result.overall_u_external_w_m2k,
                    "Installed area [m²]": ac_result.installed_external_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in ac_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Air-cooled calculation failed: {exc}")

    else:
        st.markdown("#### Service selector")
        s1,s2,s3 = st.columns(3)
        with s1:
            sel_duty = st.number_input("Duty [kW]", 1.0, 50000.0, 1000.0, 100.0)
            sel_hot_p = st.number_input("Hot pressure [bar]", 0.1, 300.0, 5.0, 1.0)
            sel_cold_p = st.number_input("Cold pressure [bar]", 0.1, 300.0, 3.0, 1.0)
        with s2:
            sel_hot_mu = st.number_input("Hot viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_cold_mu = st.number_input("Cold viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_phase = st.checkbox("Phase-change service")
        with s3:
            sel_fouling = st.checkbox("Solids / heavy fouling")
            sel_close = st.checkbox("Close temperature approach")
            sel_water = st.checkbox("Cooling water available", value=True)
            sel_compact = st.checkbox("Compactness is a priority")

        ranking = rank_exchangers(
            SelectionCase(
                duty_kw=float(sel_duty),
                hot_viscosity_mpa_s=float(sel_hot_mu),
                cold_viscosity_mpa_s=float(sel_cold_mu),
                hot_pressure_bar=float(sel_hot_p),
                cold_pressure_bar=float(sel_cold_p),
                phase_change=sel_phase,
                solids_or_heavy_fouling=sel_fouling,
                close_temperature_approach=sel_close,
                cooling_water_available=sel_water,
                compactness_priority=sel_compact,
            )
        )

        rank_df = pd.DataFrame([
            {
                "Rank": i+1,
                "Exchanger": c.exchanger_type,
                "Suitability score": c.score,
                "Reasons": "; ".join(c.reasons) or "General-purpose fit",
                "Cautions": "; ".join(c.cautions) or "—",
            }
            for i,c in enumerate(ranking)
        ])
        st.dataframe(rank_df, use_container_width=True, hide_index=True)

        st.info(
            f"Current P1 recommendation: **{ranking[0].exchanger_type}** "
            f"with screening score {ranking[0].score:.0f}/100."
        )

with tab_multi:
    st.markdown("### Multicomponent Condenser / Reboiler Integration")

    st.caption(
        "Couples equilibrium flash calculations to segment-by-segment exchanger "
        "duty, U, LMTD, area and pressure-drop screening."
    )

    m1, m2, m3 = st.columns(3)

    with m1:
        multi_mode = st.selectbox(
            "Integrated mode",
            ["Cooling / condensation", "Heating / boiling"],
            key="multi_mode_v08",
        )

        multi_package = st.selectbox(
            "VLE package",
            [
                "Ideal mixture",
                "NRTL",
                "UNIQUAC",
                "Peng-Robinson",
                "SRK",
            ],
            key="multi_package_v08",
        )

        multi_basis = st.radio(
            "Composition basis",
            ["mole", "mass"],
            horizontal=True,
            key="multi_basis_v08",
        )

    with m2:
        multi_pressure = st.number_input(
            "Process pressure [bar]",
            min_value=0.05,
            value=1.20,
            step=0.05,
            key="multi_pressure_v08",
        )

        multi_flow = st.number_input(
            "Process mass flow [kg/s]",
            min_value=0.01,
            value=2.0,
            step=0.1,
            key="multi_flow_v08",
        )

        if multi_mode.startswith("Cooling"):
            default_multi_tin = 125.0
            default_multi_tout = 55.0
        else:
            default_multi_tin = 55.0
            default_multi_tout = 120.0

        multi_tin = st.number_input(
            "Process inlet [°C]",
            value=default_multi_tin,
            step=1.0,
            key=f"multi_tin_{multi_mode}",
        )

        multi_tout = st.number_input(
            "Process outlet [°C]",
            value=default_multi_tout,
            step=1.0,
            key=f"multi_tout_{multi_mode}",
        )

    with m3:
        if multi_mode.startswith("Cooling"):
            multi_utility_default = "Water"
            multi_utility_t_default = 20.0
            multi_utility_flow_default = 30.0
        else:
            multi_utility_default = "Thermal oil"
            multi_utility_t_default = 220.0
            multi_utility_flow_default = 35.0

        utility_choices = [
            "Water",
            "Ethanol",
            "Butanol",
            "Acetone",
            "Thermal oil",
            "Light hydrocarbon",
        ]

        multi_utility = st.selectbox(
            "Utility",
            utility_choices,
            index=utility_choices.index(multi_utility_default),
            key=f"multi_utility_{multi_mode}",
        )

        multi_utility_tin = st.number_input(
            "Utility inlet [°C]",
            value=multi_utility_t_default,
            step=1.0,
            key=f"multi_utility_tin_{multi_mode}",
        )

        multi_utility_flow = st.number_input(
            "Utility flow [kg/s]",
            min_value=0.01,
            value=multi_utility_flow_default,
            step=0.5,
            key=f"multi_utility_flow_{multi_mode}",
        )

        multi_segments = st.selectbox(
            "Computational segments",
            [8, 10, 12, 16, 20, 24],
            index=3,
            key="multi_segments_v08",
        )

    multi_composition = composition_editor(
        "Process mixture",
        [
            {"Component": "Ethanol", "Fraction": 0.70},
            {"Component": "Water", "Fraction": 0.20},
            {"Component": "Butanol", "Fraction": 0.10},
        ],
        "multi_composition_editor_v08",
    )

    mm1, mm2, mm3 = st.columns(3)

    with mm1:
        multi_process_side = st.selectbox(
            "Process location",
            ["Tube side", "Shell side"],
            key="multi_process_side_v08",
        )

    with mm2:
        multi_flow_arrangement = st.selectbox(
            "Flow arrangement",
            ["Counter-current", "Co-current"],
            key="multi_flow_arrangement_v08",
        )

    with mm3:
        multi_wall_dt = st.number_input(
            "Condensing wall ΔT [K]",
            min_value=1.0,
            value=8.0,
            step=1.0,
            key="multi_wall_dt_v08",
        )

    multi_run = st.button(
        "🧬 RUN MULTICOMPONENT HX",
        type="primary",
        use_container_width=True,
        key="run_multi_hx_v08",
    )

with tab_phase:
    st.markdown("### Phase Change Pro")

    st.caption(
        "Dedicated pure-component condenser/reboiler screening engine with "
        "zone-by-zone duty, U, LMTD and area."
    )

    pc1, pc2, pc3 = st.columns(3)

    with pc1:
        pc_operation = st.selectbox(
            "Operation",
            ["Condenser", "Reboiler"],
            key="pc_operation",
        )

        pc_process_fluid = st.selectbox(
            "Process fluid",
            ["Water", "Ethanol", "Butanol", "Acetone"],
            index=1,
            key="pc_process_fluid",
        )

        pc_pressure = st.number_input(
            "Process pressure [bar]",
            min_value=0.2,
            value=1.50,
            step=0.10,
            key="pc_pressure",
        )

        try:
            pc_sat_preview = get_saturation_state(
                pc_process_fluid,
                float(pc_pressure),
            )
            pc_tsat = pc_sat_preview.saturation_temperature_c
        except Exception:
            pc_tsat = 80.0

    with pc2:
        if pc_operation == "Condenser":
            default_pin = pc_tsat + 20.0
            default_pout = pc_tsat - 10.0
            default_uin = 20.0
            default_u_flow = 30.0
            default_utility = "Water"
        else:
            default_pin = pc_tsat - 15.0
            default_pout = pc_tsat + 8.0
            default_uin = max(pc_tsat + 70.0, 180.0)
            default_u_flow = 25.0
            default_utility = "Thermal oil"

        pc_process_flow = st.number_input(
            "Process flow [kg/s]",
            min_value=0.01,
            value=2.0 if pc_operation == "Condenser" else 1.0,
            step=0.1,
            key="pc_process_flow",
        )

        pc_process_tin = st.number_input(
            "Process inlet [°C]",
            value=float(default_pin),
            step=1.0,
            key=f"pc_tin_{pc_operation}",
        )

        pc_process_tout = st.number_input(
            "Process outlet [°C]",
            value=float(default_pout),
            step=1.0,
            key=f"pc_tout_{pc_operation}",
        )

    with pc3:
        utility_options = [
            "Water",
            "Ethanol",
            "Butanol",
            "Acetone",
            "Thermal oil",
            "Light hydrocarbon",
        ]

        pc_utility = st.selectbox(
            "Utility fluid",
            utility_options,
            index=utility_options.index(default_utility),
            key=f"pc_utility_{pc_operation}",
        )

        pc_utility_flow = st.number_input(
            "Utility flow [kg/s]",
            min_value=0.01,
            value=float(default_u_flow),
            step=0.5,
            key=f"pc_utility_flow_{pc_operation}",
        )

        pc_utility_tin = st.number_input(
            "Utility inlet [°C]",
            value=float(default_uin),
            step=1.0,
            key=f"pc_utility_tin_{pc_operation}",
        )

    st.markdown("#### Two-phase setup")

    pc4, pc5, pc6, pc7 = st.columns(4)

    with pc4:
        pc_process_side = st.selectbox(
            "Process location",
            ["Tube side", "Shell side"],
            key="pc_process_side",
        )

    with pc5:
        pc_wall_subcool = st.number_input(
            "Condensing wall ΔT [K]",
            min_value=1.0,
            value=8.0,
            step=1.0,
        )

    with pc6:
        pc_roughness = st.number_input(
            "Boiling surface roughness [μm]",
            min_value=0.1,
            value=1.0,
            step=0.1,
        )

    with pc7:
        pc_flow_arrangement = st.selectbox(
            "Phase-change flow arrangement",
            ["Counter-current", "Co-current"],
            key="pc_flow_arrangement",
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



with tab_mechanical:
    st.markdown("### Mechanical / TEMA Screening")

    st.warning(
        "This tab is a preliminary engineering screen only. It does not constitute "
        "ASME code design, TEMA certification, fabrication approval or a stamped calculation."
    )

    m1, m2, m3 = st.columns(3)

    with m1:
        mech_tema_class = st.selectbox(
            "TEMA class basis",
            ["R", "B", "C"],
            index=0,
            help="Recorded as a design-basis field only; HX-RACE does not certify TEMA class compliance.",
        )

        mech_shell_dp = st.number_input(
            "Shell design pressure [bar]",
            min_value=0.5,
            value=10.0,
            step=0.5,
        )
        mech_tube_dp = st.number_input(
            "Tube design pressure [bar]",
            min_value=0.5,
            value=12.0,
            step=0.5,
        )

    with m2:
        mech_shell_dt = st.number_input(
            "Shell design temperature [°C]",
            value=180.0,
            step=5.0,
        )
        mech_tube_dt = st.number_input(
            "Tube design temperature [°C]",
            value=160.0,
            step=5.0,
        )
        mech_joint_eff = st.slider(
            "Shell weld joint efficiency E",
            0.60,
            1.00,
            0.85,
            0.01,
        )

    with m3:
        mech_shell_ca = st.number_input(
            "Shell corrosion allowance [mm]",
            min_value=0.0,
            value=1.5,
            step=0.5,
        )
        mech_tube_ca = st.number_input(
            "Tube corrosion allowance [mm]",
            min_value=0.0,
            value=0.0,
            step=0.1,
        )
        mech_selected_shell_t = st.number_input(
            "Selected shell nominal thickness [mm]",
            min_value=1.0,
            value=10.0,
            step=1.0,
        )

    material_options = material_names()

    mm1, mm2 = st.columns(2)

    with mm1:
        mech_shell_material = st.selectbox(
            "Shell material",
            material_options,
            index=material_options.index(
                "Carbon steel SA-516 Gr 70 (screening)"
            ),
        )

    with mm2:
        mech_tube_material = st.selectbox(
            "Tube material",
            material_options,
            index=material_options.index(
                "Carbon steel SA-179 tube (screening)"
            ),
        )

    st.markdown("#### Nozzle velocity screen")

    n1, n2, n3, n4 = st.columns(4)

    with n1:
        mech_shell_mass = st.number_input(
            "Shell-side flow [kg/s]",
            min_value=0.01,
            value=18.0,
            step=0.5,
        )
        mech_shell_density = st.number_input(
            "Shell-side density [kg/m³]",
            min_value=0.1,
            value=950.0,
            step=10.0,
        )

    with n2:
        mech_shell_noz_v = st.number_input(
            "Shell nozzle target v [m/s]",
            min_value=0.1,
            value=2.0,
            step=0.1,
        )

    with n3:
        mech_tube_mass = st.number_input(
            "Tube-side flow [kg/s]",
            min_value=0.01,
            value=12.0,
            step=0.5,
        )
        mech_tube_density = st.number_input(
            "Tube-side density [kg/m³]",
            min_value=0.1,
            value=800.0,
            step=10.0,
        )

    with n4:
        mech_tube_noz_v = st.number_input(
            "Tube nozzle target v [m/s]",
            min_value=0.1,
            value=2.0,
            step=0.1,
        )

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


mechanical_result = None
mechanical_error = None

try:
    mechanical_input = MechanicalDesignInput(
        tema_code=tema_code,
        shell_inside_diameter_m=float(shell_id),
        tube_od_m=float(tube_od_mm) / 1000.0,
        tube_id_m=float(tube_id_mm) / 1000.0,
        tube_length_m=float(tube_length),
        tube_pitch_m=float(tube_pitch_mm) / 1000.0,
        tube_passes=int(tube_passes),
        baffle_count=int(baffle_count),
        baffle_cut_fraction=float(baffle_cut) / 100.0,
        front_head=front,
        shell_type=shell,
        rear_head=rear,
        shell_design_pressure_bar=float(mech_shell_dp),
        tube_design_pressure_bar=float(mech_tube_dp),
        shell_design_temperature_c=float(mech_shell_dt),
        tube_design_temperature_c=float(mech_tube_dt),
        shell_material=mech_shell_material,
        tube_material=mech_tube_material,
        shell_joint_efficiency=float(mech_joint_eff),
        tube_joint_efficiency=1.0,
        shell_corrosion_allowance_mm=float(mech_shell_ca),
        tube_corrosion_allowance_mm=float(mech_tube_ca),
        selected_shell_nominal_thickness_mm=float(mech_selected_shell_t),
        shell_mass_flow_kg_s=float(mech_shell_mass),
        shell_density_kg_m3=float(mech_shell_density),
        tube_mass_flow_kg_s=float(mech_tube_mass),
        tube_density_kg_m3=float(mech_tube_density),
        shell_nozzle_target_velocity_m_s=float(mech_shell_noz_v),
        tube_nozzle_target_velocity_m_s=float(mech_tube_noz_v),
        tema_class=mech_tema_class,
    )

    mechanical_result = run_mechanical_design(mechanical_input)

except Exception as exc:
    mechanical_error = str(exc)

clearances = BellDelawareInputs(
    shell_to_baffle_clearance_m=float(shell_baffle_clearance_mm) / 1000.0,
    tube_to_baffle_clearance_m=float(tube_baffle_clearance_mm) / 1000.0,
    bundle_to_shell_clearance_m=float(bundle_shell_clearance_mm) / 1000.0,
    sealing_strip_pairs=int(sealing_strip_pairs),
)


if multi_run:
    try:
        multi_input = MulticomponentPhaseHXInput(
            mode=multi_mode,
            fractions=multi_composition,
            composition_basis=multi_basis,
            package=multi_package,
            interaction_parameters=interaction_parameters,
            process_mass_flow_kg_s=float(multi_flow),
            process_pressure_bar=float(multi_pressure),
            process_inlet_temperature_c=float(multi_tin),
            process_outlet_temperature_c=float(multi_tout),
            utility_fluid=multi_utility,
            utility_mass_flow_kg_s=float(multi_utility_flow),
            utility_pressure_bar=3.0,
            utility_inlet_temperature_c=float(multi_utility_tin),
            geometry=geometry,
            front_head=front,
            shell_type=shell,
            rear_head=rear,
            process_on_tube_side=(multi_process_side == "Tube side"),
            flow_arrangement=multi_flow_arrangement,
            segments=int(multi_segments),
            tube_wall_k_w_mk=float(wall_k),
            process_fouling_m2k_w=float(tube_fouling),
            utility_fouling_m2k_w=float(shell_fouling),
            wall_subcooling_k=float(multi_wall_dt),
            boiling_surface_roughness_um=1.0,
            allowable_process_dp_kpa=float(allowable_tube_dp),
            allowable_utility_dp_kpa=float(allowable_shell_dp),
            bell_clearances=clearances,
        )

        with st.spinner("Integrating VLE and exchanger segments…"):
            multi_result = simulate_multicomponent_phase_hx(
                multi_input
            )

        st.session_state["multi_hx_v08"] = multi_result.as_dict()
        st.session_state.pop("multi_hx_v08_error", None)

    except Exception as exc:
        st.session_state["multi_hx_v08_error"] = str(exc)
        st.session_state.pop("multi_hx_v08", None)


phase_result = None
phase_error = None

try:
    phase_input = PhaseChangeHXInput(
        operation=pc_operation,
        process=PhaseChangeStream(
            fluid=pc_process_fluid,
            mass_flow_kg_s=float(pc_process_flow),
            pressure_bar=float(pc_pressure),
            inlet_temperature_c=float(pc_process_tin),
            outlet_temperature_c=float(pc_process_tout),
        ),
        utility=UtilityStream(
            fluid=pc_utility,
            mass_flow_kg_s=float(pc_utility_flow),
            pressure_bar=3.0,
            inlet_temperature_c=float(pc_utility_tin),
        ),
        geometry=geometry,
        front_head=front,
        shell_type=shell,
        rear_head=rear,
        process_on_tube_side=(pc_process_side == "Tube side"),
        flow_arrangement=pc_flow_arrangement,
        tube_wall_k_w_mk=float(wall_k),
        process_fouling_m2k_w=float(tube_fouling),
        utility_fouling_m2k_w=float(shell_fouling),
        wall_subcooling_k=float(pc_wall_subcool),
        boiling_surface_roughness_um=float(pc_roughness),
        allowable_process_dp_kpa=float(allowable_tube_dp),
        allowable_utility_dp_kpa=float(allowable_shell_dp),
        bell_clearances=clearances,
    )

    phase_result = simulate_phase_change(phase_input)

except Exception as exc:
    phase_error = str(exc)

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




with tab_flash:
    st.markdown("### Rigorous Flash / VLE Garage")

    f1, f2, f3 = st.columns(3)

    with f1:
        flash_package = st.selectbox(
            "Flash package",
            [
                "Peng-Robinson",
                "SRK",
                "NRTL",
                "UNIQUAC",
                "Ideal mixture",
            ],
            key="flash_package",
        )

        flash_basis = st.radio(
            "Feed composition basis",
            ["mole", "mass"],
            horizontal=True,
            key="flash_basis",
        )

    with f2:
        flash_temperature = st.number_input(
            "Flash temperature [°C]",
            value=90.0,
            step=1.0,
            key="flash_temperature",
        )

        flash_pressure = st.number_input(
            "Flash pressure [bar]",
            min_value=0.05,
            value=1.50,
            step=0.05,
            key="flash_pressure",
        )

    with f3:
        flash_feed_mol_s = st.number_input(
            "Flash feed [mol/s]",
            min_value=0.001,
            value=100.0,
            step=5.0,
            key="flash_feed_mol_s",
        )

        flash_points = st.selectbox(
            "Path resolution",
            [12, 20, 30, 40],
            index=1,
            key="flash_points",
        )

    flash_composition = composition_editor(
        "Flash feed composition",
        [
            {"Component": "Ethanol", "Fraction": 0.60},
            {"Component": "Water", "Fraction": 0.25},
            {"Component": "Butanol", "Fraction": 0.15},
        ],
        "flash_composition_editor",
    )

    flash_run = st.button(
        "⚗️ RUN ISOTHERMAL FLASH",
        type="primary",
        use_container_width=True,
        key="run_flash_v07",
    )

    if flash_run:
        try:
            flash_result = flash_isothermal(
                temperature_c=float(flash_temperature),
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
            )

            st.session_state["flash_v07_result"] = flash_result.as_dict()
            st.session_state.pop("flash_v07_error", None)

        except Exception as exc:
            st.session_state["flash_v07_error"] = str(exc)
            st.session_state.pop("flash_v07_result", None)

    if "flash_v07_error" in st.session_state:
        st.error(st.session_state["flash_v07_error"])

    flash_data = st.session_state.get("flash_v07_result")

    if flash_data:
        q1, q2, q3, q4 = st.columns(4)

        q1.metric(
            "Vapour fraction β",
            f"{flash_data['vapour_fraction']:.5f}",
        )
        q2.metric(
            "Phase",
            flash_data["phase"],
        )
        q3.metric(
            "Iterations",
            str(flash_data["iterations"]),
        )
        q4.metric(
            "Converged",
            "YES" if flash_data["converged"] else "NO",
        )

        split_svg = flash_split_svg(
            flash_data["vapour_fraction"],
            flash_data["phase"],
        )
        components.html(split_svg, height=340, scrolling=False)

        names = list(flash_data["feed_mole_fractions"])

        phase_df = pd.DataFrame(
            {
                "Component": names,
                "Feed z": [
                    flash_data["feed_mole_fractions"][n]
                    for n in names
                ],
                "Liquid x": [
                    flash_data["liquid_mole_fractions"][n]
                    for n in names
                ],
                "Vapour y": [
                    flash_data["vapour_mole_fractions"][n]
                    for n in names
                ],
                "K = y/x": [
                    flash_data["k_values"][n]
                    for n in names
                ],
                "γ": [
                    flash_data["activity_coefficients"].get(n, 1.0)
                    for n in names
                ],
            }
        )

        st.dataframe(
            phase_df.style.format(
                {
                    "Feed z": "{:.6f}",
                    "Liquid x": "{:.6f}",
                    "Vapour y": "{:.6f}",
                    "K = y/x": "{:.5f}",
                    "γ": "{:.5f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        drum = simulate_flash_drum(
            feed_mol_s=float(flash_feed_mol_s),
            temperature_c=float(flash_temperature),
            pressure_bar=float(flash_pressure),
            fractions=flash_composition,
            composition_basis=flash_basis,
            package=flash_package,
            interaction_parameters=interaction_parameters,
        )

        d1, d2, d3 = st.columns(3)

        d1.metric(
            "Feed",
            f"{drum.feed_mol_s:.2f} mol/s",
        )
        d2.metric(
            "Vapour",
            f"{drum.vapour_mol_s:.2f} mol/s",
        )
        d3.metric(
            "Liquid",
            f"{drum.liquid_mol_s:.2f} mol/s",
        )

        with st.expander("EOS / activity diagnostics"):
            if flash_data.get("liquid_z") is not None:
                st.write(
                    f"Liquid Z: {flash_data['liquid_z']:.6f}"
                )
            if flash_data.get("vapour_z") is not None:
                st.write(
                    f"Vapour Z: {flash_data['vapour_z']:.6f}"
                )

            st.write(
                f"Rachford–Rice residual: "
                f"{flash_data['residual']:.3e}"
            )

            for warning in flash_data["warnings"]:
                st.warning(warning)

        st.markdown("### Isobaric vapour-fraction sweep")

        sw1, sw2 = st.columns(2)

        with sw1:
            sweep_tmin = st.number_input(
                "Sweep Tmin [°C]",
                value=50.0,
                step=5.0,
                key="sweep_tmin",
            )

        with sw2:
            sweep_tmax = st.number_input(
                "Sweep Tmax [°C]",
                value=140.0,
                step=5.0,
                key="sweep_tmax",
            )

        try:
            envelope = temperature_flash_sweep(
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
                temperature_min_c=float(sweep_tmin),
                temperature_max_c=float(sweep_tmax),
                points=int(flash_points),
            )

            env_df = pd.DataFrame(
                [
                    {
                        "Temperature [°C]": p.temperature_c,
                        "Vapour fraction": p.vapour_fraction,
                        "Phase": p.phase,
                    }
                    for p in envelope.points
                ]
            )

            fig_env = go.Figure()
            fig_env.add_trace(
                go.Scatter(
                    x=env_df["Temperature [°C]"],
                    y=env_df["Vapour fraction"],
                    mode="lines+markers",
                    name="β",
                )
            )
            fig_env.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=25, r=20, t=30, b=35),
                xaxis_title="Temperature [°C]",
                yaxis_title="Vapour fraction β",
                yaxis_range=[-0.03, 1.03],
            )

            st.plotly_chart(fig_env, use_container_width=True)

            e1, e2 = st.columns(2)

            e1.metric(
                "Approx. bubble T",
                "—"
                if envelope.bubble_temperature_c is None
                else f"{envelope.bubble_temperature_c:.2f} °C",
            )
            e2.metric(
                "Approx. dew T",
                "—"
                if envelope.dew_temperature_c is None
                else f"{envelope.dew_temperature_c:.2f} °C",
            )

        except Exception as exc:
            st.warning(
                f"Temperature flash sweep could not be generated: {exc}"
            )

        st.markdown("### Multicomponent phase path")

        path_mode = st.radio(
            "Path mode",
            ["Cooling / condensation", "Heating / boiling"],
            horizontal=True,
            key="flash_path_mode",
        )

        if path_mode.startswith("Cooling"):
            path_t_start_default = max(
                float(flash_temperature),
                120.0,
            )
            path_t_end_default = min(
                float(flash_temperature) - 30.0,
                55.0,
            )
        else:
            path_t_start_default = min(
                float(flash_temperature),
                55.0,
            )
            path_t_end_default = max(
                float(flash_temperature) + 30.0,
                125.0,
            )

        pp1, pp2 = st.columns(2)

        with pp1:
            path_t_start = st.number_input(
                "Path start [°C]",
                value=float(path_t_start_default),
                step=2.0,
                key=f"path_start_{path_mode}",
            )

        with pp2:
            path_t_end = st.number_input(
                "Path end [°C]",
                value=float(path_t_end_default),
                step=2.0,
                key=f"path_end_{path_mode}",
            )

        try:
            path = build_phase_path(
                mode=path_mode,
                pressure_bar=float(flash_pressure),
                fractions=flash_composition,
                composition_basis=flash_basis,
                package=flash_package,
                interaction_parameters=interaction_parameters,
                temperature_start_c=float(path_t_start),
                temperature_end_c=float(path_t_end),
                points=int(flash_points),
            )

            path_rows = []

            for point in path.points:
                row = {
                    "Temperature [°C]": point.temperature_c,
                    "Vapour fraction": point.vapour_fraction,
                }

                for comp in flash_composition:
                    row[f"x {comp}"] = (
                        point.liquid_mole_fractions.get(comp, 0.0)
                    )
                    row[f"y {comp}"] = (
                        point.vapour_mole_fractions.get(comp, 0.0)
                    )

                path_rows.append(row)

            path_df = pd.DataFrame(path_rows)

            fig_path = go.Figure()
            fig_path.add_trace(
                go.Scatter(
                    x=path_df["Temperature [°C]"],
                    y=path_df["Vapour fraction"],
                    mode="lines+markers",
                    name="Vapour fraction",
                )
            )

            fig_path.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=25, r=20, t=30, b=35),
                xaxis_title="Temperature [°C]",
                yaxis_title="β",
                yaxis_range=[-0.03, 1.03],
            )

            st.plotly_chart(fig_path, use_container_width=True)

            with st.expander("Phase-composition path table"):
                st.dataframe(
                    path_df,
                    use_container_width=True,
                    hide_index=True,
                )

        except Exception as exc:
            st.warning(
                f"Multicomponent phase path could not be generated: {exc}"
            )

        flash_json = json.dumps(
            flash_data,
            indent=2,
        ).encode("utf-8")

        st.download_button(
            "↓ Download flash / VLE JSON",
            data=flash_json,
            file_name="HX-RACE_v07_flash_vle.json",
            mime="application/json",
            use_container_width=True,
        )



with tab_alternatives:
    st.markdown("### Multi-Exchanger Platform")

    alt_type = st.radio(
        "Exchanger",
        ["Plate & Frame", "Double Pipe", "Air-Cooled", "Selector"],
        horizontal=True,
        key="alt_hx_type_v09",
    )

    if alt_type in {"Plate & Frame", "Double Pipe"}:
        aa, bb = st.columns(2)

        with aa:
            alt_hot_fluid = st.selectbox(
                "Hot fluid",
                FLUIDS,
                index=1,
                key=f"alt_hot_fluid_{alt_type}",
            )
            alt_hot_flow = st.number_input(
                "Hot flow [kg/s]",
                min_value=0.01,
                value=3.0,
                step=0.1,
                key=f"alt_hot_flow_{alt_type}",
            )
            alt_hot_tin = st.number_input(
                "Hot inlet [°C]",
                value=120.0,
                step=1.0,
                key=f"alt_hot_tin_{alt_type}",
            )
            alt_hot_tout = st.number_input(
                "Target hot outlet [°C]",
                value=70.0 if alt_type == "Plate & Frame" else 80.0,
                step=1.0,
                key=f"alt_hot_tout_{alt_type}",
            )
            alt_hot_p = st.number_input(
                "Hot pressure [bar]",
                min_value=0.1,
                value=4.0,
                step=0.1,
                key=f"alt_hot_p_{alt_type}",
            )

        with bb:
            alt_cold_fluid = st.selectbox(
                "Cold fluid",
                FLUIDS,
                index=0,
                key=f"alt_cold_fluid_{alt_type}",
            )
            alt_cold_flow = st.number_input(
                "Cold flow [kg/s]",
                min_value=0.01,
                value=8.0,
                step=0.1,
                key=f"alt_cold_flow_{alt_type}",
            )
            alt_cold_tin = st.number_input(
                "Cold inlet [°C]",
                value=25.0,
                step=1.0,
                key=f"alt_cold_tin_{alt_type}",
            )
            alt_cold_p = st.number_input(
                "Cold pressure [bar]",
                min_value=0.1,
                value=3.0,
                step=0.1,
                key=f"alt_cold_p_{alt_type}",
            )
            alt_flow_arrangement = st.selectbox(
                "Flow arrangement",
                ["Counter-current", "Co-current"],
                key=f"alt_flow_arrangement_{alt_type}",
            )

        hot_service = ServiceStream(
            fluid=alt_hot_fluid,
            mass_flow_kg_s=float(alt_hot_flow),
            inlet_temperature_c=float(alt_hot_tin),
            pressure_bar=float(alt_hot_p),
        )
        cold_service = ServiceStream(
            fluid=alt_cold_fluid,
            mass_flow_kg_s=float(alt_cold_flow),
            inlet_temperature_c=float(alt_cold_tin),
            pressure_bar=float(alt_cold_p),
        )

    if alt_type == "Plate & Frame":
        st.markdown("#### Plate geometry")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            plate_count_alt = st.number_input("Plates", 4, 500, 100, 2)
            plate_length_alt = st.number_input("Plate length [m]", 0.2, 3.0, 1.0, 0.1)
        with p2:
            plate_width_alt = st.number_input("Plate width [m]", 0.1, 1.5, 0.40, 0.05)
            plate_gap_alt = st.number_input("Plate gap [mm]", 1.0, 10.0, 3.0, 0.1)
        with p3:
            chevron_alt = st.slider("Chevron angle [°]", 20, 70, 45, 1)
            enlargement_alt = st.number_input("Enlargement factor", 1.0, 1.6, 1.18, 0.01)
        with p4:
            plate_hot_passes = st.selectbox("Hot passes", [1,2,3,4], index=0)
            plate_cold_passes = st.selectbox("Cold passes", [1,2,3,4], index=0)

        try:
            plate_result = simulate_plate_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                PlateGeometry(
                    plate_length_m=float(plate_length_alt),
                    plate_width_m=float(plate_width_alt),
                    plate_gap_m=float(plate_gap_alt)/1000.0,
                    plate_count=int(plate_count_alt),
                    passes_hot=int(plate_hot_passes),
                    passes_cold=int(plate_cold_passes),
                    chevron_angle_deg=float(chevron_alt),
                    enlargement_factor=float(enlargement_alt),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
            )

            components.html(
                plate_hx_svg(int(plate_count_alt), int(plate_hot_passes), int(plate_cold_passes)),
                height=315,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{plate_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{plate_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{plate_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{plate_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": plate_result.hot_outlet_c,
                    "Cold outlet [°C]": plate_result.cold_outlet_c,
                    "Hot velocity [m/s]": plate_result.hot_velocity_m_s,
                    "Cold velocity [m/s]": plate_result.cold_velocity_m_s,
                    "Hot Re": plate_result.hot_reynolds,
                    "Cold Re": plate_result.cold_reynolds,
                    "Hot h [W/m²K]": plate_result.hot_h_w_m2k,
                    "Cold h [W/m²K]": plate_result.cold_h_w_m2k,
                    "Hot ΔP [kPa]": plate_result.hot_dp_kpa,
                    "Cold ΔP [kPa]": plate_result.cold_dp_kpa,
                    "LMTD [°C]": plate_result.lmtd_c,
                    "Installed area [m²]": plate_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in plate_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Plate HX calculation failed: {exc}")

    elif alt_type == "Double Pipe":
        st.markdown("#### Double-pipe geometry")
        d1,d2,d3,d4 = st.columns(4)
        with d1:
            dp_inner_od = st.number_input("Inner tube OD [mm]", 10.0, 100.0, 48.3, 0.1)
            dp_inner_id = st.number_input("Inner tube ID [mm]", 8.0, 95.0, 40.9, 0.1)
        with d2:
            dp_outer_id = st.number_input("Outer pipe ID [mm]", 20.0, 200.0, 77.9, 0.1)
            dp_length = st.number_input("Hairpin length [m]", 1.0, 12.0, 6.0, 0.5)
        with d3:
            dp_hairpins = st.number_input("Hairpins", 1, 50, 12, 1)
            dp_hot_inner = st.checkbox("Hot stream in inner tube", value=True)
        with d4:
            st.metric("Total flow length", f"{2*float(dp_length)*int(dp_hairpins):.1f} m")

        try:
            dp_result = simulate_double_pipe_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                DoublePipeGeometry(
                    inner_tube_od_m=float(dp_inner_od)/1000.0,
                    inner_tube_id_m=float(dp_inner_id)/1000.0,
                    outer_pipe_id_m=float(dp_outer_id)/1000.0,
                    hairpin_length_m=float(dp_length),
                    hairpins=int(dp_hairpins),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
                hot_in_inner=dp_hot_inner,
            )

            components.html(
                double_pipe_svg(int(dp_hairpins)),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{dp_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{dp_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{dp_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{dp_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": dp_result.hot_outlet_c,
                    "Cold outlet [°C]": dp_result.cold_outlet_c,
                    "Inner velocity [m/s]": dp_result.inner_velocity_m_s,
                    "Annulus velocity [m/s]": dp_result.annulus_velocity_m_s,
                    "Inner Re": dp_result.inner_reynolds,
                    "Annulus Re": dp_result.annulus_reynolds,
                    "Inner h [W/m²K]": dp_result.inner_h_w_m2k,
                    "Annulus h [W/m²K]": dp_result.annulus_h_w_m2k,
                    "Inner ΔP [kPa]": dp_result.inner_dp_kpa,
                    "Annulus ΔP [kPa]": dp_result.annulus_dp_kpa,
                    "Installed area [m²]": dp_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in dp_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Double-pipe calculation failed: {exc}")

    elif alt_type == "Air-Cooled":
        a1,a2,a3 = st.columns(3)
        with a1:
            ac_fluid = st.selectbox("Process fluid", FLUIDS, index=4, key="ac_fluid_v09")
            ac_flow = st.number_input("Process flow [kg/s]", 0.01, 500.0, 2.0, 0.1)
            ac_tin = st.number_input("Process inlet [°C]", value=160.0, step=1.0)
            ac_tout = st.number_input("Process outlet [°C]", value=110.0, step=1.0)
            ac_pressure = st.number_input("Process pressure [bar]", 0.1, 200.0, 5.0, 0.5)
        with a2:
            ac_air_tin = st.number_input("Ambient air [°C]", value=30.0, step=1.0)
            ac_air_flow = st.number_input("Air flow [m³/s]", 1.0, 500.0, 70.0, 5.0)
            ac_rows = st.number_input("Rows", 1, 12, 4, 1)
            ac_tpr = st.number_input("Tubes / row", 4, 200, 40, 2)
        with a3:
            ac_length = st.number_input("Tube length [m]", 1.0, 20.0, 8.0, 0.5)
            ac_fins = st.number_input("Fins / m", 50.0, 800.0, 394.0, 10.0)
            ac_fin_od = st.number_input("Fin OD [mm]", 30.0, 120.0, 57.0, 1.0)
            ac_fan_eff = st.slider("Fan efficiency", 0.30, 0.90, 0.65, 0.01)

        try:
            ac_result = simulate_air_cooled_hx(
                ServiceStream(
                    fluid=ac_fluid,
                    mass_flow_kg_s=float(ac_flow),
                    inlet_temperature_c=float(ac_tin),
                    pressure_bar=float(ac_pressure),
                ),
                process_outlet_target_c=float(ac_tout),
                air_inlet_temperature_c=float(ac_air_tin),
                geometry=AirCooledGeometry(
                    tube_length_m=float(ac_length),
                    tubes_per_row=int(ac_tpr),
                    rows=int(ac_rows),
                    fin_od_m=float(ac_fin_od)/1000.0,
                    fins_per_m=float(ac_fins),
                    air_flow_m3_s=float(ac_air_flow),
                    fan_efficiency=float(ac_fan_eff),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
            )

            components.html(
                air_cooler_svg(int(ac_rows), int(ac_tpr), ac_result.fan_power_kw),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{ac_result.duty_kw/1000:.3f} MW")
            c2.metric("Fan power", f"{ac_result.fan_power_kw:.1f} kW")
            c3.metric("Required area", f"{ac_result.required_external_area_m2:.0f} m²")
            c4.metric("Area margin", f"{ac_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Process outlet [°C]": ac_result.process_outlet_c,
                    "Air outlet [°C]": ac_result.air_outlet_c,
                    "Process velocity [m/s]": ac_result.process_velocity_m_s,
                    "Process Re": ac_result.process_reynolds,
                    "Process h [W/m²K]": ac_result.process_h_w_m2k,
                    "Process ΔP [kPa]": ac_result.process_dp_kpa,
                    "Air face velocity [m/s]": ac_result.air_face_velocity_m_s,
                    "Air Re": ac_result.air_reynolds,
                    "Air h [W/m²K]": ac_result.air_h_w_m2k,
                    "Air ΔP [Pa]": ac_result.air_dp_pa,
                    "Fin efficiency": ac_result.fin_efficiency,
                    "Surface efficiency": ac_result.overall_surface_efficiency,
                    "U ext [W/m²K]": ac_result.overall_u_external_w_m2k,
                    "Installed area [m²]": ac_result.installed_external_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in ac_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Air-cooled calculation failed: {exc}")

    else:
        st.markdown("#### Service selector")
        s1,s2,s3 = st.columns(3)
        with s1:
            sel_duty = st.number_input("Duty [kW]", 1.0, 50000.0, 1000.0, 100.0)
            sel_hot_p = st.number_input("Hot pressure [bar]", 0.1, 300.0, 5.0, 1.0)
            sel_cold_p = st.number_input("Cold pressure [bar]", 0.1, 300.0, 3.0, 1.0)
        with s2:
            sel_hot_mu = st.number_input("Hot viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_cold_mu = st.number_input("Cold viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_phase = st.checkbox("Phase-change service")
        with s3:
            sel_fouling = st.checkbox("Solids / heavy fouling")
            sel_close = st.checkbox("Close temperature approach")
            sel_water = st.checkbox("Cooling water available", value=True)
            sel_compact = st.checkbox("Compactness is a priority")

        ranking = rank_exchangers(
            SelectionCase(
                duty_kw=float(sel_duty),
                hot_viscosity_mpa_s=float(sel_hot_mu),
                cold_viscosity_mpa_s=float(sel_cold_mu),
                hot_pressure_bar=float(sel_hot_p),
                cold_pressure_bar=float(sel_cold_p),
                phase_change=sel_phase,
                solids_or_heavy_fouling=sel_fouling,
                close_temperature_approach=sel_close,
                cooling_water_available=sel_water,
                compactness_priority=sel_compact,
            )
        )

        rank_df = pd.DataFrame([
            {
                "Rank": i+1,
                "Exchanger": c.exchanger_type,
                "Suitability score": c.score,
                "Reasons": "; ".join(c.reasons) or "General-purpose fit",
                "Cautions": "; ".join(c.cautions) or "—",
            }
            for i,c in enumerate(ranking)
        ])
        st.dataframe(rank_df, use_container_width=True, hide_index=True)

        st.info(
            f"Current P1 recommendation: **{ranking[0].exchanger_type}** "
            f"with screening score {ranking[0].score:.0f}/100."
        )

with tab_multi:
    st.markdown("### Multicomponent Condenser / Reboiler Integration")

    st.caption(
        "Couples equilibrium flash calculations to segment-by-segment exchanger "
        "duty, U, LMTD, area and pressure-drop screening."
    )

    m1, m2, m3 = st.columns(3)

    with m1:
        multi_mode = st.selectbox(
            "Integrated mode",
            ["Cooling / condensation", "Heating / boiling"],
            key="multi_mode_v08",
        )

        multi_package = st.selectbox(
            "VLE package",
            [
                "Ideal mixture",
                "NRTL",
                "UNIQUAC",
                "Peng-Robinson",
                "SRK",
            ],
            key="multi_package_v08",
        )

        multi_basis = st.radio(
            "Composition basis",
            ["mole", "mass"],
            horizontal=True,
            key="multi_basis_v08",
        )

    with m2:
        multi_pressure = st.number_input(
            "Process pressure [bar]",
            min_value=0.05,
            value=1.20,
            step=0.05,
            key="multi_pressure_v08",
        )

        multi_flow = st.number_input(
            "Process mass flow [kg/s]",
            min_value=0.01,
            value=2.0,
            step=0.1,
            key="multi_flow_v08",
        )

        if multi_mode.startswith("Cooling"):
            default_multi_tin = 125.0
            default_multi_tout = 55.0
        else:
            default_multi_tin = 55.0
            default_multi_tout = 120.0

        multi_tin = st.number_input(
            "Process inlet [°C]",
            value=default_multi_tin,
            step=1.0,
            key=f"multi_tin_{multi_mode}",
        )

        multi_tout = st.number_input(
            "Process outlet [°C]",
            value=default_multi_tout,
            step=1.0,
            key=f"multi_tout_{multi_mode}",
        )

    with m3:
        if multi_mode.startswith("Cooling"):
            multi_utility_default = "Water"
            multi_utility_t_default = 20.0
            multi_utility_flow_default = 30.0
        else:
            multi_utility_default = "Thermal oil"
            multi_utility_t_default = 220.0
            multi_utility_flow_default = 35.0

        utility_choices = [
            "Water",
            "Ethanol",
            "Butanol",
            "Acetone",
            "Thermal oil",
            "Light hydrocarbon",
        ]

        multi_utility = st.selectbox(
            "Utility",
            utility_choices,
            index=utility_choices.index(multi_utility_default),
            key=f"multi_utility_{multi_mode}",
        )

        multi_utility_tin = st.number_input(
            "Utility inlet [°C]",
            value=multi_utility_t_default,
            step=1.0,
            key=f"multi_utility_tin_{multi_mode}",
        )

        multi_utility_flow = st.number_input(
            "Utility flow [kg/s]",
            min_value=0.01,
            value=multi_utility_flow_default,
            step=0.5,
            key=f"multi_utility_flow_{multi_mode}",
        )

        multi_segments = st.selectbox(
            "Computational segments",
            [8, 10, 12, 16, 20, 24],
            index=3,
            key="multi_segments_v08",
        )

    multi_composition = composition_editor(
        "Process mixture",
        [
            {"Component": "Ethanol", "Fraction": 0.70},
            {"Component": "Water", "Fraction": 0.20},
            {"Component": "Butanol", "Fraction": 0.10},
        ],
        "multi_composition_editor_v08",
    )

    mm1, mm2, mm3 = st.columns(3)

    with mm1:
        multi_process_side = st.selectbox(
            "Process location",
            ["Tube side", "Shell side"],
            key="multi_process_side_v08",
        )

    with mm2:
        multi_flow_arrangement = st.selectbox(
            "Flow arrangement",
            ["Counter-current", "Co-current"],
            key="multi_flow_arrangement_v08",
        )

    with mm3:
        multi_wall_dt = st.number_input(
            "Condensing wall ΔT [K]",
            min_value=1.0,
            value=8.0,
            step=1.0,
            key="multi_wall_dt_v08",
        )

    multi_run = st.button(
        "🧬 RUN MULTICOMPONENT HX",
        type="primary",
        use_container_width=True,
        key="run_multi_hx_v08",
    )



with tab_alternatives:
    st.markdown("### Multi-Exchanger Platform")

    alt_type = st.radio(
        "Exchanger",
        ["Plate & Frame", "Double Pipe", "Air-Cooled", "Selector"],
        horizontal=True,
        key="alt_hx_type_v09",
    )

    if alt_type in {"Plate & Frame", "Double Pipe"}:
        aa, bb = st.columns(2)

        with aa:
            alt_hot_fluid = st.selectbox(
                "Hot fluid",
                FLUIDS,
                index=1,
                key=f"alt_hot_fluid_{alt_type}",
            )
            alt_hot_flow = st.number_input(
                "Hot flow [kg/s]",
                min_value=0.01,
                value=3.0,
                step=0.1,
                key=f"alt_hot_flow_{alt_type}",
            )
            alt_hot_tin = st.number_input(
                "Hot inlet [°C]",
                value=120.0,
                step=1.0,
                key=f"alt_hot_tin_{alt_type}",
            )
            alt_hot_tout = st.number_input(
                "Target hot outlet [°C]",
                value=70.0 if alt_type == "Plate & Frame" else 80.0,
                step=1.0,
                key=f"alt_hot_tout_{alt_type}",
            )
            alt_hot_p = st.number_input(
                "Hot pressure [bar]",
                min_value=0.1,
                value=4.0,
                step=0.1,
                key=f"alt_hot_p_{alt_type}",
            )

        with bb:
            alt_cold_fluid = st.selectbox(
                "Cold fluid",
                FLUIDS,
                index=0,
                key=f"alt_cold_fluid_{alt_type}",
            )
            alt_cold_flow = st.number_input(
                "Cold flow [kg/s]",
                min_value=0.01,
                value=8.0,
                step=0.1,
                key=f"alt_cold_flow_{alt_type}",
            )
            alt_cold_tin = st.number_input(
                "Cold inlet [°C]",
                value=25.0,
                step=1.0,
                key=f"alt_cold_tin_{alt_type}",
            )
            alt_cold_p = st.number_input(
                "Cold pressure [bar]",
                min_value=0.1,
                value=3.0,
                step=0.1,
                key=f"alt_cold_p_{alt_type}",
            )
            alt_flow_arrangement = st.selectbox(
                "Flow arrangement",
                ["Counter-current", "Co-current"],
                key=f"alt_flow_arrangement_{alt_type}",
            )

        hot_service = ServiceStream(
            fluid=alt_hot_fluid,
            mass_flow_kg_s=float(alt_hot_flow),
            inlet_temperature_c=float(alt_hot_tin),
            pressure_bar=float(alt_hot_p),
        )
        cold_service = ServiceStream(
            fluid=alt_cold_fluid,
            mass_flow_kg_s=float(alt_cold_flow),
            inlet_temperature_c=float(alt_cold_tin),
            pressure_bar=float(alt_cold_p),
        )

    if alt_type == "Plate & Frame":
        st.markdown("#### Plate geometry")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            plate_count_alt = st.number_input("Plates", 4, 500, 100, 2)
            plate_length_alt = st.number_input("Plate length [m]", 0.2, 3.0, 1.0, 0.1)
        with p2:
            plate_width_alt = st.number_input("Plate width [m]", 0.1, 1.5, 0.40, 0.05)
            plate_gap_alt = st.number_input("Plate gap [mm]", 1.0, 10.0, 3.0, 0.1)
        with p3:
            chevron_alt = st.slider("Chevron angle [°]", 20, 70, 45, 1)
            enlargement_alt = st.number_input("Enlargement factor", 1.0, 1.6, 1.18, 0.01)
        with p4:
            plate_hot_passes = st.selectbox("Hot passes", [1,2,3,4], index=0)
            plate_cold_passes = st.selectbox("Cold passes", [1,2,3,4], index=0)

        try:
            plate_result = simulate_plate_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                PlateGeometry(
                    plate_length_m=float(plate_length_alt),
                    plate_width_m=float(plate_width_alt),
                    plate_gap_m=float(plate_gap_alt)/1000.0,
                    plate_count=int(plate_count_alt),
                    passes_hot=int(plate_hot_passes),
                    passes_cold=int(plate_cold_passes),
                    chevron_angle_deg=float(chevron_alt),
                    enlargement_factor=float(enlargement_alt),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
            )

            components.html(
                plate_hx_svg(int(plate_count_alt), int(plate_hot_passes), int(plate_cold_passes)),
                height=315,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{plate_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{plate_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{plate_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{plate_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": plate_result.hot_outlet_c,
                    "Cold outlet [°C]": plate_result.cold_outlet_c,
                    "Hot velocity [m/s]": plate_result.hot_velocity_m_s,
                    "Cold velocity [m/s]": plate_result.cold_velocity_m_s,
                    "Hot Re": plate_result.hot_reynolds,
                    "Cold Re": plate_result.cold_reynolds,
                    "Hot h [W/m²K]": plate_result.hot_h_w_m2k,
                    "Cold h [W/m²K]": plate_result.cold_h_w_m2k,
                    "Hot ΔP [kPa]": plate_result.hot_dp_kpa,
                    "Cold ΔP [kPa]": plate_result.cold_dp_kpa,
                    "LMTD [°C]": plate_result.lmtd_c,
                    "Installed area [m²]": plate_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in plate_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Plate HX calculation failed: {exc}")

    elif alt_type == "Double Pipe":
        st.markdown("#### Double-pipe geometry")
        d1,d2,d3,d4 = st.columns(4)
        with d1:
            dp_inner_od = st.number_input("Inner tube OD [mm]", 10.0, 100.0, 48.3, 0.1)
            dp_inner_id = st.number_input("Inner tube ID [mm]", 8.0, 95.0, 40.9, 0.1)
        with d2:
            dp_outer_id = st.number_input("Outer pipe ID [mm]", 20.0, 200.0, 77.9, 0.1)
            dp_length = st.number_input("Hairpin length [m]", 1.0, 12.0, 6.0, 0.5)
        with d3:
            dp_hairpins = st.number_input("Hairpins", 1, 50, 12, 1)
            dp_hot_inner = st.checkbox("Hot stream in inner tube", value=True)
        with d4:
            st.metric("Total flow length", f"{2*float(dp_length)*int(dp_hairpins):.1f} m")

        try:
            dp_result = simulate_double_pipe_hx(
                hot_service,
                cold_service,
                float(alt_hot_tout),
                DoublePipeGeometry(
                    inner_tube_od_m=float(dp_inner_od)/1000.0,
                    inner_tube_id_m=float(dp_inner_id)/1000.0,
                    outer_pipe_id_m=float(dp_outer_id)/1000.0,
                    hairpin_length_m=float(dp_length),
                    hairpins=int(dp_hairpins),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
                flow_arrangement=alt_flow_arrangement,
                hot_in_inner=dp_hot_inner,
            )

            components.html(
                double_pipe_svg(int(dp_hairpins)),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{dp_result.duty_kw/1000:.3f} MW")
            c2.metric("U", f"{dp_result.overall_u_w_m2k:.0f} W/m²K")
            c3.metric("Required area", f"{dp_result.required_area_m2:.1f} m²")
            c4.metric("Area margin", f"{dp_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Hot outlet [°C]": dp_result.hot_outlet_c,
                    "Cold outlet [°C]": dp_result.cold_outlet_c,
                    "Inner velocity [m/s]": dp_result.inner_velocity_m_s,
                    "Annulus velocity [m/s]": dp_result.annulus_velocity_m_s,
                    "Inner Re": dp_result.inner_reynolds,
                    "Annulus Re": dp_result.annulus_reynolds,
                    "Inner h [W/m²K]": dp_result.inner_h_w_m2k,
                    "Annulus h [W/m²K]": dp_result.annulus_h_w_m2k,
                    "Inner ΔP [kPa]": dp_result.inner_dp_kpa,
                    "Annulus ΔP [kPa]": dp_result.annulus_dp_kpa,
                    "Installed area [m²]": dp_result.installed_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in dp_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Double-pipe calculation failed: {exc}")

    elif alt_type == "Air-Cooled":
        a1,a2,a3 = st.columns(3)
        with a1:
            ac_fluid = st.selectbox("Process fluid", FLUIDS, index=4, key="ac_fluid_v09")
            ac_flow = st.number_input("Process flow [kg/s]", 0.01, 500.0, 2.0, 0.1)
            ac_tin = st.number_input("Process inlet [°C]", value=160.0, step=1.0)
            ac_tout = st.number_input("Process outlet [°C]", value=110.0, step=1.0)
            ac_pressure = st.number_input("Process pressure [bar]", 0.1, 200.0, 5.0, 0.5)
        with a2:
            ac_air_tin = st.number_input("Ambient air [°C]", value=30.0, step=1.0)
            ac_air_flow = st.number_input("Air flow [m³/s]", 1.0, 500.0, 70.0, 5.0)
            ac_rows = st.number_input("Rows", 1, 12, 4, 1)
            ac_tpr = st.number_input("Tubes / row", 4, 200, 40, 2)
        with a3:
            ac_length = st.number_input("Tube length [m]", 1.0, 20.0, 8.0, 0.5)
            ac_fins = st.number_input("Fins / m", 50.0, 800.0, 394.0, 10.0)
            ac_fin_od = st.number_input("Fin OD [mm]", 30.0, 120.0, 57.0, 1.0)
            ac_fan_eff = st.slider("Fan efficiency", 0.30, 0.90, 0.65, 0.01)

        try:
            ac_result = simulate_air_cooled_hx(
                ServiceStream(
                    fluid=ac_fluid,
                    mass_flow_kg_s=float(ac_flow),
                    inlet_temperature_c=float(ac_tin),
                    pressure_bar=float(ac_pressure),
                ),
                process_outlet_target_c=float(ac_tout),
                air_inlet_temperature_c=float(ac_air_tin),
                geometry=AirCooledGeometry(
                    tube_length_m=float(ac_length),
                    tubes_per_row=int(ac_tpr),
                    rows=int(ac_rows),
                    fin_od_m=float(ac_fin_od)/1000.0,
                    fins_per_m=float(ac_fins),
                    air_flow_m3_s=float(ac_air_flow),
                    fan_efficiency=float(ac_fan_eff),
                ),
                package=thermo_package,
                interaction_parameters=interaction_parameters,
            )

            components.html(
                air_cooler_svg(int(ac_rows), int(ac_tpr), ac_result.fan_power_kw),
                height=340,
                scrolling=False,
            )

            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Duty", f"{ac_result.duty_kw/1000:.3f} MW")
            c2.metric("Fan power", f"{ac_result.fan_power_kw:.1f} kW")
            c3.metric("Required area", f"{ac_result.required_external_area_m2:.0f} m²")
            c4.metric("Area margin", f"{ac_result.area_margin_percent:.1f}%")

            st.dataframe(
                pd.DataFrame([{
                    "Process outlet [°C]": ac_result.process_outlet_c,
                    "Air outlet [°C]": ac_result.air_outlet_c,
                    "Process velocity [m/s]": ac_result.process_velocity_m_s,
                    "Process Re": ac_result.process_reynolds,
                    "Process h [W/m²K]": ac_result.process_h_w_m2k,
                    "Process ΔP [kPa]": ac_result.process_dp_kpa,
                    "Air face velocity [m/s]": ac_result.air_face_velocity_m_s,
                    "Air Re": ac_result.air_reynolds,
                    "Air h [W/m²K]": ac_result.air_h_w_m2k,
                    "Air ΔP [Pa]": ac_result.air_dp_pa,
                    "Fin efficiency": ac_result.fin_efficiency,
                    "Surface efficiency": ac_result.overall_surface_efficiency,
                    "U ext [W/m²K]": ac_result.overall_u_external_w_m2k,
                    "Installed area [m²]": ac_result.installed_external_area_m2,
                }]),
                use_container_width=True,
                hide_index=True,
            )
            for w in ac_result.warnings:
                st.warning(w)
        except Exception as exc:
            st.error(f"Air-cooled calculation failed: {exc}")

    else:
        st.markdown("#### Service selector")
        s1,s2,s3 = st.columns(3)
        with s1:
            sel_duty = st.number_input("Duty [kW]", 1.0, 50000.0, 1000.0, 100.0)
            sel_hot_p = st.number_input("Hot pressure [bar]", 0.1, 300.0, 5.0, 1.0)
            sel_cold_p = st.number_input("Cold pressure [bar]", 0.1, 300.0, 3.0, 1.0)
        with s2:
            sel_hot_mu = st.number_input("Hot viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_cold_mu = st.number_input("Cold viscosity [mPa·s]", 0.05, 1000.0, 1.0, 0.5)
            sel_phase = st.checkbox("Phase-change service")
        with s3:
            sel_fouling = st.checkbox("Solids / heavy fouling")
            sel_close = st.checkbox("Close temperature approach")
            sel_water = st.checkbox("Cooling water available", value=True)
            sel_compact = st.checkbox("Compactness is a priority")

        ranking = rank_exchangers(
            SelectionCase(
                duty_kw=float(sel_duty),
                hot_viscosity_mpa_s=float(sel_hot_mu),
                cold_viscosity_mpa_s=float(sel_cold_mu),
                hot_pressure_bar=float(sel_hot_p),
                cold_pressure_bar=float(sel_cold_p),
                phase_change=sel_phase,
                solids_or_heavy_fouling=sel_fouling,
                close_temperature_approach=sel_close,
                cooling_water_available=sel_water,
                compactness_priority=sel_compact,
            )
        )

        rank_df = pd.DataFrame([
            {
                "Rank": i+1,
                "Exchanger": c.exchanger_type,
                "Suitability score": c.score,
                "Reasons": "; ".join(c.reasons) or "General-purpose fit",
                "Cautions": "; ".join(c.cautions) or "—",
            }
            for i,c in enumerate(ranking)
        ])
        st.dataframe(rank_df, use_container_width=True, hide_index=True)

        st.info(
            f"Current P1 recommendation: **{ranking[0].exchanger_type}** "
            f"with screening score {ranking[0].score:.0f}/100."
        )

with tab_multi:
    if "multi_hx_v08_error" in st.session_state:
        st.error(st.session_state["multi_hx_v08_error"])

    multi_data = st.session_state.get("multi_hx_v08")

    if multi_data:
        r1, r2, r3, r4 = st.columns(4)

        r1.metric(
            "Integrated duty",
            f"{multi_data['total_duty_kw']/1000:.3f} MW",
        )
        r2.metric(
            "Required area",
            f"{multi_data['total_required_area_m2']:.1f} m²",
        )
        r3.metric(
            "Process ΔP",
            f"{multi_data['process_dp_kpa']:.1f} kPa",
        )
        r4.metric(
            "Utility outlet",
            f"{multi_data['utility_outlet_c']:.1f} °C",
        )

        svg = multicomponent_hx_svg(
            multi_data["segments"],
            multi_data["mode"],
            multi_data["tema_code"],
        )
        components.html(svg, height=350, scrolling=False)

        seg_df = pd.DataFrame(
            [
                {
                    "Seg": s["index"],
                    "Process in [°C]": s["process_in_c"],
                    "Process out [°C]": s["process_out_c"],
                    "Utility in [°C]": s["utility_in_c"],
                    "Utility out [°C]": s["utility_out_c"],
                    "β in": s["beta_in"],
                    "β out": s["beta_out"],
                    "Quality": s["mass_quality_mean"],
                    "Regime": s["regime"],
                    "Δh [kJ/kg]": abs(
                        s["enthalpy_in_kj_kg"]
                        - s["enthalpy_out_kj_kg"]
                    ),
                    "Duty [kW]": s["duty_kw"],
                    "h process": s["process_h_w_m2k"],
                    "h utility": s["utility_h_w_m2k"],
                    "U [W/m²K]": s["overall_u_w_m2k"],
                    "LMTD [°C]": s["lmtd_c"],
                    "Area [m²]": s["required_area_m2"],
                    "Process ΔP [kPa]": s["process_dp_kpa"],
                    "Utility ΔP [kPa]": s["utility_dp_kpa"],
                    "Correlation": s["correlation"],
                }
                for s in multi_data["segments"]
            ]
        )

        st.dataframe(
            seg_df.style.format(
                {
                    "Process in [°C]": "{:.1f}",
                    "Process out [°C]": "{:.1f}",
                    "Utility in [°C]": "{:.1f}",
                    "Utility out [°C]": "{:.1f}",
                    "β in": "{:.4f}",
                    "β out": "{:.4f}",
                    "Quality": "{:.4f}",
                    "Δh [kJ/kg]": "{:.2f}",
                    "Duty [kW]": "{:.2f}",
                    "h process": "{:.0f}",
                    "h utility": "{:.0f}",
                    "U [W/m²K]": "{:.0f}",
                    "LMTD [°C]": "{:.2f}",
                    "Area [m²]": "{:.2f}",
                    "Process ΔP [kPa]": "{:.3f}",
                    "Utility ΔP [kPa]": "{:.3f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Integrated profiles")

        p_df = pd.DataFrame(
            [
                {
                    "Segment": s["index"],
                    "Temperature [°C]": 0.5 * (
                        s["process_in_c"]
                        + s["process_out_c"]
                    ),
                    "Vapour fraction": s["beta_mean"],
                    "U [W/m²K]": s["overall_u_w_m2k"],
                    "Area [m²]": s["required_area_m2"],
                }
                for s in multi_data["segments"]
            ]
        )

        fig_beta = go.Figure()
        fig_beta.add_trace(
            go.Scatter(
                x=p_df["Temperature [°C]"],
                y=p_df["Vapour fraction"],
                mode="lines+markers",
                name="β",
            )
        )
        fig_beta.update_layout(
            template="plotly_dark",
            height=370,
            margin=dict(l=25, r=20, t=30, b=35),
            xaxis_title="Process temperature [°C]",
            yaxis_title="Vapour fraction β",
            yaxis_range=[-0.03, 1.03],
        )
        st.plotly_chart(fig_beta, use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "β inlet",
            f"{multi_data['inlet_vapour_fraction']:.4f}",
        )
        c2.metric(
            "β outlet",
            f"{multi_data['outlet_vapour_fraction']:.4f}",
        )
        c3.metric(
            "Area margin",
            f"{multi_data['area_margin_percent']:.1f}%",
        )
        c4.metric(
            "Utility ΔP",
            f"{multi_data['utility_dp_kpa']:.1f} kPa",
        )

        with st.expander("Segment phase compositions"):
            comp_rows = []

            for s in multi_data["segments"]:
                for name in multi_composition:
                    comp_rows.append(
                        {
                            "Segment": s["index"],
                            "Component": name,
                            "Liquid x": s["liquid_x_mean"].get(name, 0.0),
                            "Vapour y": s["vapour_y_mean"].get(name, 0.0),
                        }
                    )

            comp_df = pd.DataFrame(comp_rows)

            st.dataframe(
                comp_df.style.format(
                    {
                        "Liquid x": "{:.6f}",
                        "Vapour y": "{:.6f}",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        for warning in multi_data["warnings"]:
            st.warning(warning)

        multi_json = json.dumps(
            multi_data,
            indent=2,
        ).encode("utf-8")

        st.download_button(
            "↓ Download integrated multicomponent HX JSON",
            data=multi_json,
            file_name="HX-RACE_v08_multicomponent_HX.json",
            mime="application/json",
            use_container_width=True,
        )



with tab_mechanical:
    if mechanical_error:
        st.error(f"Mechanical screening could not run: {mechanical_error}")

    elif mechanical_result is not None:
        k1, k2, k3, k4 = st.columns(4)

        k1.metric(
            "Required shell t",
            f"{mechanical_result.required_shell_thickness_mm:.2f} mm",
        )
        k2.metric(
            "Suggested nominal",
            f"{mechanical_result.suggested_shell_nominal_mm:.1f} mm",
        )
        k3.metric(
            "Shell MAWP screen",
            f"{mechanical_result.shell_mawp_bar:.1f} bar",
        )
        k4.metric(
            "Tube wall margin",
            f"{mechanical_result.tube_wall_margin_mm:.2f} mm",
        )

        mech_svg = mechanical_cutaway_svg(
            mechanical_result.tema_code,
            mechanical_result.selected_shell_nominal_mm,
            mechanical_result.suggested_head_nominal_mm,
            mechanical_result.actual_tube_wall_mm,
            mechanical_result.shell_nozzle["selected_dn_mm"],
            mechanical_result.tube_nozzle["selected_dn_mm"],
        )
        components.html(mech_svg, height=350, scrolling=False)

        st.markdown("#### Pressure / thickness telemetry")

        pressure_df = pd.DataFrame(
            [
                {
                    "Item": "Shell",
                    "Allowable stress [MPa]": mechanical_result.shell_allowable_stress_mpa,
                    "Required t [mm]": mechanical_result.required_shell_thickness_mm,
                    "Suggested nominal [mm]": mechanical_result.suggested_shell_nominal_mm,
                    "Selected nominal [mm]": mechanical_result.selected_shell_nominal_mm,
                    "MAWP screen [bar]": mechanical_result.shell_mawp_bar,
                },
                {
                    "Item": "2:1 elliptical head",
                    "Allowable stress [MPa]": mechanical_result.shell_allowable_stress_mpa,
                    "Required t [mm]": mechanical_result.required_head_thickness_mm,
                    "Suggested nominal [mm]": mechanical_result.suggested_head_nominal_mm,
                    "Selected nominal [mm]": None,
                    "MAWP screen [bar]": None,
                },
                {
                    "Item": "Tube",
                    "Allowable stress [MPa]": mechanical_result.tube_allowable_stress_mpa,
                    "Required t [mm]": mechanical_result.required_tube_wall_mm,
                    "Suggested nominal [mm]": None,
                    "Selected nominal [mm]": mechanical_result.actual_tube_wall_mm,
                    "MAWP screen [bar]": None,
                },
            ]
        )

        st.dataframe(
            pressure_df.style.format(
                {
                    "Allowable stress [MPa]": "{:.1f}",
                    "Required t [mm]": "{:.2f}",
                    "Suggested nominal [mm]": lambda v: "—" if pd.isna(v) else f"{v:.1f}",
                    "Selected nominal [mm]": lambda v: "—" if pd.isna(v) else f"{v:.2f}",
                    "MAWP screen [bar]": lambda v: "—" if pd.isna(v) else f"{v:.1f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Nozzle sizing")

        noz_df = pd.DataFrame(
            [
                {
                    "Side": "Shell",
                    "Required ID [mm]": mechanical_result.shell_nozzle[
                        "required_inside_diameter_mm"
                    ],
                    "Selected DN": mechanical_result.shell_nozzle[
                        "selected_dn_mm"
                    ],
                    "Selected velocity [m/s]": mechanical_result.shell_nozzle[
                        "selected_velocity_m_s"
                    ],
                    "Target velocity [m/s]": mechanical_result.shell_nozzle[
                        "target_velocity_m_s"
                    ],
                },
                {
                    "Side": "Tube",
                    "Required ID [mm]": mechanical_result.tube_nozzle[
                        "required_inside_diameter_mm"
                    ],
                    "Selected DN": mechanical_result.tube_nozzle[
                        "selected_dn_mm"
                    ],
                    "Selected velocity [m/s]": mechanical_result.tube_nozzle[
                        "selected_velocity_m_s"
                    ],
                    "Target velocity [m/s]": mechanical_result.tube_nozzle[
                        "target_velocity_m_s"
                    ],
                },
            ]
        )
        st.dataframe(
            noz_df.style.format(
                {
                    "Required ID [mm]": "{:.1f}",
                    "Selected velocity [m/s]": "{:.2f}",
                    "Target velocity [m/s]": "{:.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### TEMA-style geometry checks")

        checks_df = pd.DataFrame(mechanical_result.geometry_checks)
        st.dataframe(
            checks_df,
            use_container_width=True,
            hide_index=True,
        )

        c1, c2 = st.columns(2)
        c1.metric(
            "Tube–shell design ΔP",
            f"{mechanical_result.differential_design_pressure_bar:.1f} bar",
        )
        c2.metric(
            "Shell pressure margin",
            f"{mechanical_result.shell_pressure_margin_bar:.1f} bar",
        )

        for warning in mechanical_result.warnings:
            st.warning(warning)

        with st.expander("Mechanical design items still requiring specialist/code calculation"):
            for note in mechanical_result.design_notes:
                st.write("• " + note)

        mech_json = json.dumps(
            mechanical_result.as_dict(),
            indent=2,
        ).encode("utf-8")

        st.download_button(
            "↓ Download mechanical screening JSON",
            data=mech_json,
            file_name=f"{tema_code}_HX-RACE_v010_mechanical.json",
            mime="application/json",
            use_container_width=True,
        )


with tab_phase:
    if phase_error:
        st.error(f"Phase-change simulation could not run: {phase_error}")

    elif phase_result is not None:
        k1, k2, k3, k4 = st.columns(4)

        k1.metric(
            "Saturation temperature",
            f"{phase_result.saturation_temperature_c:.2f} °C",
        )
        k2.metric(
            "Total duty",
            f"{phase_result.total_duty_kw/1000:.3f} MW",
        )
        k3.metric(
            "Latent duty",
            f"{phase_result.latent_duty_kw/1000:.3f} MW",
        )
        k4.metric(
            "Required area",
            f"{phase_result.total_required_area_m2:.1f} m²",
        )

        zsvg = phase_zone_svg(
            [z.as_dict() for z in phase_result.zones],
            phase_result.operation,
            phase_result.tema_code,
        )
        components.html(zsvg, height=340, scrolling=False)

        zone_df = pd.DataFrame(
            [
                {
                    "Zone": z.name,
                    "Phase": z.phase,
                    "Duty [kW]": z.duty_kw,
                    "Duty share [%]": 100.0 * z.duty_fraction,
                    "Process in [°C]": z.process_in_c,
                    "Process out [°C]": z.process_out_c,
                    "Utility in [°C]": z.utility_in_c,
                    "Utility out [°C]": z.utility_out_c,
                    "h process [W/m²K]": z.process_h_w_m2k,
                    "h utility [W/m²K]": z.utility_h_w_m2k,
                    "U [W/m²K]": z.overall_u_w_m2k,
                    "LMTD [°C]": z.lmtd_c,
                    "Area [m²]": z.required_area_m2,
                    "Correlation": z.correlation,
                }
                for z in phase_result.zones
            ]
        )

        st.dataframe(
            zone_df.style.format(
                {
                    "Duty [kW]": "{:.1f}",
                    "Duty share [%]": "{:.1f}",
                    "Process in [°C]": "{:.1f}",
                    "Process out [°C]": "{:.1f}",
                    "Utility in [°C]": "{:.1f}",
                    "Utility out [°C]": "{:.1f}",
                    "h process [W/m²K]": "{:.0f}",
                    "h utility [W/m²K]": "{:.0f}",
                    "U [W/m²K]": "{:.0f}",
                    "LMTD [°C]": "{:.1f}",
                    "Area [m²]": "{:.1f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        p1, p2, p3, p4 = st.columns(4)

        p1.metric(
            "Latent heat",
            f"{phase_result.latent_heat_kj_kg:.1f} kJ/kg",
        )
        p2.metric(
            "Utility outlet",
            f"{phase_result.utility_outlet_c:.1f} °C",
        )
        p3.metric(
            "Area margin",
            f"{phase_result.area_margin_percent:.1f}%",
        )

        if phase_result.two_phase_pressure_drop_kpa is None:
            p4.metric("2φ process ΔP", "N/A")
        else:
            p4.metric(
                "2φ process ΔP",
                f"{phase_result.two_phase_pressure_drop_kpa:.1f} kPa",
            )

        with st.expander("Phase-change engineering notes"):
            st.write(
                f"Single-phase process ΔP: "
                f"{phase_result.process_pressure_drop_kpa:.2f} kPa"
            )
            st.write(
                f"Utility ΔP: "
                f"{phase_result.utility_pressure_drop_kpa:.2f} kPa"
            )
            if phase_result.two_phase_multiplier is not None:
                st.write(
                    f"Lockhart–Martinelli multiplier: "
                    f"{phase_result.two_phase_multiplier:.3f}"
                )

            for note in phase_result.warnings:
                st.warning(note)

        phase_json = json.dumps(
            phase_result.as_dict(),
            indent=2,
        ).encode("utf-8")

        st.download_button(
            "↓ Download phase-change calculation JSON",
            data=phase_json,
            file_name=(
                f"{phase_result.tema_code}_"
                f"{phase_result.operation}_HX-RACE_v06.json"
            ),
            mime="application/json",
            use_container_width=True,
        )

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

    validation_report = validate_shell_and_tube(
        sim_input,
        result,
        mechanical_result,
    )

    benchmark_results = run_benchmark_suite()
    calculation_trace = build_calculation_trace(sim_input, result)
    assumptions_register = build_assumptions_register(sim_input, result)

    report_payload = build_report_payload(
        sim_input=sim_input,
        result=result,
        validation=validation_report,
        benchmarks=benchmark_results,
        assumptions=assumptions_register,
        calculation_trace=calculation_trace,
        mechanical_result=mechanical_result,
        optimizer_report=st.session_state.get("hx_opt_report"),
        extra_results={
            "flash": st.session_state.get("flash_v07_result"),
            "multicomponent_hx": st.session_state.get("multi_hx_v08"),
        },
    )

    engineering_pdf = build_engineering_report_pdf(report_payload)
    technical_pack_zip = build_technical_pack_zip(report_payload)

    with tab_validation:
        st.markdown("### Validation + Model Readiness")

        st.markdown(
            readiness_gauge_html(
                validation_report.readiness_score,
                validation_report.readiness_label,
            ),
            unsafe_allow_html=True,
        )

        v1, v2, v3, v4 = st.columns(4)

        v1.metric(
            "Energy residual",
            f"{validation_report.energy_balance_residual_percent:.6f}%",
        )
        v2.metric(
            "UA/area residual",
            f"{validation_report.area_closure_residual_percent:.6f}%",
        )
        v3.metric(
            "Checks requiring review",
            str(validation_report.review_checks),
        )
        v4.metric(
            "Failed checks",
            str(validation_report.failed_checks),
        )

        validation_df = pd.DataFrame(
            [item.as_dict() for item in validation_report.items]
        )

        st.dataframe(
            validation_df[
                [
                    "category",
                    "check",
                    "status",
                    "value",
                    "criterion",
                    "note",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Analytical regression benchmarks")

        benchmark_df = pd.DataFrame(
            [x.as_dict() for x in benchmark_results]
        )

        st.dataframe(
            benchmark_df.style.format(
                {
                    "calculated": "{:.8g}",
                    "expected": "{:.8g}",
                    "relative_error_percent": "{:.3e}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        bench_pass = sum(
            1 for x in benchmark_results if x.status == "PASS"
        )

        st.caption(
            f"{bench_pass}/{len(benchmark_results)} internal analytical benchmarks pass. "
            "These are regression/implementation checks, not external experimental validation."
        )

        st.markdown("#### Calculation trace")

        st.dataframe(
            pd.DataFrame(calculation_trace),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Assumptions and limitations register"):
            st.dataframe(
                pd.DataFrame(assumptions_register),
                use_container_width=True,
                hide_index=True,
            )

            for limitation in validation_report.limitations:
                st.warning(limitation)

        dlv1, dlv2 = st.columns(2)

        with dlv1:
            st.download_button(
                "↓ Download engineering PDF",
                data=engineering_pdf,
                file_name=f"{result.tema_code}_HX-RACE_Engineering_Report_v0.11.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with dlv2:
            st.download_button(
                "↓ Download complete technical ZIP",
                data=technical_pack_zip,
                file_name=f"{result.tema_code}_HX-RACE_Technical_Pack_v0.11.zip",
                mime="application/zip",
                use_container_width=True,
            )

        st.info(
            "The readiness score measures internal consistency, completeness and "
            "constraint compliance. It is not an uncertainty estimate or engineering approval."
        )

    with tab_export:
        st.markdown("### Technical Pack — v0.11")

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

        st.markdown("#### Professional pack")

        p1, p2 = st.columns(2)

        with p1:
            st.download_button(
                "↓ Engineering report PDF",
                data=engineering_pdf,
                file_name=f"{result.tema_code}_HX-RACE_Engineering_Report_v0.11.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with p2:
            st.download_button(
                "↓ Full technical pack ZIP",
                data=technical_pack_zip,
                file_name=f"{result.tema_code}_HX-RACE_Technical_Pack_v0.11.zip",
                mime="application/zip",
                use_container_width=True,
            )

        st.caption(
            "The ZIP includes the PDF report, JSON archive, validation CSV, "
            "benchmark CSV, assumptions register, calculation trace and a "
            "TEMA-aligned preliminary specification CSV."
        )

        st.warning(
            "These downloads are engineering-simulation records only. "
            "Formal TEMA/ASME certification requires the applicable manufacturer, "
            "code calculations, review, approval, and documentation."
        )


st.caption(
    "HX//RACE v0.11 · Validation + Professional Technical Pack · "
    "Development-stage Bell–Delaware screening model"
)
