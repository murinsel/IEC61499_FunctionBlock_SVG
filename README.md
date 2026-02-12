# IEC 61499 Function Block to SVG Converter

Converts IEC 61499 function block XML definitions (`.fbt`, `.adp`, and `.sub` files) into SVG graphics styled like the [Eclipse 4diac IDE](https://eclipse.dev/4diac/).

Available as both a **Python** script and a **JavaScript** module (browser + Node.js).

## Features

- Parses `FBType`, `AdapterType`, and `SubAppType` XML elements
- Renders event and data ports with type-specific colors matching 4diac IDE
- Draws event-data association lines with connector squares
- Shows external labels with comments and type information
- Supports adapter ports (sockets and plugs)
- Configurable: toggle comments, types, and drop shadow
- Uses TGL fonts for authentic technical drawing style

## Port Colors (from 4diac IDE)

| Type Category | Color | Types |
|---------------|-------|-------|
| Event | Green `#63B31F` | Event |
| BOOL | Gray-green `#9FA48A` | BOOL |
| Integer | Dark blue `#18519E` | INT, UINT, SINT, DINT, LINT, ANY_INT, ... |
| Real | Gold `#DBB418` | REAL, LREAL, ANY_REAL |
| String | Brown `#BD8663` | STRING, WSTRING, ANY_STRING, CHAR, ... |
| Bit | Blue-gray `#82A3A9` | BYTE, WORD, DWORD, LWORD, ANY_BIT |
| Adapter | Purple `#845DAF` | Adapter types |
| Other | Blue `#0000FF` | Generic data types |

## Usage

### Python

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

Requires Python 3. Optional: `Pillow` for accurate text measurement (`pip install Pillow`).

### JavaScript (Browser)

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

### JavaScript (Node.js)

```bash
node iec61499_to_svg.js input.fbt -o output.svg
```

Requires `jsdom` (`npm install jsdom`).

## Fonts

The `tgl/` directory contains TGL fonts (technical drawing standard) licensed under the [SIL Open Font License](tgl/Open%20Font%20License.txt). Install `TGL 0-17.ttf` (regular) and `TGL 0-16.ttf` (italic) for best results.

## License

The TGL fonts are licensed under the SIL Open Font License. See `tgl/Open Font License.txt`.
