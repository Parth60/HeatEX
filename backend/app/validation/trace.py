from __future__ import annotations


def build_calculation_trace(sim_input, result) -> list[dict]:
    g = sim_input.geometry

    hot_h_in = result.hot_in_thermo["specific_enthalpy_j_kg"]
    hot_h_out = result.hot_out_thermo["specific_enthalpy_j_kg"]
    cold_h_in = result.cold_in_thermo["specific_enthalpy_j_kg"]
    cold_h_out = result.cold_out_thermo["specific_enthalpy_j_kg"]

    q_hot = sim_input.hot.mass_flow_kg_s * (hot_h_in - hot_h_out)
    q_cold = sim_input.cold.mass_flow_kg_s * (cold_h_out - cold_h_in)

    installed_area = (
        3.141592653589793
        * g.tube_od_m
        * g.tube_length_m
        * g.tube_count
    )

    return [
        {
            "Step": 1,
            "Calculation": "Hot-side duty",
            "Equation": "Qh = mh (hin - hout)",
            "Result": f"{q_hot/1000.0:.3f} kW",
            "Purpose": "Primary enthalpy duty",
        },
        {
            "Step": 2,
            "Calculation": "Cold-side duty",
            "Equation": "Qc = mc (hout - hin)",
            "Result": f"{q_cold/1000.0:.3f} kW",
            "Purpose": "Energy-balance closure",
        },
        {
            "Step": 3,
            "Calculation": "LMTD",
            "Equation": "LMTD = (DT1-DT2)/ln(DT1/DT2)",
            "Result": f"{result.lmtd_c:.3f} C",
            "Purpose": "Mean thermal driving force",
        },
        {
            "Step": 4,
            "Calculation": "Corrected driving force",
            "Equation": "DTeff = F x LMTD",
            "Result": f"{result.effective_delta_t_c:.3f} C",
            "Purpose": "Shell/pass correction",
        },
        {
            "Step": 5,
            "Calculation": "Overall U",
            "Equation": "1/Uo = sum(thermal resistances)",
            "Result": f"{result.overall_u_w_m2k:.2f} W/m2-K",
            "Purpose": "Combined film/wall/fouling resistance",
        },
        {
            "Step": 6,
            "Calculation": "Required area",
            "Equation": "Areq = Q/(U F LMTD)",
            "Result": f"{result.required_area_m2:.3f} m2",
            "Purpose": "Thermal sizing",
        },
        {
            "Step": 7,
            "Calculation": "Installed area",
            "Equation": "Ainst = pi Do L Nt",
            "Result": f"{installed_area:.3f} m2",
            "Purpose": "Geometry closure",
        },
        {
            "Step": 8,
            "Calculation": "Tube Reynolds",
            "Equation": "Re = rho v D/mu",
            "Result": f"{result.tube_reynolds:.0f}",
            "Purpose": "Tube-side regime/correlation",
        },
        {
            "Step": 9,
            "Calculation": "Tube pressure drop",
            "Equation": "Darcy + local-loss screening",
            "Result": f"{result.tube_dp_kpa:.3f} kPa",
            "Purpose": "Hydraulic constraint",
        },
        {
            "Step": 10,
            "Calculation": "Shell pressure drop",
            "Equation": "Bell-Delaware/Kern-style screening path",
            "Result": f"{result.shell_dp_kpa:.3f} kPa",
            "Purpose": "Hydraulic constraint",
        },
    ]
