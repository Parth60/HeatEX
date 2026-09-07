from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class MechanicalCheck:
    item: str
    status: str
    value: str
    criterion: str
    note: str

    def as_dict(self) -> dict:
        return asdict(self)


def run_tema_geometry_checks(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    tube_length_m: float,
    tube_passes: int,
    baffle_count: int,
    baffle_cut_fraction: float,
    shell_type: str,
    front_head: str,
    rear_head: str,
) -> list[MechanicalCheck]:
    if min(shell_id_m, tube_od_m, tube_pitch_m, tube_length_m) <= 0:
        raise ValueError("Geometry values must be positive.")

    checks: list[MechanicalCheck] = []

    pitch_ratio = tube_pitch_m / tube_od_m
    checks.append(
        MechanicalCheck(
            item="Tube pitch ratio",
            status="PASS" if pitch_ratio >= 1.25 else "REVIEW",
            value=f"{pitch_ratio:.3f} × OD",
            criterion="HX-RACE TEMA-style screen: pitch ≥ 1.25 × tube OD",
            note="Final layout must be checked against the applicable TEMA/vendor rules.",
        )
    )

    if baffle_count > 0:
        average_spacing_m = tube_length_m / (baffle_count + 1)
    else:
        average_spacing_m = tube_length_m

    minimum_spacing_m = max(0.20 * shell_id_m, 0.0508)
    maximum_spacing_m = shell_id_m

    spacing_ok = minimum_spacing_m <= average_spacing_m <= maximum_spacing_m

    checks.append(
        MechanicalCheck(
            item="Average baffle spacing",
            status="PASS" if spacing_ok else "REVIEW",
            value=f"{average_spacing_m*1000:.1f} mm",
            criterion=(
                f"Screening window {minimum_spacing_m*1000:.1f}–"
                f"{maximum_spacing_m*1000:.1f} mm"
            ),
            note="Vibration/support requirements may impose tighter limits.",
        )
    )

    cut_percent = 100.0 * baffle_cut_fraction
    cut_ok = 15.0 <= cut_percent <= 45.0

    checks.append(
        MechanicalCheck(
            item="Baffle cut",
            status="PASS" if cut_ok else "REVIEW",
            value=f"{cut_percent:.1f}%",
            criterion="HX-RACE screening range: 15–45% of shell diameter",
            note="Hydraulic optimisation may favour a narrower service-specific range.",
        )
    )

    pass_ok = tube_passes in {1, 2, 4, 6, 8}

    checks.append(
        MechanicalCheck(
            item="Tube passes",
            status="PASS" if pass_ok else "REVIEW",
            value=str(tube_passes),
            criterion="Common preliminary pass counts: 1, 2, 4, 6, 8",
            note="Pass partition geometry and nozzle arrangement require detailed design.",
        )
    )

    valid_front = front_head in {"A", "B", "C", "N", "D"}
    valid_shell = shell_type in {"E", "F", "G", "H", "J", "K", "X"}
    valid_rear = rear_head in {"L", "M", "N", "P", "S", "T", "U", "W"}

    checks.append(
        MechanicalCheck(
            item="TEMA nomenclature",
            status="PASS" if valid_front and valid_shell and valid_rear else "REVIEW",
            value=f"{front_head}{shell_type}{rear_head}",
            criterion="Valid HX-RACE TEMA-letter set",
            note="A valid three-letter code does not itself establish mechanical suitability.",
        )
    )

    if rear_head == "U":
        note = (
            "U-tube rear head selected: thermal expansion accommodation is favourable; "
            "tube-side mechanical cleaning is more limited."
        )
    elif rear_head in {"S", "T", "P", "W"}:
        note = (
            "Floating rear-head family selected: provides differential-expansion accommodation "
            "with added mechanical complexity."
        )
    else:
        note = (
            "Fixed-tubesheet-style rear arrangement: differential thermal expansion "
            "requires explicit mechanical review."
        )

    checks.append(
        MechanicalCheck(
            item="Thermal expansion concept",
            status="INFO",
            value=rear_head,
            criterion="Rear-head dependent",
            note=note,
        )
    )

    return checks
