from backend.app.mechanical.pressure_design import (
    cylindrical_shell_thickness_mm,
    cylindrical_shell_mawp_bar,
    tube_wall_screen_mm,
)
from backend.app.mechanical.nozzles import size_nozzle
from backend.app.mechanical.mechanical_design import (
    MechanicalDesignInput,
    run_mechanical_design,
)


def test_shell_pressure_screen_positive():
    t = cylindrical_shell_thickness_mm(
        design_pressure_bar=10.0,
        inside_diameter_mm=800.0,
        allowable_stress_mpa=120.0,
        joint_efficiency=0.85,
        corrosion_allowance_mm=1.5,
    )
    assert t > 1.5


def test_mawp_increases_with_thickness():
    p1 = cylindrical_shell_mawp_bar(
        8.0, 800.0, 120.0, 0.85, 1.5
    )
    p2 = cylindrical_shell_mawp_bar(
        12.0, 800.0, 120.0, 0.85, 1.5
    )
    assert p2 > p1


def test_nozzle_size_runs():
    result = size_nozzle(
        mass_flow_kg_s=20.0,
        density_kg_m3=900.0,
        target_velocity_m_s=2.0,
    )
    assert result.selected_dn_mm > 0
    assert result.selected_velocity_m_s > 0


def test_full_mechanical_design_runs():
    result = run_mechanical_design(
        MechanicalDesignInput(
            tema_code="BEM",
            shell_inside_diameter_m=0.80,
            tube_od_m=0.01905,
            tube_id_m=0.01575,
            tube_length_m=6.0,
            tube_pitch_m=0.025,
            tube_passes=2,
            baffle_count=12,
            baffle_cut_fraction=0.25,
            front_head="B",
            shell_type="E",
            rear_head="M",
            shell_design_pressure_bar=10.0,
            tube_design_pressure_bar=12.0,
            shell_design_temperature_c=180.0,
            tube_design_temperature_c=160.0,
            shell_material="Carbon steel SA-516 Gr 70 (screening)",
            tube_material="Carbon steel SA-179 tube (screening)",
            shell_joint_efficiency=0.85,
            tube_joint_efficiency=1.0,
            shell_corrosion_allowance_mm=1.5,
            tube_corrosion_allowance_mm=0.0,
            shell_mass_flow_kg_s=18.0,
            shell_density_kg_m3=950.0,
            tube_mass_flow_kg_s=12.0,
            tube_density_kg_m3=800.0,
            shell_nozzle_target_velocity_m_s=2.0,
            tube_nozzle_target_velocity_m_s=2.0,
            tema_class="R",
        )
    )

    assert result.required_shell_thickness_mm > 0
    assert result.shell_mawp_bar > 0
    assert result.required_tube_wall_mm > 0
    assert len(result.geometry_checks) >= 5
