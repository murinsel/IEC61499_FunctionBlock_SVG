/**
 * IEC 61499 Function Block Network to SVG Converter
 *
 * Renders the internal network of composite FBs, SubApps, and Systems as SVG
 * diagrams in the style of 4diac IDE's network view.
 *
 * Usage (Node.js):
 *   node iec61499_network_to_svg.js input.fbt [-o output.svg] [--type-lib path] [--no-shadow]
 *
 * Usage (Browser):
 *   const svg = convertNetworkToSvg(xmlString, options);
 */

// ===========================================================================
// Block Size Settings (4diac IDE defaults)
// ===========================================================================

class BlockSizeSettings {
    constructor(overrides = {}) {
        this.maxValueLabelSize = overrides.maxValueLabelSize ?? overrides.max_value_label_size ?? 25;
        this.maxTypeLabelSize = overrides.maxTypeLabelSize ?? overrides.max_type_label_size ?? 15;
        this.minPinLabelSize = overrides.minPinLabelSize ?? overrides.min_pin_label_size ?? 0;
        this.maxPinLabelSize = overrides.maxPinLabelSize ?? overrides.max_pin_label_size ?? 12;
        this.minInterfaceBarSize = overrides.minInterfaceBarSize ?? overrides.min_interface_bar_size ?? 0;
        this.maxInterfaceBarSize = overrides.maxInterfaceBarSize ?? overrides.max_interface_bar_size ?? 40;
        this.maxHiddenConnectionLabelSize = overrides.maxHiddenConnectionLabelSize ?? overrides.max_hidden_connection_label_size ?? 15;
        // Block margins (in pixels)
        this.marginTopBottom = overrides.marginTopBottom ?? overrides.top_bottom ?? 0;
        this.marginLeftRight = overrides.marginLeftRight ?? overrides.left_right ?? 0;
    }
}

function loadBlockSizeSettings(iniText) {
    const settings = {};
    const typeLibPaths = [];
    if (!iniText) {
        const bs = new BlockSizeSettings();
        bs.typeLibPaths = typeLibPaths;
        return bs;
    }
    let currentSection = "";
    for (const line of iniText.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith(';')) continue;
        const sectionMatch = trimmed.match(/^\[(.+)\]$/);
        if (sectionMatch) {
            currentSection = sectionMatch[1];
            continue;
        }
        const eq = trimmed.indexOf('=');
        if (eq < 0) continue;
        const key = trimmed.substring(0, eq).trim();
        const valStr = trimmed.substring(eq + 1).trim();
        if (currentSection === "TypeLibrary") {
            if (key.startsWith("path") && valStr) {
                typeLibPaths.push(valStr);
            }
        } else {
            const val = parseInt(valStr, 10);
            if (!isNaN(val)) settings[key] = val;
        }
    }
    const bs = new BlockSizeSettings(settings);
    bs.typeLibPaths = typeLibPaths;
    return bs;
}

function _truncateLabel(text, maxLen) {
    if (maxLen <= 0 || text.length <= maxLen) return text;
    return text.substring(0, maxLen) + "\u2026";
}

function _formatParameterValue(value, portType) {
    // Ensure IEC 61131-3 typed literal notation (TYPE#value).
    // If the value already has a type prefix, keep it; otherwise prepend portType.
    // Returns plain text (not XML-escaped) so truncation can be applied safely.
    if (!value.includes('#') && portType) {
        value = portType + '#' + value;
    }
    return value;
}

function _xmlEscape(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

// ===========================================================================
// Data Model
// ===========================================================================

class Port {
    constructor(name, portType = "", comment = "") {
        this.name = name;
        this.portType = portType;
        this.comment = comment;
    }
}

class FBInstance {
    constructor(name, typeName = "", x = 0, y = 0) {
        this.name = name;
        this.typeName = typeName;
        this.x = x;
        this.y = y;
        this.isSubapp = false;
        this.isAdapter = false;
        this.adapterKind = "";
        this.eventInputs = [];
        this.eventOutputs = [];
        this.dataInputs = [];
        this.dataOutputs = [];
        this.plugs = [];
        this.sockets = [];
        this.parameters = {};
        this.fbType = "";
        // Layout fields
        this.blockWidth = 0;
        this.figureWidth = 0;
        this.blockHeight = 0;
        this.renderX = 0;
        this.renderY = 0;
        this.eventSectionHeight = 0;
        this.dataSectionHeight = 0;
        this.nameSectionTop = 0;
        this.nameSectionBottom = 0;
        this.adapterSectionTop = 0;
        this.adapterSectionHeight = 0;
        this.portPositions = {};
    }
}

class Connection {
    constructor(source, destination, dx1 = 0, dx2 = 0, dy = 0, connType = "data") {
        this.source = source;
        this.destination = destination;
        this.dx1 = dx1;
        this.dx2 = dx2;
        this.dy = dy;
        this.connType = connType;
    }
}

class InterfacePort {
    constructor(name, portType = "", direction = "input", category = "data") {
        this.name = name;
        this.portType = portType;
        this.direction = direction;
        this.category = category;
        this.renderX = 0;
        this.renderY = 0;
    }
}

class NetworkModel {
    constructor() {
        this.name = "";
        this.comment = "";
        this.rootType = "";
        this.instances = [];
        this.connections = [];
        this.interfacePorts = [];
        // Sidebar geometry (set by layout engine)
        this.inputSidebarWidth = 0;
        this.outputSidebarWidth = 0;
        this.inputSidebarRect = null;   // {x, y, w, h}
        this.outputSidebarRect = null;  // {x, y, w, h}
        // Header and border geometry (set by layout engine)
        this.headerRect = null;         // {x, y, w, h}
        this.outerBorderRect = null;    // {x, y, w, h}
        // Canvas-to-pixel mapping (set by layout engine)
        this.canvasOriginX = 0;   // pixel x corresponding to canvas x=0
        this.canvasOriginY = 0;   // pixel y corresponding to canvas y=0
    }
}

// ===========================================================================
// Network Parser
// ===========================================================================

class NetworkParser {
    parse(xmlString) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlString, "text/xml");
        const root = doc.documentElement;

        if (root.tagName === "SubAppType") {
            return this._parseSubAppType(root);
        } else if (root.tagName === "FBType") {
            return this._parseFBType(root);
        } else if (root.tagName === "System") {
            return this._parseSystem(root);
        } else {
            throw new Error(`Unknown root element: ${root.tagName}`);
        }
    }

    _parseSubAppType(root) {
        const model = new NetworkModel();
        model.name = root.getAttribute("Name") || "Unknown";
        model.comment = root.getAttribute("Comment") || "";
        model.rootType = "SubAppType";

        const iface = root.querySelector("SubAppInterfaceList");
        if (iface) this._parseSubAppInterface(iface, model);

        const network = root.querySelector("SubAppNetwork");
        if (network) this._parseNetworkContents(network, model);

        return model;
    }

    _parseFBType(root) {
        const fbNetwork = root.querySelector("FBNetwork");
        const compFB = root.querySelector("CompositeFB");
        if (!fbNetwork && !compFB) {
            throw new Error("FBType has no FBNetwork or CompositeFB");
        }

        const model = new NetworkModel();
        model.name = root.getAttribute("Name") || "Unknown";
        model.comment = root.getAttribute("Comment") || "";
        model.rootType = "FBType";

        const iface = root.querySelector("InterfaceList");
        if (iface) this._parseFBTypeInterface(iface, model);

        const network = fbNetwork || compFB;
        if (network) this._parseNetworkContents(network, model);

        return model;
    }

    _parseSystem(root) {
        const model = new NetworkModel();
        model.name = root.getAttribute("Name") || "Unknown";
        model.comment = root.getAttribute("Comment") || "";
        model.rootType = "System";

        for (const app of root.querySelectorAll("Application")) {
            const network = app.querySelector("SubAppNetwork");
            if (network) this._parseNetworkContents(network, model);
        }

        return model;
    }

    _parseSubAppInterface(iface, model) {
        for (const section of iface.querySelectorAll("SubAppEventInputs")) {
            for (const ev of section.querySelectorAll("SubAppEvent")) {
                model.interfacePorts.push(new InterfacePort(
                    ev.getAttribute("Name") || "",
                    ev.getAttribute("Type") || "Event",
                    "input", "event"
                ));
            }
        }

        for (const section of iface.querySelectorAll("SubAppEventOutputs")) {
            for (const ev of section.querySelectorAll("SubAppEvent")) {
                model.interfacePorts.push(new InterfacePort(
                    ev.getAttribute("Name") || "",
                    ev.getAttribute("Type") || "Event",
                    "output", "event"
                ));
            }
        }

        for (const section of iface.querySelectorAll("InputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    v.getAttribute("Name") || "",
                    v.getAttribute("Type") || "",
                    "input", "data"
                ));
            }
        }

        for (const section of iface.querySelectorAll("OutputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    v.getAttribute("Name") || "",
                    v.getAttribute("Type") || "",
                    "output", "data"
                ));
            }
        }

        // Adapter sockets → input interface ports (in sidebar)
        for (const section of iface.querySelectorAll("Sockets")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    "input", "adapter"
                ));
            }
        }

        // Adapter plugs → output interface ports (in sidebar)
        for (const section of iface.querySelectorAll("Plugs")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    "output", "adapter"
                ));
            }
        }
    }

    _parseFBTypeInterface(iface, model) {
        for (const section of iface.querySelectorAll("EventInputs")) {
            for (const ev of section.querySelectorAll("Event")) {
                model.interfacePorts.push(new InterfacePort(
                    ev.getAttribute("Name") || "",
                    ev.getAttribute("Type") || "Event",
                    "input", "event"
                ));
            }
        }

        for (const section of iface.querySelectorAll("EventOutputs")) {
            for (const ev of section.querySelectorAll("Event")) {
                model.interfacePorts.push(new InterfacePort(
                    ev.getAttribute("Name") || "",
                    ev.getAttribute("Type") || "Event",
                    "output", "event"
                ));
            }
        }

        for (const section of iface.querySelectorAll("InputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    v.getAttribute("Name") || "",
                    v.getAttribute("Type") || "",
                    "input", "data"
                ));
            }
        }

        for (const section of iface.querySelectorAll("OutputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                model.interfacePorts.push(new InterfacePort(
                    v.getAttribute("Name") || "",
                    v.getAttribute("Type") || "",
                    "output", "data"
                ));
            }
        }

        // Plugs → adapter instances
        for (const section of iface.querySelectorAll("Plugs")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                const inst = new FBInstance(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    parseFloat(adp.getAttribute("x") || "0"),
                    parseFloat(adp.getAttribute("y") || "0")
                );
                inst.isAdapter = true;
                inst.adapterKind = "plug";
                inst.fbType = "Adapter";
                model.instances.push(inst);
            }
        }

        // Sockets → adapter instances
        for (const section of iface.querySelectorAll("Sockets")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                const inst = new FBInstance(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    parseFloat(adp.getAttribute("x") || "0"),
                    parseFloat(adp.getAttribute("y") || "0")
                );
                inst.isAdapter = true;
                inst.adapterKind = "socket";
                inst.fbType = "Adapter";
                model.instances.push(inst);
            }
        }
    }

    _parseNetworkContents(network, model) {
        // FB instances
        for (const fb of network.querySelectorAll(":scope > FB")) {
            const inst = new FBInstance(
                fb.getAttribute("Name") || "",
                fb.getAttribute("Type") || "",
                parseFloat(fb.getAttribute("x") || "0"),
                parseFloat(fb.getAttribute("y") || "0")
            );
            for (const param of fb.querySelectorAll("Parameter")) {
                inst.parameters[param.getAttribute("Name") || ""] = param.getAttribute("Value") || "";
            }
            for (const attr of fb.querySelectorAll("Attribute")) {
                if (attr.getAttribute("Name") === "DataType") {
                    inst.parameters["__DataType__"] = attr.getAttribute("Value") || "";
                }
            }
            model.instances.push(inst);
        }

        // SubApp instances
        for (const sub of network.querySelectorAll(":scope > SubApp")) {
            const inst = new FBInstance(
                sub.getAttribute("Name") || "",
                sub.getAttribute("Type") || "",
                parseFloat(sub.getAttribute("x") || "0"),
                parseFloat(sub.getAttribute("y") || "0")
            );
            inst.isSubapp = true;
            inst.fbType = "SubApp";
            for (const param of sub.querySelectorAll("Parameter")) {
                inst.parameters[param.getAttribute("Name") || ""] = param.getAttribute("Value") || "";
            }
            model.instances.push(inst);
        }

        // Connections
        for (const ec of network.querySelectorAll("EventConnections")) {
            for (const conn of ec.querySelectorAll("Connection")) {
                model.connections.push(new Connection(
                    conn.getAttribute("Source") || "",
                    conn.getAttribute("Destination") || "",
                    parseFloat(conn.getAttribute("dx1") || "0"),
                    parseFloat(conn.getAttribute("dx2") || "0"),
                    parseFloat(conn.getAttribute("dy") || "0"),
                    "event"
                ));
            }
        }

        for (const dc of network.querySelectorAll("DataConnections")) {
            for (const conn of dc.querySelectorAll("Connection")) {
                model.connections.push(new Connection(
                    conn.getAttribute("Source") || "",
                    conn.getAttribute("Destination") || "",
                    parseFloat(conn.getAttribute("dx1") || "0"),
                    parseFloat(conn.getAttribute("dx2") || "0"),
                    parseFloat(conn.getAttribute("dy") || "0"),
                    "data"
                ));
            }
        }

        for (const ac of network.querySelectorAll("AdapterConnections")) {
            for (const conn of ac.querySelectorAll("Connection")) {
                model.connections.push(new Connection(
                    conn.getAttribute("Source") || "",
                    conn.getAttribute("Destination") || "",
                    parseFloat(conn.getAttribute("dx1") || "0"),
                    parseFloat(conn.getAttribute("dx2") || "0"),
                    parseFloat(conn.getAttribute("dy") || "0"),
                    "adapter"
                ));
            }
        }
    }
}

