#!/usr/bin/env python3
"""Trace simple PNG icons into filled SVG paths.

This is a dependency-free fallback for icon-style PNG assets. It decodes 8-bit
PNG files, groups visible pixels by dominant color, traces connected component
boundaries, and emits filled SVG paths. Use SVGO and, when the PNG represents
stroke outlines, svg-centerline-cli.py after this step.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class Image:
    width: int
    height: int
    pixels: list[tuple[int, int, int, int]]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace a PNG icon into filled SVG paths.")
    parser.add_argument("--input", "-i", required=True, help="Input PNG file.")
    parser.add_argument("--output", "-o", help="Write SVG output to this file instead of stdout.")
    parser.add_argument(
        "--mode",
        choices=("palette", "alpha", "exact"),
        default="palette",
        help="Trace dominant color regions, one alpha mask, or exact RGBA colors.",
    )
    parser.add_argument("--alpha-threshold", type=int, default=16, help="Minimum alpha to include a pixel.")
    parser.add_argument("--white-threshold", type=int, default=250, help="RGB threshold for --drop-white.")
    parser.add_argument("--drop-white", action="store_true", help="Treat near-white pixels as background.")
    parser.add_argument("--quantize", type=int, default=24, help="Color bucket size for palette/exact modes.")
    parser.add_argument("--max-colors", type=int, default=8, help="Maximum dominant colors in palette mode.")
    parser.add_argument("--min-area", type=int, default=4, help="Drop connected components smaller than this many pixels.")
    parser.add_argument("--scale", type=float, default=1.0, help="Scale output coordinates by this value.")
    parser.add_argument("--decimals", type=int, default=3, help="Decimal places for coordinates.")
    parser.add_argument("--title", help="Optional SVG title.")
    return parser.parse_args(argv)


def fail(message: str) -> None:
    print(f"svg-raster-trace-cli: {message}", file=sys.stderr)
    sys.exit(1)


def paeth(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def read_png(path: Path) -> Image:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        fail("Input is not a PNG file")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    palette: list[tuple[int, int, int]] = []
    transparency: bytes | None = None
    idat = bytearray()

    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(">IIBBBBB", chunk)
            if compression != 0 or filter_method != 0 or interlace != 0:
                fail("Only non-interlaced standard PNG files are supported")
        elif chunk_type == b"PLTE":
            palette = [tuple(chunk[i : i + 3]) for i in range(0, len(chunk), 3)]
        elif chunk_type == b"tRNS":
            transparency = chunk
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or bit_depth is None or color_type is None:
        fail("PNG is missing IHDR")
    if bit_depth != 8:
        fail("Only 8-bit PNG files are supported")

    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in channels_by_type:
        fail(f"Unsupported PNG color type: {color_type}")
    channels = channels_by_type[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    rows: list[bytearray] = []
    src = 0
    for _row in range(height):
        filter_type = raw[src]
        src += 1
        row = bytearray(raw[src : src + stride])
        src += stride
        prev = rows[-1] if rows else bytearray(stride)
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 1:
                row[i] = (row[i] + left) & 0xFF
            elif filter_type == 2:
                row[i] = (row[i] + up) & 0xFF
            elif filter_type == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[i] = (row[i] + paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                fail(f"Unsupported PNG row filter: {filter_type}")
        rows.append(row)

    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for col in range(width):
            i = col * channels
            if color_type == 0:
                gray = row[i]
                pixels.append((gray, gray, gray, 255))
            elif color_type == 2:
                pixels.append((row[i], row[i + 1], row[i + 2], 255))
            elif color_type == 3:
                index = row[i]
                if index >= len(palette):
                    fail("PNG palette index out of range")
                r, g, b = palette[index]
                a = transparency[index] if transparency is not None and index < len(transparency) else 255
                pixels.append((r, g, b, a))
            elif color_type == 4:
                gray, alpha = row[i], row[i + 1]
                pixels.append((gray, gray, gray, alpha))
            elif color_type == 6:
                pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
    return Image(width=width, height=height, pixels=pixels)


def visible(pixel: tuple[int, int, int, int], args: argparse.Namespace) -> bool:
    r, g, b, a = pixel
    if a < args.alpha_threshold:
        return False
    if args.drop_white and r >= args.white_threshold and g >= args.white_threshold and b >= args.white_threshold:
        return False
    return True


def quantized_rgb(pixel: tuple[int, int, int, int], step: int) -> tuple[int, int, int]:
    step = max(1, step)
    return tuple(min(255, int(round(channel / step) * step)) for channel in pixel[:3])


def nearest_color(color: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return min(palette, key=lambda candidate: sum((color[i] - candidate[i]) ** 2 for i in range(3)))


def group_pixels(image: Image, args: argparse.Namespace) -> dict[tuple[int, int, int], set[tuple[int, int]]]:
    visible_pixels: list[tuple[int, int, tuple[int, int, int, int]]] = []
    for row in range(image.height):
        for col in range(image.width):
            pixel = image.pixels[row * image.width + col]
            if visible(pixel, args):
                visible_pixels.append((row, col, pixel))
    if not visible_pixels:
        fail("No visible pixels found")

    groups: dict[tuple[int, int, int], set[tuple[int, int]]] = defaultdict(set)
    if args.mode == "alpha":
        color = Counter(quantized_rgb(pixel, args.quantize) for _row, _col, pixel in visible_pixels).most_common(1)[0][0]
        for row, col, _pixel in visible_pixels:
            groups[color].add((row, col))
        return groups

    if args.mode == "exact":
        for row, col, pixel in visible_pixels:
            groups[quantized_rgb(pixel, args.quantize)].add((row, col))
        return groups

    histogram = Counter(quantized_rgb(pixel, args.quantize) for _row, _col, pixel in visible_pixels)
    palette = [color for color, _count in histogram.most_common(max(1, args.max_colors))]
    for row, col, pixel in visible_pixels:
        groups[nearest_color(quantized_rgb(pixel, args.quantize), palette)].add((row, col))
    return groups


def components(mask: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(mask)
    found: list[set[tuple[int, int]]] = []
    while remaining:
        first = remaining.pop()
        component = {first}
        queue = deque([first])
        while queue:
            row, col = queue.popleft()
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        found.append(component)
    return found


def trace_edges(component: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for row, col in component:
        if (row - 1, col) not in component:
            edges[(col, row)].append((col + 1, row))
        if (row, col + 1) not in component:
            edges[(col + 1, row)].append((col + 1, row + 1))
        if (row + 1, col) not in component:
            edges[(col + 1, row + 1)].append((col, row + 1))
        if (row, col - 1) not in component:
            edges[(col, row + 1)].append((col, row))

    loops: list[list[tuple[int, int]]] = []
    while edges:
        start = next(iter(edges))
        current = start
        loop = [start]
        while True:
            targets = edges.get(current)
            if not targets:
                break
            nxt = targets.pop()
            if not targets:
                del edges[current]
            loop.append(nxt)
            current = nxt
            if current == start:
                break
        if len(loop) > 3:
            loops.append(simplify_collinear(loop))
    return loops


def simplify_collinear(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(points) <= 3:
        return points
    closed = points[0] == points[-1]
    body = points[:-1] if closed else points[:]
    changed = True
    while changed and len(body) > 2:
        changed = False
        simplified: list[tuple[int, int]] = []
        count = len(body)
        for i, point in enumerate(body):
            prev = body[(i - 1) % count]
            nxt = body[(i + 1) % count]
            if (prev[0] == point[0] == nxt[0]) or (prev[1] == point[1] == nxt[1]):
                changed = True
                continue
            simplified.append(point)
        body = simplified
    return body + [body[0]] if closed and body else body


def fmt(value: float, decimals: int) -> str:
    text = f"{round(value, decimals):.{decimals}f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def path_from_loops(loops: list[list[tuple[int, int]]], scale: float, decimals: int) -> str:
    parts: list[str] = []
    for loop in loops:
        if len(loop) < 4:
            continue
        first = loop[0]
        parts.append(f"M{fmt(first[0] * scale, decimals)} {fmt(first[1] * scale, decimals)}")
        for point in loop[1:-1]:
            parts.append(f"L{fmt(point[0] * scale, decimals)} {fmt(point[1] * scale, decimals)}")
        parts.append("Z")
    return " ".join(parts)


def color_hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(image: Image, groups: dict[tuple[int, int, int], set[tuple[int, int]]], args: argparse.Namespace) -> str:
    paths: list[str] = []
    for color, mask in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
        loops: list[list[tuple[int, int]]] = []
        for component in components(mask):
            if len(component) < args.min_area:
                continue
            loops.extend(trace_edges(component))
        d = path_from_loops(loops, args.scale, args.decimals)
        if d:
            paths.append(f'<path fill="{color_hex(color)}" fill-rule="evenodd" d="{escape_attr(d)}"/>')
    if not paths:
        fail("No traceable components survived --min-area")

    width = image.width * args.scale
    height = image.height * args.scale
    title = f"<title>{escape_attr(args.title)}</title>\n  " if args.title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(width, args.decimals)} {fmt(height, args.decimals)}">\n'
        f"  {title}" + "\n  ".join(paths) + "\n</svg>"
    )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.alpha_threshold < 0 or args.alpha_threshold > 255:
        fail("--alpha-threshold must be between 0 and 255")
    if args.max_colors < 1:
        fail("--max-colors must be at least 1")
    if args.scale <= 0:
        fail("--scale must be greater than zero")
    image = read_png(Path(args.input))
    groups = group_pixels(image, args)
    svg = build_svg(image, groups, args)
    if args.output:
        Path(args.output).write_text(svg + "\n", encoding="utf-8")
    else:
        print(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
