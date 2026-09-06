from backend.app.engine.geometry import ShellTubeGeometry
from backend.app.engine.tube_side import calculate_tube_side
from backend.app.engine.bell_delaware import calculate_bell_delaware


def geometry():
    return ShellTubeGeometry(
        shell_id_m=0.8,
        tube_od_m=0.01905,
        tube_id_m=0.01575,
        tube_length_m=6.0,
        tube_count=420,
        tube_passes=2,
        tube_pitch_m=0.025,
        tube_layout="triangular",
        baffle_count=12,
        baffle_cut_fraction=0.25,
    )


def test_tube_side_returns_finite_values():
    g = geometry()
    r = calculate_tube_side(
        mass_flow_kg_s=12.0,
        rho_kg_m3=789.0,
        mu_pa_s=0.0012,
        cp_j_kgk=2550.0,
        k_w_mk=0.171,
        geometry=g,
    )
    assert r.velocity_m_s > 0
    assert r.reynolds > 0
    assert r.h_w_m2k > 0
    assert r.pressure_drop_kpa >= 0


def test_bell_delaware_returns_correction_factors():
    g = geometry()
    r = calculate_bell_delaware(
        mass_flow_kg_s=18.0,
        rho_kg_m3=997.0,
        mu_pa_s=0.00089,
        cp_j_kgk=4180.0,
        k_w_mk=0.60,
        geometry=g,
    )
    assert 0 < r.j_c <= 1.2
    assert 0 < r.j_l <= 1.0
    assert 0 < r.j_b <= 1.0
    assert 0 < r.corrected_h_w_m2k
    assert r.shell_pressure_drop_kpa >= 0
