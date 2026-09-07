from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


R = 8.31446261815324  # J/mol/K


@dataclass(frozen=True)
class ComponentData:
    name: str
    mw_g_mol: float

    # Cubic-EOS constants
    tc_k: Optional[float]
    pc_pa: Optional[float]
    acentric_factor: Optional[float]

    # Liquid-property model referenced to 25 °C
    cp_ref_j_kgk: float
    cp_slope_j_kgk2: float
    rho_ref_kg_m3: float
    thermal_expansion_1_k: float
    mu_ref_pa_s: float
    mu_temp_coeff_1_k: float
    k_ref_w_mk: float
    k_slope_w_mk2: float

    # Phase-change fallback data
    normal_boiling_point_c: Optional[float] = None
    latent_heat_nbp_j_kg: Optional[float] = None
    vapour_cp_ref_j_kgk: Optional[float] = None
    vapour_cp_slope_j_kgk2: float = 0.0

    # UNIQUAC structural constants
    uniquac_r: Optional[float] = None
    uniquac_q: Optional[float] = None

    @property
    def mw_kg_mol(self) -> float:
        return self.mw_g_mol / 1000.0

    def cp_j_kgk(self, temperature_c: float) -> float:
        cp = self.cp_ref_j_kgk + self.cp_slope_j_kgk2 * (temperature_c - 25.0)
        return max(250.0, cp)

    def vapour_cp_j_kgk(self, temperature_c: float) -> float:
        if self.vapour_cp_ref_j_kgk is None:
            return self.cp_j_kgk(temperature_c)

        cp = (
            self.vapour_cp_ref_j_kgk
            + self.vapour_cp_slope_j_kgk2 * (temperature_c - 25.0)
        )
        return max(250.0, cp)

    def sensible_enthalpy_j_kg(
        self,
        temperature_c: float,
        reference_temperature_c: float = 25.0,
        phase: str = "liquid",
    ) -> float:
        """
        Integral of the screening Cp model.

        phase='vapour' uses the vapour Cp fallback when available.
        """
        t = temperature_c
        tr = reference_temperature_c

        if phase.lower().startswith("vap"):
            cp0 = self.vapour_cp_ref_j_kgk or self.cp_ref_j_kgk
            slope = self.vapour_cp_slope_j_kgk2
        else:
            cp0 = self.cp_ref_j_kgk
            slope = self.cp_slope_j_kgk2

        return (
            cp0 * (t - tr)
            + 0.5 * slope * ((t - 25.0) ** 2 - (tr - 25.0) ** 2)
        )

    def liquid_density_kg_m3(self, temperature_c: float) -> float:
        denominator = 1.0 + self.thermal_expansion_1_k * (temperature_c - 25.0)
        return max(1.0, self.rho_ref_kg_m3 / max(0.15, denominator))

    def viscosity_pa_s(self, temperature_c: float) -> float:
        value = self.mu_ref_pa_s * math.exp(
            -self.mu_temp_coeff_1_k * (temperature_c - 25.0)
        )
        return max(1e-6, min(5.0, value))

    def thermal_conductivity_w_mk(self, temperature_c: float) -> float:
        value = self.k_ref_w_mk + self.k_slope_w_mk2 * (temperature_c - 25.0)
        return max(0.02, value)

    def saturation_pressure_pa(self, temperature_c: float) -> Optional[float]:
        """
        Lee-Kesler/Pitzer corresponding-states saturation-pressure screening model.
        """
        if self.tc_k is None or self.pc_pa is None or self.acentric_factor is None:
            return None

        t_k = temperature_c + 273.15
        if t_k <= 0 or t_k >= self.tc_k:
            return None

        tr = t_k / self.tc_k
        f0 = (
            5.92714
            - 6.09648 / tr
            - 1.28862 * math.log(tr)
            + 0.169347 * tr**6
        )
        f1 = (
            15.2518
            - 15.6875 / tr
            - 13.4721 * math.log(tr)
            + 0.43577 * tr**6
        )

        ln_pr = f0 + self.acentric_factor * f1
        return self.pc_pa * math.exp(ln_pr)

    def latent_heat_j_kg(self, saturation_temperature_c: float) -> Optional[float]:
        """
        Watson correlation referenced to latent heat at the normal boiling point.

        h_fg(T2) = h_fg(T1) * [(1-Tr2)/(1-Tr1)]^0.38
        """
        if (
            self.tc_k is None
            or self.normal_boiling_point_c is None
            or self.latent_heat_nbp_j_kg is None
        ):
            return None

        t1 = self.normal_boiling_point_c + 273.15
        t2 = saturation_temperature_c + 273.15

        if t2 >= self.tc_k:
            return 0.0

        tr1 = t1 / self.tc_k
        tr2 = t2 / self.tc_k

        numerator = max(1e-12, 1.0 - tr2)
        denominator = max(1e-12, 1.0 - tr1)

        return self.latent_heat_nbp_j_kg * (numerator / denominator) ** 0.38


