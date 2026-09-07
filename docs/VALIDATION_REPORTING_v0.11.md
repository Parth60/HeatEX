# HX//RACE v0.11 - Validation + Professional Engineering Pack

## Objective

v0.11 freezes the core engineering architecture and adds credibility,
traceability and professional reporting.

## Validation checks

The shell-and-tube validation layer checks:

- hot/cold enthalpy energy closure
- Q = U A F LMTD closure
- installed-area geometry identity
- positive LMTD
- LMTD correction factor screening
- tube Reynolds regime
- tube Prandtl plausibility
- shell Reynolds plausibility
- Bell-Delaware correction-factor numerical sanity
- tube pressure-drop limit
- shell pressure-drop limit
- tube velocity screen
- area margin
- phase-model suitability
- mechanical-screening status

## Model readiness score

The score is a weighted internal quality/completeness metric.

It is NOT:

- a probability of correctness
- an uncertainty interval
- a code-compliance score
- a vendor accuracy guarantee
- an engineering approval

## Regression benchmarks

v0.11 includes analytical implementation checks for:

- counter-current LMTD
- known Rachford-Rice binary solution
- composition normalization
- pressure-thickness / MAWP inverse consistency

These tests catch implementation regressions.

They do not replace external experimental/software validation.

## Calculation trace

A calculation trace records the major design sequence:

1. hot-side enthalpy duty
2. cold-side enthalpy duty
3. LMTD
4. corrected temperature driving force
5. overall U
6. required area
7. installed area
8. Reynolds number
9. tube pressure drop
10. shell pressure drop

## Assumptions register

The generated report explicitly records:

- thermodynamic package
- enthalpy basis
- shell-side method status
- tube-side method status
- fouling inputs
- correction-factor basis
- mechanical limitations
- certification wording

## PDF report

The generated PDF includes:

- cover / status
- executive summary
- design basis
- thermodynamic state table
- thermal/hydraulic summary
- mechanical screening
- validation dashboard
- benchmark table
- calculation trace
- assumptions/limitations
- TEMA-aligned preliminary specification sheet
- design-release follow-up actions

## Technical ZIP

The downloadable ZIP contains:

- PDF engineering report
- full JSON design archive
- validation CSV
- benchmark CSV
- assumptions CSV
- calculation-trace CSV
- TEMA-aligned preliminary specification CSV
- README / disclaimer

## Required wording

Do not label any HX//RACE document:

- TEMA Certified
- ASME Certified
- ASME Stamped
- fabrication approved

Use:

- TEMA-aligned preliminary specification
- TEMA-style screening
- ASME-style preliminary pressure screen
- engineering screening report
