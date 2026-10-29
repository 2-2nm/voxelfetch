import ctypes
import os
import re

ESC = "\x1b["
RESET = ESC + "0m"
BOLD = ESC + "1m"
HIDE_CURSOR = ESC + "?25l"
SHOW_CURSOR = ESC + "?25h"

_STRIP = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def fg(rgb):
    return f"{ESC}38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def bg(rgb):
    return f"{ESC}48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def paint(text, rgb, bold=False):
    return f"{BOLD if bold else ''}{fg(rgb)}{text}{RESET}"


def visible_len(text):
    return len(_STRIP.sub("", text))


def parse_hex(value):
    digits = value.lstrip("#")
    if len(digits) != 6:
        raise ValueError(value)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def enable_vt():
    if os.name != "nt":
        return
    kernel = ctypes.windll.kernel32
    handle = kernel.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel.SetConsoleMode(handle, mode.value | 0x0004)
