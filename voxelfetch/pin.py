import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import raster
from ansi import RESET, visible_len

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
MIN_FREE_ROWS = 6
PINNED = 0
FALLBACK = 3
SAVE = "\x1b7"
RESTORE = "\x1b8"


def parent_alive(pid):
    if not pid:
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    alive = kernel.WaitForSingleObject(handle, 0) == 0x102
    kernel.CloseHandle(handle)
    return alive


def stop_path(pid):
    return os.path.join(tempfile.gettempdir(), f"voxelfetch-stop-{pid}")


def request_stop(pid):
    open(stop_path(pid), "w").close()


def _clear_stop(pid):
    try:
        os.remove(stop_path(pid))
    except OSError:
        pass


def frame_width(frame):
    return max(visible_len(line) for line in frame)


def unfit_reason(frame, height):
    term = shutil.get_terminal_size()
    if not sys.stdout.isatty():
        return "output is not a terminal"
    if term.lines < height + MIN_FREE_ROWS:
        return f"window has {term.lines} rows, needs {height + MIN_FREE_ROWS}; make it taller or use --height"
    if term.columns < frame_width(frame):
        return f"window has {term.columns} columns, needs {frame_width(frame)}; make it wider or use --width"
    return None


def margins(height, rows):
    return f"\x1b[{height + 1};{rows}r"


def draw(frame):
    body = "".join(f"\x1b[{i};1H{line}{RESET}" for i, line in enumerate(frame, 1))
    return SAVE + body + RESTORE


def launch(argv):
    base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, HERE]
    child = base + [a for a in argv if a != "--pin"] + ["--pin-child"]
    options = {"stdin": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    subprocess.Popen(child, **options)


def start(frame_for, height, argv, parent):
    frame = frame_for(raster.START_ANGLES)
    reason = unfit_reason(frame, height)
    if reason:
        print("\n".join(frame) + RESET)
        print(f"voxelfetch: --pin skipped: {reason}", file=sys.stderr)
        return FALLBACK
    rows = shutil.get_terminal_size().lines
    sys.stdout.write("\x1b[2J\x1b[H" + "\n".join(frame) + RESET + "\n")
    sys.stdout.write(margins(height, rows) + f"\x1b[{height + 1};1H")
    sys.stdout.flush()
    _clear_stop(parent)
    launch(argv)
    return PINNED


def _ignore_interrupt():
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        pass


def animate(frame_for, height, fps, spin, parent):
    _ignore_interrupt()
    angles = list(raster.START_ANGLES)
    width = frame_width(frame_for(angles))
    size = tuple(shutil.get_terminal_size())
    try:
        while parent_alive(parent) and not os.path.exists(stop_path(parent)):
            term = shutil.get_terminal_size()
            if tuple(term) != size:
                size = tuple(term)
                rows = term.lines
                sys.stdout.write(SAVE + margins(height, rows) + RESTORE)
            if term.columns >= width:
                sys.stdout.write(draw(frame_for(angles)))
            sys.stdout.flush()
            angles = [a + s for a, s in zip(angles, spin)]
            time.sleep(1 / max(fps, 1))
    except (OSError, ValueError):
        return
    finally:
        _clear_stop(parent)
        try:
            sys.stdout.write(SAVE + "\x1b[r" + RESTORE)
            sys.stdout.flush()
        except (OSError, ValueError):
            pass