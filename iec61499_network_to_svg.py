#!/usr/bin/env python3
"""
IEC 61499 Function Block Network to SVG Converter

Renders the internal network of composite FBs, SubApps, and Systems as SVG
diagrams in the style of 4diac IDE's network view.

Shows FB instances as boxes with event/data/adapter connections routed between them.
"""

import xml.etree.ElementTree as ET
import argparse
import configparser
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple

# Try to import Pillow for accurate text measurement
try:
    from PIL import ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


# ===========================================================================
# Block Size Settings (4diac IDE defaults)
# ===========================================================================

@dataclass
class BlockSizeSettings:
    """4diac IDE Block Size settings that control label truncation and margins."""
    max_value_label_size: int = 25
    max_type_label_size: int = 15
    min_pin_label_size: int = 0
    max_pin_label_size: int = 12
    min_interface_bar_size: int = 0
    max_interface_bar_size: int = 40
    max_hidden_connection_label_size: int = 15
    # Block margins (in pixels)
    margin_top_bottom: int = 0
    margin_left_right: int = 0


def load_block_size_settings(path: str = None) -> BlockSizeSettings:
    """Load block size settings from an INI file.

    Falls back to defaults if file not found or on parse error.
    """
    settings = BlockSizeSettings()
    if path is None:
        # Look for block_size_settings.ini next to this script
        path = str(Path(__file__).parent / "block_size_settings.ini")
    if not Path(path).exists():
        return settings
    cp = configparser.ConfigParser()
    cp.read(path)
    if "BlockSize" in cp:
        section = cp["BlockSize"]
        for fld in ("max_value_label_size", "max_type_label_size",
                     "min_pin_label_size", "max_pin_label_size",
                     "min_interface_bar_size", "max_interface_bar_size",
                     "max_hidden_connection_label_size"):
            if fld in section:
                setattr(settings, fld, int(section[fld]))
    if "BlockMargins" in cp:
        section = cp["BlockMargins"]
        if "top_bottom" in section:
            settings.margin_top_bottom = int(section["top_bottom"])
        if "left_right" in section:
            settings.margin_left_right = int(section["left_right"])
    return settings


def _truncate_label(text: str, max_len: int) -> str:
    """Truncate a label and append '...' if it exceeds max_len characters.

    If max_len <= 0, no truncation is applied.
    """
    if max_len <= 0 or len(text) <= max_len:
        return text
    return text[:max_len] + "…"


# ===========================================================================
# Data Model
# ===========================================================================

@dataclass
class Port:
    """Represents an event, data, or adapter port."""
    name: str
    port_type: str = ""
    comment: str = ""
    associated_vars: list = field(default_factory=list)  # WITH associations (event→data var names)


@dataclass
class FBInstance:
    """Represents an FB or SubApp instance in the network."""
    name: str
    type_name: str = ""
    x: float = 0
    y: float = 0
    is_subapp: bool = False
    is_adapter: bool = False
    adapter_kind: str = ""       # "plug" or "socket"
    event_inputs: List[Port] = field(default_factory=list)
    event_outputs: List[Port] = field(default_factory=list)
    data_inputs: List[Port] = field(default_factory=list)
    data_outputs: List[Port] = field(default_factory=list)
    plugs: List[Port] = field(default_factory=list)
    sockets: List[Port] = field(default_factory=list)
    parameters: Dict[str, str] = field(default_factory=dict)
    fb_type: str = ""            # "BasicFB", "CompositeFB", "SubApp", "Adapter", etc.

    # Computed layout fields
    block_width: float = 0
    block_height: float = 0
    render_x: float = 0         # Final rendered x position
    render_y: float = 0         # Final rendered y position
    event_section_height: float = 0
    data_section_height: float = 0
    name_section_top: float = 0
    name_section_bottom: float = 0
    adapter_section_top: float = 0
    adapter_section_height: float = 0
    port_positions: Dict[str, Tuple[float, float]] = field(default_factory=dict)


@dataclass
class Connection:
    """Represents a connection between ports in the network."""
    source: str
    destination: str
    dx1: float = 0
    dx2: float = 0
    dy: float = 0
    conn_type: str = "data"      # "event", "data", or "adapter"


@dataclass
class InterfacePort:
    """Port on the SubApp/Composite boundary (left/right edges)."""
    name: str
    port_type: str = ""
    direction: str = "input"     # "input" (left) or "output" (right)
    category: str = "data"       # "event", "data", or "adapter"
    render_x: float = 0
    render_y: float = 0


@dataclass
class NetworkModel:
    """Complete network model."""
    name: str = ""
    comment: str = ""
    root_type: str = ""          # "SubAppType", "FBType", "System"
    instances: List[FBInstance] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    interface_ports: List[InterfacePort] = field(default_factory=list)
    # Sidebar geometry (set by layout engine)
    input_sidebar_width: float = 0
    output_sidebar_width: float = 0
    input_sidebar_rect: Optional[Tuple[float, float, float, float]] = None   # (x, y, w, h)
    output_sidebar_rect: Optional[Tuple[float, float, float, float]] = None  # (x, y, w, h)
    # Header and border geometry (set by layout engine)
    header_rect: Optional[Tuple[float, float, float, float]] = None          # (x, y, w, h)
    outer_border_rect: Optional[Tuple[float, float, float, float]] = None    # (x, y, w, h)
    # Canvas-to-pixel mapping (set by layout engine)
    canvas_origin_x: float = 0   # pixel x corresponding to canvas x=0
    canvas_origin_y: float = 0   # pixel y corresponding to canvas y=0


# ===========================================================================
# Network Parser
# ===========================================================================

class NetworkParser:
    """Parses IEC 61499 XML to extract the internal network structure."""

    def parse(self, xml_source) -> NetworkModel:
        """Parse XML from file path or string."""
        if isinstance(xml_source, str) and ('<' in xml_source):
            root = ET.fromstring(xml_source)
        else:
            tree = ET.parse(xml_source)
            root = tree.getroot()

        if root.tag == "SubAppType":
            return self._parse_subapp_type(root)
        elif root.tag == "FBType":
            return self._parse_fb_type(root)
        elif root.tag == "System":
            return self._parse_system(root)
        else:
            raise ValueError(f"Unknown root element: {root.tag}")

    def _parse_subapp_type(self, root: ET.Element) -> NetworkModel:
        model = NetworkModel(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", ""),
            root_type="SubAppType"
        )

        # Parse interface ports
        iface = root.find("SubAppInterfaceList")
        if iface is not None:
            self._parse_subapp_interface(iface, model)

        # Parse network
        network = root.find("SubAppNetwork")
        if network is not None:
            self._parse_network_contents(network, model)

        return model

    def _parse_fb_type(self, root: ET.Element) -> NetworkModel:
        """Parse a composite FBType with FBNetwork."""
        # Check if this is actually a composite FB
        fb_network = root.find("FBNetwork")
        comp_fb = root.find("CompositeFB")
        if fb_network is None and comp_fb is None:
            raise ValueError("FBType has no FBNetwork or CompositeFB — not a composite FB")

        model = NetworkModel(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", ""),
            root_type="FBType"
        )

        # Parse interface ports
        iface = root.find("InterfaceList")
        if iface is not None:
            self._parse_fbtype_interface(iface, model)

        # Parse network
        network = fb_network if fb_network is not None else comp_fb
        if network is not None:
            self._parse_network_contents(network, model)

        return model

    def _parse_system(self, root: ET.Element) -> NetworkModel:
        """Parse a System file."""
        model = NetworkModel(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", ""),
            root_type="System"
        )

        # Systems have Application elements containing SubAppNetwork
        for app in root.findall("Application"):
            network = app.find("SubAppNetwork")
            if network is not None:
                self._parse_network_contents(network, model)

        return model

    def _parse_subapp_interface(self, iface: ET.Element, model: NetworkModel):
        """Parse SubAppInterfaceList to extract boundary ports."""
        # Event inputs
        for section in iface.findall("SubAppEventInputs"):
            for ev in section.findall("SubAppEvent"):
                model.interface_ports.append(InterfacePort(
                    name=ev.get("Name", ""),
                    port_type=ev.get("Type", "Event"),
                    direction="input",
                    category="event"
                ))

        # Event outputs
        for section in iface.findall("SubAppEventOutputs"):
            for ev in section.findall("SubAppEvent"):
                model.interface_ports.append(InterfacePort(
                    name=ev.get("Name", ""),
                    port_type=ev.get("Type", "Event"),
                    direction="output",
                    category="event"
                ))

        # Data inputs
        for section in iface.findall("InputVars"):
            for var in section.findall("VarDeclaration"):
                model.interface_ports.append(InterfacePort(
                    name=var.get("Name", ""),
                    port_type=var.get("Type", ""),
                    direction="input",
                    category="data"
                ))

        # Data outputs
        for section in iface.findall("OutputVars"):
            for var in section.findall("VarDeclaration"):
                model.interface_ports.append(InterfacePort(
                    name=var.get("Name", ""),
                    port_type=var.get("Type", ""),
                    direction="output",
                    category="data"
                ))

    def _parse_fbtype_interface(self, iface: ET.Element, model: NetworkModel):
        """Parse InterfaceList for a composite FBType."""
        # Event inputs
        for section in iface.findall("EventInputs"):
            for ev in section.findall("Event"):
                model.interface_ports.append(InterfacePort(
                    name=ev.get("Name", ""),
                    port_type=ev.get("Type", "Event"),
                    direction="input",
                    category="event"
                ))

        # Event outputs
        for section in iface.findall("EventOutputs"):
            for ev in section.findall("Event"):
                model.interface_ports.append(InterfacePort(
                    name=ev.get("Name", ""),
                    port_type=ev.get("Type", "Event"),
                    direction="output",
                    category="event"
                ))

        # Data inputs
        for section in iface.findall("InputVars"):
            for var in section.findall("VarDeclaration"):
                model.interface_ports.append(InterfacePort(
                    name=var.get("Name", ""),
                    port_type=var.get("Type", ""),
                    direction="input",
                    category="data"
                ))

        # Data outputs
        for section in iface.findall("OutputVars"):
            for var in section.findall("VarDeclaration"):
                model.interface_ports.append(InterfacePort(
                    name=var.get("Name", ""),
                    port_type=var.get("Type", ""),
                    direction="output",
                    category="data"
                ))

        # Plugs → adapter instances in the network
        for section in iface.findall("Plugs"):
            for adp in section.findall("AdapterDeclaration"):
                inst = FBInstance(
                    name=adp.get("Name", ""),
                    type_name=adp.get("Type", ""),
                    x=float(adp.get("x", "0")),
                    y=float(adp.get("y", "0")),
                    is_adapter=True,
                    adapter_kind="plug",
                    fb_type="Adapter"
                )
                model.instances.append(inst)

        # Sockets → adapter instances in the network
        for section in iface.findall("Sockets"):
            for adp in section.findall("AdapterDeclaration"):
                inst = FBInstance(
                    name=adp.get("Name", ""),
                    type_name=adp.get("Type", ""),
                    x=float(adp.get("x", "0")),
                    y=float(adp.get("y", "0")),
                    is_adapter=True,
                    adapter_kind="socket",
                    fb_type="Adapter"
                )
                model.instances.append(inst)

    def _parse_network_contents(self, network: ET.Element, model: NetworkModel):
        """Parse FB/SubApp instances and connections from network element."""
        # Parse FB instances
        for fb_elem in network.findall("FB"):
            inst = FBInstance(
                name=fb_elem.get("Name", ""),
                type_name=fb_elem.get("Type", ""),
                x=float(fb_elem.get("x", "0")),
                y=float(fb_elem.get("y", "0")),
            )
            # Parse parameters
            for param in fb_elem.findall("Parameter"):
                inst.parameters[param.get("Name", "")] = param.get("Value", "")
            # Check for DataType attribute (type override)
            for attr in fb_elem.findall("Attribute"):
                if attr.get("Name") == "DataType":
                    inst.parameters["__DataType__"] = attr.get("Value", "")
            model.instances.append(inst)

        # Parse SubApp instances
        for sub_elem in network.findall("SubApp"):
            inst = FBInstance(
                name=sub_elem.get("Name", ""),
                type_name=sub_elem.get("Type", ""),
                x=float(sub_elem.get("x", "0")),
                y=float(sub_elem.get("y", "0")),
                is_subapp=True,
                fb_type="SubApp"
            )
            for param in sub_elem.findall("Parameter"):
                inst.parameters[param.get("Name", "")] = param.get("Value", "")
            model.instances.append(inst)

        # Parse connections
        for ec in network.findall("EventConnections"):
            for conn in ec.findall("Connection"):
                model.connections.append(Connection(
                    source=conn.get("Source", ""),
                    destination=conn.get("Destination", ""),
                    dx1=float(conn.get("dx1", "0")),
                    dx2=float(conn.get("dx2", "0")),
                    dy=float(conn.get("dy", "0")),
                    conn_type="event"
                ))

        for dc in network.findall("DataConnections"):
            for conn in dc.findall("Connection"):
                model.connections.append(Connection(
                    source=conn.get("Source", ""),
                    destination=conn.get("Destination", ""),
                    dx1=float(conn.get("dx1", "0")),
                    dx2=float(conn.get("dx2", "0")),
                    dy=float(conn.get("dy", "0")),
                    conn_type="data"
                ))

        for ac in network.findall("AdapterConnections"):
            for conn in ac.findall("Connection"):
                model.connections.append(Connection(
                    source=conn.get("Source", ""),
                    destination=conn.get("Destination", ""),
                    dx1=float(conn.get("dx1", "0")),
                    dx2=float(conn.get("dx2", "0")),
                    dy=float(conn.get("dy", "0")),
                    conn_type="adapter"
                ))


