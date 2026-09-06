from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, model_validator


class Mode(str, Enum):
    design = "design"
    rating = "rating"


class FlowArrangement(str, Enum):
    counter_current = "counter-current"
    co_current = "co-current"


class ThermalSpec(str, Enum):
    hot_outlet = "hot-outlet"
    cold_outlet = "cold-outlet"
    duty = "duty"


class ThermoPackage(str, Enum):
    coolprop = "CoolProp"
    ideal = "Ideal"
    peng_robinson = "Peng-Robinson"
    srk = "SRK"
    nrtl = "NRTL"
    uniquac = "UNIQUAC"
    iapws = "IAPWS"


class StreamInput(BaseModel):
    fluid: str = "Water"
    mass_flow_kg_s: float = Field(gt=0, default=10.0)
    inlet_temp_c: float = 25.0
    pressure_bar: float = Field(gt=0, default=1.5)


class GeometryInput(BaseModel):
    shell_id_m: float = Field(gt=0.1, default=0.8)
    tube_od_mm: float = Field(gt=5, default=19.05)
    tube_id_mm: float = Field(gt=3, default=15.75)
    tube_length_m: float = Field(gt=0.2, default=6.0)
    tube_count: int = Field(ge=4, le=10000, default=420)
    tube_passes: int = Field(ge=1, le=16, default=2)
    tube_pitch_mm: float = Field(gt=6, default=25.0)
    tube_layout: str = "triangular-30"
    baffle_count: int = Field(ge=0, le=100, default=12)
    baffle_cut_pct: float = Field(ge=10, le=50, default=25.0)
    tube_wall_k_w_mk: float = Field(gt=0.1, default=16.0)
    tube_fouling_m2k_w: float = Field(ge=0, default=0.0002)
    shell_fouling_m2k_w: float = Field(ge=0, default=0.0002)

    @model_validator(mode="after")
    def physical_geometry(self):
        if self.tube_id_mm >= self.tube_od_mm:
            raise ValueError("Tube ID must be smaller than tube OD")
        if self.tube_pitch_mm <= self.tube_od_mm:
            raise ValueError("Tube pitch must exceed tube OD")
        return self


class TemaInput(BaseModel):
    front: str = "B"
    shell: str = "E"
    rear: str = "M"


class SimulationRequest(BaseModel):
    mode: Mode = Mode.design
    thermo_package: ThermoPackage = ThermoPackage.coolprop
    flow_arrangement: FlowArrangement = FlowArrangement.counter_current
    thermal_spec: ThermalSpec = ThermalSpec.hot_outlet
    thermal_target: float = 70.0
    hot_stream: StreamInput = StreamInput(fluid="Ethanol", mass_flow_kg_s=12, inlet_temp_c=140, pressure_bar=4)
    cold_stream: StreamInput = StreamInput(fluid="Water", mass_flow_kg_s=18, inlet_temp_c=25, pressure_bar=3)
    geometry: GeometryInput = GeometryInput()
    tema: TemaInput = TemaInput()
    tube_dp_limit_kpa: float = Field(gt=0, default=70)
    shell_dp_limit_kpa: float = Field(gt=0, default=50)


class PropertyState(BaseModel):
    cp_j_kgk: float
    rho_kg_m3: float
    mu_pa_s: float
    k_w_mk: float
    source: str


class SimulationResult(BaseModel):
    tema_code: str
    tema_description: dict[str, str]
    duty_kw: float
    hot_outlet_c: float
    cold_outlet_c: float
    lmtd_c: float
    correction_factor: float
    effective_delta_t_c: float
    overall_u_w_m2k: float
    required_area_m2: float
    installed_area_m2: float
    area_margin_pct: float
    tube_velocity_m_s: float
    tube_reynolds: float
    tube_prandtl: float
    tube_nusselt: float
    tube_h_w_m2k: float
    tube_dp_kpa: float
    shell_velocity_m_s: float
    shell_reynolds: float
    shell_prandtl: float
    shell_nusselt: float
    shell_h_w_m2k: float
    shell_dp_kpa: float
    hot_properties: PropertyState
    cold_properties: PropertyState
    screening_score: float
    warnings: list[str]
    methodology: list[str]
