#!/usr/bin/env python3
"""
IEC 61499 Function Block to SVG Converter

Converts IEC 61499 function block XML definitions (.fbt files) to SVG graphics
in the style of 4diac IDE.
"""

import xml.etree.ElementTree as ET
import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict

# Try to import Pillow for accurate text measurement
try:
    from PIL import ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


@dataclass
class Port:
    """Represents an event or data port."""
    name: str
    port_type: str = ""
    comment: str = ""
    associated_vars: list = field(default_factory=list)


@dataclass
class FunctionBlock:
    """Represents an IEC 61499 Function Block."""
    name: str
    comment: str = ""
    fb_type: str = "BasicFB"
    version: str = ""

    event_inputs: list = field(default_factory=list)
    event_outputs: list = field(default_factory=list)
    data_inputs: list = field(default_factory=list)
    data_outputs: list = field(default_factory=list)

    plugs: list = field(default_factory=list)
    sockets: list = field(default_factory=list)


class IEC61499Parser:
    """Parser for IEC 61499 XML files."""

    def parse(self, xml_path: str) -> FunctionBlock:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        if root.tag == "FBType":
            return self._parse_fbtype(root)
        elif root.tag == "AdapterType":
            return self._parse_adapter(root)
        elif root.tag == "SubAppType":
            return self._parse_subapp(root)
        else:
            raise ValueError(f"Unknown root element: {root.tag}")

    def _parse_fbtype(self, root: ET.Element) -> FunctionBlock:
        fb = FunctionBlock(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", "")
        )

        version_info = root.find("VersionInfo")
        if version_info is not None:
            fb.version = version_info.get("Version", "")

        if root.find("BasicFB") is not None:
            fb.fb_type = "BasicFB"
        elif root.find("CompositeFB") is not None or root.find("FBNetwork") is not None:
            fb.fb_type = "CompositeFB"
        elif root.find("SimpleFB") is not None:
            fb.fb_type = "SimpleFB"
        else:
            fb.fb_type = "ServiceInterfaceFB"

        interface = root.find("InterfaceList")
        if interface is not None:
            self._parse_interface(interface, fb)

        return fb

    def _parse_adapter(self, root: ET.Element) -> FunctionBlock:
        fb = FunctionBlock(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", ""),
            fb_type="Adapter"
        )

        version_info = root.find("VersionInfo")
        if version_info is not None:
            fb.version = version_info.get("Version", "")

        interface = root.find("InterfaceList")
        if interface is not None:
            self._parse_interface(interface, fb)

        return fb

    def _parse_subapp(self, root: ET.Element) -> FunctionBlock:
        fb = FunctionBlock(
            name=root.get("Name", "Unknown"),
            comment=root.get("Comment", ""),
            fb_type="SubApp"
        )

        version_info = root.find("VersionInfo")
        if version_info is not None:
            fb.version = version_info.get("Version", "")

        # SubApps can use either InterfaceList or SubAppInterfaceList
        interface = root.find("SubAppInterfaceList")
        if interface is None:
            interface = root.find("InterfaceList")
        if interface is not None:
            self._parse_interface(interface, fb)

        return fb

    @staticmethod
    def _build_type_string(var_element: ET.Element) -> str:
        """Build a type string from a VarDeclaration element, handling arrays.

        If the element has an ArraySize attribute, formats the type as:
          ARRAY [0..n-1] OF Type    (for a plain integer size, e.g. ArraySize="4")
          ARRAY [*] OF Type         (for variable-length, e.g. ArraySize="*")
          ARRAY [expr] OF Type      (for sub-range expressions, e.g. ArraySize="1..5, 0..3")
        """
        base_type = var_element.get("Type", "")
        array_size = var_element.get("ArraySize", "")
        if not array_size or array_size == "0":
            return base_type
        # Plain integer → convert to 0-based sub-range
        if array_size.isdigit():
            n = int(array_size)
            return f"ARRAY [0..{n - 1}] OF {base_type}"
        # Already a sub-range expression or "*"
        return f"ARRAY [{array_size}] OF {base_type}"

    def _parse_interface(self, interface: ET.Element, fb: FunctionBlock):
        # Support both standard (EventInputs/Event) and SubApp (SubAppEventInputs/SubAppEvent) tags
        event_inputs = interface.find("EventInputs")
        if event_inputs is None:
            event_inputs = interface.find("SubAppEventInputs")
        if event_inputs is not None:
            for event in event_inputs.findall("Event") or event_inputs.findall("SubAppEvent"):
                port = Port(
                    name=event.get("Name", ""),
                    port_type="Event",
                    comment=event.get("Comment", ""),
                    associated_vars=[w.get("Var", "") for w in event.findall("With")]
                )
                fb.event_inputs.append(port)

        event_outputs = interface.find("EventOutputs")
        if event_outputs is None:
            event_outputs = interface.find("SubAppEventOutputs")
        if event_outputs is not None:
            for event in event_outputs.findall("Event") or event_outputs.findall("SubAppEvent"):
                port = Port(
                    name=event.get("Name", ""),
                    port_type="Event",
                    comment=event.get("Comment", ""),
                    associated_vars=[w.get("Var", "") for w in event.findall("With")]
                )
                fb.event_outputs.append(port)

        input_vars = interface.find("InputVars")
        if input_vars is not None:
            for var in input_vars.findall("VarDeclaration"):
                port = Port(
                    name=var.get("Name", ""),
                    port_type=self._build_type_string(var),
                    comment=var.get("Comment", "")
                )
                fb.data_inputs.append(port)

        output_vars = interface.find("OutputVars")
        if output_vars is not None:
            for var in output_vars.findall("VarDeclaration"):
                port = Port(
                    name=var.get("Name", ""),
                    port_type=self._build_type_string(var),
                    comment=var.get("Comment", "")
                )
                fb.data_outputs.append(port)

        plugs = interface.find("Plugs")
        if plugs is not None:
            for adapter in plugs.findall("AdapterDeclaration"):
                port = Port(
                    name=adapter.get("Name", ""),
                    port_type=adapter.get("Type", ""),
                    comment=adapter.get("Comment", "")
                )
                fb.plugs.append(port)

        sockets = interface.find("Sockets")
        if sockets is not None:
            for adapter in sockets.findall("AdapterDeclaration"):
                port = Port(
                    name=adapter.get("Name", ""),
                    port_type=adapter.get("Type", ""),
                    comment=adapter.get("Comment", "")
                )
                fb.sockets.append(port)


