import argparse
import os
import shutil
import sys
import time

import pin
import raster
from ansi import HIDE_CURSOR, RESET, SHOW_CURSOR, enable_vt, parse_hex
from config import load_config
from layout import GAP, compose, info_lines, info_width, place
from specs import collect
from vxlfile import INK_FULL, builtin_cube, load

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
MIN_LOGO_COLS = 16
DEFAULT_ACCENT = "#c8d2f0"


def parse_box(value):
    try:
        cols, rows = (int(v) for v in value.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, for example 60x30")
    if cols < 1 or rows < 1:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, for example 60x30")
    return cols, rows


def parse_args(argv):
    p = argparse.ArgumentParser(prog="voxelfetch", description="System info with a 3D .vxl model as the logo.")
    p.add_argument("model", nargs="?", help="path to a .vxl file")
    p.add_argument("--spin", nargs="?", type=float, const=0.0, default=None, metavar="SECONDS",
                   help="animate the model for SECONDS, or until a key is pressed (no value: until a key is pressed)")
    p.add_argument("--fps", type=int, default=25)
    p.add_argument("--speed", type=float, default=1.0, help="rotation speed multiplier")
    p.add_argument("--pin", action="store_true", help="keep the animated header at the top while the shell runs below")
    p.add_argument("--unpin", action="store_true", help="release a pinned header so the terminal scrolls normally")
    p.add_argument("--pin-child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--parent", type=int, default=0, help="PID of the shell; pinned animation stops when it exits")
    p.add_argument("--color", type=parse_hex, default=None,
                   help="logo color, e.g. #ff6b6b; overrides the colors stored in a v3 .vxl")
    p.add_argument("--config", metavar="FILE", help="path to a config.json (default: $VOXELFETCH_CONFIG, then config.json next to the program)")
    p.add_argument("--shell", help="shell name shown in the Shell row")
    p.add_argument("--box", type=parse_box, help="fixed logo space as WIDTHxHEIGHT (default: matches the info block)")
    p.add_argument("--width", type=int, help="model width, never larger than the box")
    p.add_argument("--height", type=int, help="model height, never larger than the box")
    p.add_argument("--style", choices=raster.STYLES, default="braille",
                   help="braille: 8x finer detail per cell (default); ascii: plain characters only")
    p.add_argument("--source-width", type=int, metavar="COLS",
                   help="ascii style only: width the model was edited at; overrides the value stored in a v2 .vxl "
                        "and enables supersampled rendering for v1 files")
    p.add_argument("--no-logo", action="store_true")
    return p.parse_args(argv)


def model_path(arg):
    candidates = [arg, os.environ.get("VOXELFETCH_MODEL"), os.path.join(HERE, "default.vxl")]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def load_model(arg):
    path = model_path(arg)
    if not path:
        return builtin_cube()
    try:
        return load(path)
    except (OSError, ValueError) as exc:
        print(f"voxelfetch: {exc}; using built-in cube", file=sys.stderr)
        return builtin_cube()


def logo_box(args, lines, term_cols):
    box_cols, box_rows = args.box or (len(lines) * 2, len(lines))
    box_cols = min(box_cols, term_cols - info_width(lines) - GAP)
    if args.no_logo or box_cols < MIN_LOGO_COLS:
        return None
    draw = (max(min(args.width or box_cols, box_cols), 1), max(min(args.height or box_rows, box_rows), 1))
    return (box_cols, box_rows), draw


def resolve_colors(color, ink, edge_colors):
    if color is not None:
        return color, [None] * len(edge_colors), True
    accent = tuple(ink[1]) if ink else parse_hex(DEFAULT_ACCENT)
    return accent, edge_colors, ink is None or ink[0] == INK_FULL


def build_frame(points, edges, angles, box, draw, palette, lines, factor=1, style="braille", tints=None):
    logo = raster.render(points, edges, angles, draw[0], draw[1], palette, factor, style, tints)
    return compose(place(logo, draw[0], box[0], box[1]), box[0], lines)


def key_pressed():
    if os.name != "nt":
        return False
    import msvcrt
    if msvcrt.kbhit():
        msvcrt.getwch()
        return True
    return False


def spin_loop(frame_for, count, fps, spin, duration):
    angles = list(raster.START_ANGLES)
    start = time.time()
    sys.stdout.write(HIDE_CURSOR)
    try:
        while True:
            sys.stdout.write("\n".join(frame_for(angles)) + RESET + "\n")
            sys.stdout.flush()
            time.sleep(1 / max(fps, 1))
            if key_pressed() or (duration and time.time() - start >= duration):
                break
            angles = [a + s for a, s in zip(angles, spin)]
            sys.stdout.write(f"\x1b[{count}A")
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)


def main(argv=None):
    args = parse_args(argv)
    if args.unpin:
        pin.request_stop(args.parent)
        return
    enable_vt()
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    vertices, edges, spin, stored, ink, edge_colors = load_model(args.model)
    points = raster.normalize(vertices)
    config = load_config(args.config)
    lines = info_lines(collect(config["modules"], args.shell), config["display"])
    term_cols = shutil.get_terminal_size((120, 30)).columns
    sizes = logo_box(args, lines, term_cols)
    accent, edge_colors, fade = resolve_colors(args.color, ink, edge_colors)
    palette = raster.make_palette(accent, fade)
    tints = raster.make_tints(edge_colors, fade)
    source_cols = args.source_width or (stored[0] if stored else None)
    factor = raster.supersample_factor(source_cols, sizes[1][0]) if sizes else 1

    def frame_for(angles):
        if not sizes:
            return lines
        return build_frame(points, edges, angles, sizes[0], sizes[1], palette, lines, factor, args.style, tints)

    height = max(len(lines), sizes[0][1]) if sizes else len(lines)
    speed = [a * args.speed for a in (spin if any(spin) else raster.FALLBACK_SPIN)]
    if args.pin_child:
        pin.animate(frame_for, height, args.fps, speed, args.parent)
        return
    if args.pin and sizes:
        sys.exit(pin.start(frame_for, height, sys.argv[1:] if argv is None else argv, args.parent))
    if args.spin is not None and sizes:
        spin_loop(frame_for, height, args.fps, speed, args.spin)
        return
    print("\n".join(frame_for(raster.START_ANGLES)) + RESET)
