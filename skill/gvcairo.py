"""Render a Graphviz .dot file as a slide-grade diagram.

Graphviz decides the layout (node positions and edge geometry); this script draws it with cairo so
that every edge label sits on the middle of its line, all text is outlined to paths (no live <text>,
so no viewer font can shift a label), and the colors are hex (which slide tools accept).

Usage:   python3 gvcairo.py <input.dot> <output-basename>
Writes:  <output-basename>.svg
         <output-basename>.png   (rendered at 2x)
         <output-basename>.routes.json   (the final edge routes, for check.py to measure)
"""
import cairo, math, subprocess, json, sys, re, os
from dataclasses import dataclass

# All distances below are in PostScript points, the unit graphviz reports.
PAGE_MARGIN = 24            # blank border around the whole drawing
TITLE_BAND = 44             # height reserved at the top for the graph title, above the content
MIN_ROUTE_MARGIN = 0.4 * 72 # keep an edge at least this far from any box it does not connect to
FONT = os.environ.get("DIAGRAM_FONT", "DejaVu Sans")  # any installed font; DejaVu is a broad-coverage default
LINE_SPACING = 1.18         # gap between text lines, as a multiple of the font size
ANNOTATION_SCALE = 0.82     # '~' annotation lines are drawn this much smaller than the title
TITLE_FONT_SIZE = 20
CLUSTER_LABEL_FONT_SIZE = 13
EDGE_LABEL_FONT_SIZE = 9


