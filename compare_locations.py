"""
compare_locations.py — XOR-style location comparison between Ruby and Python .lyrdb files
==========================================================================================
Author: Rumali Siddiqua — GSoC 2026

"""

import xml.etree.ElementTree as ET
import os
import re


def parse_lyrdb(filepath):
    """
    Parse a .lyrdb file and return a dict:
      { rule_name: [ "edge-pair or box string", ... ] }
    """
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return {}

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"[ERROR] Could not parse {filepath}: {e}")
        return {}

    results = {}

    for category in root.iter('category'):
        # Get rule name
        name_el = category.find('name')
        if name_el is None:
            continue
        rule_name = name_el.text.strip().replace('_', '.')

        locations = []
        for item in category.iter('item'):
            # Try edge-pair format first
            for ep in item.iter('edge-pair'):
                if ep.text:
                    locations.append(('edge-pair', ep.text.strip()))
            # Fall back to box format
            for box in item.iter('box'):
                if box.text:
                    locations.append(('box', box.text.strip()))

        if rule_name not in results:
            results[rule_name] = []
        results[rule_name].extend(locations)

    return results


def extract_coords(location_str):
    """Extract all numeric coordinates from a location string."""
    nums = re.findall(r'-?\d+\.?\d*', location_str)
    return [float(n) for n in nums]


def coords_match(loc1, loc2, tolerance=5):
    """
    Check if two locations refer to roughly the same place.
    Compares the first coordinate pair (centroid-like) within tolerance.
    Tolerance is in database units (5 = 0.005um at 1nm DBU).
    """
    c1 = extract_coords(loc1[1])
    c2 = extract_coords(loc2[1])
    if not c1 or not c2:
        return False
    # Compare first x,y pair
    return abs(c1[0] - c2[0]) <= tolerance and abs(c1[1] - c2[1]) <= tolerance


def compare_rule(rule_name, ruby_locs, python_locs):
    """Compare locations for one rule and return match statistics."""
    matched_ruby = set()
    matched_python = set()

    for i, r_loc in enumerate(ruby_locs):
        for j, p_loc in enumerate(python_locs):
            if j in matched_python:
                continue
            if coords_match(r_loc, p_loc):
                matched_ruby.add(i)
                matched_python.add(j)
                break

    matching = len(matched_ruby)
    missed_by_python = len(ruby_locs) - matching
    false_positives = len(python_locs) - matching

    return {
        'ruby_total': len(ruby_locs),
        'python_total': len(python_locs),
        'matching': matching,
        'missed_by_python': missed_by_python,
        'false_positives': false_positives,
        'sample_missed': [ruby_locs[i] for i in range(len(ruby_locs)) if i not in matched_ruby][:2],
        'sample_fp': [python_locs[j] for j in range(len(python_locs)) if j not in matched_python][:2],
    }


def main():
    # File paths — adjust if your filenames differ
    ruby_file   = 'comp_golden.lyrdb'
    python_file = 'comp_v3_drc.lyrdb'

    print(f"[INFO] Reading Ruby reference: {ruby_file}")
    ruby_data = parse_lyrdb(ruby_file)

    print(f"[INFO] Reading Python output:  {python_file}")
    python_data = parse_lyrdb(python_file)

    if not ruby_data:
        print("[ERROR] Ruby .lyrdb could not be read. Exiting.")
        return
    if not python_data:
        print("[ERROR] Python .lyrdb could not be read. Exiting.")
        return

    ruby_cats   = sorted(ruby_data.keys())
    python_cats = sorted(python_data.keys())
    print(f"\nRuby categories found:  {ruby_cats}")
    print(f"Python categories found: {python_cats}")

    # Rules to compare — only ones present in both
    common_rules = sorted(set(ruby_cats) & set(python_cats))

    print("\n" + "=" * 55)
    for rule in common_rules:
        r_locs = ruby_data[rule]
        p_locs = python_data[rule]
        stats  = compare_rule(rule, r_locs, p_locs)

        print(f"\nRule: {rule}")
        print(f"  Ruby total:            {stats['ruby_total']}")
        print(f"  Python total:          {stats['python_total']}")
        print(f"  Matching locations:    {stats['matching']}")
        print(f"  Missed by Python:      {stats['missed_by_python']}")
        print(f"  False positives Python:{stats['false_positives']}")

        if stats['ruby_total'] > 0:
            accuracy = stats['matching'] / stats['ruby_total'] * 100
            print(f"  Matching accuracy:     {stats['matching']}/{stats['ruby_total']} "
                  f"= {accuracy:.0f}%")

        if stats['sample_missed']:
            print(f"  Sample missed (Ruby edge-pairs):")
            for loc in stats['sample_missed']:
                print(f"    {loc[0]}: {loc[1]}")

        if stats['sample_fp']:
            print(f"  Sample Python output:")
            for loc in stats['sample_fp']:
                print(f"    {loc[0]}: {loc[1]}")

        print("=" * 55)

    # FORMAT CHECK
    print(f"\nFORMAT CHECK:")
    print(f"Checking what format Python is now saving...")
    for rule, locs in python_data.items():
        if locs:
            fmt, sample = locs[0]
            # Truncate long samples
            sample_short = sample[:60] + '...' if len(sample) > 60 else sample
            print(f"  {rule}: {fmt} format — sample: {fmt}: {sample_short}")


if __name__ == "__main__":
    main()