# ===========================================================================
# Type Resolver
# ===========================================================================

class TypeResolver:
    """Resolves FB instance interfaces from type library or connection inference."""

    def __init__(self, type_lib_paths: List[str] = None):
        self.type_lib_paths = type_lib_paths or []
        self._type_cache: Dict[str, dict] = {}
        self._file_index: Dict[str, str] = {}  # type_name → file_path
        self._index_built = False

    def _build_file_index(self):
        """Build an index of type names to file paths."""
        if self._index_built:
            return
        for lib_path in self.type_lib_paths:
            lib = Path(lib_path)
            if not lib.exists():
                continue
            for ext in ['*.fbt', '*.sub', '*.adp']:
                for f in lib.rglob(ext):
                    # Index by filename (without extension)
                    name = f.stem
                    self._file_index[name] = str(f)
                    # Also index by relative path with :: separators
                    try:
                        rel = f.relative_to(lib)
                        # Convert path to :: namespace: iec61499/events/E_SWITCH.fbt → iec61499::events::E_SWITCH
                        parts = list(rel.parts)
                        parts[-1] = f.stem  # Remove extension
                        qualified = "::".join(parts)
                        self._file_index[qualified] = str(f)
                    except ValueError:
                        pass
        self._index_built = True

    def resolve(self, model: NetworkModel):
        """Resolve interfaces for all instances in the model."""
        self._build_file_index()

        for inst in model.instances:
            if inst.is_adapter:
                self._resolve_adapter_instance(inst, model)
            else:
                self._resolve_instance(inst, model)

    def _resolve_instance(self, inst: FBInstance, model: NetworkModel):
        """Resolve a single FB/SubApp instance interface."""
        # Tier 1: Filesystem lookup
        iface = self._lookup_type(inst.type_name)
        if iface:
            inst.event_inputs = iface.get('event_inputs', [])
            inst.event_outputs = iface.get('event_outputs', [])
            inst.data_inputs = iface.get('data_inputs', [])
            inst.data_outputs = iface.get('data_outputs', [])
            inst.plugs = iface.get('plugs', [])
            inst.sockets = iface.get('sockets', [])
            if not inst.fb_type:
                inst.fb_type = iface.get('fb_type', 'BasicFB')
            return

        # Tier 2: Connection inference
        self._infer_from_connections(inst, model)

    def _resolve_adapter_instance(self, inst: FBInstance, model: NetworkModel):
        """Resolve adapter instance interface from .adp file."""
        iface = self._lookup_type(inst.type_name)
        if iface:
            # For adapters, the interface is swapped based on plug/socket
            if inst.adapter_kind == "plug":
                # Plug: socket-side faces inward
                # Adapter file defines from socket perspective:
                #   EventInputs = events coming IN to socket
                #   EventOutputs = events going OUT from socket
                # For a plug, these are reversed in the network view
                inst.event_inputs = iface.get('event_outputs', [])
                inst.event_outputs = iface.get('event_inputs', [])
                inst.data_inputs = iface.get('data_outputs', [])
                inst.data_outputs = iface.get('data_inputs', [])
            else:
                # Socket: socket-side interface directly
                inst.event_inputs = iface.get('event_inputs', [])
                inst.event_outputs = iface.get('event_outputs', [])
                inst.data_inputs = iface.get('data_inputs', [])
                inst.data_outputs = iface.get('data_outputs', [])
            inst.fb_type = "Adapter"
            return

        # Fallback: infer from connections
        self._infer_from_connections(inst, model)

    def _lookup_type(self, type_name: str) -> Optional[dict]:
        """Look up a type definition from the file index."""
        if type_name in self._type_cache:
            return self._type_cache[type_name]

        # Try full qualified name first
        file_path = self._file_index.get(type_name)
        if not file_path:
            # Try short name (after last ::)
            short_name = type_name.split("::")[-1] if "::" in type_name else type_name
            file_path = self._file_index.get(short_name)

        if not file_path:
            return None

        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            iface = self._extract_interface(root)
            self._type_cache[type_name] = iface
            return iface
        except Exception:
            return None

    def _extract_interface(self, root: ET.Element) -> dict:
        """Extract interface from a parsed XML root."""
        result = {
            'event_inputs': [],
            'event_outputs': [],
            'data_inputs': [],
            'data_outputs': [],
            'plugs': [],
            'sockets': [],
            'fb_type': 'BasicFB'
        }

        # Determine FB type
        if root.tag == "AdapterType":
            result['fb_type'] = 'Adapter'
        elif root.tag == "SubAppType":
            result['fb_type'] = 'SubApp'
        elif root.tag == "FBType":
            if root.find("BasicFB") is not None:
                result['fb_type'] = 'BasicFB'
            elif root.find("CompositeFB") is not None or root.find("FBNetwork") is not None:
                result['fb_type'] = 'CompositeFB'
            elif root.find("SimpleFB") is not None:
                result['fb_type'] = 'SimpleFB'
            else:
                result['fb_type'] = 'ServiceInterfaceFB'

        # Find interface list
        iface = root.find("InterfaceList")
        if iface is None:
            iface = root.find("SubAppInterfaceList")
        if iface is None:
            return result

        # Event inputs
        for section_tag in ["EventInputs", "SubAppEventInputs"]:
            for section in iface.findall(section_tag):
                for ev in section.findall("Event") + section.findall("SubAppEvent"):
                    with_vars = [w.get("Var", "") for w in ev.findall("With") if w.get("Var")]
                    result['event_inputs'].append(Port(
                        name=ev.get("Name", ""),
                        port_type=ev.get("Type", "Event"),
                        comment=ev.get("Comment", ""),
                        associated_vars=with_vars,
                    ))

        # Event outputs
        for section_tag in ["EventOutputs", "SubAppEventOutputs"]:
            for section in iface.findall(section_tag):
                for ev in section.findall("Event") + section.findall("SubAppEvent"):
                    with_vars = [w.get("Var", "") for w in ev.findall("With") if w.get("Var")]
                    result['event_outputs'].append(Port(
                        name=ev.get("Name", ""),
                        port_type=ev.get("Type", "Event"),
                        comment=ev.get("Comment", ""),
                        associated_vars=with_vars,
                    ))

        # Data inputs
        for section in iface.findall("InputVars"):
            for var in section.findall("VarDeclaration"):
                result['data_inputs'].append(Port(
                    name=var.get("Name", ""),
                    port_type=self._build_type_string(var),
                    comment=var.get("Comment", "")
                ))

        # Data outputs
        for section in iface.findall("OutputVars"):
            for var in section.findall("VarDeclaration"):
                result['data_outputs'].append(Port(
                    name=var.get("Name", ""),
                    port_type=self._build_type_string(var),
                    comment=var.get("Comment", "")
                ))

        # Plugs
        for section in iface.findall("Plugs"):
            for adp in section.findall("AdapterDeclaration"):
                result['plugs'].append(Port(
                    name=adp.get("Name", ""),
                    port_type=adp.get("Type", ""),
                    comment=adp.get("Comment", "")
                ))

        # Sockets
        for section in iface.findall("Sockets"):
            for adp in section.findall("AdapterDeclaration"):
                result['sockets'].append(Port(
                    name=adp.get("Name", ""),
                    port_type=adp.get("Type", ""),
                    comment=adp.get("Comment", "")
                ))

        return result

    def _build_type_string(self, var_elem: ET.Element) -> str:
        """Build type string from VarDeclaration, including array dimensions."""
        base_type = var_elem.get("Type", "")
        array_size = var_elem.get("ArraySize", "")
        if array_size:
            return f"ARRAY [0..{int(array_size)-1}] OF {base_type}"
        return base_type

    def _infer_from_connections(self, inst: FBInstance, model: NetworkModel):
        """Infer ports from connection endpoints."""
        event_in_names = []
        event_out_names = []
        data_in_names = []
        data_out_names = []

        for conn in model.connections:
            src_parts = conn.source.split(".")
            dst_parts = conn.destination.split(".")

            # Source: FBName.PortName → output port
            if len(src_parts) == 2 and src_parts[0] == inst.name:
                port_name = src_parts[1]
                if conn.conn_type == "event":
                    if port_name not in event_out_names:
                        event_out_names.append(port_name)
                elif conn.conn_type == "data":
                    if port_name not in data_out_names:
                        data_out_names.append(port_name)

            # Destination: FBName.PortName → input port
            if len(dst_parts) == 2 and dst_parts[0] == inst.name:
                port_name = dst_parts[1]
                if conn.conn_type == "event":
                    if port_name not in event_in_names:
                        event_in_names.append(port_name)
                elif conn.conn_type == "data":
                    if port_name not in data_in_names:
                        data_in_names.append(port_name)

        inst.event_inputs = [Port(name=n, port_type="Event") for n in event_in_names]
        inst.event_outputs = [Port(name=n, port_type="Event") for n in event_out_names]
        inst.data_inputs = [Port(name=n) for n in data_in_names]
        inst.data_outputs = [Port(name=n) for n in data_out_names]

        if not inst.fb_type:
            inst.fb_type = "SubApp" if inst.is_subapp else "BasicFB"


