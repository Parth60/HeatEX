from app.engine.shell_tube import simulate
from app.models import SimulationRequest


def test_default_simulation_is_finite():
    result = simulate(SimulationRequest())
    assert result.duty_kw > 0
    assert result.required_area_m2 > 0
    assert result.installed_area_m2 > 0
    assert result.tema_code == "BEM"
