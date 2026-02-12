/**
 * IEC 61499 Function Block to SVG Converter
 *
 * Converts IEC 61499 function block XML definitions (.fbt files) to SVG graphics
 * in the style of 4diac IDE.
 *
 * Usage (Node.js):
 *   node iec61499_to_svg.js input.fbt [-o output.svg] [--no-comments] [--no-types] [--no-shadow]
 *
 * Usage (Browser):
 *   const svg = convertFbtToSvg(xmlString, options);
 */

// Port class
class Port {
    constructor(name, portType = "", comment = "", associatedVars = []) {
        this.name = name;
        this.portType = portType;
        this.comment = comment;
        this.associatedVars = associatedVars;
    }
}

// FunctionBlock class
class FunctionBlock {
    constructor(name, comment = "", fbType = "BasicFB", version = "") {
        this.name = name;
        this.comment = comment;
        this.fbType = fbType;
        this.version = version;
        this.eventInputs = [];
        this.eventOutputs = [];
        this.dataInputs = [];
        this.dataOutputs = [];
        this.plugs = [];
        this.sockets = [];
    }
}

// Parser for IEC 61499 XML
class IEC61499Parser {
    parse(xmlString) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlString, "text/xml");
        const root = doc.documentElement;

        if (root.tagName === "FBType") {
            return this._parseFbtype(root);
        } else if (root.tagName === "AdapterType") {
            return this._parseAdapter(root);
        } else if (root.tagName === "SubAppType") {
            return this._parseSubapp(root);
        } else {
            throw new Error(`Unknown root element: ${root.tagName}`);
        }
    }

    _parseFbtype(root) {
        const fb = new FunctionBlock(
            root.getAttribute("Name") || "Unknown",
            root.getAttribute("Comment") || ""
        );

        const versionInfo = root.querySelector("VersionInfo");
        if (versionInfo) {
            fb.version = versionInfo.getAttribute("Version") || "";
        }

        if (root.querySelector("BasicFB")) {
            fb.fbType = "BasicFB";
        } else if (root.querySelector("CompositeFB")) {
            fb.fbType = "CompositeFB";
        } else if (root.querySelector("SimpleFB")) {
            fb.fbType = "SimpleFB";
        } else {
            fb.fbType = "ServiceInterfaceFB";
        }

        const interfaceList = root.querySelector("InterfaceList");
        if (interfaceList) {
            this._parseInterface(interfaceList, fb);
        }

        return fb;
    }

    _parseAdapter(root) {
        const fb = new FunctionBlock(
            root.getAttribute("Name") || "Unknown",
            root.getAttribute("Comment") || "",
            "Adapter"
        );

        const versionInfo = root.querySelector("VersionInfo");
        if (versionInfo) {
            fb.version = versionInfo.getAttribute("Version") || "";
        }

        const interfaceList = root.querySelector("InterfaceList");
        if (interfaceList) {
            this._parseInterface(interfaceList, fb);
        }

        return fb;
    }

    _parseSubapp(root) {
        const fb = new FunctionBlock(
            root.getAttribute("Name") || "Unknown",
            root.getAttribute("Comment") || "",
            "SubApp"
        );

        const versionInfo = root.querySelector("VersionInfo");
        if (versionInfo) {
            fb.version = versionInfo.getAttribute("Version") || "";
        }

        // SubApps can use either InterfaceList or SubAppInterfaceList
        const interfaceList = root.querySelector("SubAppInterfaceList") || root.querySelector("InterfaceList");
        if (interfaceList) {
            this._parseInterface(interfaceList, fb);
        }

        return fb;
    }

    _parseInterface(interfaceList, fb) {
        // Event inputs (support both standard and SubApp tags)
        const eventInputs = interfaceList.querySelector("EventInputs") || interfaceList.querySelector("SubAppEventInputs");
        if (eventInputs) {
            const events = eventInputs.querySelectorAll("Event");
            const eventList = events.length > 0 ? events : eventInputs.querySelectorAll("SubAppEvent");
            for (const event of eventList) {
                const withElements = event.querySelectorAll("With");
                const associatedVars = Array.from(withElements).map(w => w.getAttribute("Var") || "");
                const port = new Port(
                    event.getAttribute("Name") || "",
                    "Event",
                    event.getAttribute("Comment") || "",
                    associatedVars
                );
                fb.eventInputs.push(port);
            }
        }

        // Event outputs (support both standard and SubApp tags)
        const eventOutputs = interfaceList.querySelector("EventOutputs") || interfaceList.querySelector("SubAppEventOutputs");
        if (eventOutputs) {
            const events = eventOutputs.querySelectorAll("Event");
            const eventList = events.length > 0 ? events : eventOutputs.querySelectorAll("SubAppEvent");
            for (const event of eventList) {
                const withElements = event.querySelectorAll("With");
                const associatedVars = Array.from(withElements).map(w => w.getAttribute("Var") || "");
                const port = new Port(
                    event.getAttribute("Name") || "",
                    "Event",
                    event.getAttribute("Comment") || "",
                    associatedVars
                );
                fb.eventOutputs.push(port);
            }
        }

        // Input vars
        const inputVars = interfaceList.querySelector("InputVars");
        if (inputVars) {
            for (const varDecl of inputVars.querySelectorAll("VarDeclaration")) {
                const port = new Port(
                    varDecl.getAttribute("Name") || "",
                    varDecl.getAttribute("Type") || "",
                    varDecl.getAttribute("Comment") || ""
                );
                fb.dataInputs.push(port);
            }
        }

        // Output vars
        const outputVars = interfaceList.querySelector("OutputVars");
        if (outputVars) {
            for (const varDecl of outputVars.querySelectorAll("VarDeclaration")) {
                const port = new Port(
                    varDecl.getAttribute("Name") || "",
                    varDecl.getAttribute("Type") || "",
                    varDecl.getAttribute("Comment") || ""
                );
                fb.dataOutputs.push(port);
            }
        }

        // Plugs
        const plugs = interfaceList.querySelector("Plugs");
        if (plugs) {
            for (const adapter of plugs.querySelectorAll("AdapterDeclaration")) {
                const port = new Port(
                    adapter.getAttribute("Name") || "",
                    adapter.getAttribute("Type") || "",
                    adapter.getAttribute("Comment") || ""
                );
                fb.plugs.push(port);
            }
        }

        // Sockets
        const sockets = interfaceList.querySelector("Sockets");
        if (sockets) {
            for (const adapter of sockets.querySelectorAll("AdapterDeclaration")) {
                const port = new Port(
                    adapter.getAttribute("Name") || "",
                    adapter.getAttribute("Type") || "",
                    adapter.getAttribute("Comment") || ""
                );
                fb.sockets.push(port);
            }
        }
    }
}

