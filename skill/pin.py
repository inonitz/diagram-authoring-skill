"""Pin a dense, cluster-heavy diagram to a fixed layout so its cluster boxes do not overlap.

Graphviz's `dot` respects flat top-to-bottom node ordering, but only when there are no clusters; with
clusters it reshuffles. So this runs two passes:
  1. Strip the cluster wrappers and run `dot` to get clean node positions.
  2. Write those positions back into the ORIGINAL clustered file as fixed pins (pos="x,y!"), switch
     the engine to neato (which keeps pins under -n), and push each cluster's nodes down by `gap`
     points so the cluster boxes pull apart.
Then render the pinned file with gvcairo.py.

Usage: python3 pin.py <source.dot> <pinned.dot> <gap-points> ['{"node": dx, ...}']
       The optional 4th argument nudges named nodes horizontally by dx points.
"""
import subprocess, re, sys

POINTS_PER_INCH = 72


def flat_layout(source_text):
    """Lay the graph out with clusters removed so dot keeps the flat ordering.
    Returns node center positions and widths, both in points."""
    without_clusters = "\n".join(
        line for line in source_text.splitlines()
        if not (line.strip().startswith("subgraph cluster")
                or line.startswith("    label=")
                or line == "  }"))
    plain = subprocess.run(["dot", "-Tplain", "/dev/stdin"], input=without_clusters,
                           capture_output=True, text=True).stdout
    positions, widths = {}, {}
    for line in plain.splitlines():
        tokens = line.split()
        if tokens and tokens[0] == "node":
            name = tokens[1]
            positions[name] = (float(tokens[2]) * POINTS_PER_INCH, float(tokens[3]) * POINTS_PER_INCH)
            widths[name] = float(tokens[4]) * POINTS_PER_INCH
    return positions, widths


def apply_harden2_nudge(positions, widths):
    """Diagram-specific tweak for the harden2 diagram: center the remote controller under the
    virtual-stick/control channel and place the aircraft to its left. Auto-skips on any other graph."""
    if {"vtx", "ctl", "rc", "ac"} <= set(positions) and {"rc", "ac"} <= set(widths):
        channel_x = (positions["vtx"][0] + positions["ctl"][0]) / 2
        positions["rc"] = (channel_x, positions["rc"][1])
        positions["ac"] = (channel_x - (widths["rc"] + widths["ac"]) / 2 - 0.9 * POINTS_PER_INCH,
                           positions["ac"][1])


def apply_manual_nudges(positions, nudges):
    """nudges is {node_name: horizontal_shift_in_points}."""
    for name, dx in nudges.items():
        positions[name] = (positions[name][0] + dx, positions[name][1])


def separate_clusters_vertically(source_text, positions, gap_points):
    """Push each cluster's nodes down by gap * (cluster index in file order) so the boxes separate."""
    cluster_order, current_cluster = [], None
    for line in source_text.splitlines():
        cluster_match = re.match(r'\s*subgraph (cluster_\w+)', line)
        if cluster_match:
            current_cluster = cluster_match.group(1)
            cluster_order.append(current_cluster)
            continue
        node_match = re.match(r'\s+(\w+)\s+\[fillcolor', line)
        if node_match and current_cluster and node_match.group(1) in positions:
            name = node_match.group(1)
            x, y = positions[name]
            positions[name] = (x, y - gap_points * cluster_order.index(current_cluster))


def write_pinned_dot(source_text, positions, out_path):
    pinned = source_text.replace(
        "graph [rankdir=TB, splines=ortho, compound=true,",
        "graph [layout=neato, inputscale=72, splines=ortho, compound=true,")
    for name, (x, y) in positions.items():
        pinned = re.sub(r'(\n\s+%s\s+\[)' % re.escape(name),
                        r'\1pos="%.1f,%.1f!", ' % (x, y), pinned, count=1)
    with open(out_path, "w") as f:
        f.write(pinned)


if __name__ == "__main__":
    source_path, out_path, gap = sys.argv[1], sys.argv[2], float(sys.argv[3])
    nudges = eval(sys.argv[4]) if len(sys.argv) > 4 else {}
    source_text = open(source_path).read()

    positions, widths = flat_layout(source_text)
    apply_harden2_nudge(positions, widths)
    apply_manual_nudges(positions, nudges)
    separate_clusters_vertically(source_text, positions, gap)
    write_pinned_dot(source_text, positions, out_path)
    print(f"pinned {len(positions)} nodes; gap {gap}")
