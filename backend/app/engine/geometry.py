from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass
class ShellTubeGeometry:
    shell_id_m: float
    tube_od_m: float
    tube_id_m: float
    tube_length_m: float
    tube_count: int
    tube_passes: int
    tube_pitch_m: float
    tube_layout: str
    baffle_count: int
    baffle_cut_fraction: float

    def validate(self) -> None:
        if self.shell_id_m <= 0:
            raise ValueError("Shell ID must be positive.")
        if self.tube_od_m <= 0 or self.tube_id_m <= 0:
            raise ValueError("Tube diameters must be positive.")
        if self.tube_id_m >= self.tube_od_m:
            raise ValueError("Tube ID must be smaller than tube OD.")
        if self.tube_pitch_m <= self.tube_od_m:
            raise ValueError("Tube pitch must exceed tube OD.")
        if self.tube_length_m <= 0:
            raise ValueError("Tube length must be positive.")
        if self.tube_count <= 0 or self.tube_passes <= 0:
            raise ValueError("Tube count and passes must be positive.")
        if self.baffle_count < 0:
            raise ValueError("Baffle count cannot be negative.")
        if not 0.05 <= self.baffle_cut_fraction <= 0.50:
            raise ValueError("Baffle cut fraction should be between 0.05 and 0.50.")

    @property
    def installed_area_m2(self) -> float:
        return math.pi * self.tube_od_m * self.tube_length_m * self.tube_count

    @property
    def tubes_per_pass(self) -> float:
        return self.tube_count / self.tube_passes

    @property
    def tube_flow_area_m2(self) -> float:
        return self.tubes_per_pass * math.pi * self.tube_id_m**2 / 4.0

    @property
    def baffle_spacing_m(self) -> float:
        return self.tube_length_m / (self.baffle_count + 1)

    def equivalent_shell_diameter_m(self) -> float:
        pt = self.tube_pitch_m
        do = self.tube_od_m

        layout = self.tube_layout.lower()
        if "tri" in layout:
            return 1.10 * (pt**2 - 0.917 * do**2) / do

        return 1.27 * (pt**2 - 0.785 * do**2) / do

    def shell_crossflow_area_m2(self) -> float:
        """
        Kern-style minimum crossflow area estimate.
        Bell-Delaware-specific leakage and bypass areas are handled separately.
        """
        return (
            self.shell_id_m
            * self.baffle_spacing_m
            * (self.tube_pitch_m - self.tube_od_m)
            / self.tube_pitch_m
        )
