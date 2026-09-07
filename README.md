# HX//RACE — HeatEX v1.0

HX//RACE is an educational and engineering-screening heat-exchanger simulator built for the HeatEX capstone project.

## v1.0 scope

The final release integrates:

- shell-and-tube thermal and hydraulic screening
- TEMA configuration selection and dynamic exchanger schematics
- tube-bundle cross-section visualisation
- Bell–Delaware-style shell-side correction architecture
- enthalpy-based stream balances
- ideal-mixture, Peng–Robinson, SRK, NRTL and UNIQUAC thermodynamic architecture
- Rachford–Rice flash/VLE
- pure-fluid condenser and reboiler zoning
- multicomponent phase-change segmentation
- plate-and-frame exchanger screening
- double-pipe exchanger screening
- air-cooled exchanger screening
- rule-based exchanger selection
- shell-and-tube discrete optimisation
- preliminary mechanical/TEMA-style screening
- validation and model-readiness checks
- PDF engineering reports and technical ZIP packs
- project snapshot save/restore
- engineering presets
- SI / metric-plant / US-customary result display
- automated regression tests

## Run locally

```bash
python -m venv .venv
```

Activate the environment, then:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional high-fidelity pure-fluid properties:

```bash
pip install -r requirements-optional.txt
```

## Important engineering boundary

HX//RACE is a capstone/engineering-screening tool.

Outputs must **not** be represented as:

- TEMA Certified
- ASME Certified
- ASME Stamped
- fabrication approved
- vendor guaranteed

Use wording such as:

- TEMA-aligned preliminary specification
- TEMA-style screening
- ASME-style preliminary pressure screen
- engineering screening report

Final design release requires the applicable codes, validated physical-property data, specialist mechanical calculations, vendor/fabricator review, and qualified engineering approval.

## Repository structure

```text
app.py
backend/
  app/
    core/
    engine/
    mechanical/
    reporting/
    thermo/
    validation/
    visualization/
  tests/
data/
docs/
.streamlit/
.github/workflows/
```

## Testing

```bash
pytest -q
```

## Deployment

The Streamlit entry point is:

```text
app.py
```

Use the root `requirements.txt` for the core deployment. `CoolProp` is intentionally optional so the application can deploy even when a platform has no compatible CoolProp wheel. HX//RACE automatically falls back to its internal property engine and exposes the active property source in the interface/report.

See `docs/DEPLOYMENT_v1.0.md`.

## Version

**HX//RACE v1.0.0 — Final Capstone Release**