def parse_color(value):
    """A graphviz color string to an (r, g, b) triple in 0..1. Accepts '#rrggbb' or a few names."""
    named = {"white": (1, 1, 1), "black": (0, 0, 0), "none": (1, 1, 1)}
    if not value:
        return (0, 0, 0)
    if value.startswith("#"):
        digits = value[1:]
        return tuple(int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return named.get(value, (0, 0, 0))


ANNOTATION_COLOR = (0.42, 0.45, 0.50)
TITLE_COLOR = parse_color("#0f172a")
CLUSTER_LABEL_COLOR = parse_color("#475569")
DEFAULT_EDGE_COLOR = "#64748b"


@dataclass
class Node:
    name: str
    center_x: float
    center_y: float
    width: float
    height: float
    label: str
    fill: tuple
    border: tuple
    text_color: tuple
    shape: str
    pen_width: float
    font_size: float
    invisible: bool


@dataclass
class Cluster:
    label: str
    left: float
    bottom: float
    right: float
    top: float
    fill: tuple
    border: tuple


@dataclass
class Edge:
    tail: str
    head: str
    points: list          # polyline in graphviz coordinates (y points up)
    label: str
    color: tuple
    dashed: bool
    pen_width: float
    direction: str        # "", "forward", "back", or "both"
    label_color: tuple
    invisible: bool


@dataclass
class Graph:
    width: float
    height: float
    title: str
    nodes: dict           # name -> Node
    clusters: list
    edges: list


# ---------------------------------------------------------------------------- load the layout

def _graphviz_json(dot_path):
    result = subprocess.run(["dot", "-Tjson", dot_path], capture_output=True, text=True)
    return json.loads(result.stdout)


def _parse_edge_points(pos):
    """Turn a graphviz spline 'pos' string into an ordered polyline.
    'e,x,y' marks the arrow end, 's,x,y' the start; the rest are control points in between."""
    start = end = None
    middle = []
    for token in pos.split():
        if token.startswith("e,"):
            _, x, y = token.split(",")
            end = (float(x), float(y))
        elif token.startswith("s,"):
            _, x, y = token.split(",")
            start = (float(x), float(y))
        else:
            x, y = token.split(",")
            middle.append((float(x), float(y)))
    points = middle
    if end:
        points = points + [end]
    if start:
        points = [start] + points
    return points


def load_graph(dot_path):
    document = _graphviz_json(dot_path)
    width, height = (float(v) for v in document["bb"].split(",")[2:])
    name_of_id = {obj["_gvid"]: obj.get("name", "") for obj in document.get("objects", [])}

    nodes = {}
    clusters = []
    for obj in document.get("objects", []):
        name = obj.get("name", "")
        if "pos" in obj:
            center_x, center_y = (float(v) for v in obj["pos"].split(","))
            nodes[name] = Node(
                name=name,
                center_x=center_x,
                center_y=center_y,
                width=float(obj.get("width", 1)) * 72,
                height=float(obj.get("height", 0.5)) * 72,
                label=obj.get("label", name),
                fill=parse_color(obj.get("fillcolor", "#ffffff")),
                border=parse_color(obj.get("color", "#000000")),
                text_color=parse_color(obj.get("fontcolor", "#000000")),
                shape=obj.get("shape", "box"),
                pen_width=float(obj.get("penwidth", 1) or 1),
                font_size=float(obj.get("fontsize", 14) or 14),
                invisible="invis" in (obj.get("style", "") or ""),
            )
        elif name.startswith("cluster"):
            left, bottom, right, top = (float(v) for v in obj["bb"].split(","))
            clusters.append(Cluster(
                label=obj.get("label", ""),
                left=left, bottom=bottom, right=right, top=top,
                fill=parse_color(obj.get("bgcolor", "#f8fafc")),
                border=parse_color(obj.get("color", "#94a3b8")),
            ))

    edges = []
    for obj in document.get("edges", []):
        style = obj.get("style", "")
        edges.append(Edge(
            tail=name_of_id[obj["tail"]],
            head=name_of_id[obj["head"]],
            points=_parse_edge_points(obj.get("pos", "")),
            label=obj.get("label", ""),
            color=parse_color(obj.get("color", DEFAULT_EDGE_COLOR)),
            dashed=(style == "dashed"),
            pen_width=float(obj.get("penwidth", 1) or 1),
            direction=obj.get("dir", ""),
            label_color=parse_color(obj.get("fontcolor", "") or obj.get("color", DEFAULT_EDGE_COLOR)),
            invisible=(style == "invis"),
        ))

    return Graph(width=width, height=height, title=document.get("label", ""),
                 nodes=nodes, clusters=clusters, edges=edges)


# ---------------------------------------------------------------------------- tidy the edge routes

def _simplify_polyline(points):
    """Drop near-duplicate points, then drop any midpoint that lies on a straight run."""
    kept = []
    for point in points:
        if kept and abs(point[0] - kept[-1][0]) < 0.5 and abs(point[1] - kept[-1][1]) < 0.5:
            continue
        kept.append(point)
    i = 1
    while i < len(kept) - 1:
        before, here, after = kept[i - 1], kept[i], kept[i + 1]
        on_vertical_run = abs(before[0] - here[0]) < 0.5 and abs(here[0] - after[0]) < 0.5
        on_horizontal_run = abs(before[1] - here[1]) < 0.5 and abs(here[1] - after[1]) < 0.5
        if on_vertical_run or on_horizontal_run:
            kept.pop(i)
        else:
            i += 1
    return kept


def center_routes_in_channels(graph):
    """Orthogonal routing hugs the corners of boxes. For each straight segment of each edge, slide
    it sideways to the middle of the empty channel it passes through, keeping at least
    MIN_ROUTE_MARGIN from every box it does not connect to. This is what makes the lines look
    deliberate instead of glued to the boxes."""
    boxes = {
        node.name: (node.center_x - node.width / 2, node.center_y - node.height / 2,
                    node.center_x + node.width / 2, node.center_y + node.height / 2)
        for node in graph.nodes.values() if not node.invisible
    }
    fixed_segments = []   # (is_vertical, slide_coord, span_lo, span_hi) already placed

    for edge in graph.edges:
        if edge.invisible or len(edge.points) < 2:
            continue
        points = _simplify_polyline(edge.points)
        edge.points = points

        for i in range(len(points) - 1):
            start, finish = points[i], points[i + 1]
            is_vertical = abs(start[0] - finish[0]) < 0.5
            slide_axis = 0 if is_vertical else 1        # the coordinate we may move
            along_axis = 1 - slide_axis                 # the coordinate that runs along the segment
            slide_coord = start[slide_axis]
            span_lo = min(start[along_axis], finish[along_axis]) - 8
            span_hi = max(start[along_axis], finish[along_axis]) + 8

            free_lo = -PAGE_MARGIN + 10
            free_hi = (graph.width if is_vertical else graph.height) + PAGE_MARGIN - 10
            is_terminal_segment = (i == 0 or i == len(points) - 2)

            for name, (box_left, box_bottom, box_right, box_top) in boxes.items():
                if is_vertical:
                    box_slide_lo, box_slide_hi = box_left, box_right
                    box_along_lo, box_along_hi = box_bottom, box_top
                else:
                    box_slide_lo, box_slide_hi = box_bottom, box_top
                    box_along_lo, box_along_hi = box_left, box_right

                if box_along_hi < span_lo or box_along_lo > span_hi:
                    continue   # this box does not sit beside the segment

                endpoint_here = (i == 0 and name == edge.tail) or (i == len(points) - 2 and name == edge.head)
                if name in (edge.tail, edge.head) and is_terminal_segment and endpoint_here:
                    # A segment touching its own endpoint may only slide within that box's face.
                    if box_slide_lo - 0.5 <= slide_coord <= box_slide_hi + 0.5:
                        free_lo = max(free_lo, box_slide_lo + 10)
                        free_hi = min(free_hi, box_slide_hi - 10)
                        continue

                if box_slide_hi <= slide_coord + 0.5:
                    free_lo = max(free_lo, box_slide_hi)       # box is on the low side
                elif box_slide_lo >= slide_coord - 0.5:
                    free_hi = min(free_hi, box_slide_lo)       # box is on the high side
                else:
                    free_lo = free_hi = slide_coord            # segment runs through this box: leave it

            channel_width = free_hi - free_lo
            already_clear = min(slide_coord - free_lo, free_hi - slide_coord) >= MIN_ROUTE_MARGIN
            if channel_width < 2 * MIN_ROUTE_MARGIN and already_clear:
                continue
            if channel_width < 6 * MIN_ROUTE_MARGIN:
                new_coord = (free_lo + free_hi) / 2          # narrow channel: center in it
            else:
                new_coord = max(free_lo + MIN_ROUTE_MARGIN + 12,
                                min(free_hi - MIN_ROUTE_MARGIN - 12, slide_coord))  # wide: just clear the margin
            if abs(new_coord - slide_coord) < 1:
                continue

            for other_vertical, other_coord, other_lo, other_hi in fixed_segments:
                overlaps = not (other_hi < span_lo or other_lo > span_hi)
                if other_vertical == is_vertical and overlaps and abs(other_coord - new_coord) < 10:
                    new_coord = other_coord + 12 if other_coord + 12 <= free_hi - 6 else other_coord - 12

            if is_vertical:
                points[i] = (new_coord, start[along_axis])
                points[i + 1] = (new_coord, finish[along_axis])
            else:
                points[i] = (start[along_axis], new_coord)
                points[i + 1] = (finish[along_axis], new_coord)
            fixed_segments.append((is_vertical, new_coord, span_lo, span_hi))


def write_routes_json(graph, out_basename):
    """Dump the final node boxes and edge routes so check.py can measure the rendered geometry."""
    data = {
        "W": graph.width,
        "H": graph.height,
        "nodes": {n.name: {"x": n.center_x, "y": n.center_y, "w": n.width, "h": n.height}
                  for n in graph.nodes.values() if not n.invisible},
        "edges": [{"tl": e.tail, "hd": e.head, "pts": e.points, "label": e.label}
                  for e in graph.edges if not e.invisible],
    }
    with open(out_basename + ".routes.json", "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------- text and shape drawing

def _label_lines(label):
    """Split a graphviz label into visible lines. Graphviz uses \\l \\n \\r for line breaks."""
    return [line for line in re.split(r'\\[lnr]|\n', label) if line != ""]


def _draw_line_of_text(ctx, center_x, baseline_y, text, size, bold, color):
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ctx.set_source_rgb(*color)
    x_bearing, _, text_width, _, _, _ = ctx.text_extents(text)
    ctx.move_to(center_x - text_width / 2 - x_bearing, baseline_y)
    ctx.text_path(text)   # outline the glyphs to a path so the SVG has no live <text>
    ctx.fill()


def _draw_centered_block(ctx, center_x, center_y, lines, size, bold, color):
    """A vertically centered block of identical-style lines (the title and cluster labels)."""
    line_height = size * LINE_SPACING
    top_baseline = center_y - line_height * len(lines) / 2 + line_height * 0.78
    for i, line in enumerate(lines):
        _draw_line_of_text(ctx, center_x, top_baseline + i * line_height, line, size, bold, color)


def _draw_node_label(ctx, center_x, center_y, label, base_size, color):
    """Draw a node's label: the first line is a bold title, lines starting with '~' are dim,
    smaller annotations (typically a source filename), and the rest is regular body text."""
    lines = _label_lines(label)
    if not lines:
        return
    styled_lines = []   # (text, size, bold, color)
    for i, line in enumerate(lines):
        if line.startswith("~"):
            styled_lines.append((line[1:].strip(), base_size * ANNOTATION_SCALE, False, ANNOTATION_COLOR))
        else:
            styled_lines.append((line, base_size, i == 0, color))
    line_heights = [size * LINE_SPACING for _, size, _, _ in styled_lines]
    y = center_y - sum(line_heights) / 2
    for (text, size, bold, text_color), line_height in zip(styled_lines, line_heights):
        _draw_line_of_text(ctx, center_x, y + line_height * 0.78, text, size, bold, text_color)
        y += line_height


def _draw_label_chip(ctx, center_x, center_y, label, size, color):
    """Draw an edge label on a small white background chip so the line behind it does not clash."""
    lines = _label_lines(label)
    if not lines:
        return
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    text_width = max(ctx.text_extents(line)[2] for line in lines)
    block_height = size * LINE_SPACING * len(lines)
    ctx.set_source_rgb(1, 1, 1)
    ctx.rectangle(center_x - text_width / 2 - 3, center_y - block_height / 2 - 1, text_width + 6, block_height + 2)
    ctx.fill()
    _draw_centered_block(ctx, center_x, center_y, lines, size, False, color)


def _draw_arrowhead(ctx, from_point, to_point, color, size=8):
    angle = math.atan2(to_point[1] - from_point[1], to_point[0] - from_point[0])
    ctx.save()
    ctx.translate(*to_point)
    ctx.rotate(angle)
    ctx.move_to(0, 0)
    ctx.line_to(-size, -size * 0.42)
    ctx.line_to(-size, size * 0.42)
    ctx.close_path()
    ctx.set_source_rgb(*color)
    ctx.fill()
    ctx.restore()


def _rounded_rect_path(ctx, x, y, width, height, radius=4):
    ctx.new_sub_path()
    ctx.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    ctx.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    ctx.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    ctx.arc(x + radius, y + radius, radius, math.pi, 1.5 * math.pi)
    ctx.close_path()


def _diamond_path(ctx, center_x, center_y, half_width, half_height):
    ctx.move_to(center_x, center_y - half_height)
    ctx.line_to(center_x + half_width, center_y)
    ctx.line_to(center_x, center_y + half_height)
    ctx.line_to(center_x - half_width, center_y)
    ctx.close_path()


def _ellipse_path(ctx, center_x, center_y, radius_x, radius_y):
    ctx.save()
    ctx.translate(center_x, center_y)
    ctx.scale(radius_x, radius_y)
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


# ---------------------------------------------------------------------------- compose the drawing

def _canvas_size(graph):
    title_band = TITLE_BAND if graph.title else 0
    return (graph.width + 2 * PAGE_MARGIN, graph.height + 2 * PAGE_MARGIN + title_band, title_band)


def _place_edge_labels(ctx, graph, labels_to_place):
    """Put each edge label on the longest free stretch of its line, as a white chip that avoids
    both the boxes and the other labels. labels_to_place holds (edge, screen_points) pairs."""
    height = graph.height
    boxes = [(n.center_x - n.width / 2, height - n.center_y - n.height / 2,
              n.center_x + n.width / 2, height - n.center_y + n.height / 2)
             for n in graph.nodes.values() if not n.invisible]
    placed_chips = []
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(EDGE_LABEL_FONT_SIZE)

    def chip_rect(center_x, center_y, width, height):
        return (center_x - width / 2 - 3, center_y - height / 2 - 1,
                center_x + width / 2 + 3, center_y + height / 2 + 1)

    def collides(rect):
        return any(not (rect[2] < other[0] or rect[0] > other[2] or rect[3] < other[1] or rect[1] > other[3])
                   for other in boxes + placed_chips)

    for edge, screen_points in labels_to_place:
        lines = _label_lines(edge.label)
        text_width = max(ctx.text_extents(line)[2] for line in lines)
        text_height = EDGE_LABEL_FONT_SIZE * LINE_SPACING * len(lines)
        segments = sorted(
            ((screen_points[i], screen_points[i + 1]) for i in range(len(screen_points) - 1)),
            key=lambda seg: -((seg[0][0] - seg[1][0]) ** 2 + (seg[0][1] - seg[1][1]) ** 2))

        chosen = None
        for a, b in segments:
            for t in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
                center_x = a[0] + t * (b[0] - a[0])
                center_y = a[1] + t * (b[1] - a[1])
                rect = chip_rect(center_x, center_y, text_width, text_height)
                if not collides(rect):
                    chosen = (center_x, center_y, rect)
                    break
            if chosen:
                break
        if not chosen:
            a, b = segments[0]
            center_x, center_y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            chosen = (center_x, center_y, chip_rect(center_x, center_y, text_width, text_height))

        placed_chips.append(chosen[2])
        _draw_label_chip(ctx, chosen[0], chosen[1], edge.label, EDGE_LABEL_FONT_SIZE, edge.label_color)


def draw_graph(ctx, graph):
    """Draw the whole diagram onto a cairo context: background, title, clusters, edges, labels, nodes.
    Node coordinates come from graphviz with y pointing up, so drawing flips y to (height - y)."""
    canvas_width, _, title_band = _canvas_size(graph)

    ctx.set_source_rgb(1, 1, 1)
    ctx.rectangle(0, 0, canvas_width, graph.height + 2 * PAGE_MARGIN + title_band)
    ctx.fill()

    if graph.title:
        _draw_centered_block(ctx, canvas_width / 2, PAGE_MARGIN + title_band / 2,
                             _label_lines(graph.title), TITLE_FONT_SIZE, True, TITLE_COLOR)

    ctx.translate(PAGE_MARGIN, PAGE_MARGIN + title_band)
    height = graph.height

    for cluster in graph.clusters:
        left = cluster.left - 12
        right = cluster.right + 12
        top = cluster.top + 26
        bottom = cluster.bottom - 10
        _rounded_rect_path(ctx, left, height - top, right - left, top - bottom, 8)
        ctx.set_source_rgb(*cluster.fill)
        ctx.fill_preserve()
        ctx.set_source_rgb(*cluster.border)
        ctx.set_line_width(1.5)
        ctx.stroke()
        _draw_centered_block(ctx, (left + right) / 2, height - top + 15,
                             _label_lines(cluster.label), CLUSTER_LABEL_FONT_SIZE, True, CLUSTER_LABEL_COLOR)

    labels_to_place = []
    for edge in graph.edges:
        if edge.invisible or len(edge.points) < 2:
            continue
        screen_points = [(x, height - y) for x, y in edge.points]
        ctx.set_source_rgb(*edge.color)
        ctx.set_line_width(max(edge.pen_width * 1.2, 1.2))
        ctx.set_dash([6, 4] if edge.dashed else [])
        ctx.move_to(*screen_points[0])
        for point in screen_points[1:]:
            ctx.line_to(*point)
        ctx.stroke()
        ctx.set_dash([])
        if edge.direction in ("", "forward", "both"):
            _draw_arrowhead(ctx, screen_points[-2], screen_points[-1], edge.color)
        if edge.direction in ("both", "back"):
            _draw_arrowhead(ctx, screen_points[1], screen_points[0], edge.color)
        if edge.label:
            labels_to_place.append((edge, screen_points))

    _place_edge_labels(ctx, graph, labels_to_place)

    for node in graph.nodes.values():
        if node.invisible:
            continue
        center_x = node.center_x
        center_y = height - node.center_y
        half_width, half_height = node.width / 2, node.height / 2
        if node.shape == "diamond":
            _diamond_path(ctx, center_x, center_y, half_width, half_height)
        elif node.shape == "ellipse":
            _ellipse_path(ctx, center_x, center_y, half_width, half_height)
        else:
            _rounded_rect_path(ctx, center_x - half_width, center_y - half_height, node.width, node.height, 4)
        ctx.set_source_rgb(*node.fill)
        ctx.fill_preserve()
        ctx.set_source_rgb(*node.border)
        ctx.set_line_width(max(node.pen_width * 1.1, 1))
        ctx.stroke()
        _draw_node_label(ctx, center_x, center_y, node.label, node.font_size, node.text_color)


def render(dot_path, out_basename):
    graph = load_graph(dot_path)
    center_routes_in_channels(graph)
    write_routes_json(graph, out_basename)

    canvas_width, canvas_height, _ = _canvas_size(graph)

    svg_surface = cairo.SVGSurface(out_basename + ".svg", canvas_width, canvas_height)
    draw_graph(cairo.Context(svg_surface), graph)
    svg_surface.finish()

    scale = 2
    png_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(canvas_width * scale), int(canvas_height * scale))
    png_context = cairo.Context(png_surface)
    png_context.scale(scale, scale)
    draw_graph(png_context, graph)
    png_surface.write_to_png(out_basename + ".png")

    print(f"rendered {out_basename}  {int(graph.width)}x{int(graph.height)}pt")


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
