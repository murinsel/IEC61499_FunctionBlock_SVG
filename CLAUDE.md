# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Converts IEC 61499 function block XML definitions (`.fbt`, `.adp`, `.sub`, `.fct`) into SVG graphics styled like Eclipse 4diac IDE. Dual Python/JavaScript implementations with mirror functionality.

Two converter pipelines:
- **Single FB converter** (`iec61499_to_svg.py/.js`) — renders individual FB signatures with ports, labels, association lines
- **Network converter** (`iec61499_network_to_svg.py/.js`) — renders internal network diagrams of composite FBs and SubApps with instances, connections, and interface sidebars

## Commands

```bash
# Single FB
python3 iec61499_to_svg.py input.fbt -o output.svg
python3 iec61499_to_svg.py /path/to/dir --batch -o /output/dir
python3 iec61499_to_svg.py input.fbt --stdout --no-comments --no-types --no-shadow

# Network diagram
python3 iec61499_network_to_svg.py input.fbt -o output.network.svg
python3 iec61499_network_to_svg.py /path/to/dir --batch --type-lib /lib/path -o /output/dir

# JavaScript (Node.js, requires: npm install jsdom)
node iec61499_to_svg.js input.fbt -o output.svg
node iec61499_network_to_svg.js input.fbt -o output.svg --type-lib /lib/path

# Convert SVG to PNG
/usr/bin/sips -s format png -o output.png input.svg

# Browser test pages (open directly in browser)
# test_iec61499_to_svg.html — single FB converter
# test_iec61499_network_to_svg.html — network diagram converter
```

Python deps: stdlib only. Optional `Pillow` for accurate text measurement.

## Architecture

```
Input XML → Parser → Data Model → Type Resolver (network only) → Layout Engine → SVG Renderer → SVG
```

### Single FB pipeline
`IEC61499Parser.parse()` → `FunctionBlock` model → `SVGRenderer.render()` computes dimensions and emits SVG elements (block outline, port triangles, association lines, external labels).

### Network pipeline
`NetworkParser.parse()` → `NetworkModel` → `TypeResolver.resolve()` fills instance interfaces from type library or infers from connections → `NetworkLayoutEngine.layout()` computes positions/sizes → `ConnectionRouter.route()` generates orthogonal paths → `NetworkSVGRenderer.render()` emits SVG.

### Key data model classes
- `Port`: name, port_type, comment, associated_vars
- `FunctionBlock`: complete FB signature with all port lists
- `FBInstance`: network instance with position, type, layout fields, port_positions dict
- `Connection`: source, destination, dx1/dx2/dy bend hints, conn_type
- `InterfacePort`: boundary ports rendered in left/right sidebars
- `NetworkModel`: instances, connections, interface ports, computed bounds

### Type resolution (network converter)
TypeResolver indexes `.fbt/.sub/.adp` files by basename and namespace path (`::` separated). Resolution order: filesystem lookup → connection inference (creates ports from connection endpoints).

## Key Constants

Port colors match 4diac IDE: Event `#63B31F`, BOOL `#A3B08F`, Integer `#18519E`, Real `#DBB418`, String `#BD8663`, Bit `#82A3A9`, Adapter `#845DAF`, Other `#3366FF`.

Font stack (default): `TGL, 'Times New Roman', Times, serif` with `@font-face` declarations for TGL 0-17 (regular) and TGL 0-16 (italic). Fonts in `tgl/` directory. Overridable per run via `--font` / `--font-italic` / `--font-size`, or a `[Font]` section in `block_size_settings.ini` (network converters). Overriding both fonts drops the TGL `@font-face` block, which would otherwise misdirect the renderer.

Network layout uses canvas→pixel scale (default 0.05), 20-unit grid snap, auto-scaling from instance bounds.

## Implementation Notes

- Python and JS versions must be kept in sync — changes to rendering logic need to be applied to both
- The release version is duplicated in all four converters (`__version__` / `VERSION`) and must be
  bumped in all four together, matching the git tag. There is no packaging file to derive it from.
- Port triangles: left-side triangles have base at x=0 (left FB border), tip points right; right-side triangles have tip at x=block_width (right FB border)
- Connection endpoints resolve to triangle apex coordinates via `port_positions` dict (absolute coords)
- JS `interfaceMap` is a plain object (not a Map) — use `in` operator, not `.has()`
- Text measurement: Pillow `ImageFont` if available, fallback to char_count * avg_width.
  **Measure the advance width (`getlength`), never the ink extent (`getbbox`)**, and open
  faces at `MEASURE_SUPERSAMPLE`x the nominal size, dividing the result back down: Pillow's
  basic layout rounds every glyph advance to a whole pixel (Menlo at 12px advances 7.228px
  but reports 7.0), and over a long label the error accumulates until the text overruns the
  canvas the layout computed for it. Raqm would give subpixel advances directly but is
  frequently absent from Pillow builds. The JS converters measure via Canvas `measureText`,
  which is already subpixel — they need no equivalent workaround.
- Measuring font vs rendering font must agree. The JS `_measureText` has to expand the bare
  `TGL` family to its `_std` face names, because a measurement canvas does not see the SVG's
  `@font-face` block.
- SVG uses `<polygon>` for port triangles, `<path>` for adapter symbols and connections