# ===========================================================================
# Layout Engine
# ===========================================================================

class NetworkLayoutEngine:
    """Computes positions and sizes for all network elements."""

    # Layout constants – calibrated to match 4diac IDE at 100 % zoom
    PORT_ROW_HEIGHT = 16
    BLOCK_PADDING = 10
    NAME_SECTION_HEIGHT = 16
    CONNECTOR_WIDTH = 10
    TRIANGLE_WIDTH = 5
    TRIANGLE_HEIGHT = 10
    FONT_SIZE = 12
    MARGIN = 60           # Margin around the diagram for interface ports
    SCALE = 0.16          # Default: 4diac canvas units → SVG pixels (100 % zoom)

    def __init__(self, scale: float = None, settings: BlockSizeSettings = None):
        self._auto_scale_needed = (scale is None)
        if scale is not None:
            self.SCALE = scale
        self.settings = settings or BlockSizeSettings()
        self._font = None
        self._font_italic = None
        self._init_fonts()

    def _init_fonts(self):
        """Initialize fonts for text measurement."""
        if not PILLOW_AVAILABLE:
            return

        home = os.path.expanduser("~")
        font_candidates = [
            f"{home}/Library/Fonts/TGL 0-17.ttf",
            f"{home}/Library/Fonts/TGL 0-17 alt.ttf",
            "/Library/Fonts/TGL 0-17.ttf",
            "/Library/Fonts/TGL 0-17 alt.ttf",
            "/Library/Fonts/Times New Roman.ttf",
            "/System/Library/Fonts/Times.ttc",
            "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
            "C:\\Windows\\Fonts\\times.ttf",
        ]
        italic_candidates = [
            f"{home}/Library/Fonts/TGL 0-16.ttf",
            "/Library/Fonts/TGL 0-16.ttf",
            "/Library/Fonts/Times New Roman Italic.ttf",
            "/System/Library/Fonts/Times.ttc",
            "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Italic.ttf",
            "C:\\Windows\\Fonts\\timesi.ttf",
        ]
        for fp in font_candidates:
            try:
                self._font = ImageFont.truetype(fp, self.FONT_SIZE)
                break
            except:
                continue
        for fp in italic_candidates:
            try:
                self._font_italic = ImageFont.truetype(fp, self.FONT_SIZE)
                break
            except:
                continue
        if self._font_italic is None and self._font is not None:
            self._font_italic = self._font

    def _measure_text(self, text: str, italic: bool = False) -> float:
        if PILLOW_AVAILABLE and self._font:
            font = self._font_italic if italic and self._font_italic else self._font
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0] if bbox else len(text) * 8
        else:
            return len(text) * 8.5

    def layout(self, model: NetworkModel):
        """Compute all positions and sizes."""
        # Size each instance
        for inst in model.instances:
            self._size_instance(inst)

        # Position instances using XML coordinates
        self._position_instances(model)

        # Compute port absolute positions
        for inst in model.instances:
            self._compute_port_positions(inst)

        # Position interface ports
        self._position_interface_ports(model)

        # Compute header and outer border
        self._compute_header_and_border(model)

    def _size_instance(self, inst: FBInstance):
        """Calculate block dimensions for an instance."""
        num_event_inputs = len(inst.event_inputs)
        num_event_outputs = len(inst.event_outputs)
        num_data_inputs = len(inst.data_inputs)
        num_data_outputs = len(inst.data_outputs)
        num_sockets = len(inst.sockets)
        num_plugs = len(inst.plugs)

        num_event_rows = max(num_event_inputs, num_event_outputs, 1)
        num_data_rows = max(num_data_inputs, num_data_outputs, 1)
        num_adapter_rows = max(num_sockets, num_plugs)

        section_padding = self.PORT_ROW_HEIGHT / 2 - 4
        inst.event_section_height = num_event_rows * self.PORT_ROW_HEIGHT + section_padding
        inst.data_section_height = num_data_rows * self.PORT_ROW_HEIGHT + section_padding
        inst.adapter_section_height = num_adapter_rows * self.PORT_ROW_HEIGHT if num_adapter_rows > 0 else 0

        inst.block_height = (inst.event_section_height +
                           self.NAME_SECTION_HEIGHT +
                           inst.data_section_height +
                           inst.adapter_section_height)

        # Width calculation
        # Instance name is rendered ABOVE the block, so it doesn't constrain block width.
        # Name section shows only the type name with icon.
        short_type = inst.type_name.split("::")[-1] if "::" in inst.type_name else inst.type_name
        short_type = _truncate_label(short_type, self.settings.max_type_label_size)
        notch = 8
        icon_w = 14
        gap_icon_text = 4
        type_width = self._measure_text(short_type, italic=True)
        name_section_width = notch + 3 + icon_w + gap_icon_text + type_width + 5 + notch

        triangle_space = self.TRIANGLE_WIDTH + 3 + 1.5
        adapter_space = self.TRIANGLE_WIDTH * 2 + 3 + 1.5

        # Minimum pin label width in pixels (from min_pin_label_size setting)
        min_pin_w = self._measure_text("W" * self.settings.min_pin_label_size) if self.settings.min_pin_label_size > 0 else 0

        max_left = 0
        for port in inst.event_inputs + inst.data_inputs:
            pw = triangle_space + max(min_pin_w, self._measure_text(_truncate_label(port.name, self.settings.max_pin_label_size)))
            max_left = max(max_left, pw)
        for port in inst.sockets:
            pw = adapter_space + max(min_pin_w, self._measure_text(_truncate_label(port.name, self.settings.max_pin_label_size)))
            max_left = max(max_left, pw)

        max_right = 0
        for port in inst.event_outputs + inst.data_outputs:
            pw = triangle_space + max(min_pin_w, self._measure_text(_truncate_label(port.name, self.settings.max_pin_label_size)))
            max_right = max(max_right, pw)
        for port in inst.plugs:
            pw = adapter_space + max(min_pin_w, self._measure_text(_truncate_label(port.name, self.settings.max_pin_label_size)))
            max_right = max(max_right, pw)

        min_center_gap = 8
        ports_width = max_left + min_center_gap + max_right

        inst.block_width = max(80, name_section_width, ports_width)

        inst.name_section_top = inst.event_section_height
        inst.name_section_bottom = inst.event_section_height + self.NAME_SECTION_HEIGHT
        inst.adapter_section_top = inst.name_section_bottom + inst.data_section_height

    def _auto_scale(self, model: NetworkModel) -> float:
        """Compute a scale factor that prevents block overlap.

        For each pair of instances that could potentially overlap,
        ensure the scaled coordinate gap is large enough to fit
        the source block (with some padding).
        Only constrains pairs where blocks are close enough in
        the perpendicular axis that overlap is possible.
        """
        instances = model.instances
        if len(instances) < 2:
            return self.SCALE

        gap = 60  # minimum gap between blocks in SVG pixels

        # Sort by x and y separately to find truly adjacent blocks
        by_x = sorted(instances, key=lambda i: i.x)
        by_y = sorted(instances, key=lambda i: i.y)

        min_scale = 0.0

        # Check vertically adjacent pairs (sorted by y, looking at close x ranges)
        for i in range(len(by_y)):
            for j in range(i + 1, len(by_y)):
                top, bottom = by_y[i], by_y[j]
                dy_canvas = bottom.y - top.y
                if dy_canvas <= 0:
                    continue
                # Only constrain if they overlap horizontally at any reasonable scale
                # Two blocks overlap in x if their x-ranges intersect.
                # At scale s: block_a x-range = [a.x*s, a.x*s + a.width]
                # We check if blocks have similar x coordinates
                dx_canvas = abs(top.x - bottom.x)
                max_width = max(top.block_width, bottom.block_width)
                # If dx at current candidate scale would place them overlapping:
                # They could overlap if dx_canvas * scale < max_width
                # This means scale > max_width / dx_canvas would separate them,
                # but we also need dy_canvas * scale > top.block_height + gap
                # Conservative: only constrain if dx_canvas is small relative to dy_canvas
                if dx_canvas < dy_canvas * 3:  # they're roughly stacked
                    needed_y = top.block_height + gap
                    scale_y = needed_y / dy_canvas
                    min_scale = max(min_scale, scale_y)

        # Check horizontally adjacent pairs (sorted by x, looking at close y ranges)
        for i in range(len(by_x)):
            for j in range(i + 1, len(by_x)):
                left, right = by_x[i], by_x[j]
                dx_canvas = right.x - left.x
                if dx_canvas <= 0:
                    continue
                dy_canvas = abs(left.y - right.y)
                max_height = max(left.block_height, right.block_height)
                if dy_canvas < dx_canvas * 3:  # they're roughly side by side
                    needed_x = left.block_width + gap
                    scale_x = needed_x / dx_canvas
                    min_scale = max(min_scale, scale_x)

        # Use the default SCALE as the floor – only increase if blocks would
        # overlap at the default scale.  This keeps the layout consistent with
        # the 4diac IDE rendering scale (0.16 px / canvas-unit at 100 % zoom).
        return max(min_scale, self.SCALE)

    def _position_instances(self, model: NetworkModel):
        """Map XML canvas coordinates to SVG render positions."""
        if not model.instances:
            return

        # Auto-detect scale if not explicitly set
        if self._auto_scale_needed:
            self.SCALE = self._auto_scale(model)

        # Find coordinate bounds
        min_x = min(inst.x for inst in model.instances)
        min_y = min(inst.y for inst in model.instances)

        # Apply scale and offset
        for inst in model.instances:
            inst.render_x = (inst.x - min_x) * self.SCALE + self.MARGIN
            inst.render_y = (inst.y - min_y) * self.SCALE + self.MARGIN

        # Store the mapping from canvas origin (0, 0) to pixel coordinates.
        # This is needed by the connection router: for interface→FB connections,
        # dx1 is an absolute canvas-x coordinate of the turn point (not relative
        # to the interface port's rendered pixel position).
        model.canvas_origin_x = self.MARGIN - min_x * self.SCALE
        model.canvas_origin_y = self.MARGIN - min_y * self.SCALE

    def _compute_port_positions(self, inst: FBInstance):
        """Compute absolute (x, y) for each port on an instance."""
        top_padding = self.PORT_ROW_HEIGHT / 2 - 4

        # Event inputs (left side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in inst.event_inputs:
            abs_x = inst.render_x
            abs_y = inst.render_y + y
            inst.port_positions[port.name] = (abs_x, abs_y)
            y += self.PORT_ROW_HEIGHT

        # Event outputs (right side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in inst.event_outputs:
            abs_x = inst.render_x + inst.block_width
            abs_y = inst.render_y + y
            inst.port_positions[port.name] = (abs_x, abs_y)
            y += self.PORT_ROW_HEIGHT

        # Data inputs (left side)
        base_y = inst.name_section_bottom
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.data_inputs:
            abs_x = inst.render_x
            abs_y = inst.render_y + y
            inst.port_positions[port.name] = (abs_x, abs_y)
            y += self.PORT_ROW_HEIGHT

        # Data outputs (right side)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.data_outputs:
            abs_x = inst.render_x + inst.block_width
            abs_y = inst.render_y + y
            inst.port_positions[port.name] = (abs_x, abs_y)
            y += self.PORT_ROW_HEIGHT

        # Adapter sockets (left side)
        if inst.sockets:
            adapter_base = inst.adapter_section_top
            y = adapter_base + self.PORT_ROW_HEIGHT / 2
            for port in inst.sockets:
                abs_x = inst.render_x
                abs_y = inst.render_y + y
                inst.port_positions[port.name] = (abs_x, abs_y)
                y += self.PORT_ROW_HEIGHT

        # Adapter plugs (right side)
        if inst.plugs:
            adapter_base = inst.adapter_section_top
            y = adapter_base + self.PORT_ROW_HEIGHT / 2
            for port in inst.plugs:
                abs_x = inst.render_x + inst.block_width
                abs_y = inst.render_y + y
                inst.port_positions[port.name] = (abs_x, abs_y)
                y += self.PORT_ROW_HEIGHT

    def _position_interface_ports(self, model: NetworkModel):
        """Position interface ports in light-blue sidebar areas on left/right edges.

        Ports are evenly spaced vertically within the sidebar, which spans
        the full height of the diagram content area.
        """
        if not model.instances and not model.interface_ports:
            return

        # Group interface ports by direction
        inputs = [p for p in model.interface_ports if p.direction == "input"]
        outputs = [p for p in model.interface_ports if p.direction == "output"]

        # Measure sidebar widths: text + gap + triangle, minimal outer margin
        sidebar_outer_margin = 2   # margin at the outer border edge
        sidebar_gap = 3            # gap between text and triangle
        tri_w = self.TRIANGLE_WIDTH
        max_iface = self.settings.max_interface_bar_size
        input_sidebar_w = 0
        for p in inputs:
            tw = self._measure_text(_truncate_label(p.name, max_iface))
            input_sidebar_w = max(input_sidebar_w, tw)
        input_sidebar_w += sidebar_outer_margin + sidebar_gap + tri_w if inputs else 0

        output_sidebar_w = 0
        for p in outputs:
            tw = self._measure_text(_truncate_label(p.name, max_iface))
            output_sidebar_w = max(output_sidebar_w, tw)
        output_sidebar_w += sidebar_outer_margin + sidebar_gap + tri_w if outputs else 0

        # Clamp sidebar widths to min/max interface bar size
        min_iface_w = self._measure_text("W" * self.settings.min_interface_bar_size) if self.settings.min_interface_bar_size > 0 else 0
        if inputs and input_sidebar_w < min_iface_w + sidebar_outer_margin + sidebar_gap + tri_w:
            input_sidebar_w = min_iface_w + sidebar_outer_margin + sidebar_gap + tri_w
        if outputs and output_sidebar_w < min_iface_w + sidebar_outer_margin + sidebar_gap + tri_w:
            output_sidebar_w = min_iface_w + sidebar_outer_margin + sidebar_gap + tri_w

        # Store sidebar dimensions for use by renderer and bounds calculation
        model.input_sidebar_width = input_sidebar_w
        model.output_sidebar_width = output_sidebar_w

        # Find instance area bounds
        if model.instances:
            inst_min_x = min(inst.render_x for inst in model.instances)
            inst_max_x = max(inst.render_x + inst.block_width for inst in model.instances)
            inst_min_y = min(inst.render_y - 20 for inst in model.instances)  # label above
            inst_max_y = max(inst.render_y + inst.block_height for inst in model.instances)
        else:
            inst_min_x, inst_max_x = self.MARGIN, self.MARGIN + 200
            inst_min_y, inst_max_y = self.MARGIN, self.MARGIN + 200

        # Position sidebars based on dx1-derived turn points.
        #
        # Input (left) sidebar:
        #   turn_x = sidebar_right + dx1 * SCALE
        #   Each turn must fit before its destination FB, giving a per-connection
        #   constraint: sidebar_right < dest_FB_left - dx1 * SCALE.
        #   We use the tightest constraint (minimum) and apply a 0.88 factor
        #   to match 4diac IDE, which lets the largest turns extend slightly
        #   past the closest FB (drawn behind it).
        #
        # Output (right) sidebar:
        #   turn_x = src_port_x + dx1 * SCALE
        #   The sidebar must be to the RIGHT of ALL turn points.
        #   We take the maximum turn_x and add padding.
        input_port_names = {p.name for p in inputs}
        output_port_names = {p.name for p in outputs}
        instance_map_tmp = {inst.name: inst for inst in model.instances}

        # --- Input (left) sidebar positioning ---
        # Find the maximum turn_x for all interface→FB connections
        max_turn_x_left = 0.0
        for conn in model.connections:
            src_parts = conn.source.split(".")
            dst_parts = conn.destination.split(".")
            if len(src_parts) == 1 and src_parts[0] in input_port_names and conn.dx1 != 0:
                # turn_x is relative to sidebar_right, so the gap must be at least dx1*SCALE
                max_turn_x_left = max(max_turn_x_left, conn.dx1 * self.SCALE)

        sidebar_offset_left = 58  # fixed offset between sidebar and first turn point
        sidebar_gap_left = max_turn_x_left + sidebar_offset_left

        input_sidebar_right = inst_min_x - sidebar_gap_left
        input_sidebar_left = input_sidebar_right - input_sidebar_w

        # --- Output (right) sidebar positioning ---
        # Find the maximum turn_x across ALL FB → output-interface connections.
        max_right_turn_x = inst_max_x  # fallback
        for conn in model.connections:
            src_parts = conn.source.split(".")
            dst_parts = conn.destination.split(".")
            if len(dst_parts) == 1 and dst_parts[0] in output_port_names and conn.dx1 != 0:
                if len(src_parts) == 2:
                    fb_inst = instance_map_tmp.get(src_parts[0])
                    if fb_inst:
                        port_name = src_parts[1]
                        if port_name in fb_inst.port_positions:
                            src_x = fb_inst.port_positions[port_name][0]
                            turn_x = src_x + conn.dx1 * self.SCALE
                            max_right_turn_x = max(max_right_turn_x, turn_x)

        sidebar_offset_right = 58  # fixed offset between last turn point and sidebar
        output_sidebar_left = max_right_turn_x + sidebar_offset_right
        output_sidebar_right = output_sidebar_left + output_sidebar_w

        # Sidebar vertical extent: starts at top of instance area,
        # height determined by number of ports (line spacing)
        sidebar_top = inst_min_y - 38
        sidebar_row_h = 17  # spacing for sidebar port names
        top_pad = sidebar_row_h * 1.0  # space above first port

        input_sidebar_h = (len(inputs) * sidebar_row_h + top_pad) if inputs else 0
        output_sidebar_h = (len(outputs) * sidebar_row_h + top_pad) if outputs else 0

        # Sidebar must be at least as tall as the instance area
        content_h = inst_max_y + 10 - sidebar_top
        input_sidebar_h = max(input_sidebar_h, content_h)
        output_sidebar_h = max(output_sidebar_h, content_h)

        # Store sidebar geometry for renderer
        model.input_sidebar_rect = (input_sidebar_left, sidebar_top,
                                     input_sidebar_w, input_sidebar_h) if inputs else None
        model.output_sidebar_rect = (output_sidebar_left, sidebar_top,
                                      output_sidebar_w, output_sidebar_h) if outputs else None

        # Position input ports: start at top with line spacing
        if inputs:
            for i, port in enumerate(inputs):
                port.render_x = input_sidebar_right
                port.render_y = sidebar_top + top_pad + i * sidebar_row_h

        # Position output ports: start at top with line spacing
        if outputs:
            for i, port in enumerate(outputs):
                port.render_x = output_sidebar_left
                port.render_y = sidebar_top + top_pad + i * sidebar_row_h

    def _compute_header_and_border(self, model: NetworkModel):
        """Compute the header section and outer border rectangle.

        The header shows the Comment text at the top of the diagram.
        The outer border frames the entire diagram (header + sidebars + network area).
        Sidebars are adjusted to span from header separator to border bottom.
        """
        HEADER_HEIGHT = 25   # Height of the header bar

        # Determine the full horizontal extent (sidebars or instances)
        all_x = []
        all_y = []

        for inst in model.instances:
            all_x.extend([inst.render_x, inst.render_x + inst.block_width])
            all_y.extend([inst.render_y - 20, inst.render_y + inst.block_height])

        if model.input_sidebar_rect:
            sx, sy, sw, sh = model.input_sidebar_rect
            all_x.extend([sx, sx + sw])
            all_y.extend([sy, sy + sh])
        if model.output_sidebar_rect:
            sx, sy, sw, sh = model.output_sidebar_rect
            all_x.extend([sx, sx + sw])
            all_y.extend([sy, sy + sh])

        if not all_x:
            return

        content_left = min(all_x)
        content_right = max(all_x)
        content_top = min(all_y)
        content_bottom = max(all_y)

        border_pad_v = 20  # vertical padding (top/bottom)

        # Outer border rectangle — sidebars form the left/right edges
        border_x = content_left
        border_w = content_right - content_left

        # Header rectangle is at the top, full width
        header_x = border_x
        header_y = content_top - border_pad_v - HEADER_HEIGHT
        header_w = border_w
        header_h = HEADER_HEIGHT

        model.header_rect = (header_x, header_y, header_w, header_h)

        # Outer border encompasses header + content
        border_y = header_y
        border_h = (content_bottom + border_pad_v) - header_y

        model.outer_border_rect = (border_x, border_y, border_w, border_h)

        # Adjust sidebars to span from header separator to border bottom
        header_bottom = header_y + header_h
        sidebar_bottom = border_y + border_h
        if model.input_sidebar_rect:
            sx, sy, sw, sh = model.input_sidebar_rect
            model.input_sidebar_rect = (sx, header_bottom, sw, sidebar_bottom - header_bottom)
        if model.output_sidebar_rect:
            sx, sy, sw, sh = model.output_sidebar_rect
            model.output_sidebar_rect = (sx, header_bottom, sw, sidebar_bottom - header_bottom)

    def get_diagram_bounds(self, model: NetworkModel) -> Tuple[float, float, float, float]:
        """Get the bounding box of the entire diagram (min_x, min_y, max_x, max_y)."""
        all_x = []
        all_y = []

        # Use the outer border if available (it encompasses everything)
        if model.outer_border_rect:
            bx, by, bw, bh = model.outer_border_rect
            return bx, by, bx + bw, by + bh

        for inst in model.instances:
            all_x.extend([inst.render_x, inst.render_x + inst.block_width])
            all_y.extend([inst.render_y - 20, inst.render_y + inst.block_height])  # -20 for instance label above

        # Include sidebar rectangles in bounds
        if model.input_sidebar_rect:
            sx, sy, sw, sh = model.input_sidebar_rect
            all_x.extend([sx, sx + sw])
            all_y.extend([sy, sy + sh])
        if model.output_sidebar_rect:
            sx, sy, sw, sh = model.output_sidebar_rect
            all_x.extend([sx, sx + sw])
            all_y.extend([sy, sy + sh])

        if not all_x:
            return 0, 0, 100, 100

        return min(all_x), min(all_y), max(all_x), max(all_y)


