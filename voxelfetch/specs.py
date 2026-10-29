import ctypes
import datetime
import getpass
import glob
import os
import platform
import re
import shutil
import socket
import struct
import sys
from collections import namedtuple

IS_WIN = os.name == "nt"
GIB = 1024 ** 3
MIB = 1024 ** 2

_NT_VERSION = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
_BIOS = r"HARDWARE\DESCRIPTION\System\BIOS"
_CPU_ROOT = r"HARDWARE\DESCRIPTION\System\CentralProcessor"
_CPU = _CPU_ROOT + r"\0"
_GPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_THEMES = r"Software\Microsoft\Windows\CurrentVersion\Themes"
_CURSORS = r"Control Panel\Cursors"
_GPU_SKIP = ("Microsoft Basic", "Remote", "Virtual", "Meta Virtual")
_PLACEHOLDERS = ("system product name", "to be filled", "default string", "o.e.m.")
_ARCH = {"AMD64": "x86_64", "ARM64": "aarch64", "x86": "i686"}


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _ProcessorPower(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulong) for n in
                ("Number", "MaxMhz", "CurrentMhz", "MhzLimit", "MaxIdleState", "CurrentIdleState")]


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def _reg(path, name, default=None, hive=None):
    if not IS_WIN:
        return default
    import winreg
    try:
        with winreg.OpenKey(hive if hive is not None else winreg.HKEY_LOCAL_MACHINE, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def _reg_user(path, name, default=None):
    if not IS_WIN:
        return default
    import winreg
    return _reg(path, name, default, winreg.HKEY_CURRENT_USER)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _clean(text):
    return " ".join(str(text).split())


def _size(n):
    return f"{n / GIB:.2f} GiB" if n >= GIB else f"{n / MIB:.2f} MiB"


def _pct(used, total):
    return round(used * 100 / total) if total else None


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _arch():
    return _ARCH.get(platform.machine(), platform.machine())

_CPU_NOISE = (
    (r"\((?:R|TM)\)", ""),
    (r"\s*@\s*[\d.]+\s*[GM]Hz", ""),           
    (r"\b\d+-Core Processor\b", ""),
    (r"\bCPU\b", ""),
    (r"\bProcessor\b", ""),
)


def tidy_cpu_name(name):
    for pattern, repl in _CPU_NOISE:
        name = re.sub(pattern, repl, name, flags=re.I)
    return _clean(name)


def _cpu_name():
    if IS_WIN:
        raw = _reg(_CPU, "ProcessorNameString", "") or platform.processor()
    else:
        match = re.search(r"^model name\s*:\s*(.+)$", _read("/proc/cpuinfo"), re.M)
        raw = match.group(1) if match else platform.processor()
    return tidy_cpu_name(_clean(raw or "Unknown CPU"))


def parse_smbios_cpu_max(raw):
    """Highest populated-socket 'Max Speed' (MHz) found in a RawSMBIOSData blob (SMBIOS Type 4)."""
    if len(raw) < 8:
        return None
    length = struct.unpack_from("<I", raw, 4)[0]
    data = raw[8:8 + length]
    pos, best = 0, 0
    while pos + 4 <= len(data):
        kind, size = data[pos], data[pos + 1]
        if size < 4 or kind == 127:
            break
        if kind == 4 and size >= 0x19 and pos + 0x19 <= len(data):
            populated = data[pos + 0x18] & 0x40
            if data[pos + 5] == 3 and populated:          
                best = max(best, struct.unpack_from("<H", data, pos + 0x14)[0])
        end = data.find(b"\0\0", pos + size)            
        if end < 0:
            break
        pos = end + 2
    return best or None


def _smbios_max_mhz():
    kernel = ctypes.windll.kernel32
    sig = 0x52534D42                                       # 'RSMB'
    size = kernel.GetSystemFirmwareTable(sig, 0, None, 0)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if kernel.GetSystemFirmwareTable(sig, 0, buf, size) != size:
        return None
    return parse_smbios_cpu_max(buf.raw)


def _power_mhz():
    count = os.cpu_count() or 1
    rows = (_ProcessorPower * count)()
    if ctypes.windll.powrprof.CallNtPowerInformation(11, None, 0, rows, ctypes.sizeof(rows)) != 0:
        return []
    return [v for r in rows for v in (r.MaxMhz, r.MhzLimit) if v]


def _registry_mhz():
    values = []
    for i in range(os.cpu_count() or 1):
        mhz = _reg(f"{_CPU_ROOT}\\{i}", "~MHz")
        if mhz:
            values.append(int(mhz))
    return values


def cpu_max_mhz():
    if not IS_WIN:
        files = glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/cpuinfo_max_freq")
        khz = [int(v) for v in (_read(f).strip() for f in files) if v.isdigit()]
        return max(khz) // 1000 if khz else None
    base_values = []
    for probe in (_registry_mhz, _power_mhz):
        try:
            base_values += probe()
        except Exception:
            pass
    base = min(base_values) if base_values else 0
    best = max(base_values, default=0)
    try:
        smbios = _smbios_max_mhz()
    except Exception:
        smbios = None
    if smbios and (not base or base <= smbios <= base * 3):  
        best = max(best, smbios)
    return best or None


def _freq_text(mhz):
    return f"{mhz / 1000:.2f} GHz"


def mod_cpu(opts, ctx):
    mode = opts.get("freq", "max")
    mhz = None
    if isinstance(mode, (int, float)) and not isinstance(mode, bool):
        mhz = float(mode) * 1000                      
    elif mode != "none":
        mhz = cpu_max_mhz()
    return {"name": _cpu_name(), "cores": os.cpu_count() or 1,
            "freq": _freq_text(mhz) if mhz else "", "freq_mhz": round(mhz) if mhz else ""}


def mod_title(opts, ctx):
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "user")
    return {"user": user, "host": platform.node() or "localhost"}


