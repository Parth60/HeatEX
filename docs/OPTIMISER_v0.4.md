# HX//RACE v0.4 Optimiser

## Purpose

The v0.4 optimiser performs a bounded discrete search over shell-and-tube
geometry. Every candidate is evaluated by the same `simulate_shell_and_tube`
function used by the live cockpit.

## Variables currently searched

- tube outside diameter
- tube length
- tube count
- tube passes
- tube pitch ratio
- number of baffles
- baffle cut

## Hard feasibility checks

- minimum / maximum area margin
- maximum tube-side pressure drop
- maximum shell-side pressure drop
- minimum / maximum tube-side velocity
- finite thermal-hydraulic results

## Objectives

- Balanced
- Minimum installed area
- Minimum pressure drop
- Maximum overall U
- Minimum relative cost
- Maximum area efficiency

## Relative cost index

The relative cost index is deliberately dimensionless. It is a ranking aid,
not a purchased-equipment cost estimate.

A later version will introduce:
- material factors
- shell diameter / thickness effects
- tube material and gauge
- fabrication complexity
- pressure class
- lifecycle pumping cost
- exchanger cleaning / maintenance penalties

## Engineering limitation

The optimiser can only be as accurate as the underlying thermal, hydraulic,
property and mechanical models. Optimised output is not design certification.
