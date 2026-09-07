from __future__ import annotations

from io import BytesIO
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)


def _safe(value, fmt=None):
    if value is None:
        return "-"
    if fmt is not None:
        try:
            return fmt.format(value)
        except Exception:
            pass
    return str(value)


def _table(data, col_widths=None, header=True, font_size=8):
    """
    Build a wrapping ReportLab table.

    Strings are converted to Paragraphs so long engineering notes wrap inside
    cells instead of overflowing into neighbouring columns.
    """
    body_style = ParagraphStyle(
        "HXTableBody",
        fontName="Helvetica",
        fontSize=font_size,
        leading=max(font_size + 1.5, font_size * 1.22),
        textColor=colors.HexColor("#111111"),
        spaceAfter=0,
        spaceBefore=0,
    )
    head_style = ParagraphStyle(
        "HXTableHead",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    wrapped = []

    for r_idx, row in enumerate(data):
        current = []

        for cell in row:
            value = "-" if cell is None else str(cell)
            value = escape(value).replace("\n", "<br/>")
            style_for_cell = head_style if header and r_idx == 0 else body_style
            current.append(Paragraph(value, style_for_cell))

        wrapped.append(current)

    table = Table(
        wrapped,
        colWidths=col_widths,
        repeatRows=1 if header else 0,
        splitByRow=1,
    )

    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB2BD")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EDF2")),
        ]

    table.setStyle(TableStyle(style))
    return table


