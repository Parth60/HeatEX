from __future__ import annotations
from dataclasses import dataclass


@dataclass
class PressureDropCheck:
    calculated_kpa: float
    allowable_kpa: float

    @property
    def margin_kpa(self) -> float:
        return self.allowable_kpa - self.calculated_kpa

    @property
    def utilisation_fraction(self) -> float:
        if self.allowable_kpa <= 0:
            return float("inf")
        return self.calculated_kpa / self.allowable_kpa

    @property
    def acceptable(self) -> bool:
        return self.calculated_kpa <= self.allowable_kpa


def check_pressure_drop(calculated_kpa: float, allowable_kpa: float) -> PressureDropCheck:
    return PressureDropCheck(
        calculated_kpa=float(calculated_kpa),
        allowable_kpa=float(allowable_kpa),
    )
