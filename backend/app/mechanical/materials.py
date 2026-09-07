from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MaterialRecord:
    name: str
    family: str
    density_kg_m3: float
    thermal_conductivity_w_mk: float

    # HX-RACE preliminary allowable-stress anchors only.
    # These values are NOT a substitute for ASME Section II-D tables.
    allowable_20c_mpa: float
    allowable_100c_mpa: float
    allowable_200c_mpa: float
    allowable_300c_mpa: float

    corrosion_note: str

    def allowable_stress_mpa(self, temperature_c: float) -> float:
        """
        Linear interpolation of HX-RACE screening stress anchors.

        For code design, use the exact allowable stress from the applicable
        material specification and governing pressure-vessel code edition.
        """
        anchors = [
            (20.0, self.allowable_20c_mpa),
            (100.0, self.allowable_100c_mpa),
            (200.0, self.allowable_200c_mpa),
            (300.0, self.allowable_300c_mpa),
        ]

        t = float(temperature_c)

        if t <= anchors[0][0]:
            return anchors[0][1]
        if t >= anchors[-1][0]:
            return anchors[-1][1]

        for (t0, s0), (t1, s1) in zip(anchors[:-1], anchors[1:]):
            if t0 <= t <= t1:
                fraction = (t - t0) / (t1 - t0)
                return s0 + fraction * (s1 - s0)

        return anchors[-1][1]


MATERIALS: dict[str, MaterialRecord] = {
    "Carbon steel SA-516 Gr 70 (screening)": MaterialRecord(
        name="Carbon steel SA-516 Gr 70 (screening)",
        family="Carbon steel",
        density_kg_m3=7850.0,
        thermal_conductivity_w_mk=45.0,
        allowable_20c_mpa=138.0,
        allowable_100c_mpa=138.0,
        allowable_200c_mpa=125.0,
        allowable_300c_mpa=108.0,
        corrosion_note="Common shell material; corrosion allowance often required.",
    ),
    "Carbon steel SA-179 tube (screening)": MaterialRecord(
        name="Carbon steel SA-179 tube (screening)",
        family="Carbon steel tube",
        density_kg_m3=7850.0,
        thermal_conductivity_w_mk=50.0,
        allowable_20c_mpa=103.0,
        allowable_100c_mpa=103.0,
        allowable_200c_mpa=95.0,
        allowable_300c_mpa=82.0,
        corrosion_note="Common exchanger tube material for suitable non-corrosive services.",
    ),
    "304L stainless steel (screening)": MaterialRecord(
        name="304L stainless steel (screening)",
        family="Austenitic stainless steel",
        density_kg_m3=8000.0,
        thermal_conductivity_w_mk=16.2,
        allowable_20c_mpa=115.0,
        allowable_100c_mpa=110.0,
        allowable_200c_mpa=101.0,
        allowable_300c_mpa=92.0,
        corrosion_note="General stainless option; verify chloride and process compatibility.",
    ),
    "316L stainless steel (screening)": MaterialRecord(
        name="316L stainless steel (screening)",
        family="Austenitic stainless steel",
        density_kg_m3=8000.0,
        thermal_conductivity_w_mk=15.0,
        allowable_20c_mpa=115.0,
        allowable_100c_mpa=110.0,
        allowable_200c_mpa=101.0,
        allowable_300c_mpa=92.0,
        corrosion_note="Improved chloride resistance vs 304L, but SCC/pitting still require review.",
    ),
    "Duplex stainless 2205 (screening)": MaterialRecord(
        name="Duplex stainless 2205 (screening)",
        family="Duplex stainless steel",
        density_kg_m3=7800.0,
        thermal_conductivity_w_mk=19.0,
        allowable_20c_mpa=172.0,
        allowable_100c_mpa=165.0,
        allowable_200c_mpa=150.0,
        allowable_300c_mpa=125.0,
        corrosion_note="High strength and corrosion resistance; welding/procedure control is important.",
    ),
    "Titanium Grade 2 (screening)": MaterialRecord(
        name="Titanium Grade 2 (screening)",
        family="Titanium",
        density_kg_m3=4510.0,
        thermal_conductivity_w_mk=16.4,
        allowable_20c_mpa=95.0,
        allowable_100c_mpa=88.0,
        allowable_200c_mpa=72.0,
        allowable_300c_mpa=55.0,
        corrosion_note="Excellent seawater/chloride resistance; substantially higher material cost.",
    ),
}


def material_names() -> list[str]:
    return list(MATERIALS)


def get_material(name: str) -> MaterialRecord:
    try:
        return MATERIALS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown mechanical material '{name}'.") from exc