class SVGRenderer:
    """Renders a FunctionBlock as SVG in 4diac style."""

    FONT_FAMILY = "TGL, 'Times New Roman', Times, serif"
    FONT_FAMILY_ITALIC = "TGL, 'Times New Roman', Times, serif"
    FONT_SIZE = 14

    # @font-face declarations mapping TGL 0-17 (normal) and TGL 0-16 (italic)
    # to a unified "TGL" family. When the local TGL fonts are installed, the
    # browser uses them directly. When not installed, the fallback fonts in
    # font-family take over, and font-style="italic" applies correctly to those.
    FONT_FACE_STYLE = '''
  <style>
    @font-face {
      font-family: "TGL";
      src: local("TGL 0-17_std"), local("TGL 0-17"), local("TGL 0-17 alt");
      font-style: normal;
      font-weight: normal;
    }
    @font-face {
      font-family: "TGL";
      src: local("TGL 0-16_std"), local("TGL 0-16");
      font-style: italic;
      font-weight: normal;
    }
  </style>'''

    # Colors (from 4diac IDE plugin.xml)
    BLOCK_STROKE_COLOR = "#A0A0A0"  # Light gray for block outline
    EVENT_PORT_COLOR = "#63B31F"    # Green for event ports (99,179,31)
    BOOL_PORT_COLOR = "#A3B08F"     # Muted green-gray for BOOL (163,176,143)
    ANY_BIT_PORT_COLOR = "#82A3A9"  # Blue-gray for ANY_BIT types (130,163,169)
    ANY_INT_PORT_COLOR = "#18519E"  # Dark blue for ANY_INT types (24,81,158)
    ANY_REAL_PORT_COLOR = "#DBB418" # Gold for ANY_REAL types (219,180,24)
    STRING_PORT_COLOR = "#BD8663"   # Brown for string types (189,134,99)
    DATA_PORT_COLOR = "#3366FF"     # Blue for generic data (51,102,255)
    ADAPTER_PORT_COLOR = "#845DAF"  # Purple for adapter ports (132,93,175)

    # Type name sets for color mapping
    STRING_TYPES = {"STRING", "WSTRING", "ANY_STRING", "ANY_CHARS", "CHAR", "WCHAR"}
    INT_TYPES = {"INT", "UINT", "SINT", "USINT", "DINT", "UDINT", "LINT", "ULINT", "ANY_INT", "ANY_NUM"}
    REAL_TYPES = {"REAL", "LREAL", "ANY_REAL"}
    BIT_TYPES = {"BYTE", "WORD", "DWORD", "LWORD", "ANY_BIT"}

    # Layout
    PORT_ROW_HEIGHT = 20
    BLOCK_PADDING = 10
    NAME_SECTION_HEIGHT = 40
    CONNECTOR_WIDTH = 10
    CONNECTOR_HEIGHT = 10
    TRIANGLE_WIDTH = 5
    TRIANGLE_HEIGHT = 10

    def __init__(self, show_comments: bool = True, show_types: bool = True, show_shadow: bool = True):
        self.show_comments = show_comments
        self.show_types = show_types
        self.show_shadow = show_shadow

        # Calculated dimensions
        self.block_left = 0
        self.block_right = 0
        self.block_width = 0
        self.block_height = 0
        self.event_section_height = 0
        self.data_section_height = 0
        self.name_section_top = 0
        self.name_section_bottom = 0

        # Port positions for association lines
        self.event_input_y: Dict[str, float] = {}
        self.event_output_y: Dict[str, float] = {}
        self.data_input_y: Dict[str, float] = {}
        self.data_output_y: Dict[str, float] = {}
        self.socket_y: Dict[str, float] = {}
        self.plug_y: Dict[str, float] = {}

        # Adapter section position
        self.adapter_section_top = 0

        # Font for text measurement (Pillow)
        self._font = None
        self._font_italic = None
        self._init_fonts()

    def _init_fonts(self):
        """Initialize fonts for text measurement if Pillow is available."""
        if not PILLOW_AVAILABLE:
            return

        # Try to load TGL fonts first (the actual fonts used in SVG), then fallback to system fonts
        # TGL 0-17 is regular, TGL 0-16 is italic (for technical drawings)
        import os
        home = os.path.expanduser("~")

        script_dir = os.path.dirname(os.path.abspath(__file__))
        tgl_dir = os.path.join(script_dir, "tgl")
        font_candidates = [
            # TGL fonts - actual fonts used in the SVG
            f"{home}/Library/Fonts/TGL 0-17.ttf",
            f"{home}/Library/Fonts/TGL 0-17_std.ttf",
            f"{home}/Library/Fonts/TGL 0-17 alt.ttf",
            f"{home}/Library/Fonts/TGL 0-17 alt_std.ttf",
            os.path.join(tgl_dir, "TGL 0-17.ttf"),
            os.path.join(tgl_dir, "TGL 0-17_std.ttf"),
            "/Library/Fonts/TGL 0-17.ttf",
            "/Library/Fonts/TGL 0-17 alt.ttf",
            # Fallback system fonts (Times New Roman)
            "/Library/Fonts/Times New Roman.ttf",
            "/System/Library/Fonts/Times.ttc",
            "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
            "/usr/share/fonts/TTF/times.ttf",
            "C:\\Windows\\Fonts\\times.ttf",
        ]

        italic_candidates = [
            # TGL italic font
            f"{home}/Library/Fonts/TGL 0-16.ttf",
            f"{home}/Library/Fonts/TGL 0-16_std.ttf",
            os.path.join(tgl_dir, "TGL 0-16.ttf"),
            os.path.join(tgl_dir, "TGL 0-16_std.ttf"),
            "/Library/Fonts/TGL 0-16.ttf",
            # Fallback system fonts (Times New Roman Italic)
            "/Library/Fonts/Times New Roman Italic.ttf",
            "/System/Library/Fonts/Times.ttc",
            "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Italic.ttf",
            "C:\\Windows\\Fonts\\timesi.ttf",
        ]

        for font_path in font_candidates:
            try:
                self._font = ImageFont.truetype(font_path, self.FONT_SIZE)
                break
            except:
                continue

        # Try to load italic font
        for font_path in italic_candidates:
            try:
                self._font_italic = ImageFont.truetype(font_path, self.FONT_SIZE)
                break
            except:
                continue

        # If no italic font found, use regular font
        if self._font_italic is None and self._font is not None:
            self._font_italic = self._font

    def _get_port_color(self, port_type: str) -> str:
        """Return the fill color for a data port based on its type."""
        # For array types, use the element type for color mapping
        t = port_type
        if t.startswith("ARRAY "):
            # Extract element type after "OF "
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

    def _measure_text(self, text: str, italic: bool = False) -> float:
        """Measure text width using Pillow if available, otherwise estimate."""
        if PILLOW_AVAILABLE and self._font:
            font = self._font_italic if italic and self._font_italic else self._font
            # Use getbbox for accurate measurement
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0] if bbox else len(text) * 8
        else:
            # Fallback: estimate based on character count
            char_width = 8.5  # Average character width for font size 14
            return len(text) * char_width

    def render(self, fb: FunctionBlock) -> str:
        self._calculate_dimensions(fb)

        # Initialize connector positions (will be updated by _render_association_lines)
        self.leftmost_connector_x = -self.CONNECTOR_WIDTH - 5
        self.rightmost_connector_x = self.block_width + 5 + self.CONNECTOR_WIDTH

        parts = []
        parts.append(self._svg_header())
        parts.append(self._render_block_outline(fb))
        parts.append(self._render_event_ports(fb))
        parts.append(self._render_name_section(fb))
        parts.append(self._render_data_ports(fb))
        parts.append(self._render_adapter_ports(fb))
        # Render association lines before external labels so we know the connector positions
        parts.append(self._render_association_lines(fb))
        parts.append(self._render_external_labels(fb))
        parts.append(self._svg_footer())

        return "\n".join(parts)

    def _calculate_dimensions(self, fb: FunctionBlock):
        """Calculate block dimensions based on content."""
        # Number of ports on each side
        num_event_inputs = len(fb.event_inputs)
        num_event_outputs = len(fb.event_outputs)
        num_data_inputs = len(fb.data_inputs)
        num_data_outputs = len(fb.data_outputs)
        num_sockets = len(fb.sockets)
        num_plugs = len(fb.plugs)

        num_event_rows = max(num_event_inputs, num_event_outputs, 1)
        num_data_rows = max(num_data_inputs, num_data_outputs, 1)

        # Add extra padding: top of event section and bottom of data section only
        section_padding = self.PORT_ROW_HEIGHT / 2 - 4  # 6 pixels extra
        self.event_section_height = num_event_rows * self.PORT_ROW_HEIGHT + section_padding
        self.data_section_height = num_data_rows * self.PORT_ROW_HEIGHT + section_padding

        # Adapters are drawn below both inputs and outputs at the same y-level
        # The adapter section starts below whichever side (inputs or outputs) has more ports
        num_adapter_rows = max(num_sockets, num_plugs)
        self.adapter_section_height = num_adapter_rows * self.PORT_ROW_HEIGHT if num_adapter_rows > 0 else 0

        self.block_height = self.event_section_height + self.NAME_SECTION_HEIGHT + self.data_section_height + self.adapter_section_height

        # Calculate block width based on:
        # 1. Type name in name section (with icon)
        # 2. Left port names (inputs)
        # 3. Right port names (outputs)

        # Name section layout: notch(10) + gap(5) + icon(18) + gap(5) + text + padding + notch(10)
        # Text starts at x = 38, and we need padding on the right side plus the right notch
        notch = 10
        text_start_x = notch + 5 + 18 + 5  # = 38
        name_width = self._measure_text(fb.name, italic=True)
        name_section_width = text_start_x + name_width + 15 + notch

        # Calculate max width needed for left side ports (inputs)
        # Triangle (5px) + gap (3px) + text
        triangle_space = self.TRIANGLE_WIDTH + 3 + 1.5  # triangle + gap + stroke offset
        # Adapter rectangle is double width of triangle
        adapter_space = self.TRIANGLE_WIDTH * 2 + 3 + 1.5

        max_left_port_width = 0
        for port in fb.event_inputs + fb.data_inputs:
            port_width = triangle_space + self._measure_text(port.name)
            max_left_port_width = max(max_left_port_width, port_width)
        # Include sockets (input adapters)
        for port in fb.sockets:
            port_width = adapter_space + self._measure_text(port.name)
            max_left_port_width = max(max_left_port_width, port_width)

        # Calculate max width needed for right side ports (outputs)
        # text + gap (3px) + triangle (5px)
        max_right_port_width = 0
        for port in fb.event_outputs + fb.data_outputs:
            port_width = triangle_space + self._measure_text(port.name)
            max_right_port_width = max(max_right_port_width, port_width)
        # Include plugs (output adapters)
        for port in fb.plugs:
            port_width = adapter_space + self._measure_text(port.name)
            max_right_port_width = max(max_right_port_width, port_width)

        # Total width must accommodate:
        # - Name section width
        # - Left ports + right ports with some minimum center space
        min_center_gap = 20  # Minimum gap between left and right port labels
        ports_width = max_left_port_width + min_center_gap + max_right_port_width

        # Use the maximum of all width requirements
        self.block_width = max(100, name_section_width, ports_width)

        self.name_section_top = self.event_section_height
        self.name_section_bottom = self.event_section_height + self.NAME_SECTION_HEIGHT
        self.adapter_section_top = self.name_section_bottom + self.data_section_height

        # Calculate external label widths for margin calculation
        # Left side labels: "Comment – Type" format
        self.max_left_label_width = 0
        for port in fb.event_inputs:
            label_width = self._calculate_label_width(port, is_event=True, is_left=True)
            self.max_left_label_width = max(self.max_left_label_width, label_width)
        for port in fb.data_inputs:
            label_width = self._calculate_label_width(port, is_event=False, is_left=True)
            self.max_left_label_width = max(self.max_left_label_width, label_width)
        for port in fb.sockets:
            label_width = self._calculate_label_width(port, is_event=False, is_left=True, is_adapter=True)
            self.max_left_label_width = max(self.max_left_label_width, label_width)

        # Right side labels: "Type – Comment" format
        self.max_right_label_width = 0
        for port in fb.event_outputs:
            label_width = self._calculate_label_width(port, is_event=True, is_left=False)
            self.max_right_label_width = max(self.max_right_label_width, label_width)
        for port in fb.data_outputs:
            label_width = self._calculate_label_width(port, is_event=False, is_left=False)
            self.max_right_label_width = max(self.max_right_label_width, label_width)
        for port in fb.plugs:
            label_width = self._calculate_label_width(port, is_event=False, is_left=False, is_adapter=True)
            self.max_right_label_width = max(self.max_right_label_width, label_width)

        # Calculate connector space based on number of events with associations
        # This must match the calculation in _render_association_lines
        cw = self.CONNECTOR_WIDTH
        gap = 5
        line_spacing = cw + 4
        label_gap = 10  # Gap between connector and label

        num_left_events_with_assoc = sum(1 for e in fb.event_inputs if e.associated_vars)
        num_right_events_with_assoc = sum(1 for e in fb.event_outputs if e.associated_vars)

        # Left side: leftmost_connector_x = -cw - gap - (num_events-1) * line_spacing
        # Label ends at leftmost_connector_x - label_gap
        # So left margin = abs(leftmost_connector_x - label_gap) + max_left_label_width
        if num_left_events_with_assoc > 0:
            leftmost_x = -cw - gap - (num_left_events_with_assoc - 1) * line_spacing
            self.left_connector_space = abs(leftmost_x - label_gap)
        else:
            # Even without associations, labels need space from block edge
            # Default: gap (5) + connector_width (10) + label_gap (10) = 25
            self.left_connector_space = gap + cw + label_gap

        # Right side: rightmost_connector_x = block_width + gap + (num_events-1) * line_spacing + cw
        # Label starts at rightmost_connector_x + label_gap
        # So right margin = (rightmost_connector_x + label_gap - block_width) + max_right_label_width
        if num_right_events_with_assoc > 0:
            rightmost_x = gap + (num_right_events_with_assoc - 1) * line_spacing + cw
            self.right_connector_space = rightmost_x + label_gap
        else:
            # Even without associations, labels need space from block edge
            # Default: gap (5) + connector_width (10) + label_gap (10) = 25
            self.right_connector_space = gap + cw + label_gap

    def _calculate_label_width(self, port: Port, is_event: bool, is_left: bool,
                               is_adapter: bool = False) -> float:
        """Calculate the width of an external label for a port."""
        dash_width = self._measure_text(" – ")

        label_width = 0
        if self.show_comments and port.comment:
            label_width += self._measure_text(port.comment)
        if self.show_types:
            if label_width > 0:
                label_width += dash_width
            if is_event:
                label_width += self._measure_text("Event", italic=True)
            else:
                # Only adapter ports (sockets/plugs) use the short type name after ::
                if is_adapter:
                    type_name = port.port_type.split("::")[-1] if "::" in port.port_type else port.port_type
                else:
                    type_name = port.port_type
                label_width += self._measure_text(type_name, italic=True)

        return label_width

    def _svg_header(self) -> str:
        # Calculate margins based on actual content
        # Left margin: labels + connector space + page margin
        self.left_margin = self.max_left_label_width + self.left_connector_space + 10
        # Right margin: labels + connector space + page margin
        self.right_margin = self.max_right_label_width + self.right_connector_space + 10
        top_margin = 10
        bottom_margin = 10

        self.block_left = self.left_margin
        self.block_right = self.left_margin + self.block_width

        total_width = self.left_margin + self.block_width + self.right_margin
        total_height = self.block_height + top_margin + bottom_margin

        # Drop shadow filter definition (compatible version for Inkscape)
        # Centered shadow (visible on all sides) with higher intensity
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
     viewBox="0 0 {total_width} {total_height}"
     width="{total_width}" height="{total_height}">{self.FONT_FACE_STYLE}{shadow_defs}
  <g transform="translate({self.left_margin}, {top_margin})">'''

    def _svg_footer(self) -> str:
        return "  </g>\n</svg>"

    def _render_block_outline(self, fb: FunctionBlock) -> str:
        """Render the main block outline with notched middle section and rounded corners.

        Rounded corners:
        - 4 outer corners of the block
        - outer-facing corners at the notches (where the outline turns outward)

        Sharp corners:
        - inner corners of the notches (where the outline turns inward)
        """
        notch = 10  # Depth of the notch
        r = 3  # Corner radius
        et = self.event_section_height
        nb = self.name_section_bottom
        w = self.block_width
        h = self.block_height

        # Create the block path with notches for name section
        # Arc syntax: A rx ry x-axis-rotation large-arc-flag sweep-flag x y
        # sweep-flag=1 for clockwise (outer corners), sweep-flag=0 for counter-clockwise (outward-facing notch corners)
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

        # Apply shadow filter if enabled
        filter_attr = ' filter="url(#dropShadow)"' if self.show_shadow else ''

        return f'''
    <!-- Block Outline -->
    <path d="{path_d}"
          fill="#FFFFFF" stroke="{self.BLOCK_STROKE_COLOR}" stroke-width="1.5"
          stroke-linejoin="round"{filter_attr}/>'''

    def _render_event_ports(self, fb: FunctionBlock) -> str:
        """Render event input and output ports (triangles and labels only, no connectors)."""
        parts = []
        parts.append("\n    <!-- Event Ports -->")

        # Extra padding at top of event section
        top_padding = self.PORT_ROW_HEIGHT / 2 - 4  # 6 pixels

        # Event inputs (left side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in fb.event_inputs:
            self.event_input_y[port.name] = y
            parts.append(self._render_event_input_port(port, y))
            y += self.PORT_ROW_HEIGHT

        # Event outputs (right side)
        y = self.PORT_ROW_HEIGHT / 2 + top_padding
        for port in fb.event_outputs:
            self.event_output_y[port.name] = y
            parts.append(self._render_event_output_port(port, y))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_event_input_port(self, port: Port, y: float) -> str:
        """Render an event input port (left side) - triangle and label only."""
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5  # Offset by block outline stroke width

        # Triangle pointing right, INSIDE block, offset inward by stroke width
        tri_x = stroke_offset
        tri_points = f"{tri_x},{y - th/2} {tri_x + tw},{y} {tri_x},{y + th/2}"

        # Port name after triangle
        text_x = tri_x + tw + 3

        # Text baseline adjustment for TGL font
        text_y = y + 1

        return f'''
    <polygon points="{tri_points}" fill="{self.EVENT_PORT_COLOR}"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{port.name}</text>'''

    def _render_event_output_port(self, port: Port, y: float) -> str:
        """Render an event output port (right side) - triangle and label only."""
        w = self.block_width
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5  # Offset by block outline stroke width

        # Triangle pointing right, INSIDE block, offset inward by stroke width
        tri_x = w - tw - stroke_offset
        tri_points = f"{tri_x},{y - th/2} {tri_x + tw},{y} {tri_x},{y + th/2}"

        # Port name before triangle (right-aligned)
        text_x = tri_x - 3
        # Text baseline adjustment for TGL font
        text_y = y + 1

        return f'''
    <polygon points="{tri_points}" fill="{self.EVENT_PORT_COLOR}"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{port.name}</text>'''

    @staticmethod
    def _mini_fb_path(x: float, y: float, w: float, h: float) -> str:
        """Generate a notched function block path (same shape as the icon box) at given position and size."""
        nd = w * 0.15          # notch depth (horizontal)
        nh = h / 6             # notch height
        nt = y + h / 4         # notch top y
        nb = nt + nh           # notch bottom y
        r = 0.5                # corner radius
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

    def _render_name_section(self, fb: FunctionBlock) -> str:
        """Render the name section."""
        notch = 10  # Depth of the notch
        center_y = self.name_section_top + self.NAME_SECTION_HEIGHT / 2

        # FB type icon
        if fb.fb_type == "BasicFB":
            icon_letter = "B"
        elif fb.fb_type == "CompositeFB":
            icon_letter = "C"
        elif fb.fb_type == "ServiceInterfaceFB":
            icon_letter = "Si"
        else:
            icon_letter = "S"

        version_text = ""
        if fb.version:
            version_text = f'''
    <text x="{self.block_width / 2}" y="{center_y + 20}"
          font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE - 2}"
          fill="#666666" text-anchor="middle">{fb.version}</text>'''

        # Icon dimensions
        icon_w = 18
        icon_h = 18
        icon_notch_depth = 2  # Notch depth (horizontal)
        icon_notch_height = icon_h / 6  # Notch height = 1/6 of box height
        icon_r = 1  # Corner radius
        gap_icon_text = 5  # Gap between icon and text

        # Calculate total width of icon + gap + text name
        name_width = self._measure_text(fb.name, italic=True)
        total_content_width = icon_w + gap_icon_text + name_width

        # Center the content horizontally in the block
        content_start_x = (self.block_width - total_content_width) / 2

        # Icon position (centered together with text)
        icon_x = content_start_x
        icon_y = center_y - 9
        icon_notch_top = icon_y + icon_h / 4  # Starts at 1/4 from top
        icon_notch_bottom = icon_notch_top + icon_notch_height

        # Path with rectangular notches on both left and right sides
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

        # Text position (after icon)
        text_x = icon_x + icon_w + gap_icon_text

        # Icon content: text letter for most types, graphic for SubApp
        if fb.fb_type == "SubApp":
            # Draw two mini notched function blocks (same shape as the icon box) inside it
            # with dark blue fill, connected by a horizontal line
            # Positioned in the lower part of the light blue icon box
            mini_w = 5.5
            mini_h = 7
            gap = 3  # gap between the two mini FBs
            # Center horizontally, position in lower portion of icon box
            pair_w = mini_w * 2 + gap
            pair_x = icon_x + (icon_w - pair_w) / 2
            pair_y = icon_y + icon_h - mini_h - 1.5

            left_path = self._mini_fb_path(pair_x, pair_y, mini_w, mini_h)
            right_path = self._mini_fb_path(pair_x + mini_w + gap, pair_y, mini_w, mini_h)

            # Connection lines between the two mini FBs
            conn_x1 = pair_x + mini_w
            conn_x2 = pair_x + mini_w + gap
            # Upper event line (green, near top of mini FBs)
            event_conn_y = pair_y + mini_h * 0.12
            # Lower data line (red, in lower portion of mini FBs)
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
    <text x="{icon_x + icon_w / 2}" y="{center_y + 5}"
          font-family="{self.FONT_FAMILY}" font-size="12" font-weight="bold"
          fill="#000000" text-anchor="middle">{icon_letter}</text>'''

        return f'''
    <!-- Name Section -->
    <!-- FB Type Icon -->
    <path d="{icon_path}"
          fill="#87CEEB" stroke="#1565C0" stroke-width="1"/>{icon_content}

    <!-- Block Name -->
    <text x="{text_x}" y="{center_y + 5}"
          font-family="{self.FONT_FAMILY_ITALIC}" font-size="{self.FONT_SIZE}"
          fill="#000000" font-style="italic">{fb.name}</text>
    {version_text}'''

    def _render_data_ports(self, fb: FunctionBlock) -> str:
        """Render data input and output ports."""
        parts = []
        parts.append("\n    <!-- Data Ports -->")

        base_y = self.name_section_bottom

        # Data inputs (left side)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in fb.data_inputs:
            self.data_input_y[port.name] = y
            parts.append(self._render_data_input_port(port, y))
            y += self.PORT_ROW_HEIGHT

        # Data outputs (right side)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in fb.data_outputs:
            self.data_output_y[port.name] = y
            parts.append(self._render_data_output_port(port, y))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_data_input_port(self, port: Port, y: float) -> str:
        """Render a data input port (left side) - triangle and label only."""
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5  # Offset by block outline stroke width

        # Triangle pointing right, INSIDE block, offset inward by stroke width
        tri_x = stroke_offset
        tri_points = f"{tri_x},{y - th/2} {tri_x + tw},{y} {tri_x},{y + th/2}"

        text_x = tri_x + tw + 3
        # Text baseline adjustment for TGL font
        text_y = y + 1

        fill_color = self._get_port_color(port.port_type)

        return f'''
    <polygon points="{tri_points}" fill="{fill_color}"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{port.name}</text>'''

    def _render_data_output_port(self, port: Port, y: float) -> str:
        """Render a data output port (right side) - triangle and label only."""
        w = self.block_width
        tw = self.TRIANGLE_WIDTH
        th = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5  # Offset by block outline stroke width

        # Triangle pointing right, INSIDE block, offset inward by stroke width
        tri_x = w - tw - stroke_offset
        tri_points = f"{tri_x},{y - th/2} {tri_x + tw},{y} {tri_x},{y + th/2}"

        text_x = tri_x - 3
        # Text baseline adjustment for TGL font
        text_y = y + 1

        fill_color = self._get_port_color(port.port_type)

        return f'''
    <polygon points="{tri_points}" fill="{fill_color}"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{port.name}</text>'''

    def _render_adapter_ports(self, fb: FunctionBlock) -> str:
        """Render adapter ports (sockets and plugs) at the bottom of the block."""
        if not fb.sockets and not fb.plugs:
            return ""

        parts = []
        parts.append("\n    <!-- Adapter Ports -->")

        base_y = self.adapter_section_top

        # Sockets (left side - input adapters)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in fb.sockets:
            self.socket_y[port.name] = y
            parts.append(self._render_socket_port(port, y))
            y += self.PORT_ROW_HEIGHT

        # Plugs (right side - output adapters)
        y = base_y + self.PORT_ROW_HEIGHT / 2
        for port in fb.plugs:
            self.plug_y[port.name] = y
            parts.append(self._render_plug_port(port, y))
            y += self.PORT_ROW_HEIGHT

        return "\n".join(parts)

    def _render_socket_port(self, port: Port, y: float) -> str:
        """Render a socket (input adapter) port - notched rectangle like a rotated function block."""
        # Rectangle is double the width of triangle, same height
        rect_w = self.TRIANGLE_WIDTH * 2
        rect_h = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5

        rect_x = stroke_offset
        rect_y = y - rect_h / 2

        # Notch starts at 1/2 from left (so it ends at 3/4, leaving 1/4 on the right)
        notch_start = rect_x + rect_w / 2
        notch_width = rect_w / 4
        notch_depth = rect_h / 6  # Depth of notch (vertical)

        # Path with notch on top and bottom (like a rotated function block)
        # The notch creates a constriction in the middle
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
        # Text baseline adjustment for TGL font
        text_y = y + 1

        # Adapter color - use a distinct color (purple/magenta)
        adapter_color = self.ADAPTER_PORT_COLOR

        # Socket (input adapter) is drawn as outline only
        return f'''
    <path d="{path_d}" fill="none" stroke="{adapter_color}" stroke-width="1"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{port.name}</text>'''

    def _render_plug_port(self, port: Port, y: float) -> str:
        """Render a plug (output adapter) port - horizontally mirrored notched rectangle."""
        w = self.block_width
        rect_w = self.TRIANGLE_WIDTH * 2
        rect_h = self.TRIANGLE_HEIGHT
        stroke_offset = 1.5

        rect_x = w - rect_w - stroke_offset
        rect_y = y - rect_h / 2

        # Mirrored: Notch starts at 1/4 from left (so 1/4 space on left side)
        notch_start = rect_x + rect_w / 4
        notch_width = rect_w / 4
        notch_depth = rect_h / 6  # Depth of notch (vertical)

        # Path with notch on top and bottom (horizontally mirrored from socket)
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
        # Text baseline adjustment for TGL font
        text_y = y + 1

        # Adapter color - use a distinct color (purple/magenta)
        adapter_color = self.ADAPTER_PORT_COLOR

        return f'''
    <path d="{path_d}" fill="{adapter_color}"/>
    <text x="{text_x}" y="{text_y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{port.name}</text>'''

    def _render_external_labels(self, fb: FunctionBlock) -> str:
        """Render labels outside the block (comments and types).
        Left side: right-aligned text ending before the leftmost connector.
        Right side: left-aligned text starting after the rightmost connector."""
        parts = []
        parts.append("\n    <!-- External Labels -->")

        # Calculate label positions based on connector positions
        # Left side: text ends before leftmost connector (with gap)
        left_label_x = self.leftmost_connector_x - 10
        # Right side: text starts after rightmost connector (with gap)
        right_label_x = self.rightmost_connector_x + 10

        w = self.block_width

        # Event inputs - left side external labels (right-aligned, ending at left_label_x)
        # Format: "Comment – Type" with Type in italic (using tspan)
        for port in fb.event_inputs:
            y = self.event_input_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_comments and port.comment:
                    label_parts.append(port.comment)
                if self.show_types:
                    if label_parts:
                        label_parts.append(" – ")
                    # Type in italic using tspan
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">Event</tspan>')
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{left_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{label_text}</text>''')

        # Event outputs - right side external labels (left-aligned, starting at right_label_x)
        # Format: "Type – Comment" with Type in italic (using tspan)
        for port in fb.event_outputs:
            y = self.event_output_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_types:
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">Event</tspan>')
                if self.show_comments and port.comment:
                    if label_parts:
                        label_parts.append(" – ")
                    label_parts.append(port.comment)
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{right_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{label_text}</text>''')

        # Data inputs - left side external labels (right-aligned, ending at left_label_x)
        # Format: "Comment – Type" with Type in italic (using tspan)
        for port in fb.data_inputs:
            y = self.data_input_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_comments and port.comment:
                    label_parts.append(port.comment)
                if self.show_types:
                    if label_parts:
                        label_parts.append(" – ")
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">{port.port_type}</tspan>')
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{left_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{label_text}</text>''')

        # Data outputs - right side external labels (left-aligned, starting at right_label_x)
        # Format: "Type – Comment" with Type in italic (using tspan)
        for port in fb.data_outputs:
            y = self.data_output_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_types:
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">{port.port_type}</tspan>')
                if self.show_comments and port.comment:
                    if label_parts:
                        label_parts.append(" – ")
                    label_parts.append(port.comment)
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{right_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{label_text}</text>''')

        # Sockets (input adapters) - left side external labels
        # Format: "Comment – AdapterType" with AdapterType in italic
        for port in fb.sockets:
            y = self.socket_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_comments and port.comment:
                    label_parts.append(port.comment)
                if self.show_types:
                    if label_parts:
                        label_parts.append(" – ")
                    # Use short adapter type name (last part after ::)
                    short_type = port.port_type.split("::")[-1] if "::" in port.port_type else port.port_type
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">{short_type}</tspan>')
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{left_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" text-anchor="end" dominant-baseline="middle">{label_text}</text>''')

        # Plugs (output adapters) - right side external labels
        # Format: "AdapterType – Comment" with AdapterType in italic
        for port in fb.plugs:
            y = self.plug_y[port.name] + 1  # Text baseline adjustment for TGL font
            if self.show_types or (self.show_comments and port.comment):
                label_parts = []
                if self.show_types:
                    short_type = port.port_type.split("::")[-1] if "::" in port.port_type else port.port_type
                    label_parts.append(f'<tspan font-family="{self.FONT_FAMILY_ITALIC}" font-style="italic" dominant-baseline="middle">{short_type}</tspan>')
                if self.show_comments and port.comment:
                    if label_parts:
                        label_parts.append(" – ")
                    label_parts.append(port.comment)
                label_text = "".join(label_parts)
                parts.append(f'''
    <text x="{right_label_x}" y="{y}" font-family="{self.FONT_FAMILY}" font-size="{self.FONT_SIZE}"
          fill="#000000" dominant-baseline="middle">{label_text}</text>''')

        return "\n".join(parts)

    def _render_association_lines(self, fb: FunctionBlock) -> str:
        """Render connector squares and vertical lines for With associations.
        Staggering is per EVENT only - all data associations of one event share the same x position.
        First event (top) is closest to block, subsequent events are further out.
        Also draws horizontal lines from block edge to beyond the outermost connector for each port."""
        parts = []
        parts.append("\n    <!-- Event-Data Association Connectors and Lines -->")

        cw = self.CONNECTOR_WIDTH
        ch = self.CONNECTOR_HEIGHT
        gap = 5  # Gap between block edge and first connector
        line_spacing = cw + 4  # Spacing between staggered events
        overhang = gap  # Horizontal line extends beyond outermost connector by this amount

        w = self.block_width

        # Track outermost connector x position for each port (for horizontal lines)
        input_event_outermost_x: Dict[str, float] = {}  # event_name -> leftmost x
        input_data_outermost_x: Dict[str, float] = {}   # var_name -> leftmost x
        output_event_outermost_x: Dict[str, float] = {} # event_name -> rightmost x
        output_data_outermost_x: Dict[str, float] = {}  # var_name -> rightmost x

        # INPUT SIDE associations
        base_x_input = -cw - gap  # First connector square starts here (closest to block)

        # Track outermost x position for label positioning
        self.leftmost_connector_x = base_x_input  # Default if no associations

        event_index = 0
        for event in fb.event_inputs:
            if event.name in self.event_input_y and event.associated_vars:
                event_y = self.event_input_y[event.name]

                # All data vars for this event share the same x position
                sq_x = base_x_input - event_index * line_spacing
                line_x = sq_x + cw / 2  # Center of connector square

                # Track leftmost position for labels
                self.leftmost_connector_x = min(self.leftmost_connector_x, sq_x)

                # Track outermost connector for this event
                if event.name not in input_event_outermost_x:
                    input_event_outermost_x[event.name] = sq_x
                else:
                    input_event_outermost_x[event.name] = min(input_event_outermost_x[event.name], sq_x)

                # Event connector square (one per event)
                parts.append(f'''
    <rect x="{sq_x}" y="{event_y - ch/2}" width="{cw}" height="{ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>''')

                # Data connector squares and lines for all associated vars
                for var_name in event.associated_vars:
                    if var_name in self.data_input_y:
                        data_y = self.data_input_y[var_name]

                        # Track outermost connector for this data var
                        if var_name not in input_data_outermost_x:
                            input_data_outermost_x[var_name] = sq_x
                        else:
                            input_data_outermost_x[var_name] = min(input_data_outermost_x[var_name], sq_x)

                        # Data connector square
                        parts.append(f'''
    <rect x="{sq_x}" y="{data_y - ch/2}" width="{cw}" height="{ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>''')

                        # Vertical line connecting event to data
                        parts.append(f'''
    <line x1="{line_x}" y1="{event_y}" x2="{line_x}" y2="{data_y}"
          stroke="#000000" stroke-width="1"/>''')

                event_index += 1

        # OUTPUT SIDE associations
        base_x_output = w + gap  # First connector square starts here (closest to block)

        # Track outermost x position for label positioning
        self.rightmost_connector_x = base_x_output + cw  # Default if no associations

        event_index = 0
        for event in fb.event_outputs:
            if event.name in self.event_output_y and event.associated_vars:
                event_y = self.event_output_y[event.name]

                # All data vars for this event share the same x position
                sq_x = base_x_output + event_index * line_spacing
                line_x = sq_x + cw / 2  # Center of connector square

                # Track rightmost position for labels (right edge of connector)
                self.rightmost_connector_x = max(self.rightmost_connector_x, sq_x + cw)

                # Track outermost connector for this event (right edge)
                right_edge = sq_x + cw
                if event.name not in output_event_outermost_x:
                    output_event_outermost_x[event.name] = right_edge
                else:
                    output_event_outermost_x[event.name] = max(output_event_outermost_x[event.name], right_edge)

                # Event connector square (one per event)
                parts.append(f'''
    <rect x="{sq_x}" y="{event_y - ch/2}" width="{cw}" height="{ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>''')

                # Data connector squares and lines for all associated vars
                for var_name in event.associated_vars:
                    if var_name in self.data_output_y:
                        data_y = self.data_output_y[var_name]

                        # Track outermost connector for this data var (right edge)
                        if var_name not in output_data_outermost_x:
                            output_data_outermost_x[var_name] = right_edge
                        else:
                            output_data_outermost_x[var_name] = max(output_data_outermost_x[var_name], right_edge)

                        # Data connector square
                        parts.append(f'''
    <rect x="{sq_x}" y="{data_y - ch/2}" width="{cw}" height="{ch}"
          fill="#FFFFFF" stroke="#000000" stroke-width="1"/>''')

                        # Vertical line connecting event to data
                        parts.append(f'''
    <line x1="{line_x}" y1="{event_y}" x2="{line_x}" y2="{data_y}"
          stroke="#000000" stroke-width="1"/>''')

                event_index += 1

        # Draw horizontal lines from block edge to beyond outermost connector
        parts.append("\n    <!-- Horizontal Connection Lines -->")

        # Input side horizontal lines (from block edge x=0 to beyond leftmost connector)
        for event_name, outermost_x in input_event_outermost_x.items():
            event_y = self.event_input_y[event_name]
            parts.append(f'''
    <line x1="0" y1="{event_y}" x2="{outermost_x - overhang}" y2="{event_y}"
          stroke="#000000" stroke-width="1"/>''')

        for var_name, outermost_x in input_data_outermost_x.items():
            data_y = self.data_input_y[var_name]
            parts.append(f'''
    <line x1="0" y1="{data_y}" x2="{outermost_x - overhang}" y2="{data_y}"
          stroke="#000000" stroke-width="1"/>''')

        # Output side horizontal lines (from block edge x=w to beyond rightmost connector)
        for event_name, outermost_x in output_event_outermost_x.items():
            event_y = self.event_output_y[event_name]
            parts.append(f'''
    <line x1="{w}" y1="{event_y}" x2="{outermost_x + overhang}" y2="{event_y}"
          stroke="#000000" stroke-width="1"/>''')

        for var_name, outermost_x in output_data_outermost_x.items():
            data_y = self.data_output_y[var_name]
            parts.append(f'''
    <line x1="{w}" y1="{data_y}" x2="{outermost_x + overhang}" y2="{data_y}"
          stroke="#000000" stroke-width="1"/>''')

        return "\n".join(parts)


def convert_fbt_to_svg(input_path: str, output_path: Optional[str] = None,
                       show_comments: bool = True, show_types: bool = True,
                       show_shadow: bool = True) -> str:
    parser = IEC61499Parser()
    renderer = SVGRenderer(show_comments=show_comments, show_types=show_types, show_shadow=show_shadow)

    fb = parser.parse(input_path)
    svg = renderer.render(fb)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg)
        print(f"SVG written to: {output_path}")

    return svg


