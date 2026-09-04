#!/usr/bin/env python3
"""Fail if the four converters don't all declare the same version.

Per CLAUDE.md: "The release version is duplicated in all four converters
(__version__ / VERSION) and must be bumped in all four together." There is
no packaging file to derive it from. This is the automated check for that
rule.

Note: this only checks the four files agree with *each other*, not that
the value matches the current git tag - CLAUDE.md's stated tag-matching
requirement isn't enforced here.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "iec61499_to_svg.py",
    "iec61499_network_to_svg.py",
    "iec61499_to_svg.js",
    "iec61499_network_to_svg.js",
]
VERSION_RE = re.compile(r'(?:__version__|VERSION)\s*=\s*["\']([^"\']+)["\']')


def main() -> int:
    versions = {}
    for name in FILES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        match = VERSION_RE.search(text)
        if not match:
            print(f"ERROR: no version constant found in {name}")
            return 1
        versions[name] = match.group(1)

    for name, version in versions.items():
        print(f"{name}: {version}")

    distinct = set(versions.values())
    if len(distinct) != 1:
        print(f"\nERROR: version mismatch across converters: {versions}")
        return 1

    print(f"\nAll four converters agree on version {distinct.pop()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
