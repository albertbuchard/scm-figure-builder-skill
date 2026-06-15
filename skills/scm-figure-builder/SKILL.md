---
name: scm-figure-builder
description: Build publication-quality structural causal model (SCM), causal DAG, and causal graphical-model figures. Use when Codex needs to create or revise mathematical-letter SCM figures, expanded-node-name SCM figures, graph legends, DOT/Graphviz causal diagrams, or report-ready SCM panels with clear node/edge semantics and captions.
---

# SCM Figure Builder

Use this skill to render structural causal model figures without hand-routing arrows.

The standard approach is:

1. Express the graph as a JSON SCM spec.
2. Use Graphviz/DOT for automatic node placement and edge routing.
3. Use Matplotlib for the publication legend and mathtext symbol table.
4. Export DOT, SVG, graph-only PNG, final PNG, final PDF, and a caption sidecar.

## Choose The Figure Mode

- **Mathematical SCM**: use when the figure should look like a graphical model. Nodes contain only symbols such as `U`, `D`, `S_D`, `X`, `M`; the left legend expands each symbol into a variable or ROI-time pattern name. This is the preferred mode for thesis/manuscript SCM panels.
- **Expanded node names**: use when the reader needs the graph to be self-explanatory in the node titles. Nodes contain short semantic labels such as `diagnosis label` or `generated BOLD/tokens`; the legend explains only graph encoding.

Never use a hand-positioned drawing when the task is an SCM/DAG figure unless the user explicitly requests manual layout. Graphviz rank constraints are allowed, but edge placement must remain graph-library driven.

## Render Command

Use the bundled renderer when starting from a JSON spec:

```bash
python3 ~/.codex/skills/scm-figure-builder/scripts/render_scm_figure.py \
  --spec path/to/scm_spec.json \
  --out path/to/output.png \
  --mode math
```

Use `--mode expanded` for expanded-node-name figures.

If system Graphviz `dot` is unavailable but a project has a Viz.js renderer like `tools/graphviz-renderer/render-dot.mjs`, pass it explicitly:

```bash
python3 ~/.codex/skills/scm-figure-builder/scripts/render_scm_figure.py \
  --spec path/to/scm_spec.json \
  --out path/to/output.png \
  --mode math \
  --vizjs-renderer tools/graphviz-renderer/render-dot.mjs
```

## Spec Contract

Read `references/scm_figure_contract.md` before creating a new spec or changing node/edge semantics.

Minimum spec:

```json
{
  "title": "Measured confounding, null diagnosis effect",
  "nodes": [
    {"id": "U", "symbol": "U", "label": "latent subject state", "kind": "latent"},
    {"id": "D", "symbol": "D", "label": "diagnosis label", "kind": "observed"},
    {"id": "S_U", "symbol": "S_U", "label": "U nuisance ROI-time pattern", "kind": "roi_pattern", "style": "dashed"},
    {"id": "X", "symbol": "X", "label": "generated BOLD/tokens", "kind": "generated"},
    {"id": "M", "symbol": "M", "label": "scoring endpoint", "kind": "endpoint"}
  ],
  "edges": [
    {"source": "U", "target": "D", "kind": "structural"},
    {"source": "U", "target": "S_U", "kind": "structural"},
    {"source": "S_U", "target": "X", "kind": "structural"},
    {"source": "X", "target": "M", "kind": "observation"}
  ]
}
```

## Caption Rules

Captions must state:

- what structural mechanism the graph represents;
- that solid arrows are data-generating structural links;
- that dotted arrows are observation/scoring links;
- that dashed arrows are absent/null structural paths, not estimated no-effect results;
- that the panel is a data-generating schematic, not fitted causal discovery, performance evidence, or biological localization.

## Quality Gate

Before calling the figure done:

1. Open the generated PNG visually.
2. Confirm node symbols render as math-like letters and subscripts in math mode.
3. Confirm variable symbols are centered in the legend symbol column.
4. Confirm the legend does not duplicate shape meanings or use vague terms such as `support` without naming it as an ROI-time pattern.
5. Confirm arrows do not run through node labels; if they do, adjust rank/group hints in the JSON spec and rerun Graphviz.
6. Keep previous report figures as backups when replacing existing figures.
