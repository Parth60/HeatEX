from __future__ import annotations

from dataclasses import dataclass, asdict

APP_NAME = "HeatEX"
PRODUCT_NAME = "HX//RACE"
VERSION = "1.0.0"
RELEASE_NAME = "Final Capstone Release"
RELEASE_DATE = "2026-09-07"


def release_manifest() -> dict:
    return {
        "app_name": APP_NAME,
        "product_name": PRODUCT_NAME,
        "version": VERSION,
        "release_name": RELEASE_NAME,
        "release_date": RELEASE_DATE,
        "engineering_scope": [
            "Shell-and-tube thermal/hydraulic screening",
            "TEMA configuration visualisation",
            "Bell-Delaware-style shell-side correction architecture",
            "Enthalpy-based stream balances",
            "PR/SRK/NRTL/UNIQUAC thermodynamic architecture",
            "Flash/VLE and Rachford-Rice",
            "Pure-fluid condenser/reboiler zoning",
            "Multicomponent phase-change segmentation",
            "Plate-and-frame screening",
            "Double-pipe screening",
            "Air-cooled screening",
            "Discrete shell-and-tube optimisation",
            "Preliminary mechanical/TEMA-style screening",
            "Validation and professional technical-pack generation",
        ],
        "release_boundaries": [
            "Not TEMA Certified",
            "Not ASME Certified or ASME Stamped",
            "Not a fabrication drawing",
            "Not a vendor guarantee",
            "Not a substitute for qualified engineering review",
        ],
    }
