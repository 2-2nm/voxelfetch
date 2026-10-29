import re

from ansi import RESET, bg, paint, parse_hex, visible_len

GRAY = (150, 150, 150)
GOOD = (90, 200, 120)
WARN = (230, 190, 60)
BAD = (240, 80, 80)
PALETTE = [
    [(12, 12, 12), (197, 15, 31), (19, 161, 14), (193, 156, 0),
     (0, 55, 218), (136, 23, 152), (58, 150, 221), (204, 204, 204)],
    [(118, 118, 118), (231, 72, 86), (22, 198, 12), (249, 241, 165),
     (59, 120, 255), (180, 0, 158), (97, 214, 214), (242, 242, 242)],
]
GAP = 4
_PCT = re.compile("\x01(\\d+)\x02")


class _Safe(dict):
    def __missing__(self, key):
        return ""


def _color(value, default):
    try:
        return parse_hex(value)
    except (ValueError, AttributeError):
        return default


def _tidy(text):
    text = re.sub(r"\(\s*%?\s*\)", "", text)
    text = re.sub(r"\s+[@\-]\s*$", "", text)
    return " ".join(text.split())


def _fill(template, fields, fallback):
    safe = _Safe(fields)
    if isinstance(fields.get("pct"), int):
        safe["pct"] = f"\x01{fields['pct']}\x02"
    try:
        return _tidy(template.format_map(safe))
    except (ValueError, KeyError, IndexError, AttributeError):
        return _tidy(fallback.format_map(safe)) if fallback else template


def _paint_value(text, text_rgb):
    out, pos = [], 0
    for match in _PCT.finditer(text):
        out.append(paint(text[pos:match.start()], text_rgb) if match.start() > pos else "")
        pct = int(match.group(1))
        out.append(paint(str(pct), GOOD if pct < 60 else WARN if pct < 80 else BAD))
        pos = match.end()
    out.append(paint(text[pos:], text_rgb) if pos < len(text) else "")
    return "".join(out)


def _swatches(style):
    block = "   " if style != "circle" else None
    rows = []
    for row in PALETTE:
        if block:
            rows.append("".join(bg(c) + block + RESET for c in row))
        else:
            rows.append(" ".join(paint("●", c) for c in row))
    return rows


def info_lines(entries, display):
    sep = display.get("separator", ": ")
    prefix = display.get("keyPrefix", "")
    width = int(display.get("keyWidth", 0) or 0)
    indent = " " * int(display.get("indent", 0) or 0)
    key_rgb = _color(display.get("keyColor"), (232, 65, 75))
    title_rgb = _color(display.get("titleColor"), (232, 65, 75))
    text_rgb = _color(display.get("textColor"), (226, 226, 226))
    sep_rgb = _color(display.get("separatorColor"), GRAY)
    lines, title_len = [], 20
    for entry in entries:
        kind, fields, opts = entry["kind"], entry["fields"], entry["opts"]
        if kind == "break":
            lines.append("")
        elif kind == "colors":
            lines += [indent + row for row in _swatches(opts.get("style", "block"))]
        elif kind == "title":
            text = _fill(entry["format"], fields, entry["default_format"])
            title_len = len(text)
            lines.append(indent + paint(text, _color(opts.get("color"), title_rgb), True))
        elif kind == "separator":
            length = int(opts.get("length") or title_len)
            lines.append(indent + paint(str(opts.get("char", "-"))[:1] * length, sep_rgb))
        else:
            value = _fill(entry["format"], fields, entry["default_format"])
            if not value:
                continue
            key = _fill(entry["key"], fields, None) if entry["key"] else ""
            label = paint((prefix + key).ljust(width + len(prefix)), _color(opts.get("keyColor"), key_rgb), True)
            lines.append(indent + label + (paint(sep, sep_rgb) if key else "") + _paint_value(value, text_rgb))
    return lines


def info_width(lines):
    return max((visible_len(line) for line in lines), default=0)


def compose(logo_rows, logo_cols, lines):
    height = max(len(lines), len(logo_rows))
    top = (height - len(logo_rows)) // 2
    blank = " " * logo_cols
    padded = [blank] * top + logo_rows + [blank] * (height - top - len(logo_rows))
    padded_info = lines + [""] * (height - len(lines))
    return [left + " " * GAP + right for left, right in zip(padded, padded_info)]


def place(rows, inner_cols, box_cols, box_rows):
    left = max((box_cols - inner_cols) // 2, 0)
    right = max(box_cols - inner_cols - left, 0)
    padded = [" " * left + row + " " * right for row in rows]
    blank = " " * box_cols
    top = max((box_rows - len(padded)) // 2, 0)
    bottom = max(box_rows - len(padded) - top, 0)
    return [blank] * top + padded + [blank] * bottom