def _header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4

    canvas.setStrokeColor(colors.HexColor("#333333"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(
        18 * mm,
        9 * mm,
        "HX//RACE - Preliminary Engineering Report - Not for fabrication or certification",
    )
    canvas.drawRightString(
        width - 18 * mm,
        9 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def build_engineering_report_pdf(payload: dict) -> bytes:
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"HX-RACE {payload.get('tema_code', 'HX')} Engineering Report",
        author="HX//RACE",
    )

    styles = getSampleStyleSheet()

    title = ParagraphStyle(
        "HXTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=27,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111111"),
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "HXSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=14,
    )
    h1 = ParagraphStyle(
        "HXH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#111111"),
        spaceBefore=8,
        spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "HXH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#222222"),
        spaceBefore=6,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "HXBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        spaceAfter=6,
    )
    caution = ParagraphStyle(
        "HXCaution",
        parent=body,
        backColor=colors.HexColor("#FFF4D6"),
        borderColor=colors.HexColor("#D6A800"),
        borderWidth=0.6,
        borderPadding=7,
        spaceBefore=6,
        spaceAfter=10,
    )

    story = []

    tema = payload.get("tema_code", "HX")
    generated = payload.get(
        "generated_utc",
        datetime.now(timezone.utc).isoformat(),
    )

    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph("HX//RACE", title))
    story.append(
        Paragraph(
            f"{tema} - Engineering Calculation and Validation Report",
            ParagraphStyle(
                "HXSubTitleLarge",
                parent=subtitle,
                fontSize=14,
                leading=18,
                textColor=colors.HexColor("#222222"),
            ),
        )
    )
    story.append(
        Paragraph(
            "Thermal / Hydraulic / Thermodynamic / Mechanical Screening",
            subtitle,
        )
    )
    story.append(Spacer(1, 6 * mm))

    cover_data = [
        ["Field", "Value"],
        ["TEMA configuration", tema],
        ["Report version", "v0.11"],
        ["Generated", generated],
        ["Thermodynamic package", payload.get("thermo_package", "-")],
        ["Readiness status", payload.get("validation", {}).get("readiness_label", "-")],
        [
            "Internal readiness score",
            f"{payload.get('validation', {}).get('readiness_score', 0.0):.1f}/100",
        ],
    ]
    story.append(_table(cover_data, [55 * mm, 115 * mm]))
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "<b>IMPORTANT:</b> This document is a preliminary engineering report "
            "generated by HX//RACE. It is not TEMA certification, ASME code stamping, "
            "a fabrication drawing, a vendor guarantee, or professional engineering approval.",
            caution,
        )
    )
    story.append(PageBreak())

    # ---------------------------------------------------------
    # Executive summary
    # ---------------------------------------------------------
    story.append(Paragraph("1. Executive Summary", h1))

    sim = payload.get("simulation", {})
    summary = [
        ["Parameter", "Value"],
        ["Heat duty", f"{sim.get('duty_kw', 0):,.2f} kW"],
        ["Hot outlet", f"{sim.get('hot_outlet_c', 0):.2f} C"],
        ["Cold outlet", f"{sim.get('cold_outlet_c', 0):.2f} C"],
        ["Overall U", f"{sim.get('overall_u_w_m2k', 0):,.1f} W/m2-K"],
        ["Required area", f"{sim.get('required_area_m2', 0):,.2f} m2"],
        ["Installed area", f"{sim.get('installed_area_m2', 0):,.2f} m2"],
        ["Area margin", f"{sim.get('area_margin_percent', 0):,.2f}%"],
        ["Tube dP", f"{sim.get('tube_dp_kpa', 0):,.2f} kPa"],
        ["Shell dP", f"{sim.get('shell_dp_kpa', 0):,.2f} kPa"],
    ]
    story.append(_table(summary, [70 * mm, 100 * mm]))
    story.append(Spacer(1, 4 * mm))

    validation = payload.get("validation", {})
    story.append(
        Paragraph(
            (
                f"The internal validation layer reports "
                f"<b>{validation.get('readiness_label', '-')}</b> with a readiness "
                f"score of <b>{validation.get('readiness_score', 0):.1f}/100</b>. "
                "This score measures model consistency, constraint compliance and "
                "calculation completeness; it is not an uncertainty or accuracy guarantee."
            ),
            body,
        )
    )

    # ---------------------------------------------------------
    # Design basis
    # ---------------------------------------------------------
    story.append(Paragraph("2. Design Basis", h1))

    g = payload.get("geometry", {})
    design_basis = [
        ["Item", "Value"],
        ["TEMA configuration", tema],
        ["Shell ID", f"{g.get('shell_id_m', 0)*1000:.1f} mm"],
        ["Tube OD", f"{g.get('tube_od_m', 0)*1000:.2f} mm"],
        ["Tube ID", f"{g.get('tube_id_m', 0)*1000:.2f} mm"],
        ["Tube length", f"{g.get('tube_length_m', 0):.2f} m"],
        ["Tube count", str(g.get("tube_count", "-"))],
        ["Tube passes", str(g.get("tube_passes", "-"))],
        ["Tube pitch", f"{g.get('tube_pitch_m', 0)*1000:.2f} mm"],
        ["Tube layout", str(g.get("tube_layout", "-"))],
        ["Baffle count", str(g.get("baffle_count", "-"))],
        ["Baffle cut", f"{g.get('baffle_cut_fraction', 0)*100:.1f}%"],
    ]
    story.append(_table(design_basis, [70 * mm, 100 * mm]))

    # ---------------------------------------------------------
    # Thermodynamics
    # ---------------------------------------------------------
    story.append(Paragraph("3. Thermodynamic State Summary", h1))

    thermo_rows = [
        [
            "State",
            "T (C)",
            "P (bar)",
            "Phase",
            "Cp (J/kg-K)",
            "rho (kg/m3)",
            "mu (mPa-s)",
            "h (kJ/kg)",
        ]
    ]

    for label, key in [
        ("Hot inlet", "hot_in_thermo"),
        ("Hot outlet", "hot_out_thermo"),
        ("Cold inlet", "cold_in_thermo"),
        ("Cold outlet", "cold_out_thermo"),
    ]:
        s = sim.get(key, {})
        thermo_rows.append(
            [
                label,
                f"{s.get('temperature_c', 0):.2f}",
                f"{s.get('pressure_bar', 0):.2f}",
                str(s.get("phase", "-")),
                f"{s.get('cp_j_kgk', 0):.0f}",
                f"{s.get('density_kg_m3', 0):.2f}",
                f"{s.get('viscosity_pa_s', 0)*1000:.4f}",
                f"{s.get('specific_enthalpy_j_kg', 0)/1000:.2f}",
            ]
        )

    story.append(
        _table(
            thermo_rows,
            [
                23 * mm,
                17 * mm,
                17 * mm,
                27 * mm,
                23 * mm,
                23 * mm,
                23 * mm,
                25 * mm,
            ],
            font_size=7,
        )
    )

    # ---------------------------------------------------------
    # Thermal / hydraulic
    # ---------------------------------------------------------
    story.append(Paragraph("4. Thermal and Hydraulic Performance", h1))

    thermal_rows = [
        ["Parameter", "Value"],
        ["LMTD", f"{sim.get('lmtd_c', 0):.3f} C"],
        ["Correction factor F", f"{sim.get('correction_factor', 0):.4f}"],
        ["Tube h", f"{sim.get('tube_h_w_m2k', 0):,.1f} W/m2-K"],
        ["Shell h", f"{sim.get('shell_h_w_m2k', 0):,.1f} W/m2-K"],
        ["Overall U", f"{sim.get('overall_u_w_m2k', 0):,.1f} W/m2-K"],
        ["Tube Reynolds", f"{sim.get('tube_reynolds', 0):,.0f}"],
        ["Shell Reynolds", f"{sim.get('shell_reynolds', 0):,.0f}"],
        ["Tube velocity", f"{sim.get('tube_velocity_m_s', 0):.3f} m/s"],
        ["Tube pressure drop", f"{sim.get('tube_dp_kpa', 0):.3f} kPa"],
        ["Shell pressure drop", f"{sim.get('shell_dp_kpa', 0):.3f} kPa"],
    ]
    story.append(_table(thermal_rows, [75 * mm, 95 * mm]))

    # ---------------------------------------------------------
    # Mechanical
    # ---------------------------------------------------------
    mech = payload.get("mechanical")
    if mech:
        story.append(Paragraph("5. Mechanical Screening", h1))
        mech_rows = [
            ["Parameter", "Value"],
            ["TEMA class basis", str(mech.get("tema_class", "-"))],
            ["Required shell thickness", f"{mech.get('required_shell_thickness_mm', 0):.2f} mm"],
            ["Selected shell thickness", f"{mech.get('selected_shell_nominal_mm', 0):.2f} mm"],
            ["Shell MAWP screen", f"{mech.get('shell_mawp_bar', 0):.2f} bar"],
            ["Required head thickness", f"{mech.get('required_head_thickness_mm', 0):.2f} mm"],
            ["Required tube wall", f"{mech.get('required_tube_wall_mm', 0):.3f} mm"],
            ["Actual tube wall", f"{mech.get('actual_tube_wall_mm', 0):.3f} mm"],
            ["Shell nozzle", f"DN{mech.get('shell_nozzle', {}).get('selected_dn_mm', '-')}"],
            ["Tube nozzle", f"DN{mech.get('tube_nozzle', {}).get('selected_dn_mm', '-')}"],
        ]
        story.append(_table(mech_rows, [75 * mm, 95 * mm]))

        story.append(
            Paragraph(
                "Mechanical results are preliminary screening calculations only. "
                "Tubesheet, flange, nozzle reinforcement, external pressure, vibration, "
                "fatigue, MDMT, supports, hydrotest and other code calculations remain required.",
                caution,
            )
        )

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("6. Validation and Model Readiness", h1))

    val_summary = [
        ["Metric", "Value"],
        ["Readiness score", f"{validation.get('readiness_score', 0):.1f}/100"],
        ["Readiness label", str(validation.get("readiness_label", "-"))],
        ["Energy closure residual", f"{validation.get('energy_balance_residual_percent', 0):.6f}%"],
        ["UA/area closure residual", f"{validation.get('area_closure_residual_percent', 0):.6f}%"],
        ["Installed-area residual", f"{validation.get('installed_area_residual_percent', 0):.8f}%"],
        ["Passed checks", str(validation.get("passed_checks", 0))],
        ["Review checks", str(validation.get("review_checks", 0))],
        ["Failed checks", str(validation.get("failed_checks", 0))],
    ]
    story.append(_table(val_summary, [75 * mm, 95 * mm]))
    story.append(Spacer(1, 5 * mm))

    validation_rows = [["Category", "Check", "Status", "Value", "Criterion"]]
    for item in validation.get("items", []):
        validation_rows.append(
            [
                str(item.get("category", "")),
                str(item.get("check", "")),
                str(item.get("status", "")),
                str(item.get("value", "")),
                str(item.get("criterion", "")),
            ]
        )

    story.append(
        _table(
            validation_rows,
            [28 * mm, 48 * mm, 18 * mm, 33 * mm, 43 * mm],
            font_size=6.5,
        )
    )

    # ---------------------------------------------------------
    # Benchmarks
    # ---------------------------------------------------------
    story.append(Paragraph("7. Analytical Regression Benchmarks", h1))
    benchmark_rows = [
        ["Benchmark", "Status", "Calculated", "Expected", "Error (%)"]
    ]
    for b in payload.get("benchmarks", []):
        benchmark_rows.append(
            [
                str(b.get("name", "")),
                str(b.get("status", "")),
                f"{b.get('calculated', 0):.8g}",
                f"{b.get('expected', 0):.8g}",
                f"{b.get('relative_error_percent', 0):.3e}",
            ]
        )
    story.append(
        _table(
            benchmark_rows,
            [75 * mm, 18 * mm, 28 * mm, 28 * mm, 25 * mm],
            font_size=7,
        )
    )
    story.append(
        Paragraph(
            "These are internal analytical/regression checks. They verify implementation "
            "consistency but are not substitutes for external validation against experimental "
            "data, commercial process simulators, HTRI/HTFS/vendor software or published benchmark cases.",
            body,
        )
    )

    # ---------------------------------------------------------
    # Trace
    # ---------------------------------------------------------
    story.append(Paragraph("8. Calculation Trace", h1))
    trace_rows = [["Step", "Calculation", "Equation", "Result", "Purpose"]]
    for row in payload.get("calculation_trace", []):
        trace_rows.append(
            [
                str(row.get("Step", "")),
                str(row.get("Calculation", "")),
                str(row.get("Equation", "")),
                str(row.get("Result", "")),
                str(row.get("Purpose", "")),
            ]
        )
    story.append(
        _table(
            trace_rows,
            [12 * mm, 34 * mm, 49 * mm, 30 * mm, 45 * mm],
            font_size=6.5,
        )
    )

    # ---------------------------------------------------------
    # Assumptions
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("9. Assumptions and Limitations Register", h1))
    assumption_rows = [["ID", "Topic", "Assumption", "Impact", "Status"]]
    for row in payload.get("assumptions", []):
        assumption_rows.append(
            [
                str(row.get("ID", "")),
                str(row.get("Topic", "")),
                str(row.get("Assumption", "")),
                str(row.get("Impact", "")),
                str(row.get("Status", "")),
            ]
        )
    story.append(
        _table(
            assumption_rows,
            [14 * mm, 27 * mm, 58 * mm, 53 * mm, 20 * mm],
            font_size=6.5,
        )
    )

    # ---------------------------------------------------------
    # TEMA aligned spec sheet
    # ---------------------------------------------------------
    story.append(PageBreak())
    story.append(
        Paragraph(
            "10. TEMA-Aligned Preliminary Specification Sheet",
            h1,
        )
    )
    story.append(
        Paragraph(
            "The layout below is an HX//RACE preliminary specification summary "
            "using common exchanger-design fields. It is not an official TEMA form "
            "and must not be described as TEMA Certified.",
            caution,
        )
    )

    spec = payload.get("specification_sheet", [])
    spec_rows = [["Section", "Field", "Value"]]
    for row in spec:
        spec_rows.append(
            [
                str(row.get("Section", "")),
                str(row.get("Field", "")),
                str(row.get("Value", "")),
            ]
        )
    story.append(
        _table(
            spec_rows,
            [38 * mm, 65 * mm, 67 * mm],
            font_size=7,
        )
    )

    # ---------------------------------------------------------
    # Final release notes
    # ---------------------------------------------------------
    story.append(Paragraph("11. Required Follow-Up Before Design Release", h1))
    followups = [
        "Validate thermodynamic package and interaction parameters against trusted data.",
        "Benchmark shell-side heat transfer and pressure drop against published or trusted reference cases.",
        "Confirm tube-side correlation validity for the actual Reynolds/Prandtl regime.",
        "Complete full pressure-vessel mechanical calculations using the governing code and material tables.",
        "Perform tubesheet, flange, nozzle reinforcement, vibration and support design.",
        "Obtain vendor/fabricator review for proprietary exchanger geometries and construction details.",
        "Issue calculations through the applicable engineering review/approval process.",
    ]
    for item in followups:
        story.append(Paragraph(f"- {item}", body))

    story.append(
        Paragraph(
            "<b>Final status:</b> HX//RACE v0.11 produces a documented engineering "
            "screening package. It does not authorize fabrication, operation or code certification.",
            caution,
        )
    )

    doc.build(
        story,
        onFirstPage=_header_footer,
        onLaterPages=_header_footer,
    )

    return buffer.getvalue()
