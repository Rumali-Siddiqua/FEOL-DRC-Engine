"""
FEOL DRC Engine — Python-Based FEOL-Aware, Technology-Agnostic DRC Engine
==========================================================================
Author: Rumali Siddiqua — GSoC 2026

RULES SUPPORTED:
  - min_width     : each polygon must be at least this wide
  - min_spacing   : polygons must be at least this far apart
  - min_enclosure : layer_a must extend over layer_b by minimum amount

HOW TO RUN:
  python3 feol_drc.py <gds_file> <rule_config.yaml>

OPTIONS:
  --output PATH     Save .lyrdb to this path (default: <gds_file>_drc.lyrdb)
  --cell NAME       Override top cell name
  --verbose         Print extra debug info

EXAMPLES:
  python3 feol_drc.py testcases/unit/comp.gds gf180_rules.yaml
  python3 feol_drc.py testcases/unit/poly2.gds gf180_rules.yaml
  python3 feol_drc.py test_enclosure.gds gf180_rules.yaml --verbose
  python3 feol_drc.py comp.gds gf180_rules.yaml --output results/comp_drc.lyrdb
"""

import argparse
import os
import sys
import xml.etree.ElementTree as ET

import klayout.db as db
import yaml


# ── CONFIG ────────────────────────────────────────────────────────
def load_config(yaml_path):
    """Read rules and layer map from YAML file."""
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)


# ── GEOMETRY EXTRACTION ───────────────────────────────────────────
def extract_region(layout, cell, layer_num, datatype, verbose=False):
    """Extract all polygons from one GDS layer into a klayout Region."""
    layer_index = layout.find_layer(layer_num, datatype)
    if layer_index is None:
        if verbose:
            print(f"  [WARN] Layer {layer_num}/{datatype} not found in GDS")
        return None
    return db.Region(cell.begin_shapes_rec(layer_index))


# ── HELPERS ───────────────────────────────────────────────────────
def um_to_dbu(value_um, dbu):
    """Convert microns to database units."""
    return int(round(value_um / dbu))


# ── RULE CHECKERS ─────────────────────────────────────────────────

def check_min_width(region, rule, dbu):
    """
    Check every polygon meets minimum width.
    Uses klayout width_check() which finds locations where a polygon
    is narrower than the minimum distance.
    """
    if region is None or region.is_empty():
        return []
    violations = []
    for ep in region.width_check(um_to_dbu(rule["value"], dbu)).each():
        edge = ep.first
        x = ((edge.p1.x + edge.p2.x) / 2) * dbu
        y = ((edge.p1.y + edge.p2.y) / 2) * dbu
        violations.append({
            "rule_id":  rule["id"],
            "type":     "min_width",
            "layer":    rule["layer"],
            "required": rule["value"],
            "actual":   ep.distance() * dbu,
            "x": x, "y": y, "edge_pair": ep
        })
    return violations


def check_min_spacing(region, rule, dbu):
    """
    Check all polygons are far enough apart.
    Uses klayout space_check() which finds pairs of polygons
    that are closer than the minimum distance.
    """
    if region is None or region.is_empty():
        return []
    violations = []
    for ep in region.space_check(um_to_dbu(rule["value"], dbu)).each():
        edge = ep.first
        x = ((edge.p1.x + edge.p2.x) / 2) * dbu
        y = ((edge.p1.y + edge.p2.y) / 2) * dbu
        violations.append({
            "rule_id":  rule["id"],
            "type":     "min_spacing",
            "layer":    rule["layer"],
            "required": rule["value"],
            "actual":   ep.distance() * dbu,
            "x": x, "y": y, "edge_pair": ep
        })
    return violations


def check_min_enclosure(region_a, region_b, rule, dbu):
    """
    Check that region_a (e.g. POLY2) encloses region_b (e.g. COMP)
    by at least the minimum amount on all sides.

    Only region_b shapes that interact with region_a are checked.
    """
    violations = []
    if region_a is None or region_a.is_empty():
        return violations
    if region_b is None or region_b.is_empty():
        return violations

    min_dbu = um_to_dbu(rule["value"], dbu)
    comp_inside_poly = region_b.interacting(region_a)
    if comp_inside_poly.is_empty():
        return violations

    for ep in region_a.enclosing_check(comp_inside_poly, min_dbu).each():
        edge = ep.first
        x = ((edge.p1.x + edge.p2.x) / 2) * dbu
        y = ((edge.p1.y + edge.p2.y) / 2) * dbu
        violations.append({
            "rule_id":  rule["id"],
            "type":     "min_enclosure",
            "layer":    f"{rule.get('layer_a')} over {rule.get('layer_b')}",
            "required": rule["value"],
            "actual":   ep.distance() * dbu,
            "x": x, "y": y, "edge_pair": ep
        })
    return violations