// ===========================================================================
// Type Resolver
// ===========================================================================

class TypeResolver {
    constructor(typeLibXmls = {}) {
        // typeLibXmls: { typeName: xmlString } for browser use
        this._typeCache = {};
        this._typeLibXmls = typeLibXmls;
    }

    resolve(model) {
        for (const inst of model.instances) {
            if (inst.isAdapter) {
                this._resolveAdapterInstance(inst, model);
            } else {
                this._resolveInstance(inst, model);
            }
        }
    }

    _resolveInstance(inst, model) {
        const iface = this._lookupType(inst.typeName);
        if (iface) {
            inst.eventInputs = iface.eventInputs;
            inst.eventOutputs = iface.eventOutputs;
            inst.dataInputs = iface.dataInputs;
            inst.dataOutputs = iface.dataOutputs;
            inst.plugs = iface.plugs || [];
            inst.sockets = iface.sockets || [];
            if (!inst.fbType) inst.fbType = iface.fbType || "BasicFB";
            // Supplement with connection-referenced ports not in type definition
            this._supplementFromConnections(inst, model);
            return;
        }
        this._inferFromConnections(inst, model);
    }

    _resolveAdapterInstance(inst, model) {
        const iface = this._lookupType(inst.typeName);
        if (iface) {
            if (inst.adapterKind === "plug") {
                inst.eventInputs = iface.eventOutputs;
                inst.eventOutputs = iface.eventInputs;
                inst.dataInputs = iface.dataOutputs;
                inst.dataOutputs = iface.dataInputs;
            } else {
                inst.eventInputs = iface.eventInputs;
                inst.eventOutputs = iface.eventOutputs;
                inst.dataInputs = iface.dataInputs;
                inst.dataOutputs = iface.dataOutputs;
            }
            inst.fbType = "Adapter";
            return;
        }
        this._inferFromConnections(inst, model);
    }

    _lookupType(typeName) {
        if (this._typeCache[typeName]) return this._typeCache[typeName];

        // Try full name and short name
        let xml = this._typeLibXmls[typeName];
        if (!xml) {
            const shortName = typeName.includes("::") ? typeName.split("::").pop() : typeName;
            xml = this._typeLibXmls[shortName];
        }

        if (!xml) return null;

        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(xml, "text/xml");
            const root = doc.documentElement;
            const iface = this._extractInterface(root);
            this._typeCache[typeName] = iface;
            return iface;
        } catch (e) {
            return null;
        }
    }

    _extractInterface(root) {
        const result = {
            eventInputs: [],
            eventOutputs: [],
            dataInputs: [],
            dataOutputs: [],
            plugs: [],
            sockets: [],
            fbType: "BasicFB"
        };

        if (root.tagName === "AdapterType") result.fbType = "Adapter";
        else if (root.tagName === "SubAppType") result.fbType = "SubApp";
        else if (root.tagName === "FBType") {
            if (root.querySelector("BasicFB")) result.fbType = "BasicFB";
            else if (root.querySelector("CompositeFB") || root.querySelector("FBNetwork")) result.fbType = "CompositeFB";
            else if (root.querySelector("SimpleFB")) result.fbType = "SimpleFB";
            else result.fbType = "ServiceInterfaceFB";
        }

        let iface = root.querySelector("InterfaceList") || root.querySelector("SubAppInterfaceList");
        if (!iface) return result;

        const evInTags = ["EventInputs", "SubAppEventInputs"];
        const evOutTags = ["EventOutputs", "SubAppEventOutputs"];

        for (const tag of evInTags) {
            for (const section of iface.querySelectorAll(tag)) {
                for (const ev of section.querySelectorAll("Event, SubAppEvent")) {
                    result.eventInputs.push(new Port(
                        ev.getAttribute("Name") || "",
                        ev.getAttribute("Type") || "Event",
                        ev.getAttribute("Comment") || ""
                    ));
                }
            }
        }

        for (const tag of evOutTags) {
            for (const section of iface.querySelectorAll(tag)) {
                for (const ev of section.querySelectorAll("Event, SubAppEvent")) {
                    result.eventOutputs.push(new Port(
                        ev.getAttribute("Name") || "",
                        ev.getAttribute("Type") || "Event",
                        ev.getAttribute("Comment") || ""
                    ));
                }
            }
        }

        for (const section of iface.querySelectorAll("InputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                result.dataInputs.push(new Port(
                    v.getAttribute("Name") || "",
                    this._buildTypeString(v),
                    v.getAttribute("Comment") || ""
                ));
            }
        }

        for (const section of iface.querySelectorAll("OutputVars")) {
            for (const v of section.querySelectorAll("VarDeclaration")) {
                result.dataOutputs.push(new Port(
                    v.getAttribute("Name") || "",
                    this._buildTypeString(v),
                    v.getAttribute("Comment") || ""
                ));
            }
        }

        for (const section of iface.querySelectorAll("Plugs")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                result.plugs.push(new Port(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    adp.getAttribute("Comment") || ""
                ));
            }
        }

        for (const section of iface.querySelectorAll("Sockets")) {
            for (const adp of section.querySelectorAll("AdapterDeclaration")) {
                result.sockets.push(new Port(
                    adp.getAttribute("Name") || "",
                    adp.getAttribute("Type") || "",
                    adp.getAttribute("Comment") || ""
                ));
            }
        }

        return result;
    }

    _buildTypeString(varElem) {
        const baseType = varElem.getAttribute("Type") || "";
        const arraySize = varElem.getAttribute("ArraySize") || "";
        if (arraySize) {
            if (arraySize === "*") return `ARRAY [*] OF ${baseType}`;
            if (arraySize.includes("..")) return `ARRAY [${arraySize}] OF ${baseType}`;
            const n = parseInt(arraySize);
            if (!isNaN(n)) return `ARRAY [0..${n - 1}] OF ${baseType}`;
            return `ARRAY [${arraySize}] OF ${baseType}`;
        }
        return baseType;
    }

    _inferFromConnections(inst, model) {
        const eventInNames = [];
        const eventOutNames = [];
        const dataInNames = [];
        const dataOutNames = [];

        for (const conn of model.connections) {
            const srcParts = conn.source.split(".");
            const dstParts = conn.destination.split(".");

            if (srcParts.length === 2 && srcParts[0] === inst.name) {
                const portName = srcParts[1];
                if (conn.connType === "event" && !eventOutNames.includes(portName)) eventOutNames.push(portName);
                else if (conn.connType === "data" && !dataOutNames.includes(portName)) dataOutNames.push(portName);
            }

            if (dstParts.length === 2 && dstParts[0] === inst.name) {
                const portName = dstParts[1];
                if (conn.connType === "event" && !eventInNames.includes(portName)) eventInNames.push(portName);
                else if (conn.connType === "data" && !dataInNames.includes(portName)) dataInNames.push(portName);
            }
        }

        // Add parameter ports that aren't already in dataInNames
        for (const paramName of Object.keys(inst.parameters)) {
            if (!paramName.startsWith("__") && !dataInNames.includes(paramName) && !eventInNames.includes(paramName)) {
                dataInNames.push(paramName);
            }
        }

        inst.eventInputs = eventInNames.map(n => new Port(n, "Event"));
        inst.eventOutputs = eventOutNames.map(n => new Port(n, "Event"));
        inst.dataInputs = dataInNames.map(n => new Port(n));
        inst.dataOutputs = dataOutNames.map(n => new Port(n));

        if (!inst.fbType) inst.fbType = inst.isSubapp ? "SubApp" : "BasicFB";
    }

    _supplementFromConnections(inst, model) {
        // Handle mapped/renamed ports on SubApp instances.
        // For each port category, if any connection-referenced port is missing
        // from the type definition, replace that category with connection-inferred ports.
        const connEI = [], connEO = [], connDI = [], connDO = [];

        for (const conn of model.connections) {
            const srcParts = conn.source.split(".");
            const dstParts = conn.destination.split(".");

            if (srcParts.length === 2 && srcParts[0] === inst.name) {
                const portName = srcParts[1];
                if (conn.connType === "event" && !connEO.includes(portName)) connEO.push(portName);
                else if (conn.connType === "data" && !connDO.includes(portName)) connDO.push(portName);
            }

            if (dstParts.length === 2 && dstParts[0] === inst.name) {
                const portName = dstParts[1];
                if (conn.connType === "event" && !connEI.includes(portName)) connEI.push(portName);
                else if (conn.connType === "data" && !connDI.includes(portName)) connDI.push(portName);
            }
        }

        // For each category: if any connection port is missing from type def,
        // replace that category with connection-inferred ports
        const typeEI = new Set(inst.eventInputs.map(p => p.name));
        const typeEO = new Set(inst.eventOutputs.map(p => p.name));
        const typeDI = new Set(inst.dataInputs.map(p => p.name));
        const typeDO = new Set(inst.dataOutputs.map(p => p.name));

        if (connEI.some(n => !typeEI.has(n)))
            inst.eventInputs = connEI.map(n => new Port(n, "Event"));
        if (connEO.some(n => !typeEO.has(n)))
            inst.eventOutputs = connEO.map(n => new Port(n, "Event"));
        if (connDI.some(n => !typeDI.has(n)))
            inst.dataInputs = connDI.map(n => new Port(n));
        if (connDO.some(n => !typeDO.has(n)))
            inst.dataOutputs = connDO.map(n => new Port(n));

        // Add parameter ports not already present
        const existingDI = new Set(inst.dataInputs.map(p => p.name));
        const existingEI = new Set(inst.eventInputs.map(p => p.name));
        for (const paramName of Object.keys(inst.parameters)) {
            if (!paramName.startsWith("__") && !existingDI.has(paramName) && !existingEI.has(paramName)) {
                inst.dataInputs.push(new Port(paramName));
                existingDI.add(paramName);
            }
        }
    }
}

