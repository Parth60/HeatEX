from __future__ import annotations

from io import BytesIO
import csv
import json
import zipfile
from datetime import datetime, timezone

from .engineering_report import build_engineering_report_pdf


def _geometry_dict(geometry) -> dict:
    if isinstance(geometry, dict):
        return dict(geometry)

    names = [
        "shell_id_m",
        "tube_od_m",
        "tube_id_m",
        "tube_length_m",
        "tube_count",
        "tube_passes",
        "tube_pitch_m",
        "tube_layout",
        "baffle_count",
        "baffle_cut_fraction",
    ]

    return {
        name: getattr(geometry, name)
        for name in names
        if hasattr(geometry, name)
    }


def _specification_sheet(
    tema_code: str,
    sim_input,
    simulation: dict,
    geometry: dict,
    mechanical: dict | None,
) -> list[dict]:
    rows = []

    def add(section, field, value):
        rows.append(
            {
                "Section": section,
                "Field": field,
                "Value": value,
            }
        )

    add("Identification", "Configuration", tema_code)
    add("Identification", "Service", "Heat exchanger thermal/hydraulic screening")
    add("Thermal", "Duty", f"{simulation.get('duty_kw', 0):.2f} kW")
    add("Thermal", "Overall U", f"{simulation.get('overall_u_w_m2k', 0):.1f} W/m2-K")
    add("Thermal", "LMTD", f"{simulation.get('lmtd_c', 0):.2f} C")
    add("Thermal", "Correction factor F", f"{simulation.get('correction_factor', 0):.3f}")
    add("Thermal", "Required area", f"{simulation.get('required_area_m2', 0):.2f} m2")
    add("Thermal", "Installed area", f"{simulation.get('installed_area_m2', 0):.2f} m2")

    add("Geometry", "Shell ID", f"{geometry.get('shell_id_m', 0)*1000:.1f} mm")
    add("Geometry", "Tube OD", f"{geometry.get('tube_od_m', 0)*1000:.2f} mm")
    add("Geometry", "Tube ID", f"{geometry.get('tube_id_m', 0)*1000:.2f} mm")
    add("Geometry", "Tube length", f"{geometry.get('tube_length_m', 0):.2f} m")
    add("Geometry", "Tube count", str(geometry.get("tube_count", "-")))
    add("Geometry", "Tube passes", str(geometry.get("tube_passes", "-")))
    add("Geometry", "Tube pitch", f"{geometry.get('tube_pitch_m', 0)*1000:.2f} mm")
    add("Geometry", "Tube layout", str(geometry.get("tube_layout", "-")))
    add("Geometry", "Baffle count", str(geometry.get("baffle_count", "-")))
    add("Geometry", "Baffle cut", f"{geometry.get('baffle_cut_fraction', 0)*100:.1f}%")

    add("Hydraulics", "Tube dP", f"{simulation.get('tube_dp_kpa', 0):.2f} kPa")
    add("Hydraulics", "Shell dP", f"{simulation.get('shell_dp_kpa', 0):.2f} kPa")
    add("Hydraulics", "Tube velocity", f"{simulation.get('tube_velocity_m_s', 0):.3f} m/s")

    add("Thermodynamics", "Property package", str(sim_input.thermo_package))
    add("Thermodynamics", "Hot property source", str(simulation.get("hot_property_source", "-")))
    add("Thermodynamics", "Cold property source", str(simulation.get("cold_property_source", "-")))

    if mechanical:
        add("Mechanical", "TEMA class basis", str(mechanical.get("tema_class", "-")))
        add("Mechanical", "Required shell thickness", f"{mechanical.get('required_shell_thickness_mm', 0):.2f} mm")
        add("Mechanical", "Selected shell thickness", f"{mechanical.get('selected_shell_nominal_mm', 0):.2f} mm")
        add("Mechanical", "Shell MAWP screen", f"{mechanical.get('shell_mawp_bar', 0):.2f} bar")
        add("Mechanical", "Shell nozzle", f"DN{mechanical.get('shell_nozzle', {}).get('selected_dn_mm', '-')}")
        add("Mechanical", "Tube nozzle", f"DN{mechanical.get('tube_nozzle', {}).get('selected_dn_mm', '-')}")

    add(
        "Status",
        "Certification",
        "Preliminary / TEMA-aligned wording only - NOT TEMA Certified and NOT ASME stamped",
    )

    return rows


