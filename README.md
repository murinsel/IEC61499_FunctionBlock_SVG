# IEC 61499 Function Block to SVG Converter

Converts IEC 61499 function block XML definitions (`.fbt`, `.adp`, and `.sub` files) into SVG graphics styled like the [Eclipse 4diac IDE](https://eclipse.dev/4diac/).

Available as both a **Python** script and a **JavaScript** module (browser + Node.js).

## Features

### Single FB Converter
- Parses `FBType`, `AdapterType`, and `SubAppType` XML elements
- Renders event and data ports with type-specific colors matching 4diac IDE
- Draws event-data association lines with connector squares
- Shows external labels with comments and type information
- Supports adapter ports (sockets and plugs)
- Configurable: toggle comments, types, and drop shadow

### Network Diagram Converter
- Renders internal networks of composite FBs and SubApps
- Displays FB instances with ports, connections, and routing
- Interface sidebars for input/output boundary ports
- Type library resolution for correct port ordering
- Orthogonal connection routing with 45-degree beveled corners
- U-turn routing with dx1/dx2/dy bend hints from 4diac XML
- Optional background grid with three hierarchy levels (dotted, dashed, thick dashed)
- Configurable block sizes and margins via INI settings file

### Common
- Uses TGL fonts for authentic technical drawing style
- Dual Python/JavaScript implementations with identical output

## Port Colors (from 4diac IDE)

| Type Category | Color | Types |
|---------------|-------|-------|
| Event | Green `#63B31F` | Event |
| BOOL | Gray-green `#A3B08F` | BOOL |
| Integer | Dark blue `#18519E` | INT, UINT, SINT, DINT, LINT, ANY_INT, ... |
| Real | Gold `#DBB418` | REAL, LREAL, ANY_REAL |
| String | Brown `#BD8663` | STRING, WSTRING, ANY_STRING, CHAR, ... |
| Bit | Blue-gray `#82A3A9` | BYTE, WORD, DWORD, LWORD, ANY_BIT |
| Adapter | Purple `#845DAF` | Adapter types |
| Other | Blue `#3366FF` | Generic data types |

## Usage

### Single FB Converter

Renders individual function block signatures with ports, labels, and association lines.

#### Python

```bash
# Single file
python3 iec61499_to_svg.py input.fbt -o output.svg

# Batch convert directory
python3 iec61499_to_svg.py /path/to/fbt/dir --batch -o /path/to/output

# Print to stdout
python3 iec61499_to_svg.py input.fbt --stdout

# Options
python3 iec61499_to_svg.py input.fbt --no-comments --no-types --no-shadow
```

#### JavaScript (Browser)

Open `test_iec61499_to_svg.html` in a browser. You can:
- Paste XML directly into the textarea
- Use the **Open File...** button to select `.fbt`/`.adp`/`.sub` files
- Download the generated SVG

```javascript
const svg = convertFbtToSvg(xmlString, {
    showComments: true,
    showTypes: true,
    showShadow: true
});
```

#### JavaScript (Node.js)

```bash
node iec61499_to_svg.js input.fbt -o output.svg
```

Requires `jsdom` (`npm install jsdom`).

### Network Diagram Converter

Renders internal network diagrams of composite FBs and SubApps with FB instances, connections, interface sidebars, and an optional background grid.

#### Python

```bash
# Single file
python3 iec61499_network_to_svg.py input.fbt -o output.network.svg

# With type library (recommended for correct port ordering)
python3 iec61499_network_to_svg.py input.fbt -o output.svg --type-lib /path/to/type/library

# With background grid
python3 iec61499_network_to_svg.py input.fbt -o output.svg --grid

# With block size settings
python3 iec61499_network_to_svg.py input.fbt -o output.svg --settings block_size_settings.ini

# Batch convert directory
python3 iec61499_network_to_svg.py /path/to/dir --batch --type-lib /lib/path -o /output/dir

# All options combined
python3 iec61499_network_to_svg.py input.fbt -o output.svg --type-lib /lib/path --grid --settings block_size_settings.ini
```

#### JavaScript (Browser)

Open `test_iec61499_network_to_svg.html` in a browser. Supports file loading, grid toggle, and settings configuration.

#### JavaScript (Node.js)

```bash
node iec61499_network_to_svg.js input.fbt -o output.svg --type-lib /path/to/type/library --grid
```

Requires `jsdom` (`npm install jsdom`).

### Settings File (`block_size_settings.ini`)

Controls block rendering dimensions and type library paths for network diagrams:

```ini
[BlockSize]
max_value_label_size = 25
max_type_label_size = 15
min_pin_label_size = 0
max_pin_label_size = 12
min_interface_bar_size = 0
max_interface_bar_size = 40
max_hidden_connection_label_size = 15

[BlockMargins]
top_bottom = 0
left_right = 0

[TypeLibrary]
; Type library root directories for resolving FB types in network diagrams.
; Use path, path2, path3, ... for multiple directories.
; CLI --type-lib arguments are appended to these paths.
path = /path/to/your/type/library
path2 = /path/to/another/library
```

### Requirements

- **Python**: stdlib only (Python 3). Optional `Pillow` for accurate text measurement (`pip install Pillow`).
- **Node.js**: Requires `jsdom` (`npm install jsdom`).

## Fonts

The `tgl/` directory contains TGL fonts (technical drawing standard) licensed under the [SIL Open Font License](tgl/Open%20Font%20License.txt). Install `TGL 0-17_std.ttf` (regular) and `TGL 0-16_std.ttf` (italic) for best results.

## License

The TGL fonts are licensed under the SIL Open Font License. See `tgl/Open Font License.txt`.