// ===========================================================================
// Layout Engine
// ===========================================================================

class NetworkLayoutEngine {
    constructor(settings = null) {
        // Visual lineHeight = 17 (TGL 0-17_std @ 12pt port-to-port spacing)
        // Coordinate SCALE = 0.15 (Menlo-12 lineHeight=15: 15/100 = 0.15,
        //   confirmed by retina measurement: all 9 pairwise Y-axis checks give exactly 0.15)
        this.PORT_ROW_HEIGHT = 17;
        this.BLOCK_PADDING = 10;
        this.NAME_SECTION_HEIGHT = 17;
        this.BLOCK_MARGIN_PX = 2;        // SWT GridLayout margins: marginHeight=1 per section, net +2
        this.INSTANCE_LABEL_HEIGHT = 15;  // Coordinate-system lineHeight (Menlo-12: 15px)
        this.TRIANGLE_WIDTH = 5;
        this.TRIANGLE_HEIGHT = 10;
        this.FONT_SIZE = 12;
        this.MARGIN = 60;  // Margin around the diagram for interface ports
        this.SCALE = 0.15;  // 4diac canvas units → SVG pixels (lineHeight/100 = 15/100)
        this.settings = settings || new BlockSizeSettings();

        // Canvas for text measurement (browser only)
        this._canvas = null;
        this._ctx = null;
        try {
            if (typeof document !== 'undefined') {
                this._canvas = document.createElement('canvas');
                this._ctx = this._canvas.getContext('2d');
            }
        } catch (e) {}
    }

    _measureText(text, italic = false) {
        if (this._ctx) {
            const style = italic ? 'italic' : 'normal';
            this._ctx.font = `${style} ${this.FONT_SIZE}px "TGL 0-17_std", "TGL 0-17", "Times New Roman", Times, serif`;
            return this._ctx.measureText(text).width;
        }
        return text.length * 8.5;
    }

    layout(model) {
        for (const inst of model.instances) this._sizeInstance(inst);
        this._positionInstances(model);
        for (const inst of model.instances) this._computePortPositions(inst);
        this._positionInterfacePorts(model);
        this._computeHeaderAndBorder(model);
    }

    _sizeInstance(inst) {
        const numEI = inst.eventInputs.length;
        const numEO = inst.eventOutputs.length;
        const numDI = inst.dataInputs.length;
        const numDO = inst.dataOutputs.length;
        const numSK = inst.sockets.length;
        const numPL = inst.plugs.length;

        const numEventRows = Math.max(numEI, numEO, 1);
        const numDataRows = Math.max(numDI, numDO);
        const numAdapterRows = Math.max(numSK, numPL);

        // Visual block height matches SWT GridLayout preferred size:
        //   (portRows + 1) * lineHeight + BLOCK_MARGIN_PX
        // The +1 is for the notch/name section (one lineHeight).
        // BLOCK_MARGIN_PX (2) comes from SWT GridLayout margins.
        inst.eventSectionHeight = numEventRows * this.PORT_ROW_HEIGHT;
        inst.dataSectionHeight = numDataRows > 0 ? numDataRows * this.PORT_ROW_HEIGHT : 0;
        inst.adapterSectionHeight = numAdapterRows > 0 ? numAdapterRows * this.PORT_ROW_HEIGHT : 0;

        const portRows = numEventRows + numDataRows + numAdapterRows;
        inst.blockHeight = (portRows + 1) * this.PORT_ROW_HEIGHT + this.BLOCK_MARGIN_PX;

        let shortType = inst.typeName.includes("::") ? inst.typeName.split("::").pop() : inst.typeName;
        shortType = _truncateLabel(shortType, this.settings.maxTypeLabelSize);
        const notch = 8;
        const iconW = 14;
        const gapIconText = 4;

        const typeWidth = this._measureText(shortType, true);
        const typeSectionW = notch + 1 + iconW + gapIconText + typeWidth + 5 + notch;

        const triSpace = this.TRIANGLE_WIDTH + 1 + 1.5;
        const adpSpace = this.TRIANGLE_WIDTH * 2 + 1 + 1.5;

        const minPinW = this.settings.minPinLabelSize > 0 ? this._measureText("W".repeat(this.settings.minPinLabelSize)) : 0;

        let maxLeft = 0;
        for (const p of [...inst.eventInputs, ...inst.dataInputs]) {
            maxLeft = Math.max(maxLeft, triSpace + Math.max(minPinW, this._measureText(_truncateLabel(p.name, this.settings.maxPinLabelSize))));
        }
        for (const p of inst.sockets) {
            maxLeft = Math.max(maxLeft, adpSpace + Math.max(minPinW, this._measureText(_truncateLabel(p.name, this.settings.maxPinLabelSize))));
        }

        let maxRight = 0;
        for (const p of [...inst.eventOutputs, ...inst.dataOutputs]) {
            maxRight = Math.max(maxRight, triSpace + Math.max(minPinW, this._measureText(_truncateLabel(p.name, this.settings.maxPinLabelSize))));
        }
        for (const p of inst.plugs) {
            maxRight = Math.max(maxRight, adpSpace + Math.max(minPinW, this._measureText(_truncateLabel(p.name, this.settings.maxPinLabelSize))));
        }

        const minCenterGap = 8;
        const portsWidth = maxLeft + minCenterGap + maxRight;

        inst.blockWidth = Math.max(typeSectionW, portsWidth);

        // Figure width includes the instance name label (may be wider than block)
        const instanceNameWidth = this._measureText(inst.name, false) + 4;
        inst.figureWidth = Math.max(instanceNameWidth, inst.blockWidth);

        inst.nameSectionTop = inst.eventSectionHeight;
        inst.nameSectionBottom = inst.eventSectionHeight + this.NAME_SECTION_HEIGHT;
        inst.adapterSectionTop = inst.nameSectionBottom + inst.dataSectionHeight;
    }

    _positionInstances(model) {
        if (model.instances.length === 0) return;

        const minX = Math.min(...model.instances.map(i => i.x));
        const minY = Math.min(...model.instances.map(i => i.y));

        // In 4diac IDE, (x, y) is the top-left of the entire figure including
        // the instance name label above the block body.  Offset render positions
        // so render_x/render_y point to the block body top-left.
        for (const inst of model.instances) {
            inst.renderX = (inst.x - minX) * this.SCALE + this.MARGIN;
            inst.renderX += (inst.figureWidth - inst.blockWidth) / 2;
            inst.renderY = (inst.y - minY) * this.SCALE + this.MARGIN;
            inst.renderY += this.INSTANCE_LABEL_HEIGHT;
        }

        // Store the mapping from canvas origin (0, 0) to pixel coordinates.
        model.canvasOriginX = this.MARGIN - minX * this.SCALE;
        model.canvasOriginY = this.MARGIN - minY * this.SCALE;
    }

    _computePortPositions(inst) {
        // Event inputs – centered in each row
        let y = this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.eventInputs) {
            inst.portPositions[p.name] = [inst.renderX, inst.renderY + y];
            y += this.PORT_ROW_HEIGHT;
        }