// SVG Renderer
class SVGRenderer {
    constructor(options = {}) {
        this.showComments = options.showComments !== false;
        this.showTypes = options.showTypes !== false;
        this.showShadow = options.showShadow !== false;

        // Constants
        this.FONT_FAMILY = "'TGL 0-17', 'Helvetica Neue', Helvetica, Arial, sans-serif";
        this.FONT_FAMILY_ITALIC = "'TGL 0-16', 'Helvetica Neue', Helvetica, Arial, sans-serif";
        this.FONT_SIZE = 14;

        // Canvas for text measurement
        this._measureCanvas = null;
        this._measureContext = null;
        // Colors (from 4diac IDE plugin.xml)
        this.BLOCK_STROKE_COLOR = "#A0A0A0";
        this.EVENT_PORT_COLOR = "#63B31F";    // (99,179,31)
        this.BOOL_PORT_COLOR = "#9FA48A";     // (159,164,138)
        this.ANY_BIT_PORT_COLOR = "#82A3A9";  // (130,163,169)
        this.ANY_INT_PORT_COLOR = "#18519E";  // (24,81,158)
        this.ANY_REAL_PORT_COLOR = "#DBB418";  // (219,180,24)
        this.STRING_PORT_COLOR = "#BD8663";   // (189,134,99)
        this.DATA_PORT_COLOR = "#0000FF";     // (0,0,255)
        this.ADAPTER_PORT_COLOR = "#845DAF";  // (132,93,175)

        // Type name sets for color mapping
        this.STRING_TYPES = new Set(["STRING", "WSTRING", "ANY_STRING", "ANY_CHARS", "CHAR", "WCHAR"]);
        this.INT_TYPES = new Set(["INT", "UINT", "SINT", "USINT", "DINT", "UDINT", "LINT", "ULINT", "ANY_INT", "ANY_NUM"]);
        this.REAL_TYPES = new Set(["REAL", "LREAL", "ANY_REAL"]);
        this.BIT_TYPES = new Set(["BYTE", "WORD", "DWORD", "LWORD", "ANY_BIT"]);
        this.PORT_ROW_HEIGHT = 20;
        this.BLOCK_PADDING = 10;
        this.NAME_SECTION_HEIGHT = 40;
        this.CONNECTOR_WIDTH = 10;
        this.CONNECTOR_HEIGHT = 10;
        this.TRIANGLE_WIDTH = 5;
        this.TRIANGLE_HEIGHT = 10;

        // Calculated dimensions
        this.blockLeft = 0;
        this.blockRight = 0;
        this.blockWidth = 0;
        this.blockHeight = 0;
        this.eventSectionHeight = 0;
        this.dataSectionHeight = 0;
        this.nameSectionTop = 0;
        this.nameSectionBottom = 0;
        this.adapterSectionTop = 0;
        this.adapterSectionHeight = 0;

        // Port positions
        this.eventInputY = {};
        this.eventOutputY = {};
        this.dataInputY = {};
        this.dataOutputY = {};
        this.socketY = {};
        this.plugY = {};

        // Connector positions
        this.leftmostConnectorX = 0;
        this.rightmostConnectorX = 0;

        // Margins
        this.leftMargin = 0;
        this.rightMargin = 0;
        this.maxLeftLabelWidth = 0;
        this.maxRightLabelWidth = 0;
        this.leftConnectorSpace = 0;
        this.rightConnectorSpace = 0;
    }

    /**
     * Initialize canvas for text measurement
     * @private
     */
    _initMeasureCanvas() {
        if (this._measureCanvas) return;

        if (typeof document !== 'undefined') {
            // Browser environment
            this._measureCanvas = document.createElement('canvas');
            this._measureContext = this._measureCanvas.getContext('2d');
        } else if (typeof require !== 'undefined') {
            // Node.js environment - try to use canvas package
            try {
                const { createCanvas } = require('canvas');
                this._measureCanvas = createCanvas(1, 1);
                this._measureContext = this._measureCanvas.getContext('2d');
            } catch (e) {
                // canvas package not available, will use fallback
                this._measureCanvas = null;
                this._measureContext = null;
            }
        }
    }

