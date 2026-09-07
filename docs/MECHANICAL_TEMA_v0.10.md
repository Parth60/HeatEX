# HX//RACE v0.10 — Mechanical / TEMA Design Layer

## Scope

v0.10 adds preliminary mechanical-design screening around the shell-and-tube
thermal model.

It is intentionally NOT a pressure-vessel code calculator and NOT a TEMA
certification engine.

## Added inputs

- TEMA class field
- shell-side design pressure
- tube-side design pressure
- shell-side design temperature
- tube-side design temperature
- shell material
- tube material
- shell joint efficiency
- tube joint efficiency
- shell corrosion allowance
- tube corrosion allowance
- selected shell nominal thickness
- shell / tube nozzle target velocity

## Shell thickness

The preliminary internal-pressure shell screen uses:

    t = P D / (2 S E - 1.2 P) + CA

The calculation does not include all code requirements.

## 2:1 elliptical head thickness

The preliminary head screen uses:

    t = P D / (2 S E - 0.2 P) + CA

## Shell MAWP screening

The shell equation is inverted to estimate a preliminary MAWP using the
selected nominal thickness after corrosion allowance.

## Tube wall

The tube wall uses a simple Barlow-style internal-pressure screen:

    t = P Do / (2 S E) + CA

This is not sufficient for final tube selection because real exchanger tubes
also require consideration of:

- external pressure / collapse
- manufacturing tolerance
- erosion
- vibration
- rolling / expansion / welding
- tube-sheet joint details
- corrosion
- cleaning method

## Material database

The internal database contains screening anchors for:

- SA-516 Gr 70 carbon steel
- SA-179 carbon steel tubes
- 304L stainless steel
- 316L stainless steel
- duplex 2205
- titanium Grade 2

The allowable stress values are preliminary HX-RACE anchors only.

Final code design requires exact values from the governing material tables and
the correct edition/specification.

## Nozzle sizing

Nozzles are screened from:

    Q = m_dot / rho

    A = Q / v_target

    D = sqrt(4 A / pi)

and rounded to an internal DN ladder.

This is a flow-velocity screen only. It does not replace nozzle reinforcement,
flange, piping-stress or local-load design.

## TEMA-style checks

v0.10 checks:

- tube pitch ratio
- average baffle spacing
- baffle cut
- tube-pass count
- three-letter TEMA nomenclature
- rear-head thermal-expansion concept

These are screening rules and do not reproduce or certify the TEMA standard.

## Explicitly deferred mechanical items

The following require specialist/code calculations and are intentionally not
faked in v0.10:

- tubesheet thickness / UHX design
- flange design
- gasket seating
- nozzle reinforcement
- shell external-pressure buckling
- wind / seismic
- saddles
- support loads
- lifting lugs
- local nozzle loads
- fatigue
- thermal stress
- tube vibration
- expansion joints
- hydrotest pressure
- MDMT / impact-test requirements
- PWHT
- NDE requirements

These should be exposed in the final report as required design checks rather
than silently assumed to pass.
