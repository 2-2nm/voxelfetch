import math

from ansi import RESET, fg

RAMP = " .:-=+*#%@"
START_ANGLES = (0.4, 0.6, 0.0)
FALLBACK_SPIN = (0.03, 0.05, 0.01)
CELL_RATIO = 2.0
FILL = 0.46
VERTEX_BOOST = 2
SUPER_MAX = 6
DEPTH_TRIM = 0.05


def normalize(vertices):
    if not vertices:
        return []
    lows = [min(v[i] for v in vertices) for i in range(3)]
    highs = [max(v[i] for v in vertices) for i in range(3)]
    centre = [(lo + hi) / 2 for lo, hi in zip(lows, highs)]
    shifted = [[v[i] - centre[i] for i in range(3)] for v in vertices]
    radius = max(math.sqrt(x * x + y * y + z * z) for x, y, z in shifted) or 1.0
    return [[x / radius, y / radius, z / radius] for x, y, z in shifted]


def rotate(points, ax, ay, az):
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    out = []
    for x, y, z in points:
        y, z = y * cx - z * sx, y * sx + z * cx
        x, z = x * cy + z * sy, -x * sy + z * cy
        x, y = x * cz - y * sz, x * sz + y * cz
        out.append((x, y, z))
    return out


def make_palette(accent, fade=True):
    size = len(RAMP)
    low = tuple(int(c * 0.28) for c in accent) if fade else tuple(accent)
    return [tuple(int(lo + (hi - lo) * i / (size - 1)) for lo, hi in zip(low, accent)) for i in range(size)]


def make_tints(edge_colors, fade=True):
    cache = {}
    return [None if c is None else cache.setdefault(c, make_palette(c, fade)) for c in edge_colors]


def pick(palette, tints, owner):
    if tints and 0 <= owner < len(tints) and tints[owner] is not None:
        return tints[owner]
    return palette


def shade(z, boost=0):
    t = min(1.0, max(0.0, (z + 1) / 2))
    return min(len(RAMP) - 1, 1 + int(t * (len(RAMP) - 2)) + boost)


class Canvas:
    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.depth = [-9.0] * (cols * rows)
        self.level = [0] * (cols * rows)
        self.owner = [-1] * (cols * rows)

    def plot(self, x, y, z, boost=0, owner=-1):
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < self.cols and 0 <= iy < self.rows):
            return
        i = iy * self.cols + ix
        if z > self.depth[i]:
            self.depth[i] = z
            self.level[i] = shade(z, boost)
            self.owner[i] = owner

    def line(self, a, b, owner=-1):
        steps = max(int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))), 1)
        for i in range(steps + 1):
            t = i / steps
            self.plot(*(p + (q - p) * t for p, q in zip(a, b)), owner=owner)

    def to_rows(self, palette, tints=None):
        out = []
        for r in range(self.rows):
            parts, last = [], None
            for c in range(self.cols):
                lv = self.level[r * self.cols + c]
                if lv == 0:
                    parts.append(" ")
                    continue
                rgb = pick(palette, tints, self.owner[r * self.cols + c])[lv]
                if rgb != last:
                    parts.append(fg(rgb))
                    last = rgb
                parts.append(RAMP[lv])
            out.append("".join(parts) + RESET)
        return out


