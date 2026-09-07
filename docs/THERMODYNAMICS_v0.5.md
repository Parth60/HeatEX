# HX//RACE v0.5 — Thermodynamics Pro

## New architecture

v0.5 moves the shell-and-tube simulator from a constant-Cp energy balance to
a composition-aware, enthalpy-based stream model.

## Stream composition

A stream can now be defined as:
- pure component
- multicomponent mixture

The user can enter fractions on either:
- mole basis
- mass basis

HX//RACE normalises the stream and calculates both mole and mass fractions.

## Property packages

### Ideal mixture
Internal temperature-dependent screening properties and ideal phase screening.

### Peng–Robinson
Internal PR cubic-EOS implementation:
- mixture a/b rules
- compressibility roots
- vapour/liquid Z diagnostics
- fugacity coefficients
- optional kij interaction matrix

### SRK
Internal Soave–Redlich–Kwong implementation with the same diagnostic structure.

### NRTL
Internal activity-coefficient engine.

Binary `tau_ij`, `tau_ji` and `alpha` values are supplied through a JSON
interaction-parameter file. Missing pairs default to zero and produce warnings.

### UNIQUAC
Internal combinatorial/residual activity-coefficient engine.

Binary interaction energies are supplied through JSON.

### CoolProp (pure only)
For configured pure fluids, HX//RACE attempts to obtain:
- Cp
- density
- viscosity
- thermal conductivity
- specific enthalpy

If CoolProp is unavailable or unsupported for the selected component, the
simulator falls back transparently to the internal screening property model.

## Energy balance

The new duty basis is:

    Q = m_hot (h_hot,in - h_hot,out)

The cold outlet is then found from:

    h_cold,out = h_cold,in + Q / m_cold

and a temperature solver determines the corresponding outlet temperature.

## Phase screening

v0.5 adds:
- corresponding-states saturation-pressure screening
- ideal bubble/dew diagnostics
- NRTL/UNIQUAC activity correction in the bubble-point screening path
- phase labels
- phase-boundary warnings

## Critical limitation

The internal fallback enthalpy model currently contains sensible enthalpy only.

Therefore a case that crosses a boiling/condensation boundary is flagged as a
diagnostic case. Full latent heat, two-phase heat-transfer correlations,
condensation pressure drop and boiling models belong to v0.6.

## T–Q profile

The simulator can calculate a segmented hot/cold temperature profile using
enthalpy interpolation. This provides:
- temperature approach along the duty path
- minimum approach temperature
- visual temperature-cross detection

## Interaction parameter file

See:

    data/interaction_parameters.example.json

The architecture is data-driven so validated parameters can be added later
without modifying the solver source code.