def mod_host(opts, ctx):
    if IS_WIN:
        for key in ("SystemProductName", "SystemFamily"):
            value = _clean(_reg(_BIOS, key, ""))
            if value and not any(p in value.lower() for p in _PLACEHOLDERS):
                return {"model": value}
        return {"model": platform.node() or "Unknown"}
    value = _clean(_read("/sys/devices/virtual/dmi/id/product_name"))
    return {"model": value} if value else None


def mod_os(opts, ctx):
    if IS_WIN:
        build = int(_reg(_NT_VERSION, "CurrentBuild", 0) or 0)
        name = _clean(_reg(_NT_VERSION, "ProductName", "") or platform.system())
        if build >= 22000:
            name = name.replace("Windows 10", "Windows 11")
        return {"name": name, "version": _reg(_NT_VERSION, "DisplayVersion") or "", "arch": _arch()}
    match = re.search(r'^PRETTY_NAME="?([^"\n]+)', _read("/etc/os-release"), re.M)
    return {"name": match.group(1) if match else platform.system(), "version": "", "arch": _arch()}


def mod_kernel(opts, ctx):
    if not IS_WIN:
        return {"name": platform.system(), "version": platform.release()}
    ubr = _reg(_NT_VERSION, "UBR")
    return {"name": "WIN32_NT", "version": f"{platform.version()}{f'.{ubr}' if ubr is not None else ''}"}