# ── LYRDB OUTPUT ──────────────────────────────────────────────────
def save_lyrdb(violations, gds_path, output_path, dbu, cell_name=None):
    """
    Save violations to .lyrdb file using xml.etree.ElementTree.

    Uses proper XML building (no string concatenation) so filenames or
    values containing special characters like & < > are safely escaped.

    Violations saved as edge-pairs (compatible with Ruby DRC deck format)
    to enable proper XOR-style location comparison.
    """
    def safe_name(rule_id):
        """KLayout category names cannot contain dots."""
        return rule_id.replace(".", "_")

    display_cell = cell_name if cell_name else os.path.basename(gds_path)

    root = ET.Element("report-database")

    desc = ET.SubElement(root, "description")
    desc.text = f"FEOL DRC: {os.path.basename(gds_path)}"

    # ── Categories ───────────────────────────────────────────────
    cats_el = ET.SubElement(root, "categories")
    seen = set()   # FIX: was a list, now a set for O(1) lookup
    for v in violations:
        sid = safe_name(v["rule_id"])
        if sid not in seen:
            seen.add(sid)
            cat = ET.SubElement(cats_el, "category")
            n = ET.SubElement(cat, "n")
            n.text = sid
            d = ET.SubElement(cat, "description")
            # ET automatically escapes & < > in .text
            d.text = (f"{v['rule_id']}: {v['type']} on {v['layer']} "
                      f"(required >= {v['required']} um)")

    # ── Cells ─────────────────────────────────────────────────────
    cells_el = ET.SubElement(root, "cells")
    cell_el = ET.SubElement(cells_el, "cell")
    n_el = ET.SubElement(cell_el, "n")
    n_el.text = display_cell   # ET escapes special chars automatically

    # ── Items ─────────────────────────────────────────────────────
    items_el = ET.SubElement(root, "items")
    for v in violations:
        ep = v.get("edge_pair")
        if ep is not None:
            try:
                e1 = ep.first
                e2 = ep.second
                val = (
                    f"edge-pair: "
                    f"({e1.p1.x * dbu:.3f},{e1.p1.y * dbu:.3f};"
                    f"{e1.p2.x * dbu:.3f},{e1.p2.y * dbu:.3f})"
                    f"|"
                    f"({e2.p1.x * dbu:.3f},{e2.p1.y * dbu:.3f};"
                    f"{e2.p2.x * dbu:.3f},{e2.p2.y * dbu:.3f})"
                )
            except Exception:
                x1, y1 = v["x"] - 0.05, v["y"] - 0.05
                x2, y2 = v["x"] + 0.05, v["y"] + 0.05
                val = f"box: ({x1:.6f},{y1:.6f};{x2:.6f},{y2:.6f})"
        else:
            x1, y1 = v["x"] - 0.05, v["y"] - 0.05
            x2, y2 = v["x"] + 0.05, v["y"] + 0.05
            val = f"box: ({x1:.6f},{y1:.6f};{x2:.6f},{y2:.6f})"

        item_el  = ET.SubElement(items_el, "item")
        cat_ref  = ET.SubElement(item_el, "category")
        cat_ref.text = safe_name(v["rule_id"])
        cell_ref = ET.SubElement(item_el, "cell")
        cell_ref.text = display_cell
        vis = ET.SubElement(item_el, "visited")
        vis.text = "false"
        mul = ET.SubElement(item_el, "multiplicity")
        mul.text = "1"
        vals_el = ET.SubElement(item_el, "values")
        val_el  = ET.SubElement(vals_el, "value")
        val_el.text = val   # ET escapes special chars automatically

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    with open(output_path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)

    print(f"\n[LYRDB] Saved: {output_path}")
    print(f"[LYRDB] Total violations saved: {len(violations)}")
    print(f"[LYRDB] Format: edge-pair (compatible with Ruby DRC deck)")
    print(f"[LYRDB] Open in KLayout: Tools -> Marker Browser -> File -> Open")