        // Event outputs
        y = this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.eventOutputs) {
            inst.portPositions[p.name] = [inst.renderX + inst.blockWidth, inst.renderY + y];
            y += this.PORT_ROW_HEIGHT;
        }

        // Data inputs
        const baseY = inst.nameSectionBottom;
        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.dataInputs) {
            inst.portPositions[p.name] = [inst.renderX, inst.renderY + y];
            y += this.PORT_ROW_HEIGHT;
        }

        // Data outputs
        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.dataOutputs) {
            inst.portPositions[p.name] = [inst.renderX + inst.blockWidth, inst.renderY + y];
            y += this.PORT_ROW_HEIGHT;
        }

        // Sockets
        if (inst.sockets.length > 0) {
            y = inst.adapterSectionTop + this.PORT_ROW_HEIGHT / 2;
            for (const p of inst.sockets) {
                inst.portPositions[p.name] = [inst.renderX, inst.renderY + y];
                y += this.PORT_ROW_HEIGHT;
            }
        }

        // Plugs
        if (inst.plugs.length > 0) {
            y = inst.adapterSectionTop + this.PORT_ROW_HEIGHT / 2;
            for (const p of inst.plugs) {
                inst.portPositions[p.name] = [inst.renderX + inst.blockWidth, inst.renderY + y];
                y += this.PORT_ROW_HEIGHT;
            }
        }
    }

    _positionInterfacePorts(model) {
        if (model.instances.length === 0 && model.interfacePorts.length === 0) return;

        const inputs = model.interfacePorts.filter(p => p.direction === "input");
        const outputs = model.interfacePorts.filter(p => p.direction === "output");

        // Measure sidebar widths: text + gap + symbol, minimal outer margin
        const sidebarOuterMargin = 1;   // 1px margin at outer border edge
        const sidebarGap = 1;           // 1px gap between text and symbol
        const triW = this.TRIANGLE_WIDTH;
        const adapterSymW = this.TRIANGLE_WIDTH * 2;  // adapter socket/plug symbol is wider
        const maxIface = this.settings.maxInterfaceBarSize;
        let inputSidebarW = 0;
        let inputSymW = triW;  // track widest symbol needed
        for (const p of inputs) {
            inputSidebarW = Math.max(inputSidebarW, this._measureText(_truncateLabel(p.name, maxIface)));
            if (p.category === "adapter") inputSymW = Math.max(inputSymW, adapterSymW);
        }
        if (inputs.length) inputSidebarW += sidebarOuterMargin + sidebarGap + inputSymW;

        let outputSidebarW = 0;
        let outputSymW = triW;
        for (const p of outputs) {
            outputSidebarW = Math.max(outputSidebarW, this._measureText(_truncateLabel(p.name, maxIface)));
            if (p.category === "adapter") outputSymW = Math.max(outputSymW, adapterSymW);
        }
        if (outputs.length) outputSidebarW += sidebarOuterMargin + sidebarGap + outputSymW;

        // Clamp sidebar widths to min interface bar size
        const minIfaceW = this.settings.minInterfaceBarSize > 0 ? this._measureText("W".repeat(this.settings.minInterfaceBarSize)) : 0;
        if (inputs.length && inputSidebarW < minIfaceW + sidebarOuterMargin + sidebarGap + triW) {
            inputSidebarW = minIfaceW + sidebarOuterMargin + sidebarGap + triW;
        }
        if (outputs.length && outputSidebarW < minIfaceW + sidebarOuterMargin + sidebarGap + triW) {
            outputSidebarW = minIfaceW + sidebarOuterMargin + sidebarGap + triW;
        }

        model.inputSidebarWidth = inputSidebarW;
        model.outputSidebarWidth = outputSidebarW;

        // Instance area bounds
        let instMinX, instMaxX, instMinY, instMaxY;
        if (model.instances.length) {
            instMinX = Math.min(...model.instances.map(i => i.renderX));
            instMaxX = Math.max(...model.instances.map(i => i.renderX + i.blockWidth));
            instMinY = Math.min(...model.instances.map(i => i.renderY - this.INSTANCE_LABEL_HEIGHT - 4));
            instMaxY = Math.max(...model.instances.map(i => i.renderY + i.blockHeight));
        } else {
            instMinX = this.MARGIN; instMaxX = this.MARGIN + 200;
            instMinY = this.MARGIN; instMaxY = this.MARGIN + 200;
        }

        // Position sidebars so the gap between sidebar and FBs accommodates
        // the dx1-based routing channels (matching 4diac IDE rendering).
        const inputPortNames = new Set(inputs.map(p => p.name));
        const outputPortNames = new Set(outputs.map(p => p.name));

        const instanceMapTmp = {};
        for (const inst of model.instances) instanceMapTmp[inst.name] = inst;

        // --- Input (left) sidebar positioning ---
        // Only consider connections whose turn point falls between sidebar and dest FB.
        let maxTurnOffset = 0;
        for (const conn of model.connections) {
            const srcParts = conn.source.split(".");
            if (srcParts.length === 1 && inputPortNames.has(srcParts[0]) && conn.dx1 !== 0) {
                const dx1Px = conn.dx1 * this.SCALE;
                const dstParts = conn.destination.split(".");
                if (dstParts.length === 2) {
                    const dstInst = instanceMapTmp[dstParts[0]];
                    if (dstInst) {
                        const distToDest = dstInst.renderX - instMinX;
                        if (dx1Px <= distToDest * 0.5) {
                            maxTurnOffset = Math.max(maxTurnOffset, dx1Px);
                        }
                    }
                }
            }
        }
        const sidebarPaddingLeft = 20;
        const sidebarGapLeft = maxTurnOffset + sidebarPaddingLeft;
        let inputSidebarRight = instMinX - sidebarGapLeft;

        // Check if any connection turn points from the sidebar would overshoot
        // past their destination FB.  Shift all instances right if needed.
        let maxOvershoot = 0;
        for (const conn of model.connections) {
            const srcParts = conn.source.split(".");
            if (srcParts.length === 1 && inputPortNames.has(srcParts[0]) && conn.dx1 !== 0) {
                const dx1Px = conn.dx1 * this.SCALE;
                const dstParts = conn.destination.split(".");
                if (dstParts.length === 2) {
                    const dstInst = instanceMapTmp[dstParts[0]];
                    if (dstInst) {
                        const turnX = inputSidebarRight + dx1Px;
                        const overshoot = turnX - dstInst.renderX;
                        if (overshoot > 0) {
                            maxOvershoot = Math.max(maxOvershoot, overshoot);
                        }
                    }
                }
            }
        }

        if (maxOvershoot > 0) {
            const shift = maxOvershoot + 91;
            for (const inst of model.instances) {
                inst.renderX += shift;
                for (const pname in inst.portPositions) {
                    inst.portPositions[pname][0] += shift;
                }
            }
            instMinX += shift;
            instMaxX += shift;
            model.canvasOriginX += shift;
        }

        const inputSidebarLeft = inputSidebarRight - inputSidebarW;

        // --- Output (right) sidebar positioning ---
        // Find the max turn-point offset (rightward from inst_max_x)
        // for FB→interface connections whose turn point extends past the
        // rightmost FB edge.
        let maxRightTurnOffset = 0;
        for (const conn of model.connections) {
            const dstParts = conn.destination.split(".");
            if (dstParts.length === 1 && outputPortNames.has(dstParts[0]) && conn.dx1 !== 0) {
                const srcParts = conn.source.split(".");
                if (srcParts.length === 2) {
                    const srcInst = instanceMapTmp[srcParts[0]];
                    if (srcInst) {
                        const portName = srcParts[1];
                        if (srcInst.portPositions && srcInst.portPositions[portName]) {
                            const srcX = srcInst.portPositions[portName][0];
                            const dx1Px = conn.dx1 * this.SCALE;
                            const turnX = srcX + dx1Px;
                            const offsetFromRight = turnX - instMaxX;
                            if (offsetFromRight > 0) {
                                maxRightTurnOffset = Math.max(maxRightTurnOffset, offsetFromRight);
                            }
                        }
                    }
                }
            }
        }
        const sidebarPaddingRight = 20;
        const sidebarGapRight = maxRightTurnOffset + sidebarPaddingRight;
        const outputSidebarLeft = instMaxX + sidebarGapRight;

        const sidebarRowH = 17; // spacing for sidebar port names (= lineHeight for TGL 0-17 @ 12pt)
        const topPad = 29; // space above first port: int(lineHeight * 1.75) = int(17 * 1.75)
        let sidebarTop = instMinY - 58;

        let inputSidebarH = inputs.length ? (inputs.length * sidebarRowH + topPad) : 0;
        let outputSidebarH = outputs.length ? (outputs.length * sidebarRowH + topPad) : 0;
        const contentH = instMaxY + 10 - sidebarTop;
        inputSidebarH = Math.max(inputSidebarH, contentH);
        outputSidebarH = Math.max(outputSidebarH, contentH);

        model.inputSidebarRect = inputs.length ? { x: inputSidebarLeft, y: sidebarTop, w: inputSidebarW, h: inputSidebarH } : null;
        model.outputSidebarRect = outputs.length ? { x: outputSidebarLeft, y: sidebarTop, w: outputSidebarW, h: outputSidebarH } : null;

        // Position input ports: start at top with line spacing
        if (inputs.length) {
            inputs.forEach((p, i) => {
                p.renderX = inputSidebarRight;
                p.renderY = sidebarTop + topPad + i * sidebarRowH;
            });
        }

        // Position output ports: start at top with line spacing
        if (outputs.length) {
            outputs.forEach((p, i) => {
                p.renderX = outputSidebarLeft;
                p.renderY = sidebarTop + topPad + i * sidebarRowH;
            });
        }
    }

    _computeHeaderAndBorder(model) {
        const HEADER_HEIGHT = 25; // Height of the header bar (margin + text + margin)

        // Determine the full horizontal and vertical extent (sidebars + instances)
        const allX = [];
        const allY = [];

        const labelAbove = this.INSTANCE_LABEL_HEIGHT + 4; // label height + padding
        for (const inst of model.instances) {
            allX.push(inst.renderX, inst.renderX + inst.blockWidth);
            allY.push(inst.renderY - labelAbove, inst.renderY + inst.blockHeight);
        }

        if (model.inputSidebarRect) {
            const r = model.inputSidebarRect;
            allX.push(r.x, r.x + r.w);
            allY.push(r.y, r.y + r.h);
        }
        if (model.outputSidebarRect) {
            const r = model.outputSidebarRect;
            allX.push(r.x, r.x + r.w);
            allY.push(r.y, r.y + r.h);
        }

        if (allX.length === 0) return;

        const contentLeft = Math.min(...allX);
        let contentRight = Math.max(...allX);
        const contentTop = Math.min(...allY);
        let contentBottom = Math.max(...allY);

        const borderPadV = 120; // vertical padding (top/bottom) between content extent and header/border

        // 4diac IDE enforces a minimum network area size (2224×1148 retina → 1112×574 CSS px).
        // This is the INNER area between sidebars and below the header.
        const MIN_NETWORK_WIDTH = 1112;
        const MIN_NETWORK_HEIGHT = 574;

        // Compute the inner network area (between sidebar edges)
        const inputSW = model.inputSidebarRect ? model.inputSidebarRect.w : 0;
        const outputSW = model.outputSidebarRect ? model.outputSidebarRect.w : 0;
        const networkLeft = contentLeft + inputSW;
        const networkRight = contentRight - outputSW;
        const networkW = networkRight - networkLeft;
        const networkH = contentBottom - contentTop + 2 * borderPadV + 25;

        if (networkW < MIN_NETWORK_WIDTH) {
            const extra = MIN_NETWORK_WIDTH - networkW;
            const shiftX = extra / 2;
            // Center FB instances within the expanded network area
            for (const inst of model.instances) {
                inst.renderX += shiftX;
                for (const pname in inst.portPositions) {
                    inst.portPositions[pname][0] += shiftX;
                }
            }
            model.canvasOriginX = (model.canvasOriginX || 0) + shiftX;
            // Expand contentRight to accommodate the wider network area + output sidebar
            contentRight = contentLeft + inputSW + MIN_NETWORK_WIDTH + outputSW;
            // Reposition output sidebar to the new right edge
            if (model.outputSidebarRect) {
                const sw = model.outputSidebarRect.w;
                model.outputSidebarRect.x = contentRight - sw;
                for (const ip of model.interfacePorts) {
                    if (ip.direction === "output") {
                        ip.renderX = contentRight - sw;
                    }
                }
            }
        }
        if (networkH < MIN_NETWORK_HEIGHT) {
            const extra = MIN_NETWORK_HEIGHT - networkH;
            contentBottom += extra;
        }

        // Sidebars form the left/right edges of the border — no extra padding
        const borderX = contentLeft;
        const borderW = contentRight - contentLeft;

        const headerX = borderX;
        const headerY = contentTop - borderPadV - HEADER_HEIGHT;
        const headerW = borderW;
        const headerH = HEADER_HEIGHT;

        model.headerRect = { x: headerX, y: headerY, w: headerW, h: headerH };

        const borderY = headerY;
        const borderH = (contentBottom + borderPadV) - headerY;

        model.outerBorderRect = { x: borderX, y: borderY, w: borderW, h: borderH };

        // Adjust sidebars to span from header separator to border bottom
        const headerBottom = headerY + headerH;
        const sidebarBottom = borderY + borderH;
        if (model.inputSidebarRect) {
            model.inputSidebarRect.y = headerBottom;
            model.inputSidebarRect.h = sidebarBottom - headerBottom;
        }
        if (model.outputSidebarRect) {
            model.outputSidebarRect.y = headerBottom;
            model.outputSidebarRect.h = sidebarBottom - headerBottom;
        }

        // Reposition interface port labels relative to header_bottom so they
        // stay near the top of the sidebar regardless of border_pad_v.
        const sidebarRowH2 = 17;
        const labelTopPad = 35; // gap from header separator to first label
        const inputs2 = model.interfacePorts.filter(p => p.direction === 'input');
        const outputs2 = model.interfacePorts.filter(p => p.direction === 'output');
        inputs2.forEach((port, i) => {
            port.renderY = headerBottom + labelTopPad + i * sidebarRowH2;
        });
        outputs2.forEach((port, i) => {
            port.renderY = headerBottom + labelTopPad + i * sidebarRowH2;
        });
    }

    getDiagramBounds(model) {
        // Use outer border if available (it encompasses everything)
        if (model.outerBorderRect) {
            const r = model.outerBorderRect;
            return { minX: r.x, minY: r.y, maxX: r.x + r.w, maxY: r.y + r.h };
        }

        const allX = [];
        const allY = [];

        for (const inst of model.instances) {
            allX.push(inst.renderX, inst.renderX + inst.blockWidth);
            allY.push(inst.renderY - 20, inst.renderY + inst.blockHeight);
        }

        // Include sidebar rectangles in bounds
        if (model.inputSidebarRect) {
            const r = model.inputSidebarRect;
            allX.push(r.x, r.x + r.w);
            allY.push(r.y, r.y + r.h);
        }
        if (model.outputSidebarRect) {
            const r = model.outputSidebarRect;
            allX.push(r.x, r.x + r.w);
            allY.push(r.y, r.y + r.h);
        }

        if (allX.length === 0) return { minX: 0, minY: 0, maxX: 100, maxY: 100 };

        return {
            minX: Math.min(...allX),
            minY: Math.min(...allY),
            maxX: Math.max(...allX),
            maxY: Math.max(...allY)
        };
    }
}

// ===========================================================================
// Connection Router
// ===========================================================================

class ConnectionRouter {
    constructor() {
        this.SCALE = 0.15;  // Must match layout engine scale
    }