def _uptime_seconds():
    if IS_WIN:
        tick = ctypes.windll.kernel32.GetTickCount64
        tick.restype = ctypes.c_ulonglong
        return int(tick() // 1000)
    text = _read("/proc/uptime").split()
    return int(float(text[0])) if text else None


def mod_uptime(opts, ctx):
    seconds = _uptime_seconds()
    if seconds is None:
        return None
    days, rest = divmod(seconds // 60, 1440)
    hours, mins = divmod(rest, 60)
    parts = [_plural(n, w) for n, w in ((days, "day"), (hours, "hour"), (mins, "min")) if n]
    return {"text": ", ".join(parts) or "0 mins"}


def _count_dirs(path, skip=()):
    try:
        return sum(1 for e in os.scandir(path) if e.is_dir() and e.name not in skip)
    except OSError:
        return 0


def mod_packages(opts, ctx):
    scoop = os.path.join(os.environ.get("SCOOP") or os.path.join(os.path.expanduser("~"), "scoop"), "apps")
    choco = os.path.join(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"), "lib")
    counts = [("scoop", _count_dirs(scoop, ("scoop",))), ("choco", _count_dirs(choco))]
    parts = [f"{n} ({name})" for name, n in counts if n]
    return {"text": ", ".join(parts)} if parts else None


def mod_shell(opts, ctx):
    name = ctx.get("shell") or os.environ.get("VOXELFETCH_SHELL") or os.path.basename(
        os.environ.get("SHELL") or os.environ.get("COMSPEC") or "unknown")
    return {"name": name}


def mod_display(opts, ctx):
    if not IS_WIN:
        return None
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)    
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
    width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    hz = ""
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
    hdc = user32.GetDC(None)
    if hdc:
        rate = gdi32.GetDeviceCaps(hdc, 116)              
        user32.ReleaseDC(None, hdc)
        hz = rate if rate > 1 else ""
    return {"width": width, "height": height, "hz": hz} if width and height else None


def mod_de(opts, ctx):
    if not IS_WIN:
        return {"name": os.environ["XDG_CURRENT_DESKTOP"]} if os.environ.get("XDG_CURRENT_DESKTOP") else None
    build = int(_reg(_NT_VERSION, "CurrentBuild", 0) or 0)
    return {"name": "Fluent" if build >= 22000 else "Metro" if build >= 9200 else "Aero"}


def mod_wm(opts, ctx):
    return {"name": "Desktop Window Manager"} if IS_WIN else None


def mod_wmtheme(opts, ctx):
    path = _reg_user(_THEMES, "CurrentTheme", "")
    if not path:
        return None
    return {"name": os.path.splitext(os.path.basename(path))[0].title()}


def mod_theme(opts, ctx):
    apps, system = (_reg_user(_PERSONALIZE, k) for k in ("AppsUseLightTheme", "SystemUsesLightTheme"))
    if apps is None and system is None:
        return None
    return {"apps": "Light" if apps else "Dark", "system": "Light" if system else "Dark"}


def mod_cursor(opts, ctx):
    if not IS_WIN:
        return None
    return {"name": _reg_user(_CURSORS, "", "") or "Windows Default"}


def mod_terminal(opts, ctx):
    env = os.environ
    if env.get("TERM_PROGRAM"):
        name = env["TERM_PROGRAM"]
    elif env.get("WT_SESSION"):
        name = "Windows Terminal"
    else:
        name = "Console Host" if IS_WIN else env.get("TERM", "unknown")
    return {"name": name}


def _vram(path):
    raw = _reg(path, "HardwareInformation.qwMemorySize")
    if isinstance(raw, (bytes, bytearray)):
        raw = int.from_bytes(raw, "little")
    return _size(raw) if raw else ""


def mod_gpu(opts, ctx):
    found = []
    for i in range(16):
        path = f"{_GPU_CLASS}\\{i:04d}"
        name = _reg(path, "DriverDesc")
        if name and not any(s in name for s in _GPU_SKIP):
            found.append({"name": _clean(name), "vram": _vram(path)})
    return found or None


def mod_memory(opts, ctx):
    if IS_WIN:
        stat = _MemStatus()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total, used = stat.ullTotalPhys, stat.ullTotalPhys - stat.ullAvailPhys
    else:
        info = dict(re.findall(r"^(\w+):\s+(\d+) kB", _read("/proc/meminfo"), re.M))
        if "MemTotal" not in info:
            return None
        total = int(info["MemTotal"]) * 1024
        used = total - int(info.get("MemAvailable", info.get("MemFree", 0))) * 1024
    return {"used": _size(used), "total": _size(total), "pct": _pct(used, total)}


def mod_swap(opts, ctx):
    if not IS_WIN:
        return None
    buf = ctypes.create_string_buffer(64 * 1024)
    ret = ctypes.c_ulong(0)
    if ctypes.windll.ntdll.NtQuerySystemInformation(18, buf, len(buf), ctypes.byref(ret)) != 0 or not ret.value:
        return None
    total = used = offset = 0
    while True:                                       
        nxt, pages, in_use, _peak = struct.unpack_from("<IIII", buf, offset)
        total, used = total + pages, used + in_use
        if not nxt:
            break
        offset += nxt
    page = 4096
    return {"used": _size(used * page), "total": _size(total * page), "pct": _pct(used, total)} if total else None


def _fs_name(root):
    if not IS_WIN:
        return ""
    fs = ctypes.create_unicode_buffer(32)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(root, None, 0, None, None, None, fs, len(fs))
    return fs.value if ok else ""


def _fixed_roots():
    if not IS_WIN:
        return ["/"]
    kernel = ctypes.windll.kernel32
    mask = kernel.GetLogicalDrives()
    roots = [f"{chr(65 + i)}:\\" for i in range(26) if mask >> i & 1]
    return [r for r in roots if kernel.GetDriveTypeW(r) == 3]


def mod_disk(opts, ctx):
    rows = []
    for root in _fixed_roots():
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        rows.append({"mount": root.rstrip("\\"), "used": _size(usage.used), "total": _size(usage.total),
                     "pct": _pct(usage.used, usage.total), "fs": _fs_name(root)})
    return rows or None


def mod_localip(opts, ctx):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))          
            return {"ip": sock.getsockname()[0]}
    except OSError:
        return None


