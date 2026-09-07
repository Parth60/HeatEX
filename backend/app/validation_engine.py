from __future__ import annotations

from dataclasses import dataclass, asdict
import math


@dataclass
class ValidationItem:
    category: str
    check: str
    status: str
    value: str
    criterion: str
    weight: float
    points: float
    note: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    readiness_score: float
    readiness_label: str
    energy_balance_residual_percent: float
    area_closure_residual_percent: float
    installed_area_residual_percent: float
    passed_checks: int
    review_checks: int
    failed_checks: int
    items: list[ValidationItem]
    limitations: list[str]

    def as_dict(self) -> dict:
        return {
            "readiness_score": self.readiness_score,
            "readiness_label": self.readiness_label,
            "energy_balance_residual_percent": self.energy_balance_residual_percent,
            "area_closure_residual_percent": self.area_closure_residual_percent,
            "installed_area_residual_percent": self.installed_area_residual_percent,
            "passed_checks": self.passed_checks,
            "review_checks": self.review_checks,
            "failed_checks": self.failed_checks,
            "items": [x.as_dict() for x in self.items],
            "limitations": self.limitations,
        }


def _score_status(status: str, weight: float) -> float:
    s = status.upper()
    if s == "PASS":
        return weight
    if s in {"INFO", "ACCEPT"}:
        return weight
    if s == "REVIEW":
        return 0.50 * weight
    return 0.0


def _add(
    items: list[ValidationItem],
    category: str,
    check: str,
    status: str,
    value: str,
    criterion: str,
    weight: float,
    note: str,
):
    items.append(
        ValidationItem(
            category=category,
            check=check,
            status=status,
            value=value,
            criterion=criterion,
            weight=weight,
            points=_score_status(status, weight),
            note=note,
        )
    )


