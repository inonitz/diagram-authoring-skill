"""Measure a rendered diagram and report what a viewer would notice.

Geometry comes from <basename>.routes.json when gvcairo.py wrote it (the actual rendered routes,
preferred), otherwise from `dot -Tplain` (the raw graphviz layout). Everything is reported in inches
and counts:
  - edge routes passing closer than 0.4 in to a box they do not connect to
  - parallel edge segments stacked almost on top of each other
  - edge-label chips overlapping a box or another chip
  - node text wider than its box
  - the bounding-box aspect ratio
  - PNG ink coverage, and whether ink reaches the right or bottom margin

Usage: python3 check.py <input.dot> [<rendered.png>]
"""
import subprocess, sys, math, re, os, json, cairo

TIGHT_MARGIN_IN = 0.4
FONT = "DejaVu Sans"
EDGE_LABEL_FONT_SIZE = 9
LINE_SPACING = 1.18
POINTS_PER_INCH = 72


def segment_to_box_distance(box_center, seg_start, seg_end, samples=41):
    """Smallest distance from a segment to an axis-aligned box, 0 if the segment enters it.
    box_center is (center_x, center_y, width, height)."""
    cx, cy, width, height = box_center
    left, top, right, bottom = cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2
    closest = 1e9
    for i in range(samples):
        t = i / (samples - 1)
        px = seg_start[0] + t * (seg_end[0] - seg_start[0])
        py = seg_start[1] + t * (seg_end[1] - seg_start[1])
        outside_x = max(left - px, 0, px - right)
        outside_y = max(top - py, 0, py - bottom)
        closest = min(closest, math.hypot(outside_x, outside_y))
    return closest


def load_plain_geometry(dot_path):
    """Node boxes and edge routes from `dot -Tplain`, in inches."""
    lines = subprocess.run(["dot", "-Tplain", dot_path], capture_output=True, text=True).stdout.splitlines()
    nodes, edges = {}, []
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        if tokens[0] == "node":
            nodes[tokens[1]] = (float(tokens[2]), float(tokens[3]), float(tokens[4]), float(tokens[5]))
        elif tokens[0] == "edge":
            point_count = int(tokens[3])
            points = [(float(tokens[4 + 2 * i]), float(tokens[5 + 2 * i])) for i in range(point_count)]
            if "invis" in tokens[-2]:
                continue
            edges.append((tokens[1], tokens[2], points))
    return nodes, edges


def load_rendered_geometry(routes_json_path):
    """Node boxes and edge routes from gvcairo's routes.json, converted from points to inches."""
    data = json.load(open(routes_json_path))
    nodes = {name: (n["x"] / POINTS_PER_INCH, n["y"] / POINTS_PER_INCH,
                    n["w"] / POINTS_PER_INCH, n["h"] / POINTS_PER_INCH)
             for name, n in data["nodes"].items()}
    edges = [(e["tl"], e["hd"], [(x / POINTS_PER_INCH, y / POINTS_PER_INCH) for x, y in e["pts"]])
             for e in data["edges"]]
    return nodes, edges


def find_tight_margins(nodes, edges):
    """Edge routes that pass closer than TIGHT_MARGIN_IN to a box they do not connect to."""
    tight = []
    for tail, head, points in edges:
        for name, box in nodes.items():
            if name in (tail, head) or name.startswith("_"):
                continue
            margin = min(segment_to_box_distance(box, points[i], points[i + 1])
                         for i in range(len(points) - 1))
            if margin < TIGHT_MARGIN_IN:
                tight.append((round(margin, 2), tail, head, name))
    tight.sort()
    return tight


def find_stacked_segments(edges):
    """Parallel segments of different edges that sit within 0.08 in of each other and overlap."""
    segments = []
    for tail, head, points in edges:
        name = f"{tail}->{head}"
        for i in range(len(points) - 1):
            a, b = points[i], points[i + 1]
            is_vertical = abs(a[0] - b[0]) < 0.01
            fixed_coord = a[0] if is_vertical else a[1]
            along_a = a[1] if is_vertical else a[0]
            along_b = b[1] if is_vertical else b[0]
            segments.append((name, is_vertical, fixed_coord, min(along_a, along_b), max(along_a, along_b)))

    stacked = []
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            name_a, vertical_a, coord_a, lo_a, hi_a = segments[i]
            name_b, vertical_b, coord_b, lo_b, hi_b = segments[j]
            same_orientation = vertical_a == vertical_b
            nearly_same_line = abs(coord_a - coord_b) < 0.08
            overlaps = min(hi_a, hi_b) - max(lo_a, lo_b) > 0.3
            if same_orientation and nearly_same_line and overlaps and name_a != name_b:
                stacked.append((name_a, name_b, round(abs(coord_a - coord_b), 2)))
    return stacked


