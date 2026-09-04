#!/usr/bin/env python3
"""Fail if the Python and JS converters produce structurally different SVGs
for the same input.

Per CLAUDE.md: "Python and JS versions must be kept in sync - changes to
rendering logic need to be applied to both." Exact byte-for-byte output
isn't realistic to enforce (Pillow vs. Canvas text measurement round
differently, so coordinates drift by fractions of a pixel), so this
compares the things that must match regardless of measurement precision:
every <text> label's content (pin names, types, comments - the actual
semantic content of the diagram) and the count of each shape element
(<polygon>, <path>, <line>, <polyline>, <rect>) as a proxy for "same ports, same
connections, same layout structure".
"""
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

SHAPE_TAGS = ("polygon", "path", "line", "polyline", "rect")


def extract_texts(svg: str) -> list:
    """Concatenated text content of every <text> element, via a real XML
    parse rather than a regex over the raw markup - so nested <tspan>s or
    entity differences between the two renderers' output don't get
    reported as a label mismatch when the actual rendered text matches."""
    root = ET.fromstring(svg)
    return [
        re.sub(r"\s+", " ", "".join(element.itertext())).strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "text"
    ]


def extract_shape_counts(svg: str) -> Counter:
    return Counter({tag: len(re.findall(rf"<{tag}\b", svg)) for tag in SHAPE_TAGS})


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: check_parity.py <python_svg> <js_svg>")
        return 2

    with open(sys.argv[1], encoding="utf-8") as f:
        py_svg = f.read()
    with open(sys.argv[2], encoding="utf-8") as f:
        js_svg = f.read()

    py_texts = sorted(extract_texts(py_svg))
    js_texts = sorted(extract_texts(js_svg))

    ok = True
    if py_texts != js_texts:
        ok = False
        print("ERROR: text label sets differ between Python and JS output")
        only_py = list((Counter(py_texts) - Counter(js_texts)).elements())
        only_js = list((Counter(js_texts) - Counter(py_texts)).elements())
        if only_py:
            print(f"  Only in Python output: {only_py}")
        if only_js:
            print(f"  Only in JS output:     {only_js}")

    py_shapes = extract_shape_counts(py_svg)
    js_shapes = extract_shape_counts(js_svg)
    if py_shapes != js_shapes:
        ok = False
        print(f"ERROR: shape element counts differ: Python={dict(py_shapes)} JS={dict(js_shapes)}")

    if ok:
        print(f"OK: {len(py_texts)} matching text labels, matching shape counts {dict(py_shapes)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