COMPONENTS: dict[str, ComponentData] = {
    "Water": ComponentData(
        name="Water",
        mw_g_mol=18.01528,
        tc_k=647.096,
        pc_pa=22.064e6,
        acentric_factor=0.344,
        cp_ref_j_kgk=4180.0,
        cp_slope_j_kgk2=0.2,
        rho_ref_kg_m3=997.0,
        thermal_expansion_1_k=3.0e-4,
        mu_ref_pa_s=0.00089,
        mu_temp_coeff_1_k=0.024,
        k_ref_w_mk=0.600,
        k_slope_w_mk2=-0.0008,
        normal_boiling_point_c=100.0,
        latent_heat_nbp_j_kg=2_257_000.0,
        vapour_cp_ref_j_kgk=1860.0,
        vapour_cp_slope_j_kgk2=0.9,
        uniquac_r=0.9200,
        uniquac_q=1.4000,
    ),
    "Ethanol": ComponentData(
        name="Ethanol",
        mw_g_mol=46.06844,
        tc_k=514.71,
        pc_pa=6.268e6,
        acentric_factor=0.646,
        cp_ref_j_kgk=2440.0,
        cp_slope_j_kgk2=5.2,
        rho_ref_kg_m3=789.0,
        thermal_expansion_1_k=1.10e-3,
        mu_ref_pa_s=0.00120,
        mu_temp_coeff_1_k=0.021,
        k_ref_w_mk=0.171,
        k_slope_w_mk2=-0.00020,
        normal_boiling_point_c=78.37,
        latent_heat_nbp_j_kg=841_000.0,
        vapour_cp_ref_j_kgk=1450.0,
        vapour_cp_slope_j_kgk2=2.0,
        uniquac_r=2.1055,
        uniquac_q=1.9720,
    ),
    "Butanol": ComponentData(
        name="Butanol",
        mw_g_mol=74.1216,
        tc_k=563.05,
        pc_pa=4.414e6,
        acentric_factor=0.590,
        cp_ref_j_kgk=2450.0,
        cp_slope_j_kgk2=4.0,
        rho_ref_kg_m3=810.0,
        thermal_expansion_1_k=9.0e-4,
        mu_ref_pa_s=0.00260,
        mu_temp_coeff_1_k=0.025,
        k_ref_w_mk=0.155,
        k_slope_w_mk2=-0.00016,
        normal_boiling_point_c=117.7,
        latent_heat_nbp_j_kg=582_000.0,
        vapour_cp_ref_j_kgk=1700.0,
        vapour_cp_slope_j_kgk2=2.5,
        uniquac_r=3.4543,
        uniquac_q=3.0520,
    ),
    "Acetone": ComponentData(
        name="Acetone",
        mw_g_mol=58.080,
        tc_k=508.10,
        pc_pa=4.700e6,
        acentric_factor=0.307,
        cp_ref_j_kgk=2160.0,
        cp_slope_j_kgk2=3.0,
        rho_ref_kg_m3=784.0,
        thermal_expansion_1_k=1.40e-3,
        mu_ref_pa_s=0.00032,
        mu_temp_coeff_1_k=0.018,
        k_ref_w_mk=0.160,
        k_slope_w_mk2=-0.00018,
        normal_boiling_point_c=56.05,
        latent_heat_nbp_j_kg=518_000.0,
        vapour_cp_ref_j_kgk=1350.0,
        vapour_cp_slope_j_kgk2=1.5,
        uniquac_r=2.5735,
        uniquac_q=2.3360,
    ),
    "Thermal oil": ComponentData(
        name="Thermal oil",
        mw_g_mol=250.0,
        tc_k=None,
        pc_pa=None,
        acentric_factor=None,
        cp_ref_j_kgk=1900.0,
        cp_slope_j_kgk2=3.5,
        rho_ref_kg_m3=850.0,
        thermal_expansion_1_k=7.5e-4,
        mu_ref_pa_s=0.0120,
        mu_temp_coeff_1_k=0.030,
        k_ref_w_mk=0.125,
        k_slope_w_mk2=-0.00008,
    ),
    "Light hydrocarbon": ComponentData(
        name="Light hydrocarbon",
        mw_g_mol=100.0,
        tc_k=None,
        pc_pa=None,
        acentric_factor=None,
        cp_ref_j_kgk=2100.0,
        cp_slope_j_kgk2=2.5,
        rho_ref_kg_m3=680.0,
        thermal_expansion_1_k=1.00e-3,
        mu_ref_pa_s=0.00055,
        mu_temp_coeff_1_k=0.020,
        k_ref_w_mk=0.130,
        k_slope_w_mk2=-0.00010,
    ),
}


def get_component(name: str) -> ComponentData:
    try:
        return COMPONENTS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown component '{name}'. Available: {', '.join(COMPONENTS)}"
        ) from exc


def component_names() -> list[str]:
    return list(COMPONENTS)