    /**
     * Measure text width using canvas
     * @param {string} text - The text to measure
     * @param {number} fontSize - Font size in pixels
     * @param {boolean} italic - Whether to use italic style
     * @returns {number} Text width in pixels
     */
    _getPortColor(portType) {
        if (portType === "BOOL") return this.BOOL_PORT_COLOR;
        if (this.STRING_TYPES.has(portType)) return this.STRING_PORT_COLOR;
        if (this.INT_TYPES.has(portType)) return this.ANY_INT_PORT_COLOR;
        if (this.REAL_TYPES.has(portType)) return this.ANY_REAL_PORT_COLOR;
        if (this.BIT_TYPES.has(portType)) return this.ANY_BIT_PORT_COLOR;
        return this.DATA_PORT_COLOR;
    }

    _measureText(text, fontSize = this.FONT_SIZE, italic = false) {
        this._initMeasureCanvas();

        if (this._measureContext) {
            const fontStyle = italic ? 'italic ' : '';
            // Use sans-serif as fallback for measurement since TGL fonts may not be available
            this._measureContext.font = `${fontStyle}${fontSize}px 'TGL 0-17', 'Helvetica Neue', Helvetica, Arial, sans-serif`;
            return this._measureContext.measureText(text).width;
        }

        // Fallback: estimate based on character count
        const avgCharWidth = fontSize * 0.6;
        return text.length * avgCharWidth;
    }

    render(fb) {
        this._calculateDimensions(fb);

        // Initialize connector positions
        this.leftmostConnectorX = -this.CONNECTOR_WIDTH - 5;
        this.rightmostConnectorX = this.blockWidth + 5 + this.CONNECTOR_WIDTH;

        const parts = [];
        parts.push(this._svgHeader());
        parts.push(this._renderBlockOutline(fb));
        parts.push(this._renderEventPorts(fb));
        parts.push(this._renderNameSection(fb));
        parts.push(this._renderDataPorts(fb));
        parts.push(this._renderAdapterPorts(fb));
        parts.push(this._renderAssociationLines(fb));
        parts.push(this._renderExternalLabels(fb));
        parts.push(this._svgFooter());

        return parts.join("\n");
    }

    _calculateDimensions(fb) {
        const numEventInputs = fb.eventInputs.length;
        const numEventOutputs = fb.eventOutputs.length;
        const numDataInputs = fb.dataInputs.length;
        const numDataOutputs = fb.dataOutputs.length;
        const numSockets = fb.sockets.length;
        const numPlugs = fb.plugs.length;

        const numEventRows = Math.max(numEventInputs, numEventOutputs, 1);
        const numDataRows = Math.max(numDataInputs, numDataOutputs, 1);

        const sectionPadding = this.PORT_ROW_HEIGHT / 2 - 4;
        this.eventSectionHeight = numEventRows * this.PORT_ROW_HEIGHT + sectionPadding;
        this.dataSectionHeight = numDataRows * this.PORT_ROW_HEIGHT + sectionPadding;

        const numAdapterRows = Math.max(numSockets, numPlugs);
        this.adapterSectionHeight = numAdapterRows > 0 ? numAdapterRows * this.PORT_ROW_HEIGHT : 0;

        this.blockHeight = this.eventSectionHeight + this.NAME_SECTION_HEIGHT +
                          this.dataSectionHeight + this.adapterSectionHeight;

        const notch = 10;
        const textStartX = notch + 5 + 18 + 5;
        const nameWidth = this._measureText(fb.name, this.FONT_SIZE, true);
        const nameSectionWidth = textStartX + nameWidth + 15 + notch;

        const triangleSpace = this.TRIANGLE_WIDTH + 3 + 1.5;
        const adapterSpace = this.TRIANGLE_WIDTH * 2 + 3 + 1.5;

        let maxLeftPortWidth = 0;
        for (const port of [...fb.eventInputs, ...fb.dataInputs]) {
            const portWidth = triangleSpace + this._measureText(port.name, this.FONT_SIZE, false);
            maxLeftPortWidth = Math.max(maxLeftPortWidth, portWidth);
        }
        for (const port of fb.sockets) {
            const portWidth = adapterSpace + this._measureText(port.name, this.FONT_SIZE, false);
            maxLeftPortWidth = Math.max(maxLeftPortWidth, portWidth);
        }

        let maxRightPortWidth = 0;
        for (const port of [...fb.eventOutputs, ...fb.dataOutputs]) {
            const portWidth = triangleSpace + this._measureText(port.name, this.FONT_SIZE, false);
            maxRightPortWidth = Math.max(maxRightPortWidth, portWidth);
        }
        for (const port of fb.plugs) {
            const portWidth = adapterSpace + this._measureText(port.name, this.FONT_SIZE, false);
            maxRightPortWidth = Math.max(maxRightPortWidth, portWidth);
        }

        const minCenterGap = 20;
        const portsWidth = maxLeftPortWidth + minCenterGap + maxRightPortWidth;

        this.blockWidth = Math.max(100, nameSectionWidth, portsWidth);

        this.nameSectionTop = this.eventSectionHeight;
        this.nameSectionBottom = this.eventSectionHeight + this.NAME_SECTION_HEIGHT;
        this.adapterSectionTop = this.nameSectionBottom + this.dataSectionHeight;

        // Calculate label widths
        this.maxLeftLabelWidth = 0;
        for (const port of fb.eventInputs) {
            const labelWidth = this._calculateLabelWidth(port, true, true);
            this.maxLeftLabelWidth = Math.max(this.maxLeftLabelWidth, labelWidth);
        }
        for (const port of fb.dataInputs) {
            const labelWidth = this._calculateLabelWidth(port, false, true);
            this.maxLeftLabelWidth = Math.max(this.maxLeftLabelWidth, labelWidth);
        }
        for (const port of fb.sockets) {
            const labelWidth = this._calculateLabelWidth(port, false, true);
            this.maxLeftLabelWidth = Math.max(this.maxLeftLabelWidth, labelWidth);
        }

        this.maxRightLabelWidth = 0;
        for (const port of fb.eventOutputs) {
            const labelWidth = this._calculateLabelWidth(port, true, false);
            this.maxRightLabelWidth = Math.max(this.maxRightLabelWidth, labelWidth);
        }
        for (const port of fb.dataOutputs) {
            const labelWidth = this._calculateLabelWidth(port, false, false);
            this.maxRightLabelWidth = Math.max(this.maxRightLabelWidth, labelWidth);
        }
        for (const port of fb.plugs) {
            const labelWidth = this._calculateLabelWidth(port, false, false);
            this.maxRightLabelWidth = Math.max(this.maxRightLabelWidth, labelWidth);
        }

        // Calculate connector space
        const cw = this.CONNECTOR_WIDTH;
        const gap = 5;
        const lineSpacing = cw + 4;
        const labelGap = 10;

        const numLeftEventsWithAssoc = fb.eventInputs.filter(e => e.associatedVars.length > 0).length;
        const numRightEventsWithAssoc = fb.eventOutputs.filter(e => e.associatedVars.length > 0).length;

        if (numLeftEventsWithAssoc > 0) {
            const leftmostX = -cw - gap - (numLeftEventsWithAssoc - 1) * lineSpacing;
            this.leftConnectorSpace = Math.abs(leftmostX - labelGap);
        } else {
            // Even without associations, labels need space from block edge
            // Default: gap (5) + connector_width (10) + label_gap (10) = 25
            this.leftConnectorSpace = gap + cw + labelGap;
        }

        if (numRightEventsWithAssoc > 0) {
            const rightmostX = gap + (numRightEventsWithAssoc - 1) * lineSpacing + cw;
            this.rightConnectorSpace = rightmostX + labelGap;
        } else {
            // Even without associations, labels need space from block edge
            // Default: gap (5) + connector_width (10) + label_gap (10) = 25
            this.rightConnectorSpace = gap + cw + labelGap;
        }
    }