def convert_batch(input_dir: str, output_dir: str, recursive: bool = True,
                  show_comments: bool = True, show_types: bool = True,
                  show_shadow: bool = True) -> int:
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pattern = "**/*.fbt" if recursive else "*.fbt"
    fbt_files = list(input_path.glob(pattern))

    adp_pattern = "**/*.adp" if recursive else "*.adp"
    fbt_files.extend(input_path.glob(adp_pattern))

    sub_pattern = "**/*.sub" if recursive else "*.sub"
    fbt_files.extend(input_path.glob(sub_pattern))

    count = 0
    for fbt_file in fbt_files:
        try:
            relative_path = fbt_file.relative_to(input_path)
            svg_file = output_path / relative_path.with_suffix('.svg')
            svg_file.parent.mkdir(parents=True, exist_ok=True)

            convert_fbt_to_svg(str(fbt_file), str(svg_file),
                             show_comments=show_comments, show_types=show_types,
                             show_shadow=show_shadow)
            count += 1
        except Exception as e:
            print(f"Error converting {fbt_file}: {e}", file=sys.stderr)

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Convert IEC 61499 Function Block XML to SVG (4diac style)"
    )
    parser.add_argument("input", help="Input .fbt file or directory")
    parser.add_argument("-o", "--output", help="Output SVG file or directory")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout")
    parser.add_argument("--batch", action="store_true", help="Batch convert directory")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse")
    parser.add_argument("--no-comments", action="store_true", help="Hide comments")
    parser.add_argument("--no-types", action="store_true", help="Hide types")
    parser.add_argument("--no-shadow", action="store_true", help="Disable drop shadow")

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    show_comments = not args.no_comments
    show_types = not args.no_types
    show_shadow = not args.no_shadow

    if args.batch or input_path.is_dir():
        output_dir = args.output or str(input_path) + "_svg"
        count = convert_batch(str(input_path), output_dir,
                            recursive=not args.no_recursive,
                            show_comments=show_comments, show_types=show_types,
                            show_shadow=show_shadow)
        print(f"Converted {count} files to {output_dir}")
    elif args.stdout:
        svg = convert_fbt_to_svg(str(input_path),
                                show_comments=show_comments, show_types=show_types,
                                show_shadow=show_shadow)
        print(svg)
    else:
        output_path = args.output or str(input_path.with_suffix('.svg'))
        convert_fbt_to_svg(str(input_path), output_path,
                          show_comments=show_comments, show_types=show_types,
                          show_shadow=show_shadow)


if __name__ == "__main__":
    main()
