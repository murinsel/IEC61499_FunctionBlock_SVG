#!/usr/bin/env python3
"""Regression test: a Comment with line breaks (&#10;) is drawn as one <text>
line per line in the diagram header, the header grows accordingly, and the
widest line lies inside the viewBox horizontally.

Usage: python tests/check_multiline_comment.py
"""
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import iec61499_network_to_svg as converter  # noqa: E402
FIXTURE = ROOT / "tests" / "fixtures" / "MultilineComment.fbt"
NS = "{http://www.w3.org/2000/svg}"
# The comment lines as the generator displays them (stripped); the second one is wider than
# the minimum network width, so the diagram has to be widened to show it.
EXPECTED = [line.strip() for line in ET.parse(FIXTURE).getroot().get("Comment").splitlines()]


def check(font_size: int) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.svg"
        subprocess.run([sys.executable, str(ROOT / "iec61499_network_to_svg.py"), str(FIXTURE), "-o", str(out),
                        "--font-size", str(font_size)], check=True, capture_output=True)
        root = ET.parse(out).getroot()

    texts = [t for t in root.iter(NS + "text") if t.get("fill") == "#333333" and t.get("font-weight") == "bold"]
    lines = ["".join(t.itertext()) for t in texts]
    errors = []
    if lines != EXPECTED:
        errors.append(f"font size {font_size}: header lines {lines!r}, expected {EXPECTED!r}")
    ys = [float(t.get("y")) for t in texts]
    # lines must not overlap: the baseline distance grows with the font size
    if any(b - a < font_size for a, b in zip(ys, ys[1:])):
        errors.append(f"font size {font_size}: header lines overlap, y positions {ys}")

    # Measure the rendered width with the generator's own bold measurement and compare the
    # text's left and right edge with the viewBox (the comment is drawn left-aligned at x).
    settings = converter.load_block_size_settings()
    settings.font_size = font_size
    engine = converter.NetworkLayoutEngine(settings=settings)
    vb_x, _, vb_w, _ = (float(v) for v in re.split(r"[ ,]+", root.get("viewBox").strip()))
    for t in texts:
        text = "".join(t.itertext())
        left = float(t.get("x"))
        right = left + engine._measure_text(text, bold=True)
        if left < vb_x or right > vb_x + vb_w:
            errors.append(f"font size {font_size}: comment line {text!r} spans x={left:.1f}..{right:.1f}, "
                          f"viewBox x={vb_x:.1f}..{vb_x + vb_w:.1f}")
    return errors


def main() -> int:
    errors = [e for size in (12, 24) for e in check(size)]
    for e in errors:
        print("ERROR:", e)
    if not errors:
        print("OK: multi-line comment is drawn line by line inside the viewBox")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