    _calculateLabelWidth(port, isEvent, isLeft) {
        const dashWidth = this._measureText(" – ", this.FONT_SIZE, false);

        let labelWidth = 0;
        if (this.showComments && port.comment) {
            labelWidth += this._measureText(port.comment, this.FONT_SIZE, false);
        }
        if (this.showTypes) {
            if (labelWidth > 0) {
                labelWidth += dashWidth;
            }
            if (isEvent) {
                labelWidth += this._measureText("Event", this.FONT_SIZE, true);
            } else {
                const typeName = port.portType.includes("::")
                    ? port.portType.split("::").pop()
                    : port.portType;
                labelWidth += this._measureText(typeName, this.FONT_SIZE, true);
            }
        }

        return labelWidth;
    }

    _svgHeader() {
        this.leftMargin = this.maxLeftLabelWidth + this.leftConnectorSpace + 10;
        this.rightMargin = this.maxRightLabelWidth + this.rightConnectorSpace + 10;
        const topMargin = 10;
        const bottomMargin = 10;

        this.blockLeft = this.leftMargin;
        this.blockRight = this.leftMargin + this.blockWidth;

        const totalWidth = this.leftMargin + this.blockWidth + this.rightMargin;
        const totalHeight = this.blockHeight + topMargin + bottomMargin;

        let shadowDefs = "";
        if (this.showShadow) {
            shadowDefs = `
  <defs>
    <filter id="dropShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="blur"/>
      <feOffset in="blur" dx="1" dy="1" result="offsetBlur"/>
      <feFlood flood-color="#000000" flood-opacity="0.5" result="shadowColor"/>
      <feComposite in="shadowColor" in2="offsetBlur" operator="in" result="shadow"/>
      <feMerge>
        <feMergeNode in="shadow"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>`;
        }

        return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 ${totalWidth} ${totalHeight}"
     width="${totalWidth}" height="${totalHeight}">${shadowDefs}
  <g transform="translate(${this.leftMargin}, ${topMargin})">`;
    }

    _svgFooter() {
        return "  </g>\n</svg>";
    }

    _renderBlockOutline(fb) {
        const notch = 10;
        const r = 3;
        const et = this.eventSectionHeight;
        const nb = this.nameSectionBottom;
        const w = this.blockWidth;
        const h = this.blockHeight;

        const pathD = `M ${r} 0
            L ${w - r} 0
            A ${r} ${r} 0 0 1 ${w} ${r}
            L ${w} ${et - r}
            A ${r} ${r} 0 0 1 ${w - r} ${et}
            L ${w - notch} ${et}
            L ${w - notch} ${nb}
            L ${w - r} ${nb}
            A ${r} ${r} 0 0 1 ${w} ${nb + r}
            L ${w} ${h - r}
            A ${r} ${r} 0 0 1 ${w - r} ${h}
            L ${r} ${h}
            A ${r} ${r} 0 0 1 0 ${h - r}
            L 0 ${nb + r}
            A ${r} ${r} 0 0 1 ${r} ${nb}
            L ${notch} ${nb}
            L ${notch} ${et}
            L ${r} ${et}
            A ${r} ${r} 0 0 1 0 ${et - r}
            L 0 ${r}
            A ${r} ${r} 0 0 1 ${r} 0
            Z`;

        const filterAttr = this.showShadow ? ' filter="url(#dropShadow)"' : '';

        return `
    <!-- Block Outline -->
    <path d="${pathD}"
          fill="#FFFFFF" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="1.5"
          stroke-linejoin="round"${filterAttr}/>`;
    }

    _renderEventPorts(fb) {
        const parts = [];
        parts.push("\n    <!-- Event Ports -->");

        const topPadding = this.PORT_ROW_HEIGHT / 2 - 4;

        // Event inputs
        let y = this.PORT_ROW_HEIGHT / 2 + topPadding;
        for (const port of fb.eventInputs) {
            this.eventInputY[port.name] = y;
            parts.push(this._renderEventInputPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        // Event outputs
        y = this.PORT_ROW_HEIGHT / 2 + topPadding;
        for (const port of fb.eventOutputs) {
            this.eventOutputY[port.name] = y;
            parts.push(this._renderEventOutputPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderEventInputPort(port, y) {
        const tw = this.TRIANGLE_WIDTH;
        const th = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const triX = strokeOffset;
        const triPoints = `${triX},${y - th/2} ${triX + tw},${y} ${triX},${y + th/2}`;
        const textX = triX + tw + 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;

        return `
    <polygon points="${triPoints}" fill="${this.EVENT_PORT_COLOR}"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${port.name}</text>`;
    }

    _renderEventOutputPort(port, y) {
        const w = this.blockWidth;
        const tw = this.TRIANGLE_WIDTH;
        const th = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const triX = w - tw - strokeOffset;
        const triPoints = `${triX},${y - th/2} ${triX + tw},${y} ${triX},${y + th/2}`;
        const textX = triX - 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;

        return `
    <polygon points="${triPoints}" fill="${this.EVENT_PORT_COLOR}"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${port.name}</text>`;
    }

    _miniFbPath(x, y, w, h) {
        const nd = w * 0.15;      // notch depth (horizontal)
        const nh = h / 6;         // notch height
        const nt = y + h / 4;     // notch top y
        const nb = nt + nh;       // notch bottom y
        const r = 0.5;            // corner radius
        return (
            `M ${x + r} ${y}` +
            ` L ${x + w - r} ${y}` +
            ` A ${r} ${r} 0 0 1 ${x + w} ${y + r}` +
            ` L ${x + w} ${nt}` +
            ` L ${x + w - nd} ${nt}` +
            ` L ${x + w - nd} ${nb}` +
            ` L ${x + w} ${nb}` +
            ` L ${x + w} ${y + h - r}` +
            ` A ${r} ${r} 0 0 1 ${x + w - r} ${y + h}` +
            ` L ${x + r} ${y + h}` +
            ` A ${r} ${r} 0 0 1 ${x} ${y + h - r}` +
            ` L ${x} ${nb}` +
            ` L ${x + nd} ${nb}` +
            ` L ${x + nd} ${nt}` +
            ` L ${x} ${nt}` +
            ` L ${x} ${y + r}` +
            ` A ${r} ${r} 0 0 1 ${x + r} ${y}` +
            ` Z`
        );
    }

    _renderNameSection(fb) {
        const centerY = this.nameSectionTop + this.NAME_SECTION_HEIGHT / 2;

        let iconLetter;
        if (fb.fbType === "BasicFB") {
            iconLetter = "B";
        } else if (fb.fbType === "CompositeFB") {
            iconLetter = "C";
        } else if (fb.fbType === "ServiceInterfaceFB") {
            iconLetter = "Si";
        } else {
            iconLetter = "S";
        }

        let versionText = "";
        if (fb.version) {
            versionText = `
    <text x="${this.blockWidth / 2}" y="${centerY + 20}"
          font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE - 2}"
          fill="#666666" text-anchor="middle">${fb.version}</text>`;
        }

        const iconW = 18;
        const iconH = 18;
        const iconNotchDepth = 2;
        const iconNotchHeight = iconH / 6;
        const iconR = 1;
        const gapIconText = 5;

        const nameWidth = this._measureText(fb.name, this.FONT_SIZE, true);
        const totalContentWidth = iconW + gapIconText + nameWidth;
        const contentStartX = (this.blockWidth - totalContentWidth) / 2;

        const iconX = contentStartX;
        const iconY = centerY - 9;
        const iconNotchTop = iconY + iconH / 4;
        const iconNotchBottom = iconNotchTop + iconNotchHeight;

        const iconPath = `M ${iconX + iconR} ${iconY}
            L ${iconX + iconW - iconR} ${iconY}
            A ${iconR} ${iconR} 0 0 1 ${iconX + iconW} ${iconY + iconR}
            L ${iconX + iconW} ${iconNotchTop}
            L ${iconX + iconW - iconNotchDepth} ${iconNotchTop}
            L ${iconX + iconW - iconNotchDepth} ${iconNotchBottom}
            L ${iconX + iconW} ${iconNotchBottom}
            L ${iconX + iconW} ${iconY + iconH - iconR}
            A ${iconR} ${iconR} 0 0 1 ${iconX + iconW - iconR} ${iconY + iconH}
            L ${iconX + iconR} ${iconY + iconH}
            A ${iconR} ${iconR} 0 0 1 ${iconX} ${iconY + iconH - iconR}
            L ${iconX} ${iconNotchBottom}
            L ${iconX + iconNotchDepth} ${iconNotchBottom}
            L ${iconX + iconNotchDepth} ${iconNotchTop}
            L ${iconX} ${iconNotchTop}
            L ${iconX} ${iconY + iconR}
            A ${iconR} ${iconR} 0 0 1 ${iconX + iconR} ${iconY}
            Z`;

        const textX = iconX + iconW + gapIconText;

        // Icon content: text letter for most types, graphic for SubApp
        let iconContent;
        if (fb.fbType === "SubApp") {
            // Draw two mini notched function blocks (same shape as the icon box)
            // with dark blue fill, connected by a horizontal line
            // Positioned in the lower part of the light blue icon box
            const miniW = 5.5;
            const miniH = 7;
            const miniGap = 3;
            const pairW = miniW * 2 + miniGap;
            const pairX = iconX + (iconW - pairW) / 2;
            const pairY = iconY + iconH - miniH - 1.5;

            const leftPath = this._miniFbPath(pairX, pairY, miniW, miniH);
            const rightPath = this._miniFbPath(pairX + miniW + miniGap, pairY, miniW, miniH);

            const connX1 = pairX + miniW;
            const connX2 = pairX + miniW + miniGap;
            // Upper event line (green, near top of mini FBs)
            const eventConnY = pairY + miniH * 0.12;
            // Lower data line (red, in lower portion of mini FBs)
            const dataConnY = pairY + miniH * 0.7;

            iconContent = `
    <path d="${leftPath}" fill="#1565C0" stroke="none"/>
    <path d="${rightPath}" fill="#1565C0" stroke="none"/>
    <line x1="${connX1}" y1="${eventConnY}" x2="${connX2}" y2="${eventConnY}"
          stroke="#3DA015" stroke-width="1.2"/>
    <line x1="${connX1}" y1="${dataConnY}" x2="${connX2}" y2="${dataConnY}"
          stroke="#FF0000" stroke-width="1.2"/>`;
        } else {
            iconContent = `
    <text x="${iconX + iconW / 2}" y="${centerY + 5}"
          font-family="${this.FONT_FAMILY}" font-size="12" font-weight="bold"
          fill="#000000" text-anchor="middle">${iconLetter}</text>`;
        }

        return `
    <!-- Name Section -->
    <!-- FB Type Icon -->
    <path d="${iconPath}"
          fill="#87CEEB" stroke="#1565C0" stroke-width="1"/>${iconContent}

