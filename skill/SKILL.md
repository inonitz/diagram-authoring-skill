---
name: diagram-authoring
description: Author slide-grade architecture and flow diagrams — clean orthogonal lines, every label centered on its line, tool-proof outlined SVG plus a PNG, and Canva-safe colors. Graphviz lays it out; cairo draws it. Use when creating any architecture diagram, system figure, flowchart, data-flow, or slide graphic from a codebase or a spec.
---

# Diagram Authoring

Goal: a diagram a reviewer reads at a glance. It must be accurate, use clean straight lines, place every label on its line, and import into slide tools without breaking.

The engine: **graphviz computes the layout; cairo draws it.** Graphviz alone forces a bad trade — orthogonal lines OR centered labels, never both. The bundled renderer `gvcairo.py` takes graphviz's geometry and draws every label, title, and annotation itself. It also draws clusters, bold titles, dim annotation lines, reversed arrows, and re-centers each route in its free channel.

## Environment on this machine
- Available: `dot` (graphviz), `python3` with `pycairo`, `python-bidi`, `PIL`. Font DejaVu Sans has Hebrew.
- NOT available: inkscape, rsvg-convert, cairosvg, chromium, mermaid CLI, drawio CLI.
- You cannot rasterize an SVG here. Cairo is the only path to a PNG.
- Use `rtk` for every read and search: `rtk read`, `rtk grep`, `rtk ls`, `rtk find`.

## The pipeline — run every step
1. Ground truth first. Read the real source: the code, the config, the `.dot` you fix. Never invent a port, endpoint, or flow. A pretty wrong diagram is worse than none. Plan the read: map file references first, then read each file at most once.
2. Write a graphviz `.dot`. Use `rankdir=TB`, `splines=ortho`, `compound=true`. Nodes: `shape=box, style="rounded,filled"`. Give the hero node one accent color. Give the rest semantic fills: inputs blue, LLM purple, backend green, safety red, output amber. Put edge text in `label=`; the renderer places it, not graphviz. Group related nodes into `subgraph cluster_*` blocks with a short cluster `label`.
3. Render: `python3 gvcairo.py <file.dot> <out-basename>`. It reads `dot -Tjson`, draws in cairo, outlines all text to paths, writes `<out>.svg` and `<out>.png` at 2x, and writes `<out>.routes.json` for the verifier. The SVG has zero `<text>`, so no font can move a label.
4. Verify with numbers, not eyes: `python3 check.py <file.dot> <out>.png`. It reports every edge-to-node margin under 0.4 in, text that overflows its box, stacked parallel lines, label-chip collisions, the aspect ratio, and PNG ink coverage. Fix a tight margin by MOVING a node, not by adding space; ortho routes rarely shift on their own.
5. Make it Canva-safe: `python3 clean_svg.py <out>.svg`. It converts cairo's `rgb(N%, …)` colors to hex and rounds coordinates. Percentage `rgb()` breaks Canva.
6. For a DENSE diagram whose clusters overlap, pin the layout: `python3 pin.py <src.dot> <pinned.dot> <gap>`. It lays the graph out flat (dot honors flat ordering without clusters), then pins every node with `neato -n` and spaces the clusters by `gap` points. Then render the pinned `.dot`.

## Box text — concise and cohesive (owner-ruled)
- Each box is a role, not a paragraph. A clear title line, then only crisp detail.
- If a box carries several facts, make them a LIST — one `•` item per line — never a run-on sentence.
- At most 3 to 4 short lines per box. More than that means it is two boxes, or the extra is filler.
- Title a box by its ROLE, not by its source file. A reviewer does not care about `router.py`. A filename may appear as ONE dim annotation line, prefixed with `~`; the renderer draws `~` lines smaller and gray.
- "Detailed" means more boxes and more real facts, not fuller boxes. It must still read at a glance.

## Rules that separate good from bad
- Measure, do not guess. You render blind. `check.py` and PIL are your eyes. State every margin as a number.
- Match the font size to graphviz. The renderer draws each label at that node's own `fontsize`; set it in the `.dot`, do not fight it.
- Fix the aspect ratio for slides. A 5-to-1 banner is unreadable. Fold peers with `{ rank=same; a; b; }` to reach about 1.3-to-1.4-to-1.
- Give boxes room. Raise node `margin` (for example `0.24,0.15`), `ranksep`, and `nodesep`.
- A data direction is a fact, not a guess. Trace the real path. A drone talks to its remote, not to the server.
- Hebrew or any right-to-left text: pass each line through `python-bidi`'s `get_display` before drawing. Right-align each line. Wrap a long line by word.
- Copy names verbatim from the source or the owner. Never "correct" a spelling; it may already be in a slide.
- Iterate with the human. Render, measure, show, fix the one thing named. One correction at a time.

## Bundled tools
- `gvcairo.py` — graphviz layout to a cairo outlined render: clusters, bold titles, dim `~` annotations, reversed arrows, chip labels centered on lines, channel-centered routes. Run: `python3 gvcairo.py in.dot out-basename`.
- `check.py` — margins, text overflow, stacked lines, chip collisions, aspect, ink. Run: `python3 check.py in.dot out.png`.
- `clean_svg.py` — `rgb(%)` to hex plus coordinate rounding for Canva. Run: `python3 clean_svg.py file.svg`.
- `pin.py` — optional layout pinner for dense, cluster-heavy diagrams. Run: `python3 pin.py src.dot pinned.dot gap`.

## The verification target
The diagram is accurate. Lines are clean and orthogonal. Every label sits on its own line. No edge touches a non-endpoint node; every measured margin is at least 0.4 in. The SVG is outlined, zero `<text>`. Colors are hex, so Canva accepts it. The aspect ratio fits a slide. Boxes are concise. After all that, a human judges the look.
