from __future__ import annotations


def build_assumptions_register(sim_input, result) -> list[dict]:
    assumptions = [
        {
            "ID": "A-01",
            "Topic": "Thermodynamics",
            "Assumption": f"Property package selected: {sim_input.thermo_package}.",
            "Impact": "Controls enthalpy and transport-property accuracy.",
            "Status": "USER INPUT",
        },
        {
            "ID": "A-02",
            "Topic": "Energy balance",
            "Assumption": "Primary duty is calculated from stream enthalpy difference.",
            "Impact": "Avoids constant-Cp energy-balance assumption.",
            "Status": "IMPLEMENTED",
        },
        {
            "ID": "A-03",
            "Topic": "Shell-side thermal model",
            "Assumption": "Bell-Delaware-style correction architecture is used for shell-side screening.",
            "Impact": "Final rating should be benchmarked against trusted literature/software.",
            "Status": "SCREENING",
        },
        {
            "ID": "A-04",
            "Topic": "Tube-side thermal model",
            "Assumption": "Laminar or turbulent internal-flow correlation selected from Reynolds regime.",
            "Impact": "Transitional flow carries higher uncertainty.",
            "Status": "SCREENING",
        },
        {
            "ID": "A-05",
            "Topic": "Fouling",
            "Assumption": (
                f"Tube fouling={sim_input.tube_fouling_m2k_w:.6f} m2-K/W; "
                f"shell fouling={sim_input.shell_fouling_m2k_w:.6f} m2-K/W."
            ),
            "Impact": "Directly affects U and required area.",
            "Status": "USER INPUT",
        },
        {
            "ID": "A-06",
            "Topic": "LMTD correction",
            "Assumption": (
                f"F={result.correction_factor:.3f} from the current HX-RACE "
                "shell-configuration screening map."
            ),
            "Impact": "Requires later replacement/benchmarking for rigorous multi-pass design.",
            "Status": "SCREENING",
        },
        {
            "ID": "A-07",
            "Topic": "Mechanical design",
            "Assumption": "Mechanical outputs are preliminary ASME/TEMA-style screens only.",
            "Impact": "Not suitable for fabrication release or code stamping.",
            "Status": "LIMITATION",
        },
        {
            "ID": "A-08",
            "Topic": "Certification",
            "Assumption": "No HX-RACE output is labelled TEMA Certified or ASME Certified.",
            "Impact": "Formal compliance remains with qualified engineering/fabrication review.",
            "Status": "MANDATORY",
        },
    ]

    if result.phase_change_flag:
        assumptions.append(
            {
                "ID": "A-09",
                "Topic": "Phase change",
                "Assumption": "The single-phase result crosses a phase boundary.",
                "Impact": "Use dedicated phase-change or multicomponent HX modules instead.",
                "Status": "REVIEW",
            }
        )

    return assumptions