def build_report_payload(
    sim_input,
    result,
    validation,
    benchmarks,
    assumptions,
    calculation_trace,
    mechanical_result=None,
    optimizer_report=None,
    extra_results=None,
) -> dict:
    simulation = (
        result.as_dict()
        if hasattr(result, "as_dict")
        else dict(result)
    )
    geometry = _geometry_dict(sim_input.geometry)

    mechanical = None
    if mechanical_result is not None:
        mechanical = (
            mechanical_result.as_dict()
            if hasattr(mechanical_result, "as_dict")
            else dict(mechanical_result)
        )

    val_dict = (
        validation.as_dict()
        if hasattr(validation, "as_dict")
        else dict(validation)
    )

    benchmark_dicts = [
        x.as_dict() if hasattr(x, "as_dict") else dict(x)
        for x in benchmarks
    ]

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "report_version": "v0.11",
        "status": (
            "Preliminary engineering screening output. "
            "Not TEMA certification, ASME code stamping or fabrication approval."
        ),
        "tema_code": simulation.get("tema_code", "HX"),
        "thermo_package": sim_input.thermo_package,
        "simulation": simulation,
        "geometry": geometry,
        "validation": val_dict,
        "benchmarks": benchmark_dicts,
        "assumptions": assumptions,
        "calculation_trace": calculation_trace,
        "mechanical": mechanical,
        "optimizer": optimizer_report,
        "extra_results": extra_results or {},
    }

    payload["specification_sheet"] = _specification_sheet(
        payload["tema_code"],
        sim_input,
        simulation,
        geometry,
        mechanical,
    )

    return payload


def _csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""

    out = BytesIO()
    text = ""

    headers = list(rows[0].keys())
    string_io = __import__("io").StringIO()

    writer = csv.DictWriter(string_io, fieldnames=headers)
    writer.writeheader()

    for row in rows:
        writer.writerow(row)

    return string_io.getvalue().encode("utf-8")


def build_technical_pack_zip(payload: dict) -> bytes:
    pdf_bytes = build_engineering_report_pdf(payload)

    validation_rows = payload.get("validation", {}).get("items", [])
    benchmark_rows = payload.get("benchmarks", [])
    assumption_rows = payload.get("assumptions", [])
    trace_rows = payload.get("calculation_trace", [])
    spec_rows = payload.get("specification_sheet", [])

    tema = payload.get("tema_code", "HX")

    buffer = BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as z:
        z.writestr(
            f"{tema}_HX-RACE_Engineering_Report_v0.11.pdf",
            pdf_bytes,
        )
        z.writestr(
            f"{tema}_HX-RACE_Design_Data_v0.11.json",
            json.dumps(payload, indent=2, default=str).encode("utf-8"),
        )
        z.writestr(
            f"{tema}_HX-RACE_Validation.csv",
            _csv_bytes(validation_rows),
        )
        z.writestr(
            f"{tema}_HX-RACE_Benchmarks.csv",
            _csv_bytes(benchmark_rows),
        )
        z.writestr(
            f"{tema}_HX-RACE_Assumptions.csv",
            _csv_bytes(assumption_rows),
        )
        z.writestr(
            f"{tema}_HX-RACE_Calculation_Trace.csv",
            _csv_bytes(trace_rows),
        )
        z.writestr(
            f"{tema}_HX-RACE_TEMA_Aligned_Preliminary_Specification.csv",
            _csv_bytes(spec_rows),
        )
        z.writestr(
            "README_FIRST.txt",
            (
                "HX//RACE v0.11 TECHNICAL PACK\n\n"
                "This pack contains preliminary engineering calculations and "
                "validation records.\n\n"
                "It is NOT TEMA certification, NOT an official TEMA specification "
                "form, NOT ASME code stamping, and NOT fabrication approval.\n\n"
                "Complete code, vendor, mechanical and professional engineering "
                "review before design release.\n"
            ).encode("utf-8"),
        )

    return buffer.getvalue()
