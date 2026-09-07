# HX//RACE v0.9 — Multi-Exchanger Platform

## Added exchanger types

### Plate-and-frame

The v0.9 plate model includes:

- number of plates
- effective area
- plate gap
- plate length / width
- chevron angle
- enlargement factor
- hot / cold pass counts
- port diameter
- plate-wall resistance
- fouling resistance
- channel velocities
- Reynolds numbers
- screening plate-side heat-transfer coefficients
- hot / cold pressure drops
- LMTD, U, required area, installed area

Final plate rating still requires vendor-specific chevron geometry and
pressure-drop data.

### Double-pipe

The v0.9 double-pipe model includes:

- inner tube OD / ID
- outer pipe ID
- annulus hydraulic diameter
- hairpin length
- number of hairpins
- inner-tube or annulus hot-side selection
- internal / annular velocity
- Reynolds / Prandtl / Nusselt
- Darcy pressure drop
- wall conduction
- fouling
- required / installed area

### Air-cooled exchanger

The v0.9 air-cooler model includes:

- finned tubes
- rows and tubes per row
- fin diameter / thickness / density
- fin conductivity
- tube-side process hydraulics
- air face velocity
- maximum bundle velocity
- Zukauskas-style air-side screening h
- annular-fin efficiency
- overall surface efficiency
- external-area-basis U
- air-side pressure drop
- fan power
- process / air outlet temperatures
- required and installed finned area

Final air-cooler design requires vendor fan curves, noise limits, bundle
layout details, recirculation checks and site ambient design data.

## Exchanger selector

The selector ranks:

- Shell & Tube
- Plate & Frame
- Double Pipe
- Air-Cooled

using engineering service characteristics such as:

- duty
- pressure
- viscosity
- phase change
- fouling / solids
- close temperature approach
- cooling-water availability
- compactness priority

This is a transparent rule-based screening selector, not a vendor selection
or mechanical design guarantee.
