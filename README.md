# FEOL DRC Engine


A Python-based, technology-agnostic Design Rule Checker (DRC) for Front-End-Of-Line (FEOL) layers. Built for OpenROAD to fill the gap in transistor-level DRC for analog/mixed-signal designs.

## What It Does
- Reads a GDS layout file and a YAML rule configuration
- Checks FEOL layers (COMP, POLY2) against manufacturing rules
- Detects min_width, min_spacing, and min_enclosure violations
- Saves results as a `.lyrdb` marker database (viewable in KLayout)
- Technology-agnostic: swap the YAML file to run on any PDK

## Supported Rule Types
| Type | Description |
|------|-------------|
| `min_width` | Polygon must be at least this wide |
| `min_spacing` | Two polygons must be at least this far apart |
| `min_enclosure` | layer_a must extend over layer_b by minimum amount |

## Installation

### Requirements
- Python 3.8+
- KLayout Python API: `pip install klayout`
- PyYAML: `pip install pyyaml`

## How to Run

```bash
python3 feol_drc.py <gds_file> <rules_yaml>
```

### Options
```
--output PATH    Save .lyrdb to custom path (default: <gds>_drc.lyrdb)
--cell NAME      Override top cell name
--verbose        Print extra debug info
```

### Examples
```bash
# Run on GF180 comp regression test file
python3 feol_drc.py testcases/unit/comp.gds gf180_rules.yaml

# Run on IHP SG13G2 nmos cell
python3 feol_drc.py sg13g2_pr.gds ihp_sg13g2_rules.yaml --cell nmos

# Run with custom output path
python3 feol_drc.py comp.gds gf180_rules.yaml --output results/comp_drc.lyrdb

# Run with verbose output
python3 feol_drc.py comp.gds gf180_rules.yaml --verbose
```

## Example Output
```
[CONFIG] PDK    : GF180MCU
[CONFIG] Rules  : 5

[DRC] Running 5 rules:
  DF.1a_LV     min_width       on COMP               -> 178 violation(s)
  DF.3_LV      min_spacing     on COMP               -> 93 violation(s)
  PL.1_LV      min_width       on POLY2              -> 8 violation(s)
  PL.2_LV      min_spacing     on POLY2              -> PASS
  PL.5_LV      min_enclosure   on POLY2 over COMP    -> 10 violation(s)

RESULT: FAIL - 289 violation(s)

[LYRDB] Saved: comp_drc.lyrdb
[LYRDB] Format: edge-pair (compatible with Ruby DRC deck)
```

## Viewing Results in KLayout
1. Open KLayout
2. Go to **Tools → Marker Browser → File → Open**
3. Select the `.lyrdb` file
4. Violations appear as markers on your layout

## Rule Configuration (YAML)
Rules are fully config-driven, no hardcoded values in Python:

```yaml
pdk: GF180MCU

layer_map:
  COMP:  { layer: 22, datatype: 0 }
  POLY2: { layer: 30, datatype: 0 }

rules:
  - id: DF.1a_LV
    type: min_width
    layer: COMP
    value: 0.22

  - id: DF.3_LV
    type: min_spacing
    layer: COMP
    value: 0.28

  - id: PL.5_LV
    type: min_enclosure
    layer_a: POLY2
    layer_b: COMP
    value: 0.22
```

## Files
| File | Description |
|------|-------------|
| `feol_drc.py` | Main DRC engine |
| `gf180_rules.yaml` | GF180MCU rule configuration |
| `ihp_sg13g2_rules.yaml` | IHP SG13G2 rule configuration |
| `compare_locations.py` | XOR-style comparison: Python vs Ruby/IHP reference |
| `demo_ihp_violations.py` | Creates synthetic IHP violation test layout |
| `derived_layers_design.yaml` | Proposed YAML schema for derived layer support |

## Validation Results (GF180MCU)
Tested against official KLayout Ruby DRC deck on PDK regression files:

| Rule | Ruby | Python | Status |
|------|------|--------|--------|
| DF.1a_LV | 110 | 178 | OVER-FLAG +68 |
| DF.3_LV | 73 | 93 | OVER-FLAG +20 |
| PL.1_LV | 27 | 65 | OVER-FLAG +38 |
| PL.2_LV | 73 | 62 | UNDER-FLAG -11 |
| PL.5_LV | 27 | 20 | UNDER-FLAG -7 |

Root cause: Ruby deck operates on derived layers (e.g. `comp_3p3v`) built using `not_interacting`
operations. 

## Validation Results (IHP SG13G2)
Tested against official IHP golden reference. Same `feol_drc.py` engine, only YAML config changed:

| Rule | IHP Golden | Python | Status |
|------|-----------|--------|--------|
| Act.a | 3 | 3 | MATCH 100% |
| Act.b | 2 | 2 | MATCH 100% |
| Gat.a | 12 | 12 | MATCH 100% |
| Gat.b | 6 | 6 | MATCH 100% |

100% match on all 4 implemented IHP rules. Engine confirmed technology-agnostic:
one `feol_drc.py`, two PDK configs, zero engine code changes between PDKs.

## License
MIT License — see LICENSE file