def mod_battery(opts, ctx):
    if not IS_WIN:
        return None
    status = _PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)) or status.BatteryFlag & 128:
        return None
    level = status.BatteryLifePercent
    if level > 100:
        return None
    state = "Charging" if status.BatteryFlag & 8 else "AC connected" if status.ACLineStatus == 1 else "Discharging"
    return {"level": level, "status": state}


def mod_locale(opts, ctx):
    if not IS_WIN:
        return {"name": os.environ.get("LANG", "")} if os.environ.get("LANG") else None
    buf = ctypes.create_unicode_buffer(85)
    return {"name": buf.value} if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, len(buf)) else None


def mod_date(opts, ctx):
    return {"text": datetime.datetime.now().strftime(opts.get("strftime", "%Y-%m-%d %H:%M:%S"))}


def mod_empty(opts, ctx):
    return {}


Module = namedtuple("Module", "kind key format fn")


def _item(key, fmt, fn):
    return Module("item", key, fmt, fn)


MODULES = {
    "title": Module("title", "", "{user}@{host}", mod_title),
    "separator": Module("separator", "", "", mod_empty),
    "break": Module("break", "", "", mod_empty),
    "colors": Module("colors", "", "", mod_empty),
    "custom": Module("item", "", "", mod_empty),
    "os": _item("OS", "{name} {version} {arch}", mod_os),
    "host": _item("Host", "{model}", mod_host),
    "kernel": _item("Kernel", "{name} {version}", mod_kernel),
    "uptime": _item("Uptime", "{text}", mod_uptime),
    "packages": _item("Packages", "{text}", mod_packages),
    "shell": _item("Shell", "{name}", mod_shell),
    "display": _item("Display", "{width}x{height} @ {hz} Hz", mod_display),
    "de": _item("DE", "{name}", mod_de),
    "wm": _item("WM", "{name}", mod_wm),
    "wmtheme": _item("WM Theme", "{name}", mod_wmtheme),
    "theme": _item("Theme", "{apps}", mod_theme),
    "cursor": _item("Cursor", "{name}", mod_cursor),
    "terminal": _item("Terminal", "{name}", mod_terminal),
    "cpu": _item("CPU", "{name} ({cores}) @ {freq}", mod_cpu),
    "gpu": _item("GPU", "{name} ({vram})", mod_gpu),
    "memory": _item("Memory", "{used} / {total} ({pct}%)", mod_memory),
    "swap": _item("Swap", "{used} / {total} ({pct}%)", mod_swap),
    "disk": _item("Disk ({mount})", "{used} / {total} ({pct}%) - {fs}", mod_disk),
    "localip": _item("Local IP", "{ip}", mod_localip),
    "battery": _item("Battery", "{level}% [{status}]", mod_battery),
    "locale": _item("Locale", "{name}", mod_locale),
    "date": _item("Date", "{text}", mod_date),
}


def collect(modules, shell_name=None):
    ctx = {"shell": shell_name}
    entries = []
    for spec in modules:
        opts = {"type": spec} if isinstance(spec, str) else dict(spec) if isinstance(spec, dict) else {}
        name = str(opts.get("type", "")).lower()
        module = MODULES.get(name)
        if module is None:
            print(f"voxelfetch: unknown module '{name}' in config, skipped", file=sys.stderr)
            continue
        try:
            result = module.fn(opts, ctx)
        except Exception:
            result = None
        if result is None:
            continue
        for fields in ([result] if isinstance(result, dict) else result):
            entries.append({
                "kind": module.kind,
                "key": opts.get("key", module.key),
                "format": opts.get("format", module.format),
                "default_format": module.format,
                "fields": fields,
                "opts": opts,
            })
    return entries