class SuperCanvas:
    def __init__(self, cols, rows, factor):
        self.factor = factor
        self.cols, self.rows = cols * factor, rows * factor
        self.out_cols, self.out_rows = cols, rows
        self.depth = [-9.0] * (self.cols * self.rows)
        self.ink = [0] * (cols * rows)
        self.front = [-9.0] * (cols * rows)
        self.owner = [-1] * (cols * rows)

    def plot(self, x, y, z, boost=0, owner=-1):
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < self.cols and 0 <= iy < self.rows):
            return
        i = iy * self.cols + ix
        if z > self.depth[i]:
            block = (iy // self.factor) * self.out_cols + ix // self.factor
            if self.depth[i] <= -9.0:
                self.ink[block] += 1
            self.depth[i] = z
            if z > self.front[block]:
                self.front[block] = z
                self.owner[block] = owner

    line = Canvas.line

    def to_rows(self, palette, tints=None):
        top = len(RAMP) - 2
        filled = [b for b, n in enumerate(self.ink) if n]
        if not filled:
            return [" " * self.out_cols + RESET for _ in range(self.out_rows)]
        depths = sorted(self.front[b] for b in filled)
        near = depths[int((len(depths) - 1) * (1 - DEPTH_TRIM))]
        far = depths[int((len(depths) - 1) * DEPTH_TRIM)]
        span = (near - far) or 1.0
        inks = sorted(self.ink[b] for b in filled)
        typical = inks[len(inks) // 2] or 1
        out = []
        for r in range(self.out_rows):
            parts, last = [], None
            for c in range(self.out_cols):
                b = r * self.out_cols + c
                if not self.ink[b]:
                    parts.append(" ")
                    continue
                depth = min(1.0, max(0.0, (self.front[b] - far) / span))
                ink = min(1.0, self.ink[b] / typical)
                glyph = 1 + int((0.5 * depth + 0.5 * ink * depth ** 0.5) * top)
                tone = 1 + int(depth * (len(palette) - 2))
                rgb = pick(palette, tints, self.owner[b])[tone]
                if rgb != last:
                    parts.append(fg(rgb))
                    last = rgb
                parts.append(RAMP[glyph])
            out.append("".join(parts) + RESET)
        return out


BRAILLE_BASE = 0x2800
BRAILLE_DOTS = (
    (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
    (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80),
)


class BrailleCanvas:

    def __init__(self, cols, rows):
        self.out_cols, self.out_rows = cols, rows
        self.cols, self.rows = cols * 2, rows * 4
        self.depth = [-9.0] * (self.cols * self.rows)
        self.owner = [-1] * (self.cols * self.rows)

    def plot(self, x, y, z, boost=0, owner=-1):
        ix, iy = int(round(x)), int(round(y))
        if 0 <= ix < self.cols and 0 <= iy < self.rows:
            i = iy * self.cols + ix
            if z > self.depth[i]:
                self.depth[i] = z
                self.owner[i] = owner

    line = Canvas.line

    def to_rows(self, palette, tints=None):
        cells = []
        for r in range(self.out_rows):
            for c in range(self.out_cols):
                mask, front, who = 0, -9.0, -1
                for dx, dy, bit in BRAILLE_DOTS:
                    i = (r * 4 + dy) * self.cols + c * 2 + dx
                    z = self.depth[i]
                    if z > -9.0:
                        mask |= bit
                        if z > front:
                            front, who = z, self.owner[i]
                cells.append((mask, front, who))
        depths = sorted(f for m, f, _ in cells if m)
        if not depths:
            return [" " * self.out_cols + RESET for _ in range(self.out_rows)]
        near = depths[int((len(depths) - 1) * (1 - DEPTH_TRIM))]
        far = depths[int((len(depths) - 1) * DEPTH_TRIM)]
        span = (near - far) or 1.0
        out = []
        for r in range(self.out_rows):
            parts, last = [], None
            for c in range(self.out_cols):
                mask, front, who = cells[r * self.out_cols + c]
                if not mask:
                    parts.append(" ")
                    continue
                depth = min(1.0, max(0.0, (front - far) / span))
                tone = 1 + int(depth * (len(palette) - 2))
                rgb = pick(palette, tints, who)[tone]
                if rgb != last:
                    parts.append(fg(rgb))
                    last = rgb
                parts.append(chr(BRAILLE_BASE + mask))
            out.append("".join(parts) + RESET)
        return out


def supersample_factor(source_cols, out_cols):
    if not source_cols:
        return 1
    return max(1, min(SUPER_MAX, round(source_cols / max(out_cols, 1))))


def project(points, cols, rows, ratio=CELL_RATIO):
    scale_y = min(rows * FILL, cols * FILL / ratio)
    scale_x = scale_y * ratio
    cx, cy = (cols - 1) / 2, (rows - 1) / 2
    return [(cx + x * scale_x, cy - y * scale_y, z) for x, y, z in points]


STYLES = ("braille", "ascii")


def render(points, edges, angles, cols, rows, palette, factor=1, style="braille", tints=None):
    if style == "braille":
        canvas, ratio = BrailleCanvas(cols, rows), 1.0  # dots are square
    else:
        canvas, ratio = (SuperCanvas(cols, rows, factor) if factor > 1 else Canvas(cols, rows)), CELL_RATIO
    projected = project(rotate(points, *angles), canvas.cols, canvas.rows, ratio)
    for i, (a, b) in enumerate(edges):
        canvas.line(projected[a], projected[b], i)
    if style == "ascii" and factor == 1:
        touch = {}
        for i, (a, b) in enumerate(edges):
            touch.setdefault(a, i)
            touch.setdefault(b, i)
        for v, (x, y, z) in enumerate(projected):
            canvas.plot(x, y, z, VERTEX_BOOST, touch.get(v, -1))
    return canvas.to_rows(palette, tints)