def validate_shell_and_tube(
    sim_input,
    result,
    mechanical_result=None,
) -> ValidationReport:
    items: list[ValidationItem] = []

    # ---------------------------------------------------------
    # 1. Energy balance closure
    # ---------------------------------------------------------
    hot_h_in = result.hot_in_thermo["specific_enthalpy_j_kg"]
    hot_h_out = result.hot_out_thermo["specific_enthalpy_j_kg"]
    cold_h_in = result.cold_in_thermo["specific_enthalpy_j_kg"]
    cold_h_out = result.cold_out_thermo["specific_enthalpy_j_kg"]

    q_hot = sim_input.hot.mass_flow_kg_s * (hot_h_in - hot_h_out)
    q_cold = sim_input.cold.mass_flow_kg_s * (cold_h_out - cold_h_in)

    energy_residual = (
        abs(q_hot - q_cold)
        / max(abs(q_hot), abs(q_cold), 1e-12)
        * 100.0
    )

    if energy_residual <= 0.01:
        status = "PASS"
    elif energy_residual <= 0.10:
        status = "REVIEW"
    else:
        status = "FAIL"

    _add(
        items,
        "Balance",
        "Enthalpy energy closure",
        status,
        f"{energy_residual:.6f}%",
        "<= 0.01% preferred; <= 0.10% review",
        16.0,
        "Compares hot-side enthalpy loss with cold-side enthalpy gain.",
    )

    # ---------------------------------------------------------
    # 2. UA / area closure
    # ---------------------------------------------------------
    q_from_area = (
        result.required_area_m2
        * result.overall_u_w_m2k
        * result.lmtd_c
        * result.correction_factor
    )

    area_closure = (
        abs(q_from_area - result.duty_kw * 1000.0)
        / max(result.duty_kw * 1000.0, 1e-12)
        * 100.0
    )

    if area_closure <= 0.01:
        status = "PASS"
    elif area_closure <= 0.10:
        status = "REVIEW"
    else:
        status = "FAIL"

    _add(
        items,
        "Thermal",
        "Q = U A F LMTD closure",
        status,
        f"{area_closure:.6f}%",
        "<= 0.01% preferred",
        14.0,
        "Checks consistency between stored duty, U, required area, LMTD and F.",
    )

    # ---------------------------------------------------------
    # 3. Installed area identity
    # ---------------------------------------------------------
    g = sim_input.geometry
    expected_installed = (
        math.pi * g.tube_od_m * g.tube_length_m * g.tube_count
    )

    installed_area_residual = (
        abs(expected_installed - result.installed_area_m2)
        / max(result.installed_area_m2, 1e-12)
        * 100.0
    )

    _add(
        items,
        "Geometry",
        "Installed tube area identity",
        "PASS" if installed_area_residual <= 1e-8 else "FAIL",
        f"{installed_area_residual:.8f}%",
        "pi Do L Nt must reproduce installed area",
        8.0,
        "Detects geometry/data-path inconsistencies.",
    )

    # ---------------------------------------------------------
    # 4. Temperature driving force
    # ---------------------------------------------------------
    _add(
        items,
        "Thermal",
        "Positive LMTD",
        "PASS" if result.lmtd_c > 0 else "FAIL",
        f"{result.lmtd_c:.3f} C",
        "LMTD > 0",
        6.0,
        "A non-positive LMTD makes the specified thermal service infeasible.",
    )

    f_status = "PASS" if result.correction_factor >= 0.75 else "REVIEW"
    _add(
        items,
        "Thermal",
        "LMTD correction factor",
        f_status,
        f"{result.correction_factor:.3f}",
        "HX-RACE design caution when F < 0.75",
        5.0,
        "This is a design screening threshold, not a code requirement.",
    )

    # ---------------------------------------------------------
    # 5. Tube-side correlation coverage
    # ---------------------------------------------------------
    re_t = result.tube_reynolds
    if re_t >= 10000:
        tube_regime = "PASS"
        tube_note = "Turbulent tube-side correlation is in its preferred screening regime."
    elif re_t < 2300:
        tube_regime = "PASS"
        tube_note = "Laminar fallback correlation is being used."
    else:
        tube_regime = "REVIEW"
        tube_note = "Transitional flow is less reliably represented by simple correlations."

    _add(
        items,
        "Correlation validity",
        "Tube-side Reynolds regime",
        tube_regime,
        f"Re = {re_t:,.0f}",
        "Laminar <2300; turbulent >=10000 preferred; transition requires review",
        8.0,
        tube_note,
    )

    pr_t = result.tube_prandtl
    _add(
        items,
        "Correlation validity",
        "Tube-side Prandtl plausibility",
        "PASS" if 0.1 <= pr_t <= 1000 else "REVIEW",
        f"Pr = {pr_t:.3f}",
        "0.1 <= Pr <= 1000 screening window",
        3.0,
        "Broad numerical sanity screen rather than a correlation certification range.",
    )

    # ---------------------------------------------------------
    # 6. Shell-side coverage
    # ---------------------------------------------------------
    re_s = result.shell_reynolds
    _add(
        items,
        "Correlation validity",
        "Shell-side Reynolds plausibility",
        "PASS" if re_s >= 100 else "REVIEW",
        f"Re = {re_s:,.0f}",
        "Re >= 100 preferred for current screening implementation",
        6.0,
        "Low shell-side Reynolds numbers increase sensitivity to geometry and laminar corrections.",
    )

    correction_factors = [
        result.j_c,
        result.j_l,
        result.j_b,
        result.j_r,
        result.j_s,
    ]
    correction_ok = all(0 < x <= 1.5 for x in correction_factors)

    _add(
        items,
        "Correlation validity",
        "Bell-Delaware correction-factor sanity",
        "PASS" if correction_ok else "REVIEW",
        (
            f"Jc={result.j_c:.3f}, Jl={result.j_l:.3f}, "
            f"Jb={result.j_b:.3f}, Jr={result.j_r:.3f}, Js={result.j_s:.3f}"
        ),
        "All correction factors finite, positive and <= 1.5",
        5.0,
        "A numerical sanity screen; final Bell-Delaware validation needs benchmark cases.",
    )

    # ---------------------------------------------------------
    # 7. Hydraulics
    # ---------------------------------------------------------
    tube_dp_ok = result.tube_dp_kpa <= sim_input.allowable_tube_dp_kpa
    shell_dp_ok = result.shell_dp_kpa <= sim_input.allowable_shell_dp_kpa

    _add(
        items,
        "Hydraulics",
        "Tube pressure-drop constraint",
        "PASS" if tube_dp_ok else "FAIL",
        f"{result.tube_dp_kpa:.2f} / {sim_input.allowable_tube_dp_kpa:.2f} kPa",
        "Calculated <= allowable",
        6.0,
        "Direct design constraint.",
    )

    _add(
        items,
        "Hydraulics",
        "Shell pressure-drop constraint",
        "PASS" if shell_dp_ok else "FAIL",
        f"{result.shell_dp_kpa:.2f} / {sim_input.allowable_shell_dp_kpa:.2f} kPa",
        "Calculated <= allowable",
        6.0,
        "Direct design constraint.",
    )

    v = result.tube_velocity_m_s
    velocity_status = "PASS" if 0.5 <= v <= 3.0 else "REVIEW"
    _add(
        items,
        "Hydraulics",
        "Tube velocity screening",
        velocity_status,
        f"{v:.3f} m/s",
        "0.5-3.0 m/s HX-RACE screening window",
        4.0,
        "Actual acceptable velocity depends on material, fouling and erosion risk.",
    )

    # ---------------------------------------------------------
    # 8. Area margin
    # ---------------------------------------------------------
    margin = result.area_margin_percent
    if 5.0 <= margin <= 35.0:
        margin_status = "PASS"
    elif margin >= 0:
        margin_status = "REVIEW"
    else:
        margin_status = "FAIL"

    _add(
        items,
        "Design margin",
        "Installed area margin",
        margin_status,
        f"{margin:.2f}%",
        "5-35% preferred screening band",
        5.0,
        "Negative margin means the selected geometry is thermally undersized.",
    )

    # ---------------------------------------------------------
    # 9. Phase-model suitability
    # ---------------------------------------------------------
    _add(
        items,
        "Model suitability",
        "Single-phase model phase consistency",
        "REVIEW" if result.phase_change_flag else "PASS",
        "Phase boundary detected" if result.phase_change_flag else "No boundary change detected",
        "Use phase-change/multicomponent module when phase boundary is crossed",
        4.0,
        "Single-phase shell-and-tube rating should not be relied on through a phase transition.",
    )

    # ---------------------------------------------------------
    # 10. Mechanical layer
    # ---------------------------------------------------------
    if mechanical_result is not None:
        mech_dict = (
            mechanical_result.as_dict()
            if hasattr(mechanical_result, "as_dict")
            else mechanical_result
        )

        mech_warnings = mech_dict.get("warnings", [])
        checks = mech_dict.get("geometry_checks", [])
        review_count = sum(
            1 for c in checks if str(c.get("status", "")).upper() == "REVIEW"
        )

        mech_status = (
            "PASS" if not mech_warnings and review_count == 0 else "REVIEW"
        )

        _add(
            items,
            "Mechanical",
            "Mechanical screening status",
            mech_status,
            (
                f"{len(mech_warnings)} warnings; "
                f"{review_count} geometry checks requiring review"
            ),
            "No mechanical screening warning preferred",
            4.0,
            "Does not replace pressure-vessel code design.",
        )

    total_weight = sum(x.weight for x in items)
    total_points = sum(x.points for x in items)

    readiness_score = (
        100.0 * total_points / total_weight
        if total_weight > 0
        else 0.0
    )

    fail_count = sum(1 for x in items if x.status == "FAIL")
    review_count = sum(1 for x in items if x.status == "REVIEW")
    pass_count = sum(
        1 for x in items if x.status in {"PASS", "INFO", "ACCEPT"}
    )

    if fail_count > 0:
        readiness_label = "NOT READY - FAILED CHECKS"
    elif readiness_score >= 90 and review_count <= 2:
        readiness_label = "STRONG SCREENING READINESS"
    elif readiness_score >= 75:
        readiness_label = "SCREENING READY WITH REVIEWS"
    else:
        readiness_label = "REQUIRES ENGINEERING REVIEW"

    limitations = [
        (
            "The readiness score is an internal completeness/consistency score. "
            "It is not a statistical confidence interval, uncertainty estimate, "
            "code approval or vendor guarantee."
        ),
        (
            "Thermodynamic accuracy depends on the selected package and validated "
            "interaction/property data."
        ),
        (
            "Current Bell-Delaware, plate, air-cooler and multicomponent two-phase "
            "models require external benchmark validation before design-release use."
        ),
        (
            "Mechanical screening does not replace ASME/TEMA code calculations, "
            "fabricator design or professional engineering approval."
        ),
    ]

    return ValidationReport(
        readiness_score=readiness_score,
        readiness_label=readiness_label,
        energy_balance_residual_percent=energy_residual,
        area_closure_residual_percent=area_closure,
        installed_area_residual_percent=installed_area_residual,
        passed_checks=pass_count,
        review_checks=review_count,
        failed_checks=fail_count,
        items=items,
        limitations=limitations,
    )
