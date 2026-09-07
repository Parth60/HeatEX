from backend.app.core.release import VERSION, release_manifest
from backend.app.core.units import build_display_summary
from backend.app.core.presets import preset_names, get_preset
from backend.app.core.project_io import (
    PROJECT_SCHEMA,
    build_project_snapshot,
    project_to_bytes,
    parse_project_bytes,
)


class DummyResult:
    duty_kw = 1000.0
    hot_outlet_c = 80.0
    cold_outlet_c = 45.0
    lmtd_c = 30.0
    overall_u_w_m2k = 500.0
    required_area_m2 = 66.7
    installed_area_m2 = 75.0
    tube_dp_kpa = 50.0
    shell_dp_kpa = 30.0


def test_release_manifest():
    assert VERSION == "1.0.0"
    manifest = release_manifest()
    assert manifest["product_name"] == "HX//RACE"
    assert "Not TEMA Certified" in manifest["release_boundaries"]


def test_all_display_unit_systems():
    for units in ["SI Engineering", "Metric Plant", "US Customary"]:
        rows = build_display_summary(DummyResult(), 2.0, 3.0, units)
        assert len(rows) >= 10
        assert rows[0]["Parameter"] == "Duty"


def test_presets_have_restorable_ui_state():
    names = preset_names()
    assert len(names) >= 3
    for name in names:
        preset = get_preset(name)
        assert "ui_state" in preset
        assert "front_head_v100" in preset["ui_state"]


def test_project_round_trip():
    p = build_project_snapshot(
        project_name="Test",
        engineer="Engineer",
        notes="",
        display_units="SI Engineering",
        ui_state={"front_head_v100": "B"},
        report_payload={"tema_code": "BEM"},
    )
    data = project_to_bytes(p)
    loaded = parse_project_bytes(data)
    assert loaded["schema"] == PROJECT_SCHEMA
    assert loaded["ui_state"]["front_head_v100"] == "B"
