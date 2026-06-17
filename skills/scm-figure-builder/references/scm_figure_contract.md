# SCM Figure Contract

Use this contract for publication-quality structural causal model figures.

## Modes

### Mathematical SCM

Purpose: graphical-model style panel.

- Node labels are mathematical symbols only.
- The left legend maps symbols to variable names.
- Symbol text in the legend is centered in the symbol column.
- Do not add a generic `Legend` title. Use section headings such as `Variable symbols` and `Graph encoding`.
- Use mathtext formatting in the legend: `S_U` should render as `S` with subscript `U`.

### Expanded Node Names

Purpose: readable audit/report panel.

- Node labels use compact semantic names.
- Keep text short enough to fit inside nodes.
- Include a graph-encoding legend.
- Use this mode next to the mathematical SCM when the report needs both readability and formal notation.

## Node Semantics

Use stable node kinds:

- `chance`: circular node for ordinary random variables in standard SCM/DAG examples.
- `latent`: circular node for latent or oracle-only chance variables.
- `observed`: square node for measured, assigned, or observed variables.
- `roi_pattern`: rounded rectangle for simulator-defined ROI-time effect, nuisance, shortcut, or cue patterns.
- `generated`: parallelogram for generated BOLD/token data.
- `endpoint`: diamond for scored endpoints or objective/evaluation targets.
- `decision`: square decision node only when the graph is a causal influence diagram with an actual decision/action.

Prefer names such as `diagnosis ROI-time pattern`, `cue ROI-time pattern`, or `U nuisance ROI-time pattern`. Avoid the bare term `support` unless the caption explicitly defines it as selected ROI-time cells or a planted ROI-time pattern.

## Edge Semantics

Use stable edge kinds:

- `structural`: solid arrow for data-generating causal/structural links.
- `observation`: dotted arrow for observation, scoring, or model-readout links.
- `absent`: dashed arrow for an absent/null structural path included to clarify the SCM.

Do not label dashed arrows as `no effect` unless the caption explicitly says it is a design-time null path, not an estimated no-effect result.

## Layout

Delegate placement to Graphviz/DOT.

Use rank hints only to express hierarchy, not to hand-draw every edge:

```json
{"id": "U", "rank": 0}
{"id": "D", "rank": 1}
{"id": "S_D", "rank": 2}
{"id": "X", "rank": 3}
{"id": "M", "rank": 4}
```

If edges overlap labels, adjust `rank`, `rankdir`, `nodesep`, or `ranksep` in the spec and rerun. Do not manually move arrows in an image editor.

## Required Claim Boundary

Every caption for a simulator SCM must include this idea:

`This is a data-generating schematic; it is not fitted causal discovery, model performance evidence, or biological localization.`

For absent/dashed paths, include:

`Dashed arrows mark absent/null structural paths, not estimated no-effect results.`