def find_chip_collisions(routes_json_path, nodes_in_inches):
    """Approximate each edge label as a chip on the midpoint of its longest segment, then flag any
    chip that overlaps a box or another chip."""
    data = json.load(open(routes_json_path))
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(EDGE_LABEL_FONT_SIZE)

    chips = []
    for edge in data["edges"]:
        if not edge["label"]:
            continue
        points = edge["pts"]
        a, b = max(((points[i], points[i + 1]) for i in range(len(points) - 1)),
                   key=lambda seg: (seg[0][0] - seg[1][0]) ** 2 + (seg[0][1] - seg[1][1]) ** 2)
        mid_x, mid_y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        half_width = ctx.text_extents(edge["label"])[2] / 2
        half_height = EDGE_LABEL_FONT_SIZE * LINE_SPACING / 2
        name = edge["tl"] + "->" + edge["hd"]
        chips.append((name,
                      (mid_x - half_width - 3) / POINTS_PER_INCH, (mid_y - half_height - 1) / POINTS_PER_INCH,
                      (mid_x + half_width + 3) / POINTS_PER_INCH, (mid_y + half_height + 1) / POINTS_PER_INCH))

    collisions = []
    for name, x1, y1, x2, y2 in chips:
        for node_name, (cx, cy, w, h) in nodes_in_inches.items():
            box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if not (x2 < box[0] or x1 > box[2] or y2 < box[1] or y1 > box[3]):
                collisions.append(("chip-vs-box", name, node_name))
        for other_name, ox1, oy1, ox2, oy2 in chips:
            if other_name > name and not (x2 < ox1 or x1 > ox2 or y2 < oy1 or y1 > oy2):
                collisions.append(("chip-vs-chip", name, other_name))
    return collisions


def find_text_overflow(dot_path):
    """Node label lines whose rendered width exceeds the box width. Returns (overflow, document)."""
    document = json.loads(subprocess.run(["dot", "-Tjson", dot_path], capture_output=True, text=True).stdout)
    ctx = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10))
    overflowing = []
    for obj in document["objects"]:
        if "pos" not in obj:
            continue
        box_width = float(obj["width"]) * POINTS_PER_INCH
        base_size = float(obj.get("fontsize", 14))
        lines = [line for line in re.split(r'\\[lnr]|\n', obj.get("label", "")) if line]
        for i, line in enumerate(lines):
            size = base_size * 0.82 if line.startswith("~") else base_size
            text = line.lstrip("~").strip()
            ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL,
                                 cairo.FONT_WEIGHT_BOLD if i == 0 else cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(size)
            text_width = ctx.text_extents(text)[2]
            if text_width > box_width - 8:
                overflowing.append((obj["name"], text, round(text_width), round(box_width)))
    return overflowing, document


def bounding_box_inches(document):
    _, _, urx, ury = (float(v) for v in document["bb"].split(","))
    width_in, height_in = urx / POINTS_PER_INCH, ury / POINTS_PER_INCH
    return width_in, height_in, width_in / height_in


def ink_report(png_path):
    from PIL import Image
    import numpy as np
    gray = np.array(Image.open(png_path).convert("L"))
    has_ink = gray < 250
    return (gray.shape[1], gray.shape[0], 100 * has_ink.mean(),
            bool(has_ink[:, -20:].any()), bool(has_ink[-20:, :].any()))


if __name__ == "__main__":
    dot_path = sys.argv[1]
    png_path = sys.argv[2] if len(sys.argv) > 2 else None
    routes_path = (png_path or dot_path).rsplit(".", 1)[0] + ".routes.json"

    nodes, edges = load_plain_geometry(dot_path)
    if os.path.exists(routes_path):
        nodes, edges = load_rendered_geometry(routes_path)
        print("(margins measured from the rendered routes)")

    stacked = find_stacked_segments(edges)
    print("stacked parallel segments:", len(stacked))
    for pair in stacked[:10]:
        print("  ", pair)

    if os.path.exists(routes_path):
        collisions = find_chip_collisions(routes_path, nodes)
        print("label chip collisions:", len(collisions))
        for collision in collisions:
            print("  ", collision)

    tight = find_tight_margins(nodes, edges)
    print(f"margins<{TIGHT_MARGIN_IN}in:", len(tight))
    for margin, tail, head, near in tight[:40]:
        print(f"  {margin:.2f}  {tail}->{head}  near {near}")

    overflowing, document = find_text_overflow(dot_path)
    print("text overflow:", len(overflowing))
    for item in overflowing:
        print("  ", item)

    width_in, height_in, aspect = bounding_box_inches(document)
    print(f"bb in: {width_in:.1f} x {height_in:.1f}  aspect {aspect:.2f}")

    if png_path:
        pixels_w, pixels_h, coverage, right_ink, bottom_ink = ink_report(png_path)
        print(f"png {pixels_w}x{pixels_h} ink {coverage:.1f}%  "
              f"right-margin ink {right_ink}  bottom-band ink {bottom_ink}")
