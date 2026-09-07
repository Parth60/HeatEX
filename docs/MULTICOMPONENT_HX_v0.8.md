# HX//RACE v0.8 — Multicomponent Condenser/Reboiler Integration

## What changed

v0.7 could solve a multicomponent flash path.

v0.8 couples that phase-equilibrium path directly to exchanger thermal sizing.

## Segment workflow

For every computational segment:

1. Run equilibrium flash at segment inlet temperature.
2. Run equilibrium flash at segment outlet temperature.
3. Build phase-aware mixture enthalpies.
4. Calculate segment enthalpy change.
5. Calculate segment heat duty.
6. Calculate utility temperature change.
7. Determine local liquid / vapour / two-phase regime.
8. Calculate local process-side heat-transfer coefficient.
9. Calculate local utility heat-transfer coefficient.
10. Calculate local overall U.
11. Calculate local LMTD.
12. Calculate required segment area.
13. Calculate segment pressure-drop contribution.

Then:

    Q_total = sum(Q_j)

    A_total = sum(A_j)

    DP_total = sum(DP_j)

## Equilibrium mixture enthalpy

The v0.8 fallback mixture enthalpy model combines:

- component liquid sensible enthalpy
- component vapour sensible enthalpy
- pure-component Watson latent heat
- flash liquid composition
- flash vapour composition
- vapour mass fraction

This is a substantial improvement over using one averaged Cp through a
two-phase region.

However it is still a screening enthalpy model, not a substitute for a
validated property package such as a production process simulator.

## Two-phase heat transfer

### Tube-side condensation

A Shah-style in-tube condensation enhancement is used.

### Shell-side condensation

A Nusselt horizontal-tube film-condensation model is evaluated with
composition-weighted mixture properties and effective latent heat.

### Boiling

A Cooper-style nucleate boiling screening model is evaluated with mixture
molecular weight and pseudo-reduced pressure.

## Pressure drop

Tube-side two-phase segments can use a Lockhart-Martinelli multiplier.

Shell-side two-phase pressure drop remains a screening treatment.

## Utility profile

Both co-current and counter-current utility temperature progressions are
handled along the process coordinate.

## Engineering boundary

This is a coupled VLE / thermal sizing model, but it is not yet a validated
industrial rating package.

Remaining validation needs include:

- benchmark mixture enthalpy against a trusted property package
- validated binary interaction parameters
- rigorous gamma-phi for polar systems
- multicomponent condensation mass-transfer resistance
- non-condensable gas treatment
- improved tube-bank inundation
- boiling dryout / CHF
- acceleration and gravitational pressure-drop terms
