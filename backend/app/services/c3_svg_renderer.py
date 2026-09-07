"""C3 SVG/HTML Rendering Engine — deterministic visual generation from specifications.

Generates high-quality SVG diagrams from VisualSpecification objects.
No external image generation APIs needed — purely deterministic rendering.
Supports: flowcharts, concept maps, hierarchies, timelines, cycles, comparisons,
sequence diagrams, process diagrams, architecture diagrams, tables, and more.
"""

from __future__ import annotations

import html as html_lib
import math

from app.core.logging import get_logger
from app.schemas.c3_visual_intelligence import (
    C3VisualType,
    VisualColumn,
    VisualSpecification,
)

logger = get_logger(__name__)

# ── Color Palette ──────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0B1626",
    "surface": "#0E1A2B",
    "primary": "#F2A623",
    "secondary": "#1D9E75",
    "accent": "#D85A30",
    "text": "#F4EFE4",
    "muted": "rgba(244,239,228,0.55)",
    "border": "rgba(244,239,228,0.14)",
    "node_fill": "#0E1A2B",
    "node_stroke": "rgba(244,239,228,0.22)",
    "highlight": "rgba(242,166,35,0.08)",
}

NODE_COLORS = ["#0E1A2B", "#1a2a3d", "#0d2137", "#1a1a2e", "#16213e", "#0f3460"]
NODE_STROKES = ["#F2A623", "#1D9E75", "#D85A30", "#F4EFE4", "#F2A623", "#1D9E75"]


def render_visual(spec: VisualSpecification) -> str:
    """Render a VisualSpecification into an SVG string."""
    renderers = {
        C3VisualType.FLOWCHART: _render_flowchart,
        C3VisualType.PROCESS_DIAGRAM: _render_process,
        C3VisualType.COMPARISON: _render_comparison,
        C3VisualType.HIERARCHY: _render_hierarchy,
        C3VisualType.TIMELINE: _render_timeline,
        C3VisualType.CYCLE: _render_cycle,
        C3VisualType.CONCEPT_MAP: _render_concept_map,
        C3VisualType.NETWORK_DIAGRAM: _render_network,
        C3VisualType.SEQUENCE_DIAGRAM: _render_sequence,
        C3VisualType.STEP_BY_STEP: _render_steps,
        C3VisualType.TABLE_VISUALIZATION: _render_table,
        C3VisualType.ARCHITECTURE_DIAGRAM: _render_architecture,
        C3VisualType.SYSTEM_DIAGRAM: _render_architecture,
        C3VisualType.STATE_DIAGRAM: _render_state_diagram,
        C3VisualType.FORMULA_VISUALIZATION: _render_formula,
        C3VisualType.RELATIONSHIP_GRAPH: _render_concept_map,
        C3VisualType.ANNOTATED_ILLUSTRATION: _render_concept_map,
        C3VisualType.TECHNICAL_DIAGRAM: _render_architecture,
        C3VisualType.CHART: _render_table,
        C3VisualType.REAL_WORLD_SCENARIO: _render_process,
    }

    renderer = renderers.get(spec.visual_type, _render_concept_map)
    return renderer(spec)


# ── Shared SVG Helpers ─────────────────────────────────────────────────────


def _svg_open(width: int = 900, height: int = 600) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" '
        f"style=\"background:{COLORS['bg']};font-family:'Space Grotesk',sans-serif;\">"
    )


def _svg_close() -> str:
    return "</svg>"


def _esc(text: str) -> str:
    return html_lib.escape(str(text))