    route(conn, model, instanceMap, interfaceMap) {
        const srcPos = this._resolveEndpoint(conn.source, instanceMap, interfaceMap);
        const dstPos = this._resolveEndpoint(conn.destination, instanceMap, interfaceMap);

        if (!srcPos || !dstPos) return [];

        const [x1, y1] = srcPos;
        const [x2, y2] = dstPos;

        // Check if source or destination is an interface port
        const srcParts = conn.source.split(".");
        const dstParts = conn.destination.split(".");
        const srcIsIface = srcParts.length === 1 && interfaceMap[srcParts[0]];
        const dstIsIface = dstParts.length === 1 && interfaceMap[dstParts[0]];

        // Interface-to-FB or FB-to-interface connections
        // Use the dx1 routing hint from the XML to place the vertical turn segment.
        if (srcIsIface && !dstIsIface) {
            const dx1 = conn.dx1 * this.SCALE;
            if (Math.abs(y1 - y2) < 1 && dx1 === 0) {
                return this._simplifyPoints([[x1, y1], [x2, y2]]);
            } else if (dx1 !== 0) {
                const turnX = x1 + dx1;
                return this._simplifyPoints([[x1, y1], [turnX, y1], [turnX, y2], [x2, y2]]);
            } else {
                const turnX = (x1 + x2) / 2;
                return this._simplifyPoints([[x1, y1], [turnX, y1], [turnX, y2], [x2, y2]]);
            }
        }

        if (dstIsIface && !srcIsIface) {
            const dx1 = conn.dx1 * this.SCALE;
            if (Math.abs(y1 - y2) < 1 && dx1 === 0) {
                return this._simplifyPoints([[x1, y1], [x2, y2]]);
            } else if (dx1 !== 0) {
                const turnX = x1 + dx1;
                return this._simplifyPoints([[x1, y1], [turnX, y1], [turnX, y2], [x2, y2]]);
            } else {
                const turnX = (x1 + x2) / 2;
                return this._simplifyPoints([[x1, y1], [turnX, y1], [turnX, y2], [x2, y2]]);
            }
        }

        // Scale the routing hints — same scale as positions
        const dx1 = conn.dx1 * this.SCALE;
        const dx2 = conn.dx2 * this.SCALE;
        const dy = conn.dy * this.SCALE;

        // Enforce minimum routing distances so lines remain visible
        const MIN_ROUTE_DX = 30;
        const MIN_ROUTE_DY = 20;

        let points;

        if (dy === 0) {
            if (dx1 !== 0) {
                let midX = x1 + dx1;
                if (Math.abs(dx1) < MIN_ROUTE_DX) {
                    midX = x1 + (dx1 > 0 ? MIN_ROUTE_DX : -MIN_ROUTE_DX);
                }
                points = [[x1, y1], [midX, y1], [midX, y2], [x2, y2]];
            } else {
                const midX = (x1 + x2) / 2;
                if (Math.abs(y1 - y2) < 1) {
                    points = [[x1, y1], [x2, y2]];
                } else {
                    points = [[x1, y1], [midX, y1], [midX, y2], [x2, y2]];
                }
            }
        } else {
            // U-turn / complex route with dy
            // dx1 = horizontal offset from SOURCE to first vertical segment
            // dx2 = horizontal offset from DESTINATION to second vertical segment
            // dy  = vertical offset from source to horizontal crossover
            if (dx2 !== 0) {
                // Full 5-segment U-turn route
                const seg1X = x1 + dx1;
                const segY  = y1 + dy;
                const seg2X = x2 - dx2;  // offset LEFT from destination
                points = [[x1, y1], [seg1X, y1], [seg1X, segY], [seg2X, segY], [seg2X, y2], [x2, y2]];
            } else {
                // 3-segment with dy
                const seg1X = x1 + dx1;
                const segY = y1 + dy;
                points = [[x1, y1], [seg1X, y1], [seg1X, segY], [x2, segY], [x2, y2]];
            }
        }

        return this._simplifyPoints(points);
    }

    _resolveEndpoint(endpoint, instanceMap, interfaceMap) {
        const parts = endpoint.split(".");
        if (parts.length === 2) {
            const inst = instanceMap[parts[0]];
            if (inst && inst.portPositions[parts[1]]) return inst.portPositions[parts[1]];
            return null;
        } else if (parts.length === 1) {
            const ip = interfaceMap[parts[0]];
            if (ip) return [ip.renderX, ip.renderY];
            return null;
        }
        return null;
    }

    _simplifyPoints(points) {
        if (points.length < 2) return points;

        const result = [points[0]];
        for (let i = 1; i < points.length; i++) {
            if (Math.abs(points[i][0] - result[result.length - 1][0]) > 0.1 ||
                Math.abs(points[i][1] - result[result.length - 1][1]) > 0.1) {
                result.push(points[i]);
            }
        }

        if (result.length < 3) return result;

        const simplified = [result[0]];
        for (let i = 1; i < result.length - 1; i++) {
            const [x0, y0] = simplified[simplified.length - 1];
            const [x1, y1] = result[i];
            const [x2, y2] = result[i + 1];
            if (!(Math.abs(x0 - x1) < 0.1 && Math.abs(x1 - x2) < 0.1) &&
                !(Math.abs(y0 - y1) < 0.1 && Math.abs(y1 - y2) < 0.1)) {
                simplified.push(result[i]);
            }
        }
        simplified.push(result[result.length - 1]);
        return simplified;
    }
}

// ===========================================================================
// SVG Renderer
// ===========================================================================

class NetworkSVGRenderer {
    constructor(options = {}) {
        this.showShadow = options.showShadow !== false;
        this.showGrid = options.showGrid || false;
        this.settings = options.settings || new BlockSizeSettings();

        this.FONT_FAMILY = "'TGL 0-17_std', 'TGL 0-17', 'Times New Roman', Times, serif";
        this.FONT_FAMILY_ITALIC = "'TGL 0-16_std', 'TGL 0-16', 'Times New Roman', Times, serif";
        this.FONT_SIZE = 12;

        this.FONT_FACE_STYLE = `
  <style>
    @font-face {
      font-family: "TGL 0-17_std";
      src: local("TGL 0-17_std");
      font-style: normal;
      font-weight: normal;
    }
    @font-face {
      font-family: "TGL 0-17";
      src: local("TGL 0-17"), local("TGL 0-17 alt");
      font-style: normal;
      font-weight: normal;
    }
    @font-face {
      font-family: "TGL 0-16_std";
      src: local("TGL 0-16_std");
      font-style: normal;
      font-weight: normal;
    }
    @font-face {
      font-family: "TGL 0-16";
      src: local("TGL 0-16");
      font-style: normal;
      font-weight: normal;
    }
  </style>`;

        this.BLOCK_STROKE_COLOR = "#A0A0A0";
        this.EVENT_PORT_COLOR = "#63B31F";
        this.BOOL_PORT_COLOR = "#A3B08F";
        this.ANY_BIT_PORT_COLOR = "#82A3A9";
        this.ANY_INT_PORT_COLOR = "#18519E";
        this.ANY_REAL_PORT_COLOR = "#DBB418";
        this.STRING_PORT_COLOR = "#BD8663";
        this.DATA_PORT_COLOR = "#3366FF";
        this.ADAPTER_PORT_COLOR = "#845DAF";

        this.STRING_TYPES = new Set(["STRING", "WSTRING", "ANY_STRING", "ANY_CHARS", "CHAR", "WCHAR"]);
        this.INT_TYPES = new Set(["INT", "UINT", "SINT", "USINT", "DINT", "UDINT", "LINT", "ULINT", "ANY_INT", "ANY_NUM"]);
        this.REAL_TYPES = new Set(["REAL", "LREAL", "ANY_REAL"]);
        this.BIT_TYPES = new Set(["BYTE", "WORD", "DWORD", "LWORD", "ANY_BIT"]);

        this.ANY_TYPES = new Set(["ANY", "ANY_ELEMENTARY", "ANY_MAGNITUDE",
            "ANY_NUM", "ANY_REAL", "ANY_INT", "ANY_BIT", "ANY_STRING",
            "ANY_CHARS", "ANY_DATE", "ANY_DURATION", "ANY_STRUCT"]);

        // All primitive IEC 61499 types (non-struct)
        this.PRIMITIVE_TYPES = new Set([
            ...this.STRING_TYPES, ...this.INT_TYPES, ...this.REAL_TYPES,
            ...this.BIT_TYPES, ...this.ANY_TYPES,
            "BOOL", "Event", "TIME", "LTIME", "DATE", "LDATE",
            "TIME_OF_DAY", "LTOD", "DATE_AND_TIME", "LDT"
        ]);

        this.PORT_ROW_HEIGHT = 17;
        this.TRIANGLE_WIDTH = 5;
        this.TRIANGLE_HEIGHT = 10;
        this.CONN_DIAG_LEN = 4;

        // Canvas for text measurement (browser only)
        this._ctx = null;
        try {
            if (typeof document !== 'undefined') {
                const canvas = document.createElement('canvas');
                this._ctx = canvas.getContext('2d');
            }
        } catch (e) {}
    }

    _measureText(text, italic = false) {
        if (this._ctx) {
            const style = italic ? 'italic' : 'normal';
            this._ctx.font = `${style} ${this.FONT_SIZE}px "TGL 0-17_std", "TGL 0-17", "Times New Roman", Times, serif`;
            return this._ctx.measureText(text).width;
        }
        return text.length * 8.5;
    }

    _getPortColor(portType) {
        let t = portType;
        if (t.startsWith("ARRAY ")) {
            const idx = t.lastIndexOf(" OF ");
            if (idx >= 0) t = t.substring(idx + 4);
        }
        if (t === "BOOL") return this.BOOL_PORT_COLOR;
        if (this.STRING_TYPES.has(t)) return this.STRING_PORT_COLOR;
        if (this.INT_TYPES.has(t)) return this.ANY_INT_PORT_COLOR;
        if (this.REAL_TYPES.has(t)) return this.ANY_REAL_PORT_COLOR;
        if (this.BIT_TYPES.has(t)) return this.ANY_BIT_PORT_COLOR;
        return this.DATA_PORT_COLOR;
    }

    _resolvePortType(endpoint, model, instanceMap) {
        const parts = endpoint.split(".");
        if (parts.length === 2) {
            const inst = instanceMap[parts[0]];
            if (inst) {
                for (const p of [...inst.dataOutputs, ...inst.dataInputs]) {
                    if (p.name === parts[1]) return p.portType;
                }
            }
        } else if (parts.length === 1) {
            for (const ip of model.interfacePorts) {
                if (ip.name === parts[0]) return ip.portType;
            }
        }
        return "";
    }

    _getConnectionColor(conn, model, instanceMap) {
        if (conn.connType === "event") return this.EVENT_PORT_COLOR;
        if (conn.connType === "adapter") return this.ADAPTER_PORT_COLOR;

        const srcType = this._resolvePortType(conn.source, model, instanceMap);
        if (srcType && !this.ANY_TYPES.has(srcType)) {
            return this._getPortColor(srcType);
        }
        // Source is generic/unknown — try destination type
        const dstType = this._resolvePortType(conn.destination, model, instanceMap);
        if (dstType && !this.ANY_TYPES.has(dstType)) {
            return this._getPortColor(dstType);
        }
        // Both generic — use source color if available, else fallback
        if (srcType) return this._getPortColor(srcType);
        return this.DATA_PORT_COLOR;
    }

