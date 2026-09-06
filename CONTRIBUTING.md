# Contributing to HX//RACE

Use feature branches for substantial changes:

- `feature/bell-delaware`
- `feature/thermodynamics`
- `feature/tema-visual`
- `feature/plate-exchanger`
- `feature/optimizer`

Before merging into `main`:

1. Run backend tests.
2. Run at least one known-case engineering check.
3. State the correlation/property-method source in code comments or documentation.
4. Do not label generated outputs as TEMA certified.
5. Keep numerical equations in the engine, not in the Streamlit UI.