def _wrap_text(text: str, max_chars: int = 18) -> str:
    """Break long text into lines."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "&#10;".join(lines[:4])


def _defs() -> str:
    return (
        "<defs>"
        '<filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/>'
        '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '<marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        '<polygon points="0 0, 8 3, 0 6" fill="rgba(244,239,228,0.4)"/>'
        "</marker>"
        '<marker id="arrowhead-amber" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">'
        '<polygon points="0 0, 8 3, 0 6" fill="#F2A623"/>'
        "</marker>"
        "</defs>"
    )


# ── Individual Renderers ───────────────────────────────────────────────────


def _render_flowchart(spec: VisualSpecification) -> str:
    """Render a vertical flowchart."""
    w, h = 900, max(400, 80 * (len(spec.nodes) + 2))
    svg = _svg_open(w, h) + _defs()

    # Title
    svg += f'<text x="{w // 2}" y="35" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    n = len(spec.nodes)
    if n == 0:
        svg += _svg_close()
        return svg

    node_w, node_h = 220, 50
    spacing_y = 80
    start_y = 80

    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        cx = w / 2
        cy = start_y + i * spacing_y
        positions[node.id] = (cx, cy)

        is_terminal = node.node_type in ("start", "end")
        fill = (
            COLORS["secondary"]
            if node.node_type == "start"
            else (COLORS["accent"] if node.node_type == "end" else COLORS["node_fill"])
        )
        stroke = (
            COLORS["secondary"]
            if node.node_type == "start"
            else (COLORS["accent"] if node.node_type == "end" else COLORS["primary"])
        )
        rx = "25" if is_terminal else "6"

        svg += f'<rect x="{cx - node_w / 2}" y="{cy - node_h / 2}" width="{node_w}" height="{node_h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        label = _wrap_text(node.label, 22)
        svg += f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" fill="{COLORS["text"]}" font-size="13" font-weight="600">{_esc(label)}</text>'

    # Edges
    for edge in spec.edges:
        src = positions.get(edge.source_id)
        tgt = positions.get(edge.target_id)
        if src and tgt:
            x1, y1 = src
            x2, y2 = tgt
            y1 += node_h / 2
            y2 -= node_h / 2
            svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="rgba(244,239,228,0.3)" stroke-width="1.5" marker-end="url(#arrowhead)"/>'
            if edge.label:
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                svg += f'<text x="{mx + 8}" y="{my}" fill="{COLORS["muted"]}" font-size="11">{_esc(edge.label)}</text>'

    svg += _svg_close()
    return svg


def _render_process(spec: VisualSpecification) -> str:
    """Render a horizontal process diagram."""
    w = max(900, 180 * len(spec.nodes) + 100)
    h = 300
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    n = len(spec.nodes)
    if n == 0:
        svg += _svg_close()
        return svg

    box_w, box_h = 150, 60
    spacing = 30
    total_w = n * box_w + (n - 1) * spacing
    start_x = (w - total_w) / 2
    cy = h / 2 + 10

    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        x = start_x + i * (box_w + spacing)
        positions[node.id] = (x + box_w / 2, cy)
        color = NODE_COLORS[i % len(NODE_COLORS)]
        stroke = NODE_STROKES[i % len(NODE_STROKES)]

        svg += f'<rect x="{x}" y="{cy - box_h / 2}" width="{box_w}" height="{box_h}" rx="6" fill="{color}" stroke="{stroke}" stroke-width="1.5"/>'
        label = _wrap_text(node.label, 16)
        svg += f'<text x="{x + box_w / 2}" y="{cy + 4}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12" font-weight="600">{_esc(label)}</text>'

        if i < n - 1:
            ax = x + box_w + 2
            svg += f'<line x1="{ax}" y1="{cy}" x2="{ax + spacing - 4}" y2="{cy}" stroke="rgba(244,239,228,0.3)" stroke-width="1.5" marker-end="url(#arrowhead)"/>'

    svg += _svg_close()
    return svg


def _render_comparison(spec: VisualSpecification) -> str:
    """Render a side-by-side comparison."""
    cols = spec.columns or [
        VisualColumn(header="A", items=["1", "2"]),
        VisualColumn(header="B", items=["3", "4"]),
    ]
    n = len(cols)
    col_w = max(150, min(250, 800 // n))
    w = max(900, n * col_w + 60)
    h = 400
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    start_x = (w - n * col_w) / 2
    for i, col in enumerate(cols):
        x = start_x + i * col_w
        color = NODE_COLORS[i % len(NODE_COLORS)]
        stroke = NODE_STROKES[i % len(NODE_STROKES)]

        # Header
        svg += f'<rect x="{x}" y="60" width="{col_w}" height="40" rx="4" fill="{stroke}" opacity="0.2"/>'
        svg += f'<text x="{x + col_w / 2}" y="85" text-anchor="middle" fill="{stroke}" font-size="14" font-weight="700">{_esc(col.header)}</text>'

        # Items
        for j, item in enumerate(col.items):
            iy = 120 + j * 36
            svg += f'<rect x="{x + 5}" y="{iy}" width="{col_w - 10}" height="30" rx="3" fill="{color}" stroke="rgba(244,239,228,0.1)"/>'
            svg += f'<text x="{x + col_w / 2}" y="{iy + 20}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12">{_esc(_wrap_text(item, 25))}</text>'

        # Divider
        if i < n - 1:
            dx = x + col_w
            svg += f'<line x1="{dx}" y1="60" x2="{dx}" y2="{h - 20}" stroke="rgba(244,239,228,0.1)" stroke-dasharray="4 4"/>'

    svg += _svg_close()
    return svg


def _render_hierarchy(spec: VisualSpecification) -> str:
    """Render a tree hierarchy."""
    w, h = 900, 550
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    # Root at top center
    root_x, root_y = w / 2, 80
    svg += f'<rect x="{root_x - 100}" y="{root_y - 20}" width="200" height="40" rx="6" fill="{COLORS["primary"]}" stroke="{COLORS["primary"]}"/>'
    svg += f'<text x="{root_x}" y="{root_y + 5}" text-anchor="middle" fill="{COLORS["surface"]}" font-size="13" font-weight="700">{_esc(spec.title)}</text>'

    n = len(spec.nodes)
    if n == 0:
        svg += _svg_close()
        return svg

    level_y = 180
    node_w, node_h = 160, 44
    spacing = 20
    total = n * node_w + (n - 1) * spacing
    sx = (w - total) / 2

    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(spec.nodes):
        x = sx + i * (node_w + spacing)
        positions[node.id] = (x + node_w / 2, level_y)
        color = NODE_COLORS[i % len(NODE_COLORS)]
        stroke = NODE_STROKES[i % len(NODE_STROKES)]

        # Connect to root
        svg += f'<line x1="{root_x}" y1="{root_y + 20}" x2="{x + node_w / 2}" y2="{level_y - node_h / 2}" stroke="rgba(244,239,228,0.2)" stroke-width="1"/>'

        svg += f'<rect x="{x}" y="{level_y - node_h / 2}" width="{node_w}" height="{node_h}" rx="6" fill="{color}" stroke="{stroke}" stroke-width="1.5"/>'
        label = _wrap_text(node.label, 16)
        svg += f'<text x="{x + node_w / 2}" y="{level_y + 4}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12" font-weight="600">{_esc(label)}</text>'

    svg += _svg_close()
    return svg


def _render_timeline(spec: VisualSpecification) -> str:
    """Render a horizontal timeline."""
    steps = spec.steps or []
    n = len(steps)
    w = max(900, 160 * n + 100)
    h = 350
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    if n == 0:
        svg += _svg_close()
        return svg

    line_y = 140
    step_w = 140
    spacing = 20
    total = n * step_w + (n - 1) * spacing
    sx = (w - total) / 2

    # Main timeline line
    svg += f'<line x1="{sx}" y1="{line_y}" x2="{sx + total}" y2="{line_y}" stroke="rgba(244,239,228,0.2)" stroke-width="2"/>'

    for i, step in enumerate(steps):
        x = sx + i * (step_w + spacing)
        cx = x + step_w / 2
        color = NODE_STROKES[i % len(NODE_STROKES)]

        # Circle node
        svg += f'<circle cx="{cx}" cy="{line_y}" r="14" fill="{color}" stroke="{COLORS["text"]}" stroke-width="2"/>'
        svg += f'<text x="{cx}" y="{line_y + 5}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12" font-weight="700">{i + 1}</text>'

        # Title below
        label = _wrap_text(step.title, 16)
        svg += f'<text x="{cx}" y="{line_y + 40}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12" font-weight="600">{_esc(label)}</text>'

        # Description
        if step.description:
            desc = _wrap_text(step.description, 20)
            svg += f'<text x="{cx}" y="{line_y + 60}" text-anchor="middle" fill="{COLORS["muted"]}" font-size="10">{_esc(desc)}</text>'

    svg += _svg_close()
    return svg


def _render_cycle(spec: VisualSpecification) -> str:
    """Render a circular cycle diagram."""
    w, h = 700, 650
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    nodes = spec.nodes
    n = len(nodes)
    if n == 0:
        svg += _svg_close()
        return svg

    cx, cy = w / 2, h / 2 + 20
    radius = 200
    node_r = 50

    # Draw edges first (behind nodes)
    for edge in spec.edges:
        src_idx = next((i for i, nd in enumerate(nodes) if nd.id == edge.source_id), None)
        tgt_idx = next((i for i, nd in enumerate(nodes) if nd.id == edge.target_id), None)
        if src_idx is not None and tgt_idx is not None:
            a1 = 2 * math.pi * src_idx / n - math.pi / 2
            a2 = 2 * math.pi * tgt_idx / n - math.pi / 2
            x1 = cx + radius * math.cos(a1)
            y1 = cy + radius * math.sin(a1)
            x2 = cx + radius * math.cos(a2)
            y2 = cy + radius * math.sin(a2)
            svg += f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="rgba(244,239,228,0.25)" stroke-width="1.5" marker-end="url(#arrowhead-amber)"/>'

    # Draw nodes
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / n - math.pi / 2
        nx = cx + radius * math.cos(angle)
        ny = cy + radius * math.sin(angle)
        color = NODE_COLORS[i % len(NODE_COLORS)]
        stroke = NODE_STROKES[i % len(NODE_STROKES)]

        svg += f'<circle cx="{nx}" cy="{ny}" r="{node_r}" fill="{color}" stroke="{stroke}" stroke-width="2"/>'
        label = _wrap_text(node.label, 14)
        svg += f'<text x="{nx}" y="{ny + 4}" text-anchor="middle" fill="{COLORS["text"]}" font-size="12" font-weight="600">{_esc(label)}</text>'

    svg += _svg_close()
    return svg


def _render_concept_map(spec: VisualSpecification) -> str:
    """Render a radial concept map / mind map."""
    w, h = 700, 650
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    nodes = spec.nodes
    n = len(nodes)
    if n == 0:
        svg += _svg_close()
        return svg

    node_w, node_h = 130, 44

    # Edges
    for edge in spec.edges:
        src = next((nd for nd in nodes if nd.id == edge.source_id), None)
        tgt = next((nd for nd in nodes if nd.id == edge.target_id), None)
        if src and tgt:
            sx = (src.position or {}).get("x", 0.5)
            sy = (src.position or {}).get("y", 0.5)
            tx = (tgt.position or {}).get("x", 0.5)
            ty = (tgt.position or {}).get("y", 0.5)
            svg += f'<line x1="{sx * w}" y1="{sy * h}" x2="{tx * w}" y2="{ty * h}" stroke="rgba(244,239,228,0.15)" stroke-width="1"/>'

    # Nodes
    for i, node in enumerate(nodes):
        px = (node.position or {}).get("x", 0.5)
        py = (node.position or {}).get("y", 0.5)
        nx, ny = px * w, py * h
        is_center = node.node_type == "center"
        fill = COLORS["primary"] if is_center else NODE_COLORS[i % len(NODE_COLORS)]
        stroke = COLORS["primary"] if is_center else NODE_STROKES[i % len(NODE_STROKES)]
        font_color = COLORS["surface"] if is_center else COLORS["text"]
        rw = 110 if is_center else node_w
        rh = 40 if is_center else node_h

        svg += f'<rect x="{nx - rw / 2}" y="{ny - rh / 2}" width="{rw}" height="{rh}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        label = _wrap_text(node.label, 14 if is_center else 16)
        svg += f'<text x="{nx}" y="{ny + 4}" text-anchor="middle" fill="{font_color}" font-size="{14 if is_center else 12}" font-weight="{"700" if is_center else "600"}">{_esc(label)}</text>'

    svg += _svg_close()
    return svg


def _render_network(spec: VisualSpecification) -> str:
    """Render a network diagram."""
    return _render_concept_map(spec)


def _render_sequence(spec: VisualSpecification) -> str:
    """Render a sequence diagram."""
    steps = spec.steps or []
    n = len(steps)
    w = max(800, 140 * n + 100)
    h = 400
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    if n == 0:
        svg += _svg_close()
        return svg

    # Two lifelines
    lx1, lx2 = w * 0.3, w * 0.7
    svg += f'<line x1="{lx1}" y1="70" x2="{lx1}" y2="{h - 40}" stroke="rgba(244,239,228,0.2)" stroke-dasharray="6 4"/>'
    svg += f'<line x1="{lx2}" y1="70" x2="{lx2}" y2="{h - 40}" stroke="rgba(244,239,228,0.2)" stroke-dasharray="6 4"/>'
    svg += f'<rect x="{lx1 - 50}" y="50" width="100" height="25" rx="4" fill="{COLORS["primary"]}" opacity="0.2"/>'
    svg += f'<text x="{lx1}" y="67" text-anchor="middle" fill="{COLORS["primary"]}" font-size="11" font-weight="600">Sender</text>'
    svg += f'<rect x="{lx2 - 50}" y="50" width="100" height="25" rx="4" fill="{COLORS["secondary"]}" opacity="0.2"/>'
    svg += f'<text x="{lx2}" y="67" text-anchor="middle" fill="{COLORS["secondary"]}" font-size="11" font-weight="600">Receiver</text>'

    step_h = (h - 140) / max(n, 1)
    for i, step in enumerate(steps):
        y = 100 + i * step_h
        from_left = i % 2 == 0
        x1 = lx1 if from_left else lx2
        x2 = lx2 if from_left else lx1
        color = COLORS["primary"] if from_left else COLORS["secondary"]

        svg += f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="1.5" marker-end="url(#arrowhead)"/>'
        label = _wrap_text(step.title, 20)
        mx = (x1 + x2) / 2
        svg += f'<text x="{mx}" y="{y - 6}" text-anchor="middle" fill="{COLORS["text"]}" font-size="11">{_esc(label)}</text>'

    svg += _svg_close()
    return svg


def _render_steps(spec: VisualSpecification) -> str:
    """Render numbered step-by-step."""
    steps = spec.steps or []
    n = len(steps)
    w = 900
    h = max(350, 70 * n + 80)
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    for i, step in enumerate(steps):
        y = 70 + i * 70
        color = NODE_STROKES[i % len(NODE_STROKES)]

        # Step number circle
        svg += f'<circle cx="50" cy="{y + 15}" r="16" fill="{color}" opacity="0.2"/>'
        svg += f'<text x="50" y="{y + 20}" text-anchor="middle" fill="{color}" font-size="13" font-weight="700">{i + 1}</text>'

        # Step content
        svg += f'<rect x="80" y="{y}" width="{w - 120}" height="40" rx="4" fill="{COLORS["node_fill"]}" stroke="rgba(244,239,228,0.1)"/>'
        label = _wrap_text(step.title, 60)
        svg += f'<text x="95" y="{y + 25}" fill="{COLORS["text"]}" font-size="13" font-weight="600">{_esc(label)}</text>'

        # Arrow to next
        if i < n - 1:
            svg += f'<line x1="50" y1="{y + 31}" x2="50" y2="{y + 70 - 4}" stroke="rgba(244,239,228,0.15)" stroke-width="1" marker-end="url(#arrowhead)"/>'

    svg += _svg_close()
    return svg


def _render_table(spec: VisualSpecification) -> str:
    """Render a table visualization."""
    cols = spec.columns or []
    n_cols = len(cols)
    if n_cols == 0:
        return _render_concept_map(spec)

    n_rows = max(len(c.items) for c in cols) if cols else 0
    w = max(800, 180 * n_cols + 60)
    h = max(300, 60 * (n_rows + 1) + 80)
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    col_w = (w - 60) // n_cols
    sx = 30

    # Header row
    for i, col in enumerate(cols):
        x = sx + i * col_w
        svg += f'<rect x="{x}" y="60" width="{col_w}" height="35" rx="3" fill="{NODE_STROKES[i % len(NODE_STROKES)]}" opacity="0.15"/>'
        svg += f'<text x="{x + col_w / 2}" y="83" text-anchor="middle" fill="{NODE_STROKES[i % len(NODE_STROKES)]}" font-size="13" font-weight="700">{_esc(col.header)}</text>'

    # Data rows
    for r in range(n_rows):
        y = 100 + r * 35
        for i, col in enumerate(cols):
            x = sx + i * col_w
            item = col.items[r] if r < len(col.items) else ""
            bg = COLORS["node_fill"] if r % 2 == 0 else COLORS["surface"]
            svg += f'<rect x="{x}" y="{y}" width="{col_w}" height="32" fill="{bg}" stroke="rgba(244,239,228,0.06)"/>'
            svg += f'<text x="{x + col_w / 2}" y="{y + 21}" text-anchor="middle" fill="{COLORS["text"]}" font-size="11">{_esc(_wrap_text(item, 20))}</text>'

    svg += _svg_close()
    return svg


def _render_architecture(spec: VisualSpecification) -> str:
    """Render a layered architecture diagram."""
    return _render_hierarchy(spec)


def _render_state_diagram(spec: VisualSpecification) -> str:
    """Render a state diagram."""
    return _render_process(spec)


def _render_formula(spec: VisualSpecification) -> str:
    """Render a formula visualization."""
    w, h = 700, 400
    svg = _svg_open(w, h) + _defs()

    svg += f'<text x="{w // 2}" y="30" text-anchor="middle" fill="{COLORS["primary"]}" font-size="18" font-weight="700">{_esc(spec.title)}</text>'

    labels = spec.labels or []
    for i, label in enumerate(labels):
        y = 80 + i * 50
        svg += f'<rect x="80" y="{y}" width="{w - 160}" height="38" rx="6" fill="{COLORS["node_fill"]}" stroke="{COLORS["primary"]}" stroke-width="1" opacity="0.8"/>'
        svg += f'<text x="{w / 2}" y="{y + 25}" text-anchor="middle" fill="{COLORS["primary"]}" font-size="15" font-weight="600">{_esc(label)}</text>'

    svg += _svg_close()
    return svg
