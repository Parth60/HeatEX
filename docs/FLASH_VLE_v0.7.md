# HX//RACE v0.7 — Rigorous Flash + Multicomponent VLE

## Purpose

v0.7 introduces the first real multicomponent vapour/liquid equilibrium engine.

The core calculation is an isothermal-isobaric flash.

## Rachford-Rice

The vapour fraction beta is found from:

    sum_i z_i (K_i - 1) / [1 + beta (K_i - 1)] = 0

The resulting phase compositions are:

    x_i = z_i / [1 + beta(K_i - 1)]

    y_i = K_i x_i

## Peng-Robinson and SRK

PR and SRK use Wilson K-values as initial guesses.

During the two-phase iteration:

    K_i = phi_i^L / phi_i^V

where phi_i is obtained from the corresponding cubic EOS.

The v0.7 implementation therefore performs a phi-phi flash architecture.

## NRTL / UNIQUAC

For liquid-phase non-ideality:

    K_i = gamma_i Psat_i / P

v0.7 uses ideal vapour fugacity in this path.

This is a gamma-Raoult flash, not yet full gamma-phi.

## Interaction parameters

The same JSON structure from v0.5 is supported:

- KIJ
- NRTL
- UNIQUAC

Validated parameters should be used for serious predictions.

## Flash drum

The flash-drum model calculates:

- total feed molar flow
- vapour molar flow
- liquid molar flow
- vapour fraction
- liquid composition
- vapour composition

## Temperature flash sweep

The phase-envelope tool repeatedly runs the flash across an isobaric temperature range.

It identifies approximate:

- bubble temperature
- dew temperature
- vapour fraction versus temperature

The reported bubble/dew values are grid estimates, not a dedicated exact
bubble/dew nonlinear solver.

## Multicomponent condensation / boiling path

The phase-path tool allows a feed to be followed through a sequence of isobaric
flash calculations while temperature changes.

This shows:

- vapour fraction progression
- liquid composition progression
- vapour composition progression
- K-value evolution

This is a major step toward a rigorous multicomponent condenser/reboiler.

## Engineering boundary

v0.7 does NOT yet calculate a rigorous multicomponent exchanger area from
the flash path.

To do that correctly we still need:

- mixture enthalpy including latent contributions
- equilibrium enthalpies for both phases
- zone-by-zone duty from flash enthalpy
- local two-phase heat-transfer coefficients
- pressure-drop coupled flash progression

That is the next integration step.