    <!-- Block Name -->
    <text x="${textX}" y="${centerY + 5}"
          font-family="${this.FONT_FAMILY_ITALIC}" font-size="${this.FONT_SIZE}"
          fill="#000000">${fb.name}</text>
    ${versionText}`;
    }

    _renderDataPorts(fb) {
        const parts = [];
        parts.push("\n    <!-- Data Ports -->");

        const baseY = this.nameSectionBottom;

        // Data inputs
        let y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const port of fb.dataInputs) {
            this.dataInputY[port.name] = y;
            parts.push(this._renderDataInputPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        // Data outputs
        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const port of fb.dataOutputs) {
            this.dataOutputY[port.name] = y;
            parts.push(this._renderDataOutputPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderDataInputPort(port, y) {
        const tw = this.TRIANGLE_WIDTH;
        const th = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const triX = strokeOffset;
        const triPoints = `${triX},${y - th/2} ${triX + tw},${y} ${triX},${y + th/2}`;
        const textX = triX + tw + 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;
        const fillColor = this._getPortColor(port.portType);

        return `
    <polygon points="${triPoints}" fill="${fillColor}"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${port.name}</text>`;
    }

    _renderDataOutputPort(port, y) {
        const w = this.blockWidth;
        const tw = this.TRIANGLE_WIDTH;
        const th = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const triX = w - tw - strokeOffset;
        const triPoints = `${triX},${y - th/2} ${triX + tw},${y} ${triX},${y + th/2}`;
        const textX = triX - 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;
        const fillColor = this._getPortColor(port.portType);

        return `
    <polygon points="${triPoints}" fill="${fillColor}"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${port.name}</text>`;
    }

    _renderAdapterPorts(fb) {
        if (fb.sockets.length === 0 && fb.plugs.length === 0) {
            return "";
        }

        const parts = [];
        parts.push("\n    <!-- Adapter Ports -->");

        const baseY = this.adapterSectionTop;

        // Sockets
        let y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const port of fb.sockets) {
            this.socketY[port.name] = y;
            parts.push(this._renderSocketPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        // Plugs
        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const port of fb.plugs) {
            this.plugY[port.name] = y;
            parts.push(this._renderPlugPort(port, y));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderSocketPort(port, y) {
        const rectW = this.TRIANGLE_WIDTH * 2;
        const rectH = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const rectX = strokeOffset;
        const rectY = y - rectH / 2;
        const notchStart = rectX + rectW / 2;
        const notchWidth = rectW / 4;
        const notchDepth = rectH / 6;

        const pathD = `M ${rectX} ${rectY}
            L ${notchStart} ${rectY}
            L ${notchStart} ${rectY + notchDepth}
            L ${notchStart + notchWidth} ${rectY + notchDepth}
            L ${notchStart + notchWidth} ${rectY}
            L ${rectX + rectW} ${rectY}
            L ${rectX + rectW} ${rectY + rectH}
            L ${notchStart + notchWidth} ${rectY + rectH}
            L ${notchStart + notchWidth} ${rectY + rectH - notchDepth}
            L ${notchStart} ${rectY + rectH - notchDepth}
            L ${notchStart} ${rectY + rectH}
            L ${rectX} ${rectY + rectH}
            Z`;

        const textX = rectX + rectW + 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;
        const adapterColor = this.ADAPTER_PORT_COLOR;

        return `
    <path d="${pathD}" fill="none" stroke="${adapterColor}" stroke-width="1"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${port.name}</text>`;
    }

    _renderPlugPort(port, y) {
        const w = this.blockWidth;
        const rectW = this.TRIANGLE_WIDTH * 2;
        const rectH = this.TRIANGLE_HEIGHT;
        const strokeOffset = 1.5;
        const rectX = w - rectW - strokeOffset;
        const rectY = y - rectH / 2;
        const notchStart = rectX + rectW / 4;
        const notchWidth = rectW / 4;
        const notchDepth = rectH / 6;

        const pathD = `M ${rectX} ${rectY}
            L ${notchStart} ${rectY}
            L ${notchStart} ${rectY + notchDepth}
            L ${notchStart + notchWidth} ${rectY + notchDepth}
            L ${notchStart + notchWidth} ${rectY}
            L ${rectX + rectW} ${rectY}
            L ${rectX + rectW} ${rectY + rectH}
            L ${notchStart + notchWidth} ${rectY + rectH}
            L ${notchStart + notchWidth} ${rectY + rectH - notchDepth}
            L ${notchStart} ${rectY + rectH - notchDepth}
            L ${notchStart} ${rectY + rectH}
            L ${rectX} ${rectY + rectH}
            Z`;

        const textX = rectX - 3;
        // Text baseline adjustment for TGL font
        const textY = y + 1;
        const adapterColor = this.ADAPTER_PORT_COLOR;

        return `
    <path d="${pathD}" fill="${adapterColor}"/>
    <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${port.name}</text>`;
    }

    _renderAssociationLines(fb) {
        const parts = [];
        parts.push("\n    <!-- Event-Data Association Connectors and Lines -->");

        const cw = this.CONNECTOR_WIDTH;
        const ch = this.CONNECTOR_HEIGHT;
        const gap = 5;
        const lineSpacing = cw + 4;
        const overhang = gap;
        const w = this.blockWidth;

        const inputEventOutermostX = {};
        const inputDataOutermostX = {};
        const outputEventOutermostX = {};
        const outputDataOutermostX = {};

        // INPUT SIDE
        const baseXInput = -cw - gap;
        this.leftmostConnectorX = baseXInput;

        let eventIndex = 0;
        for (const event of fb.eventInputs) {
            if (this.eventInputY[event.name] !== undefined && event.associatedVars.length > 0) {
                const eventY = this.eventInputY[event.name];
                const sqX = baseXInput - eventIndex * lineSpacing;
                const lineX = sqX + cw / 2;

                this.leftmostConnectorX = Math.min(this.leftmostConnectorX, sqX);

                if (inputEventOutermostX[event.name] === undefined) {
                    inputEventOutermostX[event.name] = sqX;
                } else {
                    inputEventOutermostX[event.name] = Math.min(inputEventOutermostX[event.name], sqX);
                }

                parts.push(`
    <rect x="${sqX}" y="${eventY - ch/2}" width="${cw}" height="${ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>`);

