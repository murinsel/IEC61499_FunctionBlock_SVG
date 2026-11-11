#!/usr/bin/env python3
"""Fail if any <text> label of a network SVG sticks out of its viewBox
horizontally.

Labels drawn outside an instance's block body - parameter values
right-aligned to the left of the input pins (text-anchor="end" at x=-3),
and instance names wider than the block - must be included in the diagram
bounds, or they get clipped at the left/right edge of the image.

Text widths aren't known without the font, so each label is assumed to be
at least MIN_CHAR_WIDTH * font-size per character wide. That is a lower
bound for the fonts in use, so a clipped label is reported while a label
that merely ends close to the edge is not.
"""
import re
import sys
import xml.etree.ElementTree as ET

MIN_CHAR_WIDTH = 0.35  # fraction of font-size, below any real glyph advance
TRANSLATE_RE = re.compile(r"translate\(\s*([-\d.eE+]+)")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check(path: str) -> list:
    root = ET.parse(path).getroot()
    vb_x, _, vb_w, _ = (float(v) for v in root.get("viewBox").split())
    errors = []

    def walk(element, offset_x: float) -> None:
        match = TRANSLATE_RE.search(element.get("transform", ""))
        if match:
            offset_x += float(match.group(1))
        if _local(element.tag) == "text":
            text = re.sub(r"\s+", " ", "".join(element.itertext())).strip()
            width = len(text) * float(element.get("font-size", "12")) * MIN_CHAR_WIDTH
            x = offset_x + float(element.get("x", "0"))
            anchor = element.get("text-anchor", "start")
            left = {"end": x - width, "middle": x - width / 2}.get(anchor, x)
            if text and (left < vb_x or left + width > vb_x + vb_w):
                errors.append(f"{text!r} spans x={left:.1f}..{left + width:.1f}, "
                              f"viewBox x={vb_x:.1f}..{vb_x + vb_w:.1f}")
        for child in element:
            walk(child, offset_x)

    walk(root, 0.0)
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check_viewbox.py <svg> [<svg> ...]")
        return 2

    ok = True
    for path in sys.argv[1:]:
        errors = check(path)
        if errors:
            ok = False
            print(f"ERROR: {path}: text clipped by the viewBox")
            for error in errors:
                print(f"  {error}")

    if ok:
        print("OK: all text labels lie inside the viewBox")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
