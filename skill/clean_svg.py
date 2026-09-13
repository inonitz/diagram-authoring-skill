"""Make a cairo SVG safe for slide tools (Canva in particular).

Two fixes, in place:
  - Convert cairo's percentage colors, rgb(r%, g%, b%), to #rrggbb hex. Canva mishandles percentages.
  - Round long coordinate decimals to one place, which shrinks the file with no visible change.

Usage: python3 clean_svg.py <file.svg>
"""
import re, sys


def _rgb_to_hex(match):
    channels = []
    for part in match.group(1).split(","):
        part = part.strip()
        if part.endswith("%"):
            channels.append(round(float(part[:-1]) * 255 / 100))
        else:
            channels.append(round(float(part)))
    return "#" + "".join(f"{value:02x}" for value in channels)


def canva_safe(svg_text):
    svg_text = re.sub(r"rgb\(([0-9.,%\s]+)\)", _rgb_to_hex, svg_text)
    svg_text = re.sub(r"\d+\.\d{2,}", lambda m: f"{float(m.group()):.1f}", svg_text)
    return svg_text


if __name__ == "__main__":
    path = sys.argv[1]
    with open(path) as f:
        original = f.read()
    with open(path, "w") as f:
        f.write(canva_safe(original))
    print(f"cleaned {path}")