    _lighterColor(hexColor) {
        // Compute a lighter variant of a hex color (4diac HSL lightness * 1.667)
        const hex = hexColor.replace("#", "");
        const r = parseInt(hex.substring(0, 2), 16) / 255;
        const g = parseInt(hex.substring(2, 4), 16) / 255;
        const b = parseInt(hex.substring(4, 6), 16) / 255;
        const cmax = Math.max(r, g, b), cmin = Math.min(r, g, b);
        const delta = cmax - cmin;
        let l = (cmax + cmin) / 2;
        let h = 0, s = 0;
        if (delta !== 0) {
            s = delta / (1 - Math.abs(2 * l - 1));
            if (cmax === r) h = 60 * (((g - b) / delta) % 6);
            else if (cmax === g) h = 60 * ((b - r) / delta + 2);
            else h = 60 * ((r - g) / delta + 4);
            if (h < 0) h += 360;
        }
        l = Math.min(0.9, l * (1.0 / 0.6)); // cap at 0.9 to avoid pure white in SVG
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs((h / 60) % 2 - 1));
        const m = l - c / 2;
        let r1, g1, b1;
        if (h < 60) { r1 = c; g1 = x; b1 = 0; }
        else if (h < 120) { r1 = x; g1 = c; b1 = 0; }
        else if (h < 180) { r1 = 0; g1 = c; b1 = x; }
        else if (h < 240) { r1 = 0; g1 = x; b1 = c; }
        else if (h < 300) { r1 = x; g1 = 0; b1 = c; }
        else { r1 = c; g1 = 0; b1 = x; }
        const ro = Math.min(255, Math.round((r1 + m) * 255));
        const go = Math.min(255, Math.round((g1 + m) * 255));
        const bo = Math.min(255, Math.round((b1 + m) * 255));
        return `#${ro.toString(16).padStart(2, "0").toUpperCase()}${go.toString(16).padStart(2, "0").toUpperCase()}${bo.toString(16).padStart(2, "0").toUpperCase()}`;
    }

    _isStructType(portType) {
        if (!portType) return false;
        return !this.PRIMITIVE_TYPES.has(portType);
    }

    _isDoubleLineConnection(conn, model, instanceMap) {
        if (conn.connType === "adapter") return true;
        if (conn.connType === "data") {
            const srcType = this._resolvePortType(conn.source, model, instanceMap);
            if (this._isStructType(srcType)) return true;
            const dstType = this._resolvePortType(conn.destination, model, instanceMap);
            if (this._isStructType(dstType)) return true;
        }
        return false;
    }

    render(model, layout) {
        const parts = [];
        const instanceMap = {};
        for (const inst of model.instances) instanceMap[inst.name] = inst;
        const interfaceMap = {};
        for (const ip of model.interfacePorts) interfaceMap[ip.name] = ip;

        const bounds = layout.getDiagramBounds(model);
        const padding = 7;
        const vbX = bounds.minX - padding;
        const vbY = bounds.minY - padding;
        const vbW = (bounds.maxX - bounds.minX) + padding * 2;
        const vbH = (bounds.maxY - bounds.minY) + padding * 2;

        parts.push(this._svgHeader(vbX, vbY, vbW, vbH));

        // White background
        parts.push(`  <rect x="${vbX.toFixed(1)}" y="${vbY.toFixed(1)}" width="${vbW.toFixed(1)}" height="${vbH.toFixed(1)}" fill="white"/>`);

        // Grid settings (pattern rendered later once content area is known)
        const _gridMinor = this.showGrid ? 100 * layout.SCALE : 0;
        const _gridMajor = _gridMinor * 5;
        const _gridSuper = _gridMinor * 10;

        // Outer border
        if (model.outerBorderRect) {
            const r = model.outerBorderRect;
            parts.push(`  <rect x="${r.x.toFixed(1)}" y="${r.y.toFixed(1)}" width="${r.w.toFixed(1)}" height="${r.h.toFixed(1)}" fill="none" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="2"/>`);
        }

        // Header section
        if (model.headerRect) {
            const h = model.headerRect;
            // Header background
            parts.push(`  <rect x="${h.x.toFixed(1)}" y="${h.y.toFixed(1)}" width="${h.w.toFixed(1)}" height="${h.h.toFixed(1)}" fill="white" stroke="none"/>`);
            // Separator line (inside the header area, above sidebar start)
            const sepY = h.y + h.h - 0.5;
            parts.push(`  <line x1="${h.x.toFixed(1)}" y1="${sepY.toFixed(1)}" x2="${(h.x + h.w).toFixed(1)}" y2="${sepY.toFixed(1)}" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="1"/>`);
            // Comment text
            if (model.comment) {
                const textX = h.x + 5;
                const textY = h.y + h.h / 2 + this.FONT_SIZE * 0.35;
                const commentText = model.comment
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;");
                parts.push(`  <text x="${textX.toFixed(1)}" y="${textY.toFixed(1)}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}" font-weight="bold" fill="#333333">${commentText}</text>`);
            }
        }

        // Sidebar backgrounds
        parts.push('  <g id="sidebars">');
        if (model.inputSidebarRect) {
            const r = model.inputSidebarRect;
            parts.push(`    <rect x="${r.x.toFixed(1)}" y="${r.y.toFixed(1)}" width="${r.w.toFixed(1)}" height="${r.h.toFixed(1)}" fill="#EEF5FF" stroke="none"/>`);
            // Vertical separator at right edge
            const sepX = r.x + r.w;
            parts.push(`    <line x1="${sepX.toFixed(1)}" y1="${r.y.toFixed(1)}" x2="${sepX.toFixed(1)}" y2="${(r.y + r.h).toFixed(1)}" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="0.5"/>`);
        }
        if (model.outputSidebarRect) {
            const r = model.outputSidebarRect;
            parts.push(`    <rect x="${r.x.toFixed(1)}" y="${r.y.toFixed(1)}" width="${r.w.toFixed(1)}" height="${r.h.toFixed(1)}" fill="#EEF5FF" stroke="none"/>`);
            // Vertical separator at left edge
            parts.push(`    <line x1="${r.x.toFixed(1)}" y1="${r.y.toFixed(1)}" x2="${r.x.toFixed(1)}" y2="${(r.y + r.h).toFixed(1)}" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="0.5"/>`);
        }
        parts.push('  </g>');

        // Render grid in the network content area (after header/sidebars)
        if (this.showGrid) {
            let gx, gy, gw, gh;
            if (model.outerBorderRect) {
                gx = model.outerBorderRect.x;
                gy = model.outerBorderRect.y;
                gw = model.outerBorderRect.w;
                gh = model.outerBorderRect.h;
                if (model.headerRect) {
                    gy += model.headerRect.h;
                    gh -= model.headerRect.h;
                }
                if (model.inputSidebarRect) {
                    gx += model.inputSidebarRect.w;
                    gw -= model.inputSidebarRect.w;
                }
                if (model.outputSidebarRect) {
                    gw -= model.outputSidebarRect.w;
                }
            } else {
                gx = vbX; gy = vbY; gw = vbW; gh = vbH;
            }
            // Pattern origin aligned to content area top-left
            // Tile = 10 minor cells; minor=dotted, every 5th=dashed, every 10th=thicker dashed
            // Grid offsets: 10th horizontal line at 7th position, 10th vertical line at 2nd
            const _hOff = 1;  // horizontal (y) offset for the 10th-line
            const _vOff = 7;  // vertical (x) offset for the 10th-line
            parts.push(`  <defs>`);
            parts.push(`    <pattern id="grid" x="${gx.toFixed(1)}" y="${gy.toFixed(1)}" width="${_gridSuper.toFixed(2)}" height="${_gridSuper.toFixed(2)}" patternUnits="userSpaceOnUse">`);
            for (let i = 0; i < 10; i++) {
                const pos = (i * _gridMinor).toFixed(2);
                // Horizontal lines (y positions) — offset by _hOff
                const gridIdxH = ((i - _hOff) % 10 + 10) % 10;
                if (gridIdxH === 0) {
                    parts.push(`      <line x1="0" y1="${pos}" x2="${_gridSuper.toFixed(2)}" y2="${pos}" stroke="#C0C0C0" stroke-width="1.5" stroke-dasharray="6,3"/>`);
                } else if (gridIdxH === 5) {
                    parts.push(`      <line x1="0" y1="${pos}" x2="${_gridSuper.toFixed(2)}" y2="${pos}" stroke="#C0C0C0" stroke-width="1" stroke-dasharray="4,3"/>`);
                } else {
                    parts.push(`      <line x1="0" y1="${pos}" x2="${_gridSuper.toFixed(2)}" y2="${pos}" stroke="#C0C0C0" stroke-width="0.5" stroke-dasharray="1,3"/>`);
                }
                // Vertical lines (x positions) — offset by _vOff
                const gridIdxV = ((i - _vOff) % 10 + 10) % 10;
                if (gridIdxV === 0) {
                    parts.push(`      <line x1="${pos}" y1="0" x2="${pos}" y2="${_gridSuper.toFixed(2)}" stroke="#C0C0C0" stroke-width="1.5" stroke-dasharray="6,3"/>`);
                } else if (gridIdxV === 5) {
                    parts.push(`      <line x1="${pos}" y1="0" x2="${pos}" y2="${_gridSuper.toFixed(2)}" stroke="#C0C0C0" stroke-width="1" stroke-dasharray="4,3"/>`);
                } else {
                    parts.push(`      <line x1="${pos}" y1="0" x2="${pos}" y2="${_gridSuper.toFixed(2)}" stroke="#C0C0C0" stroke-width="0.5" stroke-dasharray="1,3"/>`);
                }
            }
            parts.push(`    </pattern>`);
            parts.push(`  </defs>`);
            parts.push(`  <rect x="${gx.toFixed(1)}" y="${gy.toFixed(1)}" width="${gw.toFixed(1)}" height="${gh.toFixed(1)}" fill="url(#grid)"/>`);
        }

        // Assign interface indices for staggered routing of interface connections
        let leftIdx = 0;
        let rightIdx = 0;
        for (const conn of model.connections) {
            const srcParts = conn.source.split(".");
            const dstParts = conn.destination.split(".");
            if (srcParts.length === 1 && srcParts[0] in interfaceMap) {
                conn._ifaceIndex = leftIdx;
                leftIdx += 1;
            } else if (dstParts.length === 1 && dstParts[0] in interfaceMap) {
                conn._ifaceIndex = rightIdx;
                rightIdx += 1;
            }
        }

        // Connections
        const router = new ConnectionRouter();
        parts.push('  <g id="connections">');
        for (const conn of model.connections) {
            const waypoints = router.route(conn, model, instanceMap, interfaceMap);
            if (waypoints.length > 0) {
                const color = this._getConnectionColor(conn, model, instanceMap);
                const doubleLine = this._isDoubleLineConnection(conn, model, instanceMap);
                parts.push(this._renderConnection(waypoints, color, doubleLine));
            }
        }
        parts.push('  </g>');

        // Interface ports
        parts.push('  <g id="interface_ports">');
        for (const ip of model.interfacePorts) {
            parts.push(this._renderInterfacePort(ip));
        }
        parts.push('  </g>');

        // Instances
        parts.push('  <g id="instances">');
        for (const inst of model.instances) {
            parts.push(this._renderInstance(inst));
        }
        parts.push('  </g>');

        parts.push('</svg>');
        return parts.join("\n");
    }

    _svgHeader(vbX, vbY, vbW, vbH) {
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
     viewBox="${vbX.toFixed(1)} ${vbY.toFixed(1)} ${vbW.toFixed(1)} ${vbH.toFixed(1)}"
     width="${Math.round(vbW)}" height="${Math.round(vbH)}">${this.FONT_FACE_STYLE}${shadowDefs}`;
    }

    // Instance rendering
    _renderInstance(inst) {
        const parts = [];
        parts.push(`    <g id="fb_${inst.name}" transform="translate(${inst.renderX.toFixed(1)}, ${inst.renderY.toFixed(1)})">`);
        parts.push(this._renderBlockOutline(inst));
        parts.push(this._renderNameSection(inst));
        parts.push(this._renderEventPorts(inst));
        parts.push(this._renderDataPorts(inst));
        parts.push(this._renderParameterLabels(inst));
        parts.push(this._renderAdapterPorts(inst));
        parts.push(this._renderInstanceLabel(inst));
        parts.push('    </g>');
        return parts.join("\n");
    }

    _renderBlockOutline(inst) {
        const notch = 8, r = 3;
        const et = inst.eventSectionHeight;
        const nb = inst.nameSectionBottom;
        const w = inst.blockWidth, h = inst.blockHeight;

        const pathD = `M ${r} 0
            L ${w - r} 0 A ${r} ${r} 0 0 1 ${w} ${r}
            L ${w} ${et - r} A ${r} ${r} 0 0 1 ${w - r} ${et}
            L ${w - notch} ${et} L ${w - notch} ${nb} L ${w - r} ${nb}
            A ${r} ${r} 0 0 1 ${w} ${nb + r}
            L ${w} ${h - r} A ${r} ${r} 0 0 1 ${w - r} ${h}
            L ${r} ${h} A ${r} ${r} 0 0 1 0 ${h - r}
            L 0 ${nb + r} A ${r} ${r} 0 0 1 ${r} ${nb}
            L ${notch} ${nb} L ${notch} ${et} L ${r} ${et}
            A ${r} ${r} 0 0 1 0 ${et - r} L 0 ${r}
            A ${r} ${r} 0 0 1 ${r} 0 Z`;

        const filterAttr = this.showShadow ? ' filter="url(#dropShadow)"' : '';

        return `      <path d="${pathD}"
            fill="#FFFFFF" stroke="${this.BLOCK_STROKE_COLOR}" stroke-width="1.5"
            stroke-linejoin="round"${filterAttr}/>`;
    }

    _renderNameSection(inst) {
        const centerY = inst.nameSectionTop + (inst.nameSectionBottom - inst.nameSectionTop) / 2;
        const w = inst.blockWidth;
        const shortType = _truncateLabel(inst.typeName.includes("::") ? inst.typeName.split("::").pop() : inst.typeName, this.settings.maxTypeLabelSize);

        let iconLetter;
        if (inst.fbType === "Adapter") iconLetter = "A";
        else if (inst.fbType === "BasicFB") iconLetter = "B";
        else if (inst.fbType === "CompositeFB") iconLetter = "C";
        else if (inst.fbType === "ServiceInterfaceFB") iconLetter = "Si";
        else if (inst.fbType === "SubApp") iconLetter = "S";
        else iconLetter = "B";

        const iconW = 14, iconH = 14, iconR = 1, iconND = 1.5;
        const gapIconText = 4;

        // Calculate content width to center icon + type name between notches
        const notch = 8;
        const typeTextWidth = this._measureText(shortType, true);
        const totalContentWidth = iconW + gapIconText + typeTextWidth;
        const contentStartX = notch + ((w - 2 * notch) - totalContentWidth) / 2;

        const iconX = contentStartX;
        const iconY = centerY - iconH / 2;
        const iconNT = iconY + iconH / 4;
        const iconNB = iconNT + iconH / 6;

        const iconPath = `M ${iconX + iconR} ${iconY}
            L ${iconX + iconW - iconR} ${iconY} A ${iconR} ${iconR} 0 0 1 ${iconX + iconW} ${iconY + iconR}
            L ${iconX + iconW} ${iconNT} L ${iconX + iconW - iconND} ${iconNT}
            L ${iconX + iconW - iconND} ${iconNB} L ${iconX + iconW} ${iconNB}
            L ${iconX + iconW} ${iconY + iconH - iconR} A ${iconR} ${iconR} 0 0 1 ${iconX + iconW - iconR} ${iconY + iconH}
            L ${iconX + iconR} ${iconY + iconH} A ${iconR} ${iconR} 0 0 1 ${iconX} ${iconY + iconH - iconR}
            L ${iconX} ${iconNB} L ${iconX + iconND} ${iconNB}
            L ${iconX + iconND} ${iconNT} L ${iconX} ${iconNT}
            L ${iconX} ${iconY + iconR} A ${iconR} ${iconR} 0 0 1 ${iconX + iconR} ${iconY} Z`;

        let iconContent;
        if (inst.fbType === "SubApp") {
            const mw = 5.5, mh = 7, gap = 3;
            const pw = mw * 2 + gap;
            const px = iconX + (iconW - pw) / 2;
            const py = iconY + iconH - mh - 1.5;
            const leftPath = this._miniFbPath(px, py, mw, mh);
            const rightPath = this._miniFbPath(px + mw + gap, py, mw, mh);
            const cx1 = px + mw, cx2 = px + mw + gap;
            const ecy = py + mh * 0.12, dcy = py + mh * 0.7;
            iconContent = `
      <path d="${leftPath}" fill="#1565C0" stroke="none"/>
      <path d="${rightPath}" fill="#1565C0" stroke="none"/>
      <line x1="${cx1}" y1="${ecy}" x2="${cx2}" y2="${ecy}" stroke="#3DA015" stroke-width="1.2"/>
      <line x1="${cx1}" y1="${dcy}" x2="${cx2}" y2="${dcy}" stroke="#FF0000" stroke-width="1.2"/>`;
        } else {
            iconContent = `
      <text x="${iconX + iconW / 2}" y="${centerY + 4}"
            font-family="${this.FONT_FAMILY}" font-size="10" font-weight="bold"
            fill="#000000" text-anchor="middle">${iconLetter}</text>`;
        }

        // Type name text position (after icon)
        const textX = iconX + iconW + gapIconText;
        return `      <!-- Name Section -->
      <path d="${iconPath}"
            fill="#87CEEB" stroke="#1565C0" stroke-width="1"/>${iconContent}
      <text x="${textX}" y="${centerY + 4}"
            font-family="${this.FONT_FAMILY_ITALIC}" font-size="${this.FONT_SIZE}"
            fill="#000000">${shortType}</text>`;
    }

    _miniFbPath(x, y, w, h) {
        const nd = w * 0.15, nh = h / 6, nt = y + h / 4, nb = nt + nh, r = 0.5;
        return `M ${x + r} ${y} L ${x + w - r} ${y} A ${r} ${r} 0 0 1 ${x + w} ${y + r} L ${x + w} ${nt} L ${x + w - nd} ${nt} L ${x + w - nd} ${nb} L ${x + w} ${nb} L ${x + w} ${y + h - r} A ${r} ${r} 0 0 1 ${x + w - r} ${y + h} L ${x + r} ${y + h} A ${r} ${r} 0 0 1 ${x} ${y + h - r} L ${x} ${nb} L ${x + nd} ${nb} L ${x + nd} ${nt} L ${x} ${nt} L ${x} ${y + r} A ${r} ${r} 0 0 1 ${x + r} ${y} Z`;
    }

    _renderInstanceLabel(inst) {
        // Instance name centered above the block, slightly above the top edge
        const labelX = inst.blockWidth / 2;
        const labelY = -5;
        return `      <!-- Instance Name -->
      <text x="${labelX}" y="${labelY}"
            font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
            fill="#000000" text-anchor="middle">${inst.name}</text>`;
    }

    _renderEventPorts(inst) {
        const parts = [];
        // Event inputs – centered in each row
        let y = this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.eventInputs) {
            parts.push(this._renderPortLeft(p, y, this.EVENT_PORT_COLOR));
            y += this.PORT_ROW_HEIGHT;
        }

        y = this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.eventOutputs) {
            parts.push(this._renderPortRight(p, y, inst.blockWidth, this.EVENT_PORT_COLOR));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderDataPorts(inst) {
        const parts = [];
        const baseY = inst.nameSectionBottom;

        let y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.dataInputs) {
            parts.push(this._renderPortLeft(p, y, this._getPortColor(p.portType)));
            y += this.PORT_ROW_HEIGHT;
        }

        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.dataOutputs) {
            parts.push(this._renderPortRight(p, y, inst.blockWidth, this._getPortColor(p.portType)));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderParameterLabels(inst) {
        if (!inst.parameters || Object.keys(inst.parameters).length === 0) return "";

        const parts = [];

        // Build port name → local y lookup for all input ports
        const portYMap = {};
        // Event inputs
        let y = this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.eventInputs) {
            portYMap[p.name] = y;
            y += this.PORT_ROW_HEIGHT;
        }
        // Data inputs
        y = inst.nameSectionBottom + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.dataInputs) {
            portYMap[p.name] = y;
            y += this.PORT_ROW_HEIGHT;
        }

        // Build port name → type lookup
        const portTypeMap = {};
        for (const p of inst.eventInputs) portTypeMap[p.name] = "Event";
        for (const p of inst.dataInputs) portTypeMap[p.name] = p.portType;

        for (const [paramName, paramValue] of Object.entries(inst.parameters)) {
            if (paramName.startsWith("__")) continue;
            if (!(paramName in portYMap)) continue;
            const py = portYMap[paramName];
            const portType = portTypeMap[paramName] || "";
            let displayValue = _formatParameterValue(paramValue, portType);
            displayValue = _truncateLabel(displayValue, this.settings.maxValueLabelSize);
            displayValue = _xmlEscape(displayValue);
            const textX = -3;
            const textY = py + this.FONT_SIZE * 0.35;
            parts.push(
                `      <text x="${textX}" y="${textY.toFixed(1)}"` +
                ` font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"` +
                ` fill="#000000" text-anchor="end">${displayValue}</text>`);
        }

        return parts.join("\n");
    }

    _renderAdapterPorts(inst) {
        if (inst.sockets.length === 0 && inst.plugs.length === 0) return "";
        const parts = [];
        const baseY = inst.adapterSectionTop;

        let y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.sockets) {
            parts.push(this._renderSocketPort(p, y));
            y += this.PORT_ROW_HEIGHT;
        }

        y = baseY + this.PORT_ROW_HEIGHT / 2;
        for (const p of inst.plugs) {
            parts.push(this._renderPlugPort(p, y, inst.blockWidth));
            y += this.PORT_ROW_HEIGHT;
        }

        return parts.join("\n");
    }

    _renderPortLeft(port, y, color) {
        const tw = this.TRIANGLE_WIDTH, th = this.TRIANGLE_HEIGHT;
        const triY = y;
        const triX = 0;  // base aligned with left FB border
        const triPts = `${triX},${triY - th/2} ${triX + tw},${triY} ${triX},${triY + th/2}`;
        const textX = triX + tw + 1;
        const textY = y + this.FONT_SIZE * 0.35;
        const displayName = _truncateLabel(port.name, this.settings.maxPinLabelSize);
        return `      <polygon points="${triPts}" fill="${color}"/>
      <text x="${textX}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
            fill="#000000">${displayName}</text>`;
    }

    _renderPortRight(port, y, blockWidth, color) {
        const tw = this.TRIANGLE_WIDTH, th = this.TRIANGLE_HEIGHT;
        const triY = y;
        const triX = blockWidth - tw;  // tip at right FB border
        const triPts = `${triX},${triY - th/2} ${triX + tw},${triY} ${triX},${triY + th/2}`;
        const textY = y + this.FONT_SIZE * 0.35;
        const displayName = _truncateLabel(port.name, this.settings.maxPinLabelSize);
        return `      <polygon points="${triPts}" fill="${color}"/>
      <text x="${triX - 1}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
            fill="#000000" text-anchor="end">${displayName}</text>`;
    }

    _renderSocketPort(port, y) {
        const rw = this.TRIANGLE_WIDTH * 2, rh = this.TRIANGLE_HEIGHT;
        const symY = y;
        const rx = 0, ry = symY - rh / 2;  // aligned with left FB border
        const ns = rx + rw / 2, nw = rw / 4, nd = rh / 6;

        const pathD = `M ${rx} ${ry} L ${ns} ${ry} L ${ns} ${ry + nd} L ${ns + nw} ${ry + nd} L ${ns + nw} ${ry} L ${rx + rw} ${ry} L ${rx + rw} ${ry + rh} L ${ns + nw} ${ry + rh} L ${ns + nw} ${ry + rh - nd} L ${ns} ${ry + rh - nd} L ${ns} ${ry + rh} L ${rx} ${ry + rh} Z`;

        const textY = y + this.FONT_SIZE * 0.35;
        const displayName = _truncateLabel(port.name, this.settings.maxPinLabelSize);
        return `      <path d="${pathD}" fill="none" stroke="${this.ADAPTER_PORT_COLOR}" stroke-width="1"/>
      <text x="${rx + rw + 3}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
            fill="#000000">${displayName}</text>`;
    }

    _renderPlugPort(port, y, blockWidth) {
        const rw = this.TRIANGLE_WIDTH * 2, rh = this.TRIANGLE_HEIGHT;
        const symY = y;
        const rx = blockWidth - rw, ry = symY - rh / 2;  // aligned with right FB border
        const ns = rx + rw / 4, nw = rw / 4, nd = rh / 6;

        const pathD = `M ${rx} ${ry} L ${ns} ${ry} L ${ns} ${ry + nd} L ${ns + nw} ${ry + nd} L ${ns + nw} ${ry} L ${rx + rw} ${ry} L ${rx + rw} ${ry + rh} L ${ns + nw} ${ry + rh} L ${ns + nw} ${ry + rh - nd} L ${ns} ${ry + rh - nd} L ${ns} ${ry + rh} L ${rx} ${ry + rh} Z`;

        const textY = y + this.FONT_SIZE * 0.35;
        const displayName = _truncateLabel(port.name, this.settings.maxPinLabelSize);
        return `      <path d="${pathD}" fill="${this.ADAPTER_PORT_COLOR}"/>
      <text x="${rx - 3}" y="${textY}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
            fill="#000000" text-anchor="end">${displayName}</text>`;
    }

    // Connection rendering
    _bevelWaypoints(waypoints, bevelRadius = 5) {
        if (waypoints.length <= 2) return [...waypoints];

        const result = [waypoints[0]];

        for (let i = 1; i < waypoints.length - 1; i++) {
            const [px, py] = waypoints[i - 1];
            const [cx, cy] = waypoints[i];
            const [nx, ny] = waypoints[i + 1];

            const inDx = cx - px, inDy = cy - py;
            const inLen = Math.hypot(inDx, inDy);
            const outDx = nx - cx, outDy = ny - cy;
            const outLen = Math.hypot(outDx, outDy);

            let r = (inLen > 0 && outLen > 0) ? Math.min(bevelRadius, inLen * 0.4, outLen * 0.4) : 0;

            if (r > 0.5 && Math.abs(inDx * outDy - inDy * outDx) > 0.01) {
                const inUx = inDx / inLen, inUy = inDy / inLen;
                const outUx = outDx / outLen, outUy = outDy / outLen;
                result.push([cx - inUx * r, cy - inUy * r]);
                result.push([cx + outUx * r, cy + outUy * r]);
            } else {
                result.push([cx, cy]);
            }
        }

        result.push(waypoints[waypoints.length - 1]);
        return result;
    }

    _renderConnection(waypoints, color, doubleLine = false) {
        if (waypoints.length < 2) return "";

        // Apply bevels at direction changes
        const beveled = this._bevelWaypoints(waypoints);

        const pts = beveled.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

        if (doubleLine) {
            const lighter = this._lighterColor(color);
            const outer = `    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round"/>`;
            const inner = `    <polyline points="${pts}" fill="none" stroke="${lighter}" stroke-width="1" stroke-linejoin="round"/>`;
            return outer + "\n" + inner;
        }
        return `    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>`;
    }

    // Interface port rendering
    _renderInterfacePort(ip) {
        const x = ip.renderX, y = ip.renderY;
        let color;
        if (ip.category === "event") color = this.EVENT_PORT_COLOR;
        else if (ip.category === "adapter") color = this.ADAPTER_PORT_COLOR;
        else color = this._getPortColor(ip.portType);

        const tw = this.TRIANGLE_WIDTH, th = this.TRIANGLE_HEIGHT;
        const textY = y + this.FONT_SIZE * 0.35;
        const displayName = _truncateLabel(ip.name, this.settings.maxInterfaceBarSize);

        // Adapter ports use socket/plug symbols
        if (ip.category === "adapter") {
            return this._renderInterfaceAdapterPort(ip, x, y, textY, displayName);
        }

        let triPts, textX, textAnchor;

        if (ip.direction === "input") {
            const triX = x - tw;
            triPts = `${triX},${y - th/2} ${x},${y} ${triX},${y + th/2}`;
            textX = triX - 1;
            textAnchor = "end";
        } else {
            const triX = x + tw;
            triPts = `${triX},${y - th/2} ${x},${y} ${triX},${y + th/2}`;
            textX = triX + 1;
            textAnchor = "start";
        }

        return `    <polygon points="${triPts}" fill="${color}"/>
    <text x="${textX}" y="${textY.toFixed(1)}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="${textAnchor}">${displayName}</text>`;
    }

    _renderInterfaceAdapterPort(ip, x, y, textY, displayName) {
        const rectW = this.TRIANGLE_WIDTH * 2;
        const rectH = this.TRIANGLE_HEIGHT;
        const color = this.ADAPTER_PORT_COLOR;
        let rectX, rectY, notchStart, notchWidth, notchDepth, pathD, textX, textAnchor, fill, stroke;

        if (ip.direction === "input") {
            // Socket symbol at right edge of input sidebar (filled, mirrored)
            rectX = x - rectW;
            rectY = y - rectH / 2;
            notchStart = rectX + rectW / 4;
            notchWidth = rectW / 4;
            notchDepth = rectH / 6;
            pathD = `M ${rectX} ${rectY} L ${notchStart} ${rectY} `
                  + `L ${notchStart} ${rectY + notchDepth} `
                  + `L ${notchStart + notchWidth} ${rectY + notchDepth} `
                  + `L ${notchStart + notchWidth} ${rectY} `
                  + `L ${rectX + rectW} ${rectY} `
                  + `L ${rectX + rectW} ${rectY + rectH} `
                  + `L ${notchStart + notchWidth} ${rectY + rectH} `
                  + `L ${notchStart + notchWidth} ${rectY + rectH - notchDepth} `
                  + `L ${notchStart} ${rectY + rectH - notchDepth} `
                  + `L ${notchStart} ${rectY + rectH} `
                  + `L ${rectX} ${rectY + rectH} Z`;
            textX = rectX - 3;
            textAnchor = "end";
            fill = color;
            stroke = "";
        } else {
            // Plug symbol at left edge of output sidebar (outline, mirrored)
            rectX = x;
            rectY = y - rectH / 2;
            notchStart = rectX + rectW / 2;
            notchWidth = rectW / 4;
            notchDepth = rectH / 6;
            pathD = `M ${rectX} ${rectY} L ${notchStart} ${rectY} `
                  + `L ${notchStart} ${rectY + notchDepth} `
                  + `L ${notchStart + notchWidth} ${rectY + notchDepth} `
                  + `L ${notchStart + notchWidth} ${rectY} `
                  + `L ${rectX + rectW} ${rectY} `
                  + `L ${rectX + rectW} ${rectY + rectH} `
                  + `L ${notchStart + notchWidth} ${rectY + rectH} `
                  + `L ${notchStart + notchWidth} ${rectY + rectH - notchDepth} `
                  + `L ${notchStart} ${rectY + rectH - notchDepth} `
                  + `L ${notchStart} ${rectY + rectH} `
                  + `L ${rectX} ${rectY + rectH} Z`;
            textX = rectX + rectW + 3;
            textAnchor = "start";
            fill = "none";
            stroke = ` stroke="${color}" stroke-width="1"`;
        }

        return `    <path d="${pathD}" fill="${fill}"${stroke}/>
    <text x="${textX}" y="${textY.toFixed(1)}" font-family="${this.FONT_FAMILY}" font-size="${this.FONT_SIZE}"
          fill="#000000" text-anchor="${textAnchor}">${displayName}</text>`;
    }
}