                for (const varName of event.associatedVars) {
                    if (this.dataInputY[varName] !== undefined) {
                        const dataY = this.dataInputY[varName];

                        if (inputDataOutermostX[varName] === undefined) {
                            inputDataOutermostX[varName] = sqX;
                        } else {
                            inputDataOutermostX[varName] = Math.min(inputDataOutermostX[varName], sqX);
                        }

                        parts.push(`
    <rect x="${sqX}" y="${dataY - ch/2}" width="${cw}" height="${ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>`);

                        parts.push(`
    <line x1="${lineX}" y1="${eventY}" x2="${lineX}" y2="${dataY}"
          stroke="#000000" stroke-width="1"/>`);
                    }
                }

                eventIndex++;
            }
        }

        // OUTPUT SIDE
        const baseXOutput = w + gap;
        this.rightmostConnectorX = baseXOutput + cw;

        eventIndex = 0;
        for (const event of fb.eventOutputs) {
            if (this.eventOutputY[event.name] !== undefined && event.associatedVars.length > 0) {
                const eventY = this.eventOutputY[event.name];
                const sqX = baseXOutput + eventIndex * lineSpacing;
                const lineX = sqX + cw / 2;

                this.rightmostConnectorX = Math.max(this.rightmostConnectorX, sqX + cw);

                const rightEdge = sqX + cw;
                if (outputEventOutermostX[event.name] === undefined) {
                    outputEventOutermostX[event.name] = rightEdge;
                } else {
                    outputEventOutermostX[event.name] = Math.max(outputEventOutermostX[event.name], rightEdge);
                }

                parts.push(`
    <rect x="${sqX}" y="${eventY - ch/2}" width="${cw}" height="${ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>`);

                for (const varName of event.associatedVars) {
                    if (this.dataOutputY[varName] !== undefined) {
                        const dataY = this.dataOutputY[varName];

                        if (outputDataOutermostX[varName] === undefined) {
                            outputDataOutermostX[varName] = rightEdge;
                        } else {
                            outputDataOutermostX[varName] = Math.max(outputDataOutermostX[varName], rightEdge);
                        }

                        parts.push(`
    <rect x="${sqX}" y="${dataY - ch/2}" width="${cw}" height="${ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>`);

                        parts.push(`
    <line x1="${lineX}" y1="${eventY}" x2="${lineX}" y2="${dataY}"
          stroke="#000000" stroke-width="1"/>`);
                    }
                }

                eventIndex++;
            }
        }

        // Horizontal lines
        parts.push("\n    <!-- Horizontal Connection Lines -->");

        for (const [eventName, outermostX] of Object.entries(inputEventOutermostX)) {
            const eventY = this.eventInputY[eventName];
            parts.push(`
    <line x1="0" y1="${eventY}" x2="${outermostX - overhang}" y2="${eventY}"
          stroke="#000000" stroke-width="1"/>`);
        }

        for (const [varName, outermostX] of Object.entries(inputDataOutermostX)) {
            const dataY = this.dataInputY[varName];
            parts.push(`
    <line x1="0" y1="${dataY}" x2="${outermostX - overhang}" y2="${dataY}"
          stroke="#000000" stroke-width="1"/>`);
        }

        for (const [eventName, outermostX] of Object.entries(outputEventOutermostX)) {
            const eventY = this.eventOutputY[eventName];
            parts.push(`
    <line x1="${w}" y1="${eventY}" x2="${outermostX + overhang}" y2="${eventY}"
          stroke="#000000" stroke-width="1"/>`);
        }

        for (const [varName, outermostX] of Object.entries(outputDataOutermostX)) {
            const dataY = this.dataOutputY[varName];
            parts.push(`
    <line x1="${w}" y1="${dataY}" x2="${outermostX + overhang}" y2="${dataY}"
          stroke="#000000" stroke-width="1"/>`);
        }

        return parts.join("");
    }

    _renderExternalLabels(fb) {
        const parts = [];
        parts.push("\n    <!-- External Labels -->");

        const leftLabelX = this.leftmostConnectorX - 10;
        const rightLabelX = this.rightmostConnectorX + 10;

        // Event inputs
        for (const port of fb.eventInputs) {
            // Text baseline adjustment for TGL font
            const y = this.eventInputY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showComments && port.comment) {
                    labelParts.push(port.comment);
                }
                if (this.showTypes) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">Event</tspan>`);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${leftLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        // Event outputs
        for (const port of fb.eventOutputs) {
            // Text baseline adjustment for TGL font
            const y = this.eventOutputY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showTypes) {
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">Event</tspan>`);
                }
                if (this.showComments && port.comment) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    labelParts.push(port.comment);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${rightLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        // Data inputs
        for (const port of fb.dataInputs) {
            // Text baseline adjustment for TGL font
            const y = this.dataInputY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showComments && port.comment) {
                    labelParts.push(port.comment);
                }
                if (this.showTypes) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">${port.portType}</tspan>`);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${leftLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        // Data outputs
        for (const port of fb.dataOutputs) {
            // Text baseline adjustment for TGL font
            const y = this.dataOutputY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showTypes) {
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">${port.portType}</tspan>`);
                }
                if (this.showComments && port.comment) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    labelParts.push(port.comment);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${rightLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        // Sockets
        for (const port of fb.sockets) {
            // Text baseline adjustment for TGL font
            const y = this.socketY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showComments && port.comment) {
                    labelParts.push(port.comment);
                }
                if (this.showTypes) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    const shortType = port.portType.includes("::")
                        ? port.portType.split("::").pop()
                        : port.portType;
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">${shortType}</tspan>`);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${leftLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        // Plugs
        for (const port of fb.plugs) {
            // Text baseline adjustment for TGL font
            const y = this.plugY[port.name] + 1;
            if (this.showTypes || (this.showComments && port.comment)) {
                const labelParts = [];
                if (this.showTypes) {
                    const shortType = port.portType.includes("::")
                        ? port.portType.split("::").pop()
                        : port.portType;
                    labelParts.push(`<tspan font-family="${this.FONT_FAMILY_ITALIC}" dominant-baseline="middle">${shortType}</tspan>`);
                }
                if (this.showComments && port.comment) {
                    if (labelParts.length > 0) labelParts.push(" – ");
                    labelParts.push(port.comment);
                }
                const labelText = labelParts.join("");
                parts.push(`
    <text x="${rightLabelX}" y="${y}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">${labelText}</text>`);
            }
        }

        return parts.join("");
    }
}

/**
 * Convert FBT XML string to SVG
 * @param {string} xmlString - The FBT XML content
 * @param {Object} options - Rendering options
 * @param {boolean} options.showComments - Show port comments (default: true)
 * @param {boolean} options.showTypes - Show port types (default: true)
 * @param {boolean} options.showShadow - Show drop shadow (default: true)
 * @returns {string} SVG content
 */
function convertFbtToSvg(xmlString, options = {}) {
    const parser = new IEC61499Parser();
    const renderer = new SVGRenderer(options);
    const fb = parser.parse(xmlString);
    return renderer.render(fb);
}

// Node.js CLI support
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { convertFbtToSvg, IEC61499Parser, SVGRenderer, FunctionBlock, Port };

    // CLI execution
    if (require.main === module) {
        const fs = require('fs');
        const path = require('path');

        const args = process.argv.slice(2);
        if (args.length === 0) {
            console.log('Usage: node iec61499_to_svg.js input.fbt [-o output.svg] [--no-comments] [--no-types] [--no-shadow]');
            process.exit(1);
        }

        const inputFile = args[0];
        let outputFile = null;
        const options = {
            showComments: true,
            showTypes: true,
            showShadow: true
        };

        for (let i = 1; i < args.length; i++) {
            if (args[i] === '-o' && args[i + 1]) {
                outputFile = args[++i];
            } else if (args[i] === '--no-comments') {
                options.showComments = false;
            } else if (args[i] === '--no-types') {
                options.showTypes = false;
            } else if (args[i] === '--no-shadow') {
                options.showShadow = false;
            }
        }

        if (!outputFile) {
            outputFile = inputFile.replace(/\.(fbt|adp)$/i, '.svg');
        }

        try {
            const xmlContent = fs.readFileSync(inputFile, 'utf-8');

            // For Node.js, we need to provide a DOMParser
            const { JSDOM } = require('jsdom');
            global.DOMParser = new JSDOM().window.DOMParser;

            const svg = convertFbtToSvg(xmlContent, options);
            fs.writeFileSync(outputFile, svg, 'utf-8');
            console.log(`SVG written to: ${outputFile}`);
        } catch (error) {
            console.error(`Error: ${error.message}`);
            process.exit(1);
        }
    }
}
