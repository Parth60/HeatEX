# HX//RACE v0.6 — Phase Change Pro

## Scope

v0.6 adds a dedicated pure-component phase-change engineering mode for:

- condensers
- reboilers

It does not yet claim rigorous multicomponent condensation/boiling.

## Condenser zones

The engine can split a condenser into:

1. Desuperheating
2. Condensation
3. Subcooling

The total duty is:

    Q_total = Q_desuperheat + Q_latent + Q_subcool

## Reboiler zones

The engine can split a reboiler into:

1. Preheating
2. Boiling
3. Superheating

The total duty is:

    Q_total = Q_preheat + Q_latent + Q_superheat

## Saturation temperature

For fallback calculations, saturation temperature is solved from the
corresponding-states vapour-pressure equation already used by v0.5.

## Latent heat

The fallback latent heat is estimated with the Watson correlation referenced
to the component's latent heat at its normal boiling point.

Pure fluids currently provided with phase-change fallback data:

- Water
- Ethanol
- Butanol
- Acetone

## Condensation heat transfer

v0.6 includes a Nusselt horizontal-tube laminar film-condensation screening
correlation.

It does not yet account for all tube-bank inundation, vapour shear or
non-condensable-gas effects.

## Boiling heat transfer

v0.6 includes a Cooper nucleate pool-boiling screening correlation.

The result depends on:

- heat flux
- reduced pressure
- molecular weight
- surface roughness

This is not a critical-heat-flux/dryout design method.

## Two-phase pressure drop

A Lockhart-Martinelli screening multiplier is included for process fluid on
the tube side.

The current result represents a frictional screening component and does not
yet include all acceleration and static-head effects.

## Zone-by-zone area

Each zone receives its own:

- duty
- local LMTD
- process-side h
- utility-side h
- overall U
- required area

The total required exchanger area is the sum of the zone areas.

## Visualisation

The Phase Change tab displays a zone map whose width is proportional to each
zone's fraction of the calculated thermal duty.

This is a thermal visualisation. It is not a fabrication drawing and the
displayed zone widths should not be interpreted as actual tube length.

## Important limitation

v0.6 phase-change mode is intentionally restricted to pure-component process
streams. A rigorous multicomponent condenser/reboiler requires:

- flash calculations
- phase compositions
- dew/bubble progression
- latent enthalpy from an appropriate property model
- zone-by-zone equilibrium
- two-phase transport calculations

That belongs to the later rigorous flash engine.
