#!/usr/bin/env python3
"""Render publication-style SCM figures from a JSON graph spec.

The graph itself is laid out by Graphviz/DOT. The final figure legend is
composed with Matplotlib so mathematical symbols render consistently.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


NODE_STYLES = {
    "chance": {
        "shape": "circle",
        "fill": "#FFFFFF",
        "legend": "chance variable",
    },
    "latent": {
        "shape": "circle",
        "fill": "#FFFFFF",
        "legend": "latent/oracle chance",
    },
    "observed": {
        "shape": "box",
        "fill": "#F3F4F6",
        "legend": "observed/assigned",
    },
    "decision": {
        "shape": "box",
        "fill": "#F7B6BF",
        "legend": "decision/action",
    },
    "roi_pattern": {
        "shape": "box",
        "fill": "#FFFFFF",
        "legend": "ROI-time pattern",
    },
    "generated": {
        "shape": "parallelogram",
        "fill": "#F3E5F8",
        "legend": "generated BOLD",
    },
    "endpoint": {
        "shape": "diamond",
        "fill": "#F7A6AD",
        "legend": "scoring endpoint",
    },
}

EDGE_STYLES = {
    "structural": {"style": "solid", "color": "#5D5D5D", "legend": "structural link"},
    "causal": {"style": "solid", "color": "#5D5D5D", "legend": "structural link"},
    "observation": {"style": "dotted", "color": "#8A8A8A", "legend": "observation/scoring"},
    "scoring": {"style": "dotted", "color": "#8A8A8A", "legend": "observation/scoring"},
    "absent": {"style": "dashed", "color": "#75869E", "legend": "absent/null path"},
}


def _q(value: Any) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _wrap_label(text: str, width: int = 16) -> str:
    return "\n".join(textwrap.wrap(str(text), width=width, break_long_words=False)) or str(text)


def _symbol_to_html(symbol: str) -> str:
    """Return a Graphviz HTML-like label for visibly stacked math symbols."""
    symbol = str(symbol)
    base, sep, suffix = symbol.partition("_")
    if not sep:
        if "=" in base:
            left, right = base.split("=", 1)
            return f'<FONT FACE="Times-Roman" POINT-SIZE="24"><I>{html.escape(left)}</I> = {html.escape(right)}</FONT>'
        return f'<FONT FACE="Times-Roman" POINT-SIZE="24"><I>{html.escape(base)}</I></FONT>'
    subscript = suffix.strip("{}")
    equals_suffix = ""
    if "=" in subscript:
        subscript, right = subscript.split("=", 1)
        equals_suffix = (
            '<TD ALIGN="LEFT" VALIGN="BOTTOM">'
            f'<FONT FACE="Times-Roman" POINT-SIZE="14"> = {html.escape(right)}</FONT>'
            "</TD>"
        )
    return (
        '<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="0" CELLSPACING="0">'
        "<TR>"
        f'<TD ALIGN="LEFT" VALIGN="MIDDLE"><FONT FACE="Times-Roman" POINT-SIZE="24"><I>{html.escape(base)}</I></FONT></TD>'
        f'<TD ALIGN="LEFT" VALIGN="BOTTOM"><FONT FACE="Times-Roman" POINT-SIZE="14"><I>{html.escape(subscript)}</I></FONT></TD>'
        f"{equals_suffix}"
        "</TR>"
        "</TABLE>"
    )


def _symbol_to_mathtext(symbol: str) -> str:
    symbol = str(symbol)
    if "_" not in symbol:
        return f"${symbol}$"
    base, sub = symbol.split("_", 1)
    sub = sub.strip("{}")
    return f"${base}_{{{sub}}}$"


def _dot_node_line(node: dict[str, Any], mode: str) -> str:
    node_id = node["id"]
    kind = node.get("kind", "observed")
    style = NODE_STYLES.get(kind, NODE_STYLES["observed"])
    attrs: dict[str, Any] = {
        "shape": style["shape"],
        "fillcolor": node.get("fill", style["fill"]),
        "color": node.get("color", "#595959"),
        "fontcolor": node.get("fontcolor", "#171717"),
        "penwidth": node.get("penwidth", 2.0),
        "fontsize": node.get("fontsize", 22 if mode == "math" else 15),
        "fontname": node.get("fontname", "Times-Italic" if mode == "math" else "Helvetica"),
        "margin": node.get("margin", "0.10,0.06"),
    }
    node_style = ["filled"]
    if kind == "roi_pattern":
        node_style.append("rounded")
    if node.get("style") == "dashed":
        node_style.append("dashed")
    attrs["style"] = ",".join(node_style)
    if mode == "math":
        label = node.get("symbol", node_id)
        attrs["label"] = f"<{_symbol_to_html(label)}>"
    else:
        attrs["label"] = _wrap_label(node.get("label", node.get("symbol", node_id)), width=int(node.get("wrap", 18)))
    attr_bits = []
    for key, value in attrs.items():
        if key == "label" and isinstance(value, str) and value.startswith("<"):
            attr_bits.append(f"{key}={value}")
        else:
            attr_bits.append(f"{key}={_q(value)}")
    return f"  {_q(node_id)} [{', '.join(attr_bits)}];"


def _dot_edge_line(edge: dict[str, Any]) -> str:
    kind = edge.get("kind", "structural")
    style = EDGE_STYLES.get(kind, EDGE_STYLES["structural"])
    attrs: dict[str, Any] = {
        "style": edge.get("style", style["style"]),
        "color": edge.get("color", style["color"]),
        "penwidth": edge.get("penwidth", 2.0),
        "arrowsize": edge.get("arrowsize", 0.85),
    }
    if edge.get("label"):
        attrs["label"] = edge["label"]
        attrs["fontsize"] = edge.get("fontsize", 11)
        attrs["fontname"] = edge.get("fontname", "Helvetica")
        attrs["fontcolor"] = edge.get("fontcolor", "#4B5563")
    attr_bits = [f"{key}={_q(value)}" for key, value in attrs.items()]
    return f"  {_q(edge['source'])} -> {_q(edge['target'])} [{', '.join(attr_bits)}];"


def build_dot(spec: dict[str, Any], mode: str) -> str:
    rankdir = spec.get("rankdir", "LR")
    nodesep = float(spec.get("nodesep", 0.72))
    ranksep = float(spec.get("ranksep", 1.0))
    lines = [
        "digraph SCM {",
        f"  graph [rankdir={_q(rankdir)}, bgcolor={_q('transparent')}, margin={_q('0.02')}, nodesep={_q(nodesep)}, ranksep={_q(ranksep)}, splines=true, outputorder=edgesfirst];",
        "  node [fixedsize=false];",
        "  edge [fontname=\"Helvetica\"];",
    ]
    for node in spec.get("nodes", []):
        lines.append(_dot_node_line(node, mode))
    for edge in spec.get("edges", []):
        lines.append(_dot_edge_line(edge))
    ranks: dict[Any, list[str]] = {}
    for node in spec.get("nodes", []):
        if "rank" in node:
            ranks.setdefault(node["rank"], []).append(node["id"])
    for rank, ids in sorted(ranks.items(), key=lambda item: str(item[0])):
        if len(ids) > 1:
            joined = "; ".join(_q(node_id) for node_id in ids)
            lines.append(f"  {{ rank=same; {joined}; }}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _find_vizjs_renderer(start_paths: Iterable[Path]) -> Path | None:
    candidates: list[Path] = []
    for start in start_paths:
        for parent in [start, *start.parents]:
            candidates.append(parent / "tools" / "graphviz-renderer" / "render-dot.mjs")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def render_graph(dot_path: Path, svg_path: Path, graph_png_path: Path, width: int, vizjs_renderer: Path | None) -> str:
    if shutil.which("dot"):
        subprocess.run(["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)], check=True)
        subprocess.run(["dot", "-Tpng", str(dot_path), "-o", str(graph_png_path)], check=True)
        return "graphviz_dot"
    if vizjs_renderer and vizjs_renderer.exists():
        subprocess.run(["node", str(vizjs_renderer), str(dot_path), str(svg_path), str(graph_png_path), str(width)], check=True)
        return "graphviz_dot_vizjs_wasm"
    raise RuntimeError(
        "No Graphviz renderer found. Install system 'dot' or pass --vizjs-renderer path/to/render-dot.mjs."
    )


def _draw_shape(ax: Any, kind: str, x: float, y: float, size: float = 0.045, linestyle: str = "solid") -> None:
    style = NODE_STYLES.get(kind, NODE_STYLES["observed"])
    edge = "#666666"
    fill = style["fill"]
    if kind in {"chance", "latent"}:
        patch = Circle((x, y), size * 0.55, fc=fill, ec=edge, lw=1.2, ls=linestyle)
    elif kind in {"observed", "decision"}:
        patch = Rectangle((x - size * 0.42, y - size * 0.42), size * 0.84, size * 0.84, fc=fill, ec=edge, lw=1.1, ls=linestyle)
    elif kind == "roi_pattern":
        patch = FancyBboxPatch(
            (x - size * 0.56, y - size * 0.35),
            size * 1.12,
            size * 0.70,
            boxstyle="round,pad=0.01,rounding_size=0.015",
            fc=fill,
            ec=edge,
            lw=1.1,
            ls=linestyle,
        )
    elif kind == "generated":
        patch = Polygon(
            [
                (x - size * 0.52, y - size * 0.40),
                (x + size * 0.35, y - size * 0.40),
                (x + size * 0.52, y + size * 0.40),
                (x - size * 0.35, y + size * 0.40),
            ],
            closed=True,
            fc=fill,
            ec=edge,
            lw=1.1,
            ls=linestyle,
        )
    else:
        patch = Polygon(
            [(x, y + size * 0.55), (x + size * 0.55, y), (x, y - size * 0.55), (x - size * 0.55, y)],
            closed=True,
            fc=fill,
            ec=edge,
            lw=1.1,
            ls=linestyle,
        )
    ax.add_patch(patch)


def _draw_arrow_sample(ax: Any, x0: float, x1: float, y: float, style: str, color: str, label: str) -> None:
    arrow = FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>", mutation_scale=10, lw=1.1, linestyle=style, color=color)
    ax.add_patch(arrow)
    ax.text(x1 + 0.025, y, label, ha="left", va="center", fontsize=7.5, color="#374151")


def _draw_legend(ax: Any, spec: dict[str, Any], mode: str) -> None:
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(Rectangle((0.04, 0.04), 0.92, 0.92, fc="white", ec="#8A8A8A", lw=1.0))

    y = 0.91
    if mode == "math":
        ax.text(0.09, y, "Variable symbols", ha="left", va="top", fontsize=8.2, weight="bold", color="#6B7280")
        y -= 0.055
        nodes = spec.get("nodes", [])
        max_rows = int(spec.get("legend_max_symbols", 9))
        row_gap = min(0.055, 0.42 / max(len(nodes[:max_rows]), 1))
        symbol_x = 0.16
        label_x = 0.26
        for node in nodes[:max_rows]:
            ax.text(
                symbol_x,
                y,
                _symbol_to_mathtext(node.get("symbol", node["id"])),
                ha="center",
                va="center",
                fontsize=10.5,
                color="#111827",
            )
            ax.text(label_x, y, str(node.get("label", node["id"])), ha="left", va="center", fontsize=7.2, color="#374151")
            y -= row_gap
        if len(nodes) > max_rows:
            ax.text(label_x, y, f"+ {len(nodes) - max_rows} more in caption/spec", ha="left", va="center", fontsize=6.8, color="#6B7280")
            y -= row_gap
        sep_y = max(y - 0.01, 0.52)
    else:
        sep_y = 0.90

    ax.add_line(Line2D([0.09, 0.90], [sep_y, sep_y], lw=0.8, color="#E5E7EB"))
    ax.text(0.09, sep_y - 0.035, "Graph encoding", ha="left", va="top", fontsize=8.2, weight="bold", color="#6B7280")

    used_kinds: list[str] = []
    for node in spec.get("nodes", []):
        kind = str(node.get("kind", "observed"))
        if kind not in NODE_STYLES:
            kind = "observed"
        if kind not in used_kinds:
            used_kinds.append(kind)
    shape_items = [(kind, NODE_STYLES[kind]["legend"]) for kind in used_kinds]
    if not shape_items:
        shape_items = [("chance", NODE_STYLES["chance"]["legend"])]
    x_positions = [0.14, 0.52]
    y0 = sep_y - 0.095
    for i, (kind, label) in enumerate(shape_items):
        col = i % 2
        row = i // 2
        x = x_positions[col]
        y_item = y0 - row * 0.085
        _draw_shape(ax, kind, x, y_item, size=0.060)
        ax.text(x + 0.075, y_item, label, ha="left", va="center", fontsize=7.0, color="#374151")

    used_edge_kinds: list[str] = []
    for edge in spec.get("edges", []):
        kind = str(edge.get("kind", "structural"))
        if kind == "causal":
            kind = "structural"
        if kind == "scoring":
            kind = "observation"
        if kind not in EDGE_STYLES:
            kind = "structural"
        if kind not in used_edge_kinds:
            used_edge_kinds.append(kind)
    if not used_edge_kinds:
        used_edge_kinds = ["structural"]
    y_edge = max(0.18, y0 - math.ceil(len(shape_items) / 2) * 0.085 - 0.025)
    edge_positions = [(0.12, y_edge), (0.12, y_edge - 0.060), (0.52, y_edge), (0.52, y_edge - 0.060)]
    for (kind, (x0, y_sample)) in zip(used_edge_kinds, edge_positions):
        style = EDGE_STYLES[kind]
        _draw_arrow_sample(ax, x0, x0 + 0.10, y_sample, style["style"], style["color"], style["legend"])
        if kind == "absent":
            ax.text(x0 + 0.10, y_sample - 0.058, "not an estimated\nno-effect result", ha="left", va="center", fontsize=6.1, color="#6B7280")


def compose_figure(graph_png_path: Path, output_png: Path, output_pdf: Path, spec: dict[str, Any], mode: str, dpi: int) -> None:
    img = mpimg.imread(graph_png_path)
    fig = plt.figure(figsize=(13.8, 6.2), dpi=dpi)
    legend_ax = fig.add_axes([0.015, 0.06, 0.255, 0.88])
    graph_ax = fig.add_axes([0.285, 0.05, 0.70, 0.90])
    _draw_legend(legend_ax, spec, mode)
    graph_ax.imshow(img)
    graph_ax.set_axis_off()
    title = spec.get("title")
    if title and not spec.get("suppress_title", True):
        fig.suptitle(str(title), x=0.50, y=0.985, fontsize=13, weight="bold")
    fig.savefig(output_png, dpi=dpi, bbox_inches="tight", pad_inches=0.04)
    fig.savefig(output_pdf, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


def default_caption(spec: dict[str, Any], mode: str) -> str:
    mode_label = "Mathematical-letter SCM" if mode == "math" else "Expanded-node SCM"
    title = spec.get("title", "structural causal model")
    return (
        f"{mode_label} for {title}. Solid arrows are structural data-generating links, "
        "dotted arrows are observation/scoring links, and dashed arrows mark absent/null "
        "structural paths rather than estimated no-effect results. This is a data-generating "
        "schematic; it is not fitted causal discovery, model performance evidence, or "
        "biological localization."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Graphviz/Matplotlib SCM figures from JSON specs.")
    parser.add_argument("--spec", required=True, type=Path, help="Input JSON SCM spec.")
    parser.add_argument("--out", required=True, type=Path, help="Final output PNG path.")
    parser.add_argument("--mode", choices=["math", "expanded"], default="math", help="Figure mode.")
    parser.add_argument("--vizjs-renderer", type=Path, default=None, help="Optional tools/graphviz-renderer/render-dot.mjs path.")
    parser.add_argument("--graph-width", type=int, default=2600, help="Graph-only PNG width for Viz.js renderer.")
    parser.add_argument("--dpi", type=int, default=220, help="Final Matplotlib composition DPI.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec_path = args.spec.resolve()
    out_png = args.out.resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    spec = json.loads(spec_path.read_text())
    if "nodes" not in spec or "edges" not in spec:
        raise ValueError("Spec must contain 'nodes' and 'edges'.")

    stem = out_png.stem
    sidecar_dir = out_png.parent / f"{stem}_sidecars"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    dot_path = sidecar_dir / f"{stem}.dot"
    svg_path = sidecar_dir / f"{stem}.svg"
    graph_png = sidecar_dir / f"{stem}.graph_only.png"
    out_pdf = out_png.with_suffix(".pdf")
    caption_path = out_png.with_suffix(".caption.txt")

    dot = build_dot(spec, args.mode)
    dot_path.write_text(dot)

    vizjs_renderer = args.vizjs_renderer
    if vizjs_renderer is None:
        vizjs_renderer = _find_vizjs_renderer([Path.cwd(), spec_path.parent, out_png.parent])
    renderer_name = render_graph(dot_path, svg_path, graph_png, args.graph_width, vizjs_renderer)
    compose_figure(graph_png, out_png, out_pdf, spec, args.mode, args.dpi)
    caption_path.write_text(str(spec.get("caption") or default_caption(spec, args.mode)) + "\n")

    manifest = {
        "renderer": renderer_name,
        "mode": args.mode,
        "dot": str(dot_path),
        "svg": str(svg_path),
        "graph_only_png": str(graph_png),
        "png": str(out_png),
        "pdf": str(out_pdf),
        "caption": str(caption_path),
    }
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"render_scm_figure.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