// ===========================================================================
// High-level API
// ===========================================================================

/**
 * Convert IEC 61499 network XML to SVG
 * @param {string} xmlString - The XML content
 * @param {Object} options - Rendering options
 * @param {boolean} options.showShadow - Show drop shadow (default: true)
 * @param {Object} options.typeLibXmls - Map of type name → XML string for type resolution
 * @returns {string} SVG content
 */
function convertNetworkToSvg(xmlString, options = {}) {
    const settings = options.settings || (options.settingsIni ? loadBlockSizeSettings(options.settingsIni) : new BlockSizeSettings(options.blockSizeSettings || {}));

    const parser = new NetworkParser();
    const model = parser.parse(xmlString);

    const resolver = new TypeResolver(options.typeLibXmls || {});
    resolver.resolve(model);

    const layout = new NetworkLayoutEngine(settings);
    layout.layout(model);

    const renderer = new NetworkSVGRenderer({ ...options, settings });
    return renderer.render(model, layout);
}

// ===========================================================================
// Node.js CLI
// ===========================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        convertNetworkToSvg,
        NetworkParser, TypeResolver, NetworkLayoutEngine, ConnectionRouter, NetworkSVGRenderer,
        NetworkModel, FBInstance, Connection, InterfacePort, Port,
        BlockSizeSettings, loadBlockSizeSettings, _truncateLabel
    };

    if (require.main === module) {
        const fs = require('fs');
        const path = require('path');

        const args = process.argv.slice(2);
        if (args.length === 0) {
            console.log('Usage: node iec61499_network_to_svg.js input.fbt [-o output.svg] [--type-lib path] [--no-shadow] [--grid]');
            process.exit(1);
        }

        const inputFile = args[0];
        let outputFile = null;
        let typeLibPaths = [];
        let settingsPath = null;
        const options = { showShadow: true };

        for (let i = 1; i < args.length; i++) {
            if (args[i] === '-o' && args[i + 1]) outputFile = args[++i];
            else if (args[i] === '--type-lib' && args[i + 1]) typeLibPaths.push(args[++i]);
            else if (args[i] === '--no-shadow') options.showShadow = false;
            else if (args[i] === '--grid') options.showGrid = true;
            else if (args[i] === '--settings' && args[i + 1]) settingsPath = args[++i];
        }

        if (settingsPath) {
            options.settingsIni = fs.readFileSync(settingsPath, 'utf-8');
        } else {
            // Try loading from default location next to script
            const defaultSettings = path.join(path.dirname(process.argv[1]), 'block_size_settings.ini');
            try { options.settingsIni = fs.readFileSync(defaultSettings, 'utf-8'); } catch (e) {}
        }

        // Merge type library paths: INI defaults + CLI --type-lib arguments
        const settings = options.settingsIni ? loadBlockSizeSettings(options.settingsIni) : new BlockSizeSettings();
        const iniTypeLibPaths = settings.typeLibPaths || [];
        for (const p of typeLibPaths) {
            if (!iniTypeLibPaths.includes(p)) iniTypeLibPaths.push(p);
        }
        typeLibPaths = iniTypeLibPaths;

        if (!outputFile) {
            outputFile = inputFile.replace(/\.(fbt|sub|sys)$/i, '.network.svg');
        }

        try {
            const xmlContent = fs.readFileSync(inputFile, 'utf-8');

            // Setup DOMParser for Node.js
            const { JSDOM } = require('jsdom');
            global.DOMParser = new JSDOM().window.DOMParser;

            // Build type library from filesystem
            const typeLibXmls = {};
            for (const tlPath of typeLibPaths) {
                const walkDir = (dir, rootPath) => {
                    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
                        const fullPath = path.join(dir, entry.name);
                        if (entry.isDirectory()) {
                            walkDir(fullPath, rootPath);
                        } else if (/\.(fbt|sub|adp)$/i.test(entry.name)) {
                            try {
                                const content = fs.readFileSync(fullPath, 'utf-8');
                                const name = entry.name.replace(/\.(fbt|sub|adp)$/i, '');
                                typeLibXmls[name] = content;

                                // Also index by relative path with :: separators
                                const rel = path.relative(rootPath, fullPath);
                                const parts = rel.split(path.sep);
                                parts[parts.length - 1] = name;
                                const qualified = parts.join("::");
                                typeLibXmls[qualified] = content;
                            } catch (e) {}
                        }
                    }
                };
                if (fs.existsSync(tlPath)) walkDir(tlPath, tlPath);
            }

            // Also add the input file's directory
            const inputDir = path.dirname(inputFile);
            if (!typeLibPaths.includes(inputDir)) {
                for (const entry of fs.readdirSync(inputDir, { withFileTypes: true })) {
                    if (/\.(fbt|sub|adp)$/i.test(entry.name)) {
                        try {
                            const name = entry.name.replace(/\.(fbt|sub|adp)$/i, '');
                            if (!typeLibXmls[name]) {
                                typeLibXmls[name] = fs.readFileSync(path.join(inputDir, entry.name), 'utf-8');
                            }
                        } catch (e) {}
                    }
                }
            }

            options.typeLibXmls = typeLibXmls;
            options.settings = settings;
            const svg = convertNetworkToSvg(xmlContent, options);
            fs.writeFileSync(outputFile, svg, 'utf-8');
            console.log(`SVG written to: ${outputFile}`);
        } catch (error) {
            console.error(`Error: ${error.message}`);
            process.exit(1);
        }
    }
}