# ===========================================================================
# Connection Router
# ===========================================================================

class ConnectionRouter:
    """Routes connections using Manhattan (orthogonal) paths with dx1/dx2/dy hints."""

    SCALE = 0.05  # Must match layout engine scale

    def __init__(self, scale: float = 0.05):
        self.SCALE = scale

    def route(self, conn: Connection, model: NetworkModel,
              instance_map: Dict[str, FBInstance],
              interface_map: Dict[str, InterfacePort]) -> List[Tuple[float, float]]:
        """Compute the waypoints for a connection."""
        src_pos = self._resolve_endpoint(conn.source, instance_map, interface_map, is_source=True)
        dst_pos = self._resolve_endpoint(conn.destination, instance_map, interface_map, is_source=False)

        if src_pos is None or dst_pos is None:
            return []

        x1, y1 = src_pos
        x2, y2 = dst_pos

        # Check if source or destination is an interface port
        src_parts = conn.source.split(".")
        dst_parts = conn.destination.split(".")
        src_is_iface = len(src_parts) == 1 and src_parts[0] in interface_map
        dst_is_iface = len(dst_parts) == 1 and dst_parts[0] in interface_map

        # Interface-to-FB or FB-to-interface connections
        # For interface→FB: dx1 is the offset (in canvas units) from the
        # interface port's rendered position to the turn point.
        # For FB→interface: dx1 is a normal offset from the source FB port.
        if src_is_iface and not dst_is_iface:
            # Interface port (left sidebar) → FB input port
            dx1 = conn.dx1 * self.SCALE
            if abs(y1 - y2) < 1 and dx1 == 0:
                points = [(x1, y1), (x2, y2)]
            elif dx1 != 0:
                turn_x = x1 + dx1
                points = [(x1, y1), (turn_x, y1), (turn_x, y2), (x2, y2)]
            else:
                # No hint – place turn midway
                turn_x = (x1 + x2) / 2
                points = [(x1, y1), (turn_x, y1), (turn_x, y2), (x2, y2)]
            return self._simplify_points(points)

        if dst_is_iface and not src_is_iface:
            # FB output port → interface port (right sidebar)
            dx1 = conn.dx1 * self.SCALE
            if abs(y1 - y2) < 1 and dx1 == 0:
                points = [(x1, y1), (x2, y2)]
            elif dx1 != 0:
                turn_x = x1 + dx1
                points = [(x1, y1), (turn_x, y1), (turn_x, y2), (x2, y2)]
            else:
                turn_x = (x1 + x2) / 2
                points = [(x1, y1), (turn_x, y1), (turn_x, y2), (x2, y2)]
            return self._simplify_points(points)

        # Scale the routing hints — use proportional placement
        # dx1/dx2/dy are in canvas units; we scale them the same as positions
        dx1 = conn.dx1 * self.SCALE
        dx2 = conn.dx2 * self.SCALE
        dy = conn.dy * self.SCALE

        # Enforce minimum routing distances so lines remain visible
        MIN_ROUTE_DX = 30  # minimum horizontal detour in pixels
        MIN_ROUTE_DY = 20  # minimum vertical detour in pixels

        points = []

        if dy == 0:
            # Simple route: horizontal → vertical → horizontal (3 segments)
            if dx1 != 0:
                mid_x = x1 + dx1
                # Ensure mid_x is at least MIN_ROUTE_DX from source
                if abs(dx1) < MIN_ROUTE_DX:
                    mid_x = x1 + (MIN_ROUTE_DX if dx1 > 0 else -MIN_ROUTE_DX)
                points = [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]
            else:
                # Direct: just go horizontal then vertical
                mid_x = (x1 + x2) / 2
                if abs(y1 - y2) < 1:
                    # Same height: straight line
                    points = [(x1, y1), (x2, y2)]
                else:
                    points = [(x1, y1), (mid_x, y1), (mid_x, y2), (x2, y2)]
        else:
            # U-turn / complex route with dy (5 or 6 segments)
            # dx1 = horizontal offset from SOURCE port to first vertical segment
            # dx2 = horizontal offset from DESTINATION port to second vertical segment
            # dy  = vertical offset from source to the horizontal crossover
            if dx2 != 0:
                # Full 5-segment U-turn route:
                #   src → right by dx1 → down/up by dy → left toward dest → down to dest → dest
                seg1_x = x1 + dx1                  # first vertical segment x
                seg_y  = y1 + dy                    # horizontal crossover y
                seg2_x = x2 - dx2                   # second vertical segment x (offset LEFT from dest)
                points = [(x1, y1), (seg1_x, y1), (seg1_x, seg_y),
                          (seg2_x, seg_y), (seg2_x, y2), (x2, y2)]
            else:
                # 3-segment with dy indicating vertical offset
                seg1_x = x1 + dx1
                seg_y = y1 + dy
                points = [(x1, y1), (seg1_x, y1), (seg1_x, seg_y),
                          (x2, seg_y), (x2, y2)]

        # Clean up: remove duplicate adjacent points and collinear points
        return self._simplify_points(points)

    def _resolve_endpoint(self, endpoint: str,
                          instance_map: Dict[str, FBInstance],
                          interface_map: Dict[str, InterfacePort],
                          is_source: bool) -> Optional[Tuple[float, float]]:
        """Resolve a connection endpoint to (x, y) coordinates."""
        parts = endpoint.split(".")
        if len(parts) == 2:
            fb_name, port_name = parts
            inst = instance_map.get(fb_name)
            if inst and port_name in inst.port_positions:
                return inst.port_positions[port_name]
            return None
        elif len(parts) == 1:
            # Interface port
            iport = interface_map.get(parts[0])
            if iport:
                return (iport.render_x, iport.render_y)
            return None
        return None

    def _simplify_points(self, points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Remove redundant points (duplicates and collinear)."""
        if len(points) < 2:
            return points

        result = [points[0]]
        for i in range(1, len(points)):
            if abs(points[i][0] - result[-1][0]) > 0.1 or abs(points[i][1] - result[-1][1]) > 0.1:
                result.append(points[i])

        # Remove collinear points
        if len(result) < 3:
            return result

        simplified = [result[0]]
        for i in range(1, len(result) - 1):
            x0, y0 = simplified[-1]
            x1, y1 = result[i]
            x2, y2 = result[i + 1]
            # Check if collinear
            if not (abs(x0 - x1) < 0.1 and abs(x1 - x2) < 0.1) and \
               not (abs(y0 - y1) < 0.1 and abs(y1 - y2) < 0.1):
                simplified.append(result[i])
        simplified.append(result[-1])

        return simplified


# ===========================================================================
# SVG Renderer
# ===========================================================================

class NetworkSVGRenderer:
    """Renders the network model as SVG."""

    # Fonts
    FONT_FAMILY = "'TGL 0-17', 'Times New Roman', Times, serif"
    FONT_FAMILY_ITALIC = "'TGL 0-16', 'Times New Roman', Times, serif"
    FONT_SIZE = 12

    FONT_FACE_STYLE = '''
  <style>
    @font-face {
      font-family: "TGL 0-17";
      src: local("TGL 0-17"), local("TGL 0-17 alt");
      font-style: normal;
      font-weight: normal;
    }
    @font-face {
      font-family: "TGL 0-16";
      src: local("TGL 0-16");
      font-style: normal;
      font-weight: normal;
    }
  </style>'''

    # Colors (from 4diac IDE)
    BLOCK_STROKE_COLOR = "#A0A0A0"
    EVENT_PORT_COLOR = "#63B31F"
    BOOL_PORT_COLOR = "#9FA48A"
    ANY_BIT_PORT_COLOR = "#82A3A9"
    ANY_INT_PORT_COLOR = "#18519E"
    ANY_REAL_PORT_COLOR = "#DBB418"
    STRING_PORT_COLOR = "#BD8663"
    DATA_PORT_COLOR = "#0000FF"
    ADAPTER_PORT_COLOR = "#845DAF"

    STRING_TYPES = {"STRING", "WSTRING", "ANY_STRING", "ANY_CHARS", "CHAR", "WCHAR"}
    INT_TYPES = {"INT", "UINT", "SINT", "USINT", "DINT", "UDINT", "LINT", "ULINT", "ANY_INT", "ANY_NUM"}
    REAL_TYPES = {"REAL", "LREAL", "ANY_REAL"}
    BIT_TYPES = {"BYTE", "WORD", "DWORD", "LWORD", "ANY_BIT"}

    # Layout – must match NetworkLayoutEngine constants
    PORT_ROW_HEIGHT = 16
    BLOCK_PADDING = 10
    NAME_SECTION_HEIGHT = 16
    TRIANGLE_WIDTH = 5
    TRIANGLE_HEIGHT = 10

    # Connection diagonal endpoint length
    CONN_DIAG_LEN = 4

    def __init__(self, show_shadow: bool = True, show_grid: bool = False, settings: BlockSizeSettings = None):
        self.show_shadow = show_shadow
        self.show_grid = show_grid
        self.settings = settings or BlockSizeSettings()
        # Load font for text measurement (same as layout engine)
        self._font = None
        self._font_italic = None
        if PILLOW_AVAILABLE:
            try:
                self._font = ImageFont.truetype("TGL 0-17", self.FONT_SIZE)
            except (OSError, IOError):
                pass
            try:
                self._font_italic = ImageFont.truetype("TGL 0-16", self.FONT_SIZE)
            except (OSError, IOError):
                if self._font:
                    self._font_italic = self._font

    def _measure_text(self, text: str, italic: bool = False) -> float:
        """Measure text width for layout calculations."""
        if PILLOW_AVAILABLE and self._font:
            font = self._font_italic if italic and self._font_italic else self._font
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0] if bbox else len(text) * 8
        else:
            return len(text) * 8.5

    def _get_port_color(self, port_type: str) -> str:
        t = port_type
        if t.startswith("ARRAY "):
            of_idx = t.rfind(" OF ")
            if of_idx >= 0:
                t = t[of_idx + 4:]
        if t == "BOOL":
            return self.BOOL_PORT_COLOR
        elif t in self.STRING_TYPES:
            return self.STRING_PORT_COLOR
        elif t in self.INT_TYPES:
            return self.ANY_INT_PORT_COLOR
        elif t in self.REAL_TYPES:
            return self.ANY_REAL_PORT_COLOR
        elif t in self.BIT_TYPES:
            return self.ANY_BIT_PORT_COLOR
        else:
            return self.DATA_PORT_COLOR

    def _get_connection_color(self, conn: Connection, model: NetworkModel,
                               instance_map: Dict[str, FBInstance]) -> str:
        """Determine the color for a connection."""
        if conn.conn_type == "event":
            return self.EVENT_PORT_COLOR
        elif conn.conn_type == "adapter":
            return self.ADAPTER_PORT_COLOR
        else:
            # Data connection: try to get type from source port
            parts = conn.source.split(".")
            if len(parts) == 2:
                fb_name, port_name = parts
                inst = instance_map.get(fb_name)
                if inst:
                    for p in inst.data_outputs + inst.data_inputs:
                        if p.name == port_name:
                            return self._get_port_color(p.port_type)
            # Try interface port
            elif len(parts) == 1:
                for ip in model.interface_ports:
                    if ip.name == parts[0]:
                        return self._get_port_color(ip.port_type)
            return self.DATA_PORT_COLOR

    def render(self, model: NetworkModel, layout: NetworkLayoutEngine) -> str:
        """Render the complete network as SVG."""
        parts = []

        # Build lookup maps
        instance_map = {inst.name: inst for inst in model.instances}
        interface_map = {ip.name: ip for ip in model.interface_ports}

        # Get diagram bounds
        min_x, min_y, max_x, max_y = layout.get_diagram_bounds(model)
        padding = 7
        vb_x = min_x - padding
        vb_y = min_y - padding
        vb_w = (max_x - min_x) + padding * 2
        vb_h = (max_y - min_y) + padding * 2

        # SVG header
        parts.append(self._svg_header(vb_x, vb_y, vb_w, vb_h))

        # White background
        parts.append(f'  <rect x="{vb_x:.1f}" y="{vb_y:.1f}" width="{vb_w:.1f}" height="{vb_h:.1f}" fill="white"/>')

        # Grid settings (pattern rendered later once content area is known)
        _grid_minor = 100 * layout.SCALE if self.show_grid else 0
        _grid_major = _grid_minor * 5
        _grid_super = _grid_minor * 10

        # Render outer border
        if model.outer_border_rect:
            bx, by, bw, bh = model.outer_border_rect
            parts.append(f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}"'
                        f' fill="none" stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="2"/>')

        # Render header section
        if model.header_rect:
            hx, hy, hw, hh = model.header_rect
            # Header background
            parts.append(f'  <rect x="{hx:.1f}" y="{hy:.1f}" width="{hw:.1f}" height="{hh:.1f}"'
                        f' fill="white" stroke="none"/>')
            # Header separator line (at bottom of header)
            sep_y = hy + hh
            parts.append(f'  <line x1="{hx:.1f}" y1="{sep_y:.1f}" x2="{hx + hw:.1f}" y2="{sep_y:.1f}"'
                        f' stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="1"/>')
            # Comment text
            if model.comment:
                text_x = hx + 5
                text_y = hy + hh / 2 + self.FONT_SIZE * 0.35
                # Escape XML entities in comment
                comment_text = (model.comment
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;"))
                parts.append(f'  <text x="{text_x:.1f}" y="{text_y:.1f}"'
                            f' font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"'
                            f' fill="#333333">{comment_text}</text>')

        # Render sidebar backgrounds (behind everything else)
        parts.append('  <g id="sidebars">')
        if model.input_sidebar_rect:
            sx, sy, sw, sh = model.input_sidebar_rect
            parts.append(f'    <rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}"'
                        f' fill="#EEF5FF" stroke="none"/>')
            # Vertical separator at right edge of input sidebar
            sep_x = sx + sw
            parts.append(f'    <line x1="{sep_x:.1f}" y1="{sy:.1f}" x2="{sep_x:.1f}" y2="{sy + sh:.1f}"'
                        f' stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="0.5"/>')
        if model.output_sidebar_rect:
            sx, sy, sw, sh = model.output_sidebar_rect
            parts.append(f'    <rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}"'
                        f' fill="#EEF5FF" stroke="none"/>')
            # Vertical separator at left edge of output sidebar
            parts.append(f'    <line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx:.1f}" y2="{sy + sh:.1f}"'
                        f' stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="0.5"/>')
        parts.append('  </g>')

        # Render grid in the network content area (after header/sidebars)
        if self.show_grid:
            # Compute content area: outer border minus header and sidebars
            if model.outer_border_rect:
                gx, gy, gw, gh = model.outer_border_rect
                if model.header_rect:
                    _, _, _, hh = model.header_rect
                    gy = gy + hh
                    gh = gh - hh
                if model.input_sidebar_rect:
                    _, _, isw, _ = model.input_sidebar_rect
                    gx = gx + isw
                    gw = gw - isw
                if model.output_sidebar_rect:
                    _, _, osw, _ = model.output_sidebar_rect
                    gw = gw - osw
            else:
                gx, gy, gw, gh = vb_x, vb_y, vb_w, vb_h
            # Pattern origin aligned to content area top-left
            # Tile = 10 minor cells; minor=dotted, every 5th=dashed, every 10th=thicker dashed
            # Grid offsets: 10th horizontal line at 7th position, 10th vertical line at 2nd
            _h_off = 1  # horizontal (y) offset for the 10th-line
            _v_off = 7  # vertical (x) offset for the 10th-line
            parts.append(f'  <defs>')
            parts.append(f'    <pattern id="grid" x="{gx:.1f}" y="{gy:.1f}" width="{_grid_super:.2f}" height="{_grid_super:.2f}" patternUnits="userSpaceOnUse">')
            for i in range(10):
                pos = i * _grid_minor
                # Horizontal lines (y positions) — offset by _h_off
                grid_idx_h = (i - _h_off) % 10
                if grid_idx_h == 0:
                    parts.append(f'      <line x1="0" y1="{pos:.2f}" x2="{_grid_super:.2f}" y2="{pos:.2f}" stroke="#909090" stroke-width="1.5" stroke-dasharray="6,3"/>')
                elif grid_idx_h == 5:
                    parts.append(f'      <line x1="0" y1="{pos:.2f}" x2="{_grid_super:.2f}" y2="{pos:.2f}" stroke="#A0A0A0" stroke-width="1" stroke-dasharray="4,3"/>')
                else:
                    parts.append(f'      <line x1="0" y1="{pos:.2f}" x2="{_grid_super:.2f}" y2="{pos:.2f}" stroke="#B8B8B8" stroke-width="0.5" stroke-dasharray="1,3"/>')
                # Vertical lines (x positions) — offset by _v_off
                grid_idx_v = (i - _v_off) % 10
                if grid_idx_v == 0:
                    parts.append(f'      <line x1="{pos:.2f}" y1="0" x2="{pos:.2f}" y2="{_grid_super:.2f}" stroke="#909090" stroke-width="1.5" stroke-dasharray="6,3"/>')
                elif grid_idx_v == 5:
                    parts.append(f'      <line x1="{pos:.2f}" y1="0" x2="{pos:.2f}" y2="{_grid_super:.2f}" stroke="#A0A0A0" stroke-width="1" stroke-dasharray="4,3"/>')
                else:
                    parts.append(f'      <line x1="{pos:.2f}" y1="0" x2="{pos:.2f}" y2="{_grid_super:.2f}" stroke="#B8B8B8" stroke-width="0.5" stroke-dasharray="1,3"/>')
            parts.append(f'    </pattern>')
            parts.append(f'  </defs>')
            parts.append(f'  <rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" fill="url(#grid)"/>')

        # Assign interface indices for staggered routing of interface connections
        left_idx = 0
        right_idx = 0
        for conn in model.connections:
            src_parts = conn.source.split(".")
            dst_parts = conn.destination.split(".")
            if len(src_parts) == 1 and src_parts[0] in interface_map:
                conn._iface_index = left_idx
                left_idx += 1
            elif len(dst_parts) == 1 and dst_parts[0] in interface_map:
                conn._iface_index = right_idx
                right_idx += 1

        # Render connections first (behind blocks)
        router = ConnectionRouter(scale=layout.SCALE)
        parts.append('  <g id="connections">')
        for conn in model.connections:
            waypoints = router.route(conn, model, instance_map, interface_map)
            if waypoints:
                color = self._get_connection_color(conn, model, instance_map)
                parts.append(self._render_connection(waypoints, color))
        parts.append('  </g>')

        # Render interface ports
        parts.append('  <g id="interface_ports">')
        for ip in model.interface_ports:
            parts.append(self._render_interface_port(ip, model))
        parts.append('  </g>')

        # Render FB instance blocks (on top of connections)
        parts.append('  <g id="instances">')
        for inst in model.instances:
            parts.append(self._render_instance(inst))
        parts.append('  </g>')

        parts.append('</svg>')
        return "\n".join(parts)

    def _svg_header(self, vb_x: float, vb_y: float, vb_w: float, vb_h: float) -> str:
        shadow_defs = ""
        if self.show_shadow:
            shadow_defs = '''
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
  </defs>'''

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="{vb_x:.1f} {vb_y:.1f} {vb_w:.1f} {vb_h:.1f}"
     width="{vb_w:.0f}" height="{vb_h:.0f}">{self.FONT_FACE_STYLE}{shadow_defs}'''

    # ----- Instance Block Rendering -----

    def _render_instance(self, inst: FBInstance) -> str:
        """Render a complete FB instance block."""
        parts = []
        x = inst.render_x
        y = inst.render_y

        parts.append(f'    <g id="fb_{inst.name}" transform="translate({x:.1f}, {y:.1f})">')

        # Block outline
        parts.append(self._render_block_outline(inst))

        # Name section
        parts.append(self._render_name_section(inst))

        # Event ports
        parts.append(self._render_event_ports(inst))

        # Data ports
        parts.append(self._render_data_ports(inst))

        # Adapter ports
        parts.append(self._render_adapter_ports(inst))

        # Instance name above the block
        parts.append(self._render_instance_label(inst))

        parts.append('    </g>')
        return "\n".join(parts)

    def _render_block_outline(self, inst: FBInstance) -> str:
        notch = 8
        r = 3
        et = inst.event_section_height
        nb = inst.name_section_bottom
        w = inst.block_width
        h = inst.block_height

        path_d = f"""M {r} 0
            L {w - r} 0
            A {r} {r} 0 0 1 {w} {r}
            L {w} {et - r}
            A {r} {r} 0 0 1 {w - r} {et}
            L {w - notch} {et}
            L {w - notch} {nb}
            L {w - r} {nb}
            A {r} {r} 0 0 1 {w} {nb + r}
            L {w} {h - r}
            A {r} {r} 0 0 1 {w - r} {h}
            L {r} {h}
            A {r} {r} 0 0 1 0 {h - r}
            L 0 {nb + r}
            A {r} {r} 0 0 1 {r} {nb}
            L {notch} {nb}
            L {notch} {et}
            L {r} {et}
            A {r} {r} 0 0 1 0 {et - r}
            L 0 {r}
            A {r} {r} 0 0 1 {r} 0
            Z"""

        filter_attr = ' filter="url(#dropShadow)"' if self.show_shadow else ''

        return f'''      <path d="{path_d}"
            fill="#FFFFFF" stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="1.5"
            stroke-linejoin="round"{filter_attr}/>'''

    def _render_name_section(self, inst: FBInstance) -> str:
        """Render name section with icon and type name only (instance name is above the block)."""
        center_y = inst.name_section_top + self.NAME_SECTION_HEIGHT / 2
        w = inst.block_width

        # Short type name (after last ::), truncated per settings
        short_type = inst.type_name.split("::")[-1] if "::" in inst.type_name else inst.type_name
        short_type = _truncate_label(short_type, self.settings.max_type_label_size)

        # FB type icon letter
        if inst.fb_type == "Adapter":
            icon_letter = "A"
        elif inst.fb_type == "BasicFB":
            icon_letter = "B"
        elif inst.fb_type == "CompositeFB":
            icon_letter = "C"
        elif inst.fb_type == "ServiceInterfaceFB":
            icon_letter = "Si"
        elif inst.fb_type == "SubApp":
            icon_letter = "S"  # Will use graphic instead
        else:
            icon_letter = "B"

        # Icon dimensions
        icon_w = 14
        icon_h = 14
        icon_notch_depth = 1.5
        icon_r = 1

        # Calculate content width to center icon + type name together
        gap_icon_text = 4
        type_width = self._measure_text(short_type, italic=True)
        total_content_width = icon_w + gap_icon_text + type_width
        content_start_x = (w - total_content_width) / 2

        # Icon position (centered together with type name)
        icon_x = content_start_x
        icon_y = center_y - icon_h / 2

        icon_notch_top = icon_y + icon_h / 4
        icon_notch_bottom = icon_notch_top + icon_h / 6

        icon_path = f"""M {icon_x + icon_r} {icon_y}
            L {icon_x + icon_w - icon_r} {icon_y}
            A {icon_r} {icon_r} 0 0 1 {icon_x + icon_w} {icon_y + icon_r}
            L {icon_x + icon_w} {icon_notch_top}
            L {icon_x + icon_w - icon_notch_depth} {icon_notch_top}
            L {icon_x + icon_w - icon_notch_depth} {icon_notch_bottom}
            L {icon_x + icon_w} {icon_notch_bottom}
            L {icon_x + icon_w} {icon_y + icon_h - icon_r}
            A {icon_r} {icon_r} 0 0 1 {icon_x + icon_w - icon_r} {icon_y + icon_h}
            L {icon_x + icon_r} {icon_y + icon_h}
            A {icon_r} {icon_r} 0 0 1 {icon_x} {icon_y + icon_h - icon_r}
            L {icon_x} {icon_notch_bottom}
            L {icon_x + icon_notch_depth} {icon_notch_bottom}
            L {icon_x + icon_notch_depth} {icon_notch_top}
            L {icon_x} {icon_notch_top}
            L {icon_x} {icon_y + icon_r}
            A {icon_r} {icon_r} 0 0 1 {icon_x + icon_r} {icon_y}
            Z"""

        # Icon content
        if inst.fb_type == "SubApp":
            # SubApp icon: two mini FBs connected
            mini_w = 5.5
            mini_h = 7
            gap = 3
            pair_w = mini_w * 2 + gap
            pair_x = icon_x + (icon_w - pair_w) / 2
            pair_y = icon_y + icon_h - mini_h - 1.5

            left_path = self._mini_fb_path(pair_x, pair_y, mini_w, mini_h)
            right_path = self._mini_fb_path(pair_x + mini_w + gap, pair_y, mini_w, mini_h)

            conn_x1 = pair_x + mini_w
            conn_x2 = pair_x + mini_w + gap
            event_conn_y = pair_y + mini_h * 0.12
            data_conn_y = pair_y + mini_h * 0.7

            icon_content = f'''
      <path d="{left_path}" fill="#1565C0" stroke="none"/>
      <path d="{right_path}" fill="#1565C0" stroke="none"/>
      <line x1="{conn_x1}" y1="{event_conn_y}" x2="{conn_x2}" y2="{event_conn_y}"
            stroke="#3DA015" stroke-width="1.2"/>
      <line x1="{conn_x1}" y1="{data_conn_y}" x2="{conn_x2}" y2="{data_conn_y}"
            stroke="#FF0000" stroke-width="1.2"/>'''
        else:
            icon_content = f'''
      <text x="{icon_x + icon_w / 2}" y="{center_y + 4}"
            font-family="{self.FONT_FAMILY}" font-size="10" font-weight="bold"
            fill="#000000" text-anchor="middle">{icon_letter}</text>'''

        # Type name text position (after icon)
        text_x = icon_x + icon_w + gap_icon_text

        return f'''      <!-- Name Section -->
      <path d="{icon_path}"
            fill="#87CEEB" stroke="#1565C0" stroke-width="1"/>{icon_content}
      <text x="{text_x}" y="{center_y + 4}"
            font-family="{self.FONT_FAMILY_ITALIC}" font-size="{self.FONT_SIZE}"
            fill="#000000">{short_type}</text>'''

    @staticmethod
    def _mini_fb_path(x: float, y: float, w: float, h: float) -> str:
        nd = w * 0.15
        nh = h / 6
        nt = y + h / 4
        nb = nt + nh
        r = 0.5
        return (
            f"M {x + r} {y}"
            f" L {x + w - r} {y}"
            f" A {r} {r} 0 0 1 {x + w} {y + r}"
            f" L {x + w} {nt}"
            f" L {x + w - nd} {nt}"
            f" L {x + w - nd} {nb}"
            f" L {x + w} {nb}"
            f" L {x + w} {y + h - r}"
            f" A {r} {r} 0 0 1 {x + w - r} {y + h}"
            f" L {x + r} {y + h}"
            f" A {r} {r} 0 0 1 {x} {y + h - r}"
            f" L {x} {nb}"
            f" L {x + nd} {nb}"
            f" L {x + nd} {nt}"
            f" L {x} {nt}"
            f" L {x} {y + r}"
            f" A {r} {r} 0 0 1 {x + r} {y}"
            f" Z"
        )

    def _render_instance_label(self, inst: FBInstance) -> str:
        """Render the instance name label above the block."""
        # Instance name centered above the block, slightly above the top edge
        label_x = inst.block_width / 2
        label_y = -5  # Above the block top edge

        return f'''      <!-- Instance Name -->
      <text x="{label_x}" y="{label_y}"
            font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
            fill="#000000" text-anchor="middle">{inst.name}</text>'''

    def _render_event_ports(self, inst: FBInstance) -> str:
        parts = []
        top_padding = self.PORT_ROW_HEIGHT / 2 - 4

        # Event inputs (left side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in inst.event_inputs:
            parts.append(self._render_port_left(port, y, self.EVENT_PORT_COLOR, is_event=True))
            y += self.PORT_ROW_HEIGHT

        # Event outputs (right side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in inst.event_outputs:
            parts.append(self._render_port_right(port, y, inst.block_width, self.EVENT_PORT_COLOR, is_event=True))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_data_ports(self, inst: FBInstance) -> str:
        parts = []
        base_y = inst.name_section_bottom

        # Data inputs (left side)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.data_inputs:
            color = self._get_port_color(port.port_type)
            parts.append(self._render_port_left(port, y, color))
            y += self.PORT_ROW_HEIGHT

        # Data outputs (right side)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.data_outputs:
            color = self._get_port_color(port.port_type)
            parts.append(self._render_port_right(port, y, inst.block_width, color))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_adapter_ports(self, inst: FBInstance) -> str:
        if not inst.sockets and not inst.plugs:
            return ""

        parts = []
        base_y = inst.adapter_section_top

        # Sockets (left)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.sockets:
            parts.append(self._render_socket_port(port, y))
            y += self.PORT_ROW_HEIGHT

        # Plugs (right)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in inst.plugs:
            parts.append(self._render_plug_port(port, y, inst.block_width))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_port_left(self, port: Port, y: float, color: str, is_event: bool = False) -> str:
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT

        tri_y = y
        tri_x = 0  # base aligned with left FB border
        tri_points = f"{tri_x},{tri_y - th/2} {tri_x + tw},{tri_y} {tri_x},{tri_y + th/2}"

        text_x = tri_x + tw + 3
        text_y = y + self.FONT_SIZE * 0.35

        display_name = _truncate_label(port.name, self.settings.max_pin_label_size)
        return f'''      <polygon points="{tri_points}" fill="{color}"/>
      <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
            fill="#000000">{display_name}</text>'''

    def _render_port_right(self, port: Port, y: float, block_width: float, color: str, is_event: bool = False) -> str:
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT

        tri_y = y
        tri_x = block_width - tw  # tip at right FB border
        tri_points = f"{tri_x},{tri_y - th/2} {tri_x + tw},{tri_y} {tri_x},{tri_y + th/2}"

        text_x = tri_x - 3
        text_y = y + self.FONT_SIZE * 0.35

        display_name = _truncate_label(port.name, self.settings.max_pin_label_size)
        return f'''      <polygon points="{tri_points}" fill="{color}"/>
      <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
            fill="#000000" text-anchor="end">{display_name}</text>'''

    def _render_socket_port(self, port: Port, y: float) -> str:
        rect_w = self.TRIANGLE_WIDTH * 2
        rect_h = self.TRIANGLE_HEIGHT

        sym_y = y
        rect_x = 0  # aligned with left FB border
        rect_y = sym_y - rect_h / 2

        notch_start = rect_x + rect_w / 2
        notch_width = rect_w / 4
        notch_depth = rect_h / 6

        path_d = f"""M {rect_x} {rect_y}
            L {notch_start} {rect_y}
            L {notch_start} {rect_y + notch_depth}
            L {notch_start + notch_width} {rect_y + notch_depth}
            L {notch_start + notch_width} {rect_y}
            L {rect_x + rect_w} {rect_y}
            L {rect_x + rect_w} {rect_y + rect_h}
            L {notch_start + notch_width} {rect_y + rect_h}
            L {notch_start + notch_width} {rect_y + rect_h - notch_depth}
            L {notch_start} {rect_y + rect_h - notch_depth}
            L {notch_start} {rect_y + rect_h}
            L {rect_x} {rect_y + rect_h}
            Z"""

        text_x = rect_x + rect_w + 3
        text_y = y + self.FONT_SIZE * 0.35

        display_name = _truncate_label(port.name, self.settings.max_pin_label_size)
        return f'''      <path d="{path_d}" fill="none" stroke="{self.ADAPTER_PORT_COLOR}" stroke-width="1"/>
      <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
            fill="#000000">{display_name}</text>'''

    def _render_plug_port(self, port: Port, y: float, block_width: float) -> str:
        rect_w = self.TRIANGLE_WIDTH * 2
        rect_h = self.TRIANGLE_HEIGHT

        sym_y = y
        rect_x = block_width - rect_w  # aligned with right FB border
        rect_y = sym_y - rect_h / 2

        notch_start = rect_x + rect_w / 4
        notch_width = rect_w / 4
        notch_depth = rect_h / 6

        path_d = f"""M {rect_x} {rect_y}
            L {notch_start} {rect_y}
            L {notch_start} {rect_y + notch_depth}
            L {notch_start + notch_width} {rect_y + notch_depth}
            L {notch_start + notch_width} {rect_y}
            L {rect_x + rect_w} {rect_y}
            L {rect_x + rect_w} {rect_y + rect_h}
            L {notch_start + notch_width} {rect_y + rect_h}
            L {notch_start + notch_width} {rect_y + rect_h - notch_depth}
            L {notch_start} {rect_y + rect_h - notch_depth}
            L {notch_start} {rect_y + rect_h}
            L {rect_x} {rect_y + rect_h}
            Z"""

        text_x = rect_x - 3
        text_y = y + self.FONT_SIZE * 0.35

        display_name = _truncate_label(port.name, self.settings.max_pin_label_size)
        return f'''      <path d="{path_d}" fill="{self.ADAPTER_PORT_COLOR}"/>
      <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
            fill="#000000" text-anchor="end">{display_name}</text>'''

    # ----- Connection Rendering -----

    def _bevel_waypoints(self, waypoints: List[Tuple[float, float]],
                         bevel_radius: float = 5) -> List[Tuple[float, float]]:
        """Insert 45-degree bevel points at each direction change in the waypoints.

        At each corner, the incoming and outgoing segments are shortened by
        bevel_radius, and a diagonal segment connects them.
        """
        if len(waypoints) <= 2:
            return list(waypoints)

        result = [waypoints[0]]

        for i in range(1, len(waypoints) - 1):
            px, py = waypoints[i - 1]
            cx, cy = waypoints[i]
            nx, ny = waypoints[i + 1]

            # Incoming direction
            in_dx = cx - px
            in_dy = cy - py
            in_len = (in_dx * in_dx + in_dy * in_dy) ** 0.5

            # Outgoing direction
            out_dx = nx - cx
            out_dy = ny - cy
            out_len = (out_dx * out_dx + out_dy * out_dy) ** 0.5

            # Only bevel if both segments are long enough and direction actually changes
            r = min(bevel_radius, in_len * 0.4, out_len * 0.4) if in_len > 0 and out_len > 0 else 0

            if r > 0.5 and (abs(in_dx * out_dy - in_dy * out_dx) > 0.01):
                # Normalize directions
                in_ux = in_dx / in_len
                in_uy = in_dy / in_len
                out_ux = out_dx / out_len
                out_uy = out_dy / out_len

                # Bevel start: step back from corner along incoming direction
                bx1 = cx - in_ux * r
                by1 = cy - in_uy * r
                # Bevel end: step forward from corner along outgoing direction
                bx2 = cx + out_ux * r
                by2 = cy + out_uy * r

                result.append((bx1, by1))
                result.append((bx2, by2))
            else:
                result.append((cx, cy))

        result.append(waypoints[-1])
        return result

    def _render_connection(self, waypoints: List[Tuple[float, float]], color: str) -> str:
        """Render a connection as a polyline with 45-degree bevels and diagonal endpoint stubs."""
        if len(waypoints) < 2:
            return ""

        # Apply bevels at direction changes
        beveled = self._bevel_waypoints(waypoints)

        # Build polyline points
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in beveled)

        return f'    <polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'

    # ----- Interface Port Rendering -----

    def _render_interface_port(self, ip: InterfacePort, model: NetworkModel) -> str:
        """Render an interface port inside its sidebar area.

        Input ports: triangle at right edge (inside sidebar), name to the left
        Output ports: triangle at left edge (inside sidebar), name to the right
        The triangle and label are entirely within the blue sidebar area.
        """
        x = ip.render_x
        y = ip.render_y

        # Determine color
        if ip.category == "event":
            color = self.EVENT_PORT_COLOR
        elif ip.category == "adapter":
            color = self.ADAPTER_PORT_COLOR
        else:
            color = self._get_port_color(ip.port_type)

        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT

        if ip.direction == "input":
            # x = right edge of input sidebar
            # Triangle pointing right, entirely inside the sidebar
            tri_x = x - tw  # triangle base is inside the sidebar
            tri_points = f"{tri_x},{y - th/2} {x},{y} {tri_x},{y + th/2}"
            # Text inside sidebar, to the left of triangle
            text_x = tri_x - 3
            text_anchor = "end"
        else:
            # x = left edge of output sidebar
            # Triangle pointing left, entirely inside the sidebar
            tri_x = x + tw  # triangle base is inside the sidebar
            tri_points = f"{tri_x},{y - th/2} {x},{y} {tri_x},{y + th/2}"
            # Text inside sidebar, to the right of triangle
            text_x = tri_x + 3
            text_anchor = "start"

        text_y = y + self.FONT_SIZE * 0.35  # vertically center text with triangle
        display_name = _truncate_label(ip.name, self.settings.max_interface_bar_size)
        return f'''    <polygon points="{tri_points}" fill="{color}"/>
    <text x="{text_x}" y="{text_y:.1f}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="{text_anchor}">{display_name}</text>'''


# ===========================================================================
# High-Level API
# ===========================================================================

def convert_network_to_svg(xml_source, output_path: str = None,
                           type_lib: str = None,
                           show_shadow: bool = True,
                           show_grid: bool = False,
                           scale: float = None,
                           settings: BlockSizeSettings = None) -> str:
    """Convert an IEC 61499 network XML to SVG.

    Args:
        xml_source: File path or XML string
        output_path: Optional output file path
        type_lib: Optional type library root directory
        show_shadow: Enable drop shadow
        scale: Coordinate scale factor (default: auto)
        settings: Block size settings (default: load from block_size_settings.ini)

    Returns:
        SVG string
    """
    if settings is None:
        settings = load_block_size_settings()

    # Parse
    parser = NetworkParser()
    model = parser.parse(xml_source)

    # Resolve types
    type_lib_paths = [type_lib] if type_lib else []
    # Also try the directory containing the input file
    if isinstance(xml_source, str) and not ('<' in xml_source):
        input_dir = str(Path(xml_source).parent)
        if input_dir not in type_lib_paths:
            type_lib_paths.append(input_dir)

    resolver = TypeResolver(type_lib_paths)
    resolver.resolve(model)

    # Layout
    layout = NetworkLayoutEngine(scale=scale, settings=settings)
    layout.layout(model)

    # Render
    renderer = NetworkSVGRenderer(show_shadow=show_shadow, show_grid=show_grid, settings=settings)
    svg = renderer.render(model, layout)

    # Write output
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg)

    return svg


def convert_batch(input_dir: str, output_dir: str,
                  type_lib: str = None,
                  show_shadow: bool = True,
                  show_grid: bool = False,
                  scale: float = None,
                  recursive: bool = True,
                  settings: BlockSizeSettings = None) -> int:
    """Batch convert all network files in a directory."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for ext in ['*.fbt', '*.sub']:
        pattern = f"**/{ext}" if recursive else ext
        for f in input_path.glob(pattern):
            try:
                # Check if the file actually contains a network
                tree = ET.parse(str(f))
                root = tree.getroot()
                has_network = False
                if root.tag == "SubAppType" and root.find("SubAppNetwork") is not None:
                    has_network = True
                elif root.tag == "FBType" and (root.find("FBNetwork") is not None or root.find("CompositeFB") is not None):
                    has_network = True

                if not has_network:
                    continue

                relative = f.relative_to(input_path)
                svg_file = output_path / relative.with_suffix('.network.svg')
                svg_file.parent.mkdir(parents=True, exist_ok=True)

                convert_network_to_svg(str(f), str(svg_file),
                                      type_lib=type_lib,
                                      show_shadow=show_shadow,
                                      show_grid=show_grid,
                                      scale=scale,
                                      settings=settings)
                count += 1
            except Exception as e:
                print(f"Error converting {f}: {e}", file=sys.stderr)

    return count


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Convert IEC 61499 Function Block Network to SVG (4diac network view style)"
    )
    parser.add_argument("input", help="Input .fbt/.sub/.sys file or directory")
    parser.add_argument("-o", "--output", help="Output SVG file or directory")
    parser.add_argument("--type-lib", help="Type library root directory for interface resolution")
    parser.add_argument("--scale", type=float, default=None, help="Coordinate scale factor (default: auto)")
    parser.add_argument("--stdout", action="store_true", help="Print SVG to stdout")
    parser.add_argument("--batch", action="store_true", help="Batch convert directory")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse in batch mode")
    parser.add_argument("--no-shadow", action="store_true", help="Disable drop shadow")
    parser.add_argument("--grid", action="store_true", help="Show background grid")
    parser.add_argument("--settings", help="Path to block_size_settings.ini file")

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    show_shadow = not args.no_shadow
    show_grid = args.grid
    settings = load_block_size_settings(args.settings)

    if args.batch or input_path.is_dir():
        output_dir = args.output or str(input_path) + "_network_svg"
        count = convert_batch(str(input_path), output_dir,
                            type_lib=args.type_lib,
                            show_shadow=show_shadow,
                            show_grid=show_grid,
                            scale=args.scale,
                            recursive=not args.no_recursive,
                            settings=settings)
        print(f"Converted {count} network files to {output_dir}")
    elif args.stdout:
        svg = convert_network_to_svg(str(input_path),
                                     type_lib=args.type_lib,
                                     show_shadow=show_shadow,
                                     show_grid=show_grid,
                                     scale=args.scale,
                                     settings=settings)
        print(svg)
    else:
        output_path = args.output or str(input_path.with_suffix('.network.svg'))
        convert_network_to_svg(str(input_path), output_path,
                              type_lib=args.type_lib,
                              show_shadow=show_shadow,
                              show_grid=show_grid,
                              scale=args.scale,
                              settings=settings)
        print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
