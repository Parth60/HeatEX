# HX//RACE v1.0 User Guide

## Recommended workflow

1. Select a preset or start from the default BEM case.
2. Choose TEMA front head, shell and rear head.
3. Select the thermodynamic package.
4. Enter hot and cold stream conditions.
5. Define exchanger geometry.
6. Review Bell-Delaware clearances.
7. Review the live thermal/hydraulic results.
8. Run the optimiser when geometry alternatives are required.
9. Use phase-change or multicomponent tabs only when the service crosses a phase boundary.
10. Review Mechanical and Validation tabs.
11. Save the project snapshot.
12. Export the professional technical pack.

## Project save/restore

The `.hxrace.json` snapshot stores:

- project metadata
- display-unit preference
- core Streamlit input state
- engineering report payload from the saved run

Loading a project restores the core shell-and-tube inputs and reruns the application. Calculated outputs are recalculated instead of trusted blindly from the old file.

## Units

The solver remains SI internally.

The unit selector converts the final project summary into:

- SI Engineering
- Metric Plant
- US Customary

This separation prevents display-unit changes from altering the physics.

## Rating mode

The primary validated v1.0 path remains the target-outlet design/sizing workflow.

The sidebar `Rating preview` label is retained only as a workflow marker; it is **not** an independent installed-area rating solver. Do not describe it as one.

## Thermodynamic packages

For strongly non-ideal polar liquid mixtures, use NRTL/UNIQUAC only with suitable validated interaction parameters.

PR/SRK may be useful for hydrocarbon-like services, but package suitability must be justified for the actual system.

## Mechanical results

Mechanical calculations are preliminary screens only.

Do not use HX//RACE shell thickness, MAWP, nozzle, material or geometry outputs as fabrication-release values without the governing pressure-vessel and exchanger-code calculations.

## Validation score

The readiness score measures internal consistency and review status.

It is not an accuracy percentage.

## Final report wording

Correct:

- `TEMA-aligned preliminary specification`
- `engineering screening report`

Incorrect:

- `TEMA Certified`
- `ASME Certified`
- `ASME Stamped`