# ── MAIN DRC FUNCTION ─────────────────────────────────────────────
def run_drc(gds_path, config_path, cell_override=None, verbose=False):
    """Main DRC function — reads config, loads GDS, runs all rules."""
    config    = load_config(config_path)
    layer_map = config["layer_map"]
    rules     = config["rules"]

    print("=" * 55)
    print("  FEOL DRC Engine — GSoC 2026")
    print("  Rumali Siddiqua")
    print("=" * 55)
    print(f"\n[CONFIG] PDK    : {config['pdk']}")
    print(f"[CONFIG] Rules  : {len(rules)}")
    print(f"[CONFIG] Source : {config_path}")

    print(f"\n[GDS] Loading: {gds_path}")
    layout = db.Layout()
    layout.read(gds_path)
    dbu  = layout.dbu

    if cell_override:
        matching = [c for c in layout.top_cells() if c.name == cell_override]
        if not matching:
            print(f"[ERROR] Cell '{cell_override}' not found in GDS.")
            sys.exit(1)
        cell = matching[0]
    else:
        cell = layout.top_cells()[0]

    print(f"[GDS] Cell  : {cell.name}")
    print(f"[GDS] Units : {dbu} um per database unit")

    print(f"\n[LAYERS] Extracting:")
    layer_cache = {}
    for layer_name, info in layer_map.items():
        region = extract_region(layout, cell,
                                info["layer"], info["datatype"],
                                verbose=verbose)
        layer_cache[layer_name] = region
        count = region.count() if region else 0
        print(f"  {layer_name:8s} (layer {info['layer']:2d}) -> {count} shapes")

    print(f"\n[DRC] Running {len(rules)} rules:")
    all_violations = []

    for rule in rules:
        rtype = rule["type"]

        if rtype == "min_width":
            lname  = rule.get("layer")
            region = layer_cache.get(lname)
            v = check_min_width(region, rule, dbu)

        elif rtype == "min_spacing":
            lname  = rule.get("layer")
            region = layer_cache.get(lname)
            v = check_min_spacing(region, rule, dbu)

        elif rtype == "min_enclosure":
            layer_a  = rule.get("layer_a")
            layer_b  = rule.get("layer_b")
            region_a = layer_cache.get(layer_a)
            region_b = layer_cache.get(layer_b)
            v = check_min_enclosure(region_a, region_b, rule, dbu)
            lname = f"{layer_a} over {layer_b}"

        else:
            print(f"  {rule['id']}: rule type '{rtype}' not yet implemented")
            continue

        status = f"{len(v)} violation(s)" if v else "PASS"
        print(f"  {rule['id']:12s} {rtype:15s} on {lname:20s} -> {status}")
        all_violations.extend(v)

    return all_violations, dbu, cell.name


# ── REPORT ────────────────────────────────────────────────────────
def print_report(violations):
    """Print human-readable violation report to terminal."""
    print(f"\n[REPORT]")
    print("=" * 55)
    if not violations:
        print("  RESULT: PASS - No violations found.")
        print("  (Correct - PDK standard cells are DRC-clean)")
    else:
        print(f"  RESULT: FAIL - {len(violations)} violation(s)\n")
        for v in violations:
            print(f"  [{v['rule_id']}] {v['type']} on {v['layer']}")
            print(f"    Required : >= {v['required']} um")
            print(f"    Actual   : {v['actual']:.4f} um")
            print(f"    Location : ({v['x']:.4f}, {v['y']:.4f}) um")
            print()
    print("=" * 55)


# ── ENTRY POINT ───────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="FEOL DRC Engine — Technology-Agnostic Design Rule Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 feol_drc.py testcases/unit/comp.gds gf180_rules.yaml
  python3 feol_drc.py testcases/unit/poly2.gds gf180_rules.yaml
  python3 feol_drc.py comp.gds gf180_rules.yaml --output results/comp_drc.lyrdb
  python3 feol_drc.py comp.gds gf180_rules.yaml --verbose
        """
    )
    parser.add_argument("gds_file",    help="Path to input GDS layout file")
    parser.add_argument("rules_file",  help="Path to YAML rule configuration file")
    parser.add_argument("--output",    help="Output .lyrdb path (default: <gds>_drc.lyrdb)")
    parser.add_argument("--cell",      help="Override top cell name")
    parser.add_argument("--verbose",   action="store_true",
                        help="Print extra debug information")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    violations, dbu, cell_name = run_drc(
        args.gds_file,
        args.rules_file,
        cell_override=args.cell,
        verbose=args.verbose
    )

    print_report(violations)

    # Determine output path
    if args.output:
        lyrdb_path = args.output
        os.makedirs(os.path.dirname(lyrdb_path), exist_ok=True) \
            if os.path.dirname(lyrdb_path) else None
    else:
        lyrdb_path = args.gds_file.replace(".gds", "_drc.lyrdb")

    save_lyrdb(violations, args.gds_file, lyrdb_path, dbu, cell_name=cell_name)
