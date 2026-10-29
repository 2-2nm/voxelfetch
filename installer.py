import argparse
import base64
import codecs
import ctypes
import os
import re
import shutil
import subprocess
import sys
import winreg

BEGIN = "# >>> voxelfetch >>>"
END = "# <<< voxelfetch <<<"
LEGACY_MARKERS = [("# >>> vfetch >>>", "# <<< vfetch <<<")]
LEGACY_DIRS = (".voxelfetch", ".vfetch")
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\voxelfetch"
KEEP_ON_UPGRADE = ("config.json", "default.vxl")
BLOCKING_POLICIES = {"restricted", "allsigned"}
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

BLOCK = r'''# >>> voxelfetch >>>
# Custom model: uncomment and set the path to your .vxl file
# $env:VOXELFETCH_MODEL = "C:\path\to\model.vxl"
# Custom config: uncomment and set the path to your config.json
# $env:VOXELFETCH_CONFIG = "C:\path\to\config.json"
function voxelfetch { & "$env:LOCALAPPDATA\voxelfetch\voxelfetch.exe" --shell "PowerShell $($PSVersionTable.PSVersion)" --box 64x28 @args }
if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and ([Environment]::GetCommandLineArgs() -notcontains '-NonInteractive') -and (Test-Path "$env:LOCALAPPDATA\voxelfetch\voxelfetch.exe")) { voxelfetch --spin }
# <<< voxelfetch <<<'''


def install_dir():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local"), "voxelfetch")


def payload_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "payload")


def run_ps(exe, command):
    try:
        done = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", "replace").strip()


def find_hosts():
    found = []
    for name in ("powershell.exe", "pwsh.exe"):
        exe = shutil.which(name)
        if exe:
            found.append(exe)
    return found


def documents_dir():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
    return buf.value or os.path.join(os.path.expanduser("~"), "Documents")


def profile_paths(exes):
    unique = {}
    for exe in exes:
        encoded = run_ps(exe, "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PROFILE))")
        if not encoded:
            continue
        try:
            path = base64.b64decode(encoded).decode("utf-8")
        except ValueError:
            continue
        unique.setdefault(os.path.normcase(path), path)
    if not unique:
        fallback = os.path.join(documents_dir(), "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1")
        unique[os.path.normcase(fallback)] = fallback
    return list(unique.values())


def read_text(path):
    if not os.path.exists(path):
        return "", "utf-8-sig"
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(codecs.BOM_UTF8):
        return raw[len(codecs.BOM_UTF8):].decode("utf-8"), "utf-8-sig"
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("mbcs"), "mbcs"


def write_text(path, text, encoding):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(text.encode(encoding) if text else b"")


def strip_blocks(text):
    for begin, end in [(BEGIN, END)] + LEGACY_MARKERS:
        pattern = r"(?s)" + re.escape(begin) + r".*?" + re.escape(end) + r"(?:\r?\n)?"
        text = re.sub(pattern, "", text)
    return text


def newline_for(text):
    return "\n" if ("\n" in text and "\r\n" not in text) else "\r\n"


def install_profile(path):
    text, encoding = read_text(path)
    nl = newline_for(text)
    backup = path + ".voxelfetch.bak"
    if os.path.exists(path) and not os.path.exists(backup):
        shutil.copy2(path, backup)
    body = strip_blocks(text).rstrip()
    block = nl.join(BLOCK.splitlines())
    prefix = body + nl + nl if body else ""
    write_text(path, prefix + block + nl, encoding)


def uninstall_profile(path):
    if not os.path.exists(path):
        return False
    text, encoding = read_text(path)
    stripped = strip_blocks(text)
    if stripped == text:
        return False
    body = stripped.rstrip()
    write_text(path, body + newline_for(text) if body else "", encoding)
    return True


def execution_policy(exe):
    return run_ps(exe, "Get-ExecutionPolicy").lower()


def ensure_policy(exes, interactive):
    blocked = [exe for exe in exes if execution_policy(exe) in BLOCKING_POLICIES]
    if not blocked:
        return
    answer = "n"
    if interactive:
        try:
            answer = input("The PowerShell execution policy blocks profile scripts. Set it to RemoteSigned for the current user? [Y/n] ").strip().lower()
        except EOFError:
            answer = "n"
    if answer in ("", "y", "yes"):
        for exe in blocked:
            run_ps(exe, "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force")
    for exe in blocked:
        if execution_policy(exe) in BLOCKING_POLICIES:
            print(f"Warning: {os.path.basename(exe)} will not load your profile until the execution policy allows scripts.")


def copy_payload(src, dst):
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out, exist_ok=True)
        for name in files:
            target = os.path.join(out, name)
            if rel == "." and name in KEEP_ON_UPGRADE and os.path.exists(target):
                continue
            shutil.copy2(os.path.join(root, name), target)


def register(target):
    if not getattr(sys, "frozen", False):
        return
    uninstaller = os.path.join(target, "uninstall.exe")
    shutil.copy2(sys.executable, uninstaller)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "voxelfetch")
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}" --uninstall')
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, target)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def unregister():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass


def do_install(exes, args):
    src = payload_dir()
    if not os.path.isdir(src):
        print("Installer payload is missing.")
        return 1
    target = install_dir()
    home = os.path.expanduser("~")
    for name in LEGACY_DIRS:
        shutil.rmtree(os.path.join(home, name), ignore_errors=True)
    shutil.rmtree(os.path.join(target, "_internal"), ignore_errors=True)
    try:
        copy_payload(src, target)
        if args.model:
            shutil.copy2(args.model, os.path.join(target, "default.vxl"))
        register(target)
    except OSError as exc:
        print(f"Install failed: {exc}")
        print("Close every terminal that is running voxelfetch and try again.")
        return 1
    for path in profile_paths(exes):
        install_profile(path)
        print(f"Updated {path}")
    ensure_policy(exes, not args.quiet)
    print(f"Installed to {target}")
    print("Open a new terminal to see voxelfetch.")
    return 0


def do_uninstall(exes):
    target = install_dir()
    for path in profile_paths(exes):
        if uninstall_profile(path):
            print(f"Cleaned {path}")
    unregister()
    shutil.rmtree(target, ignore_errors=True)
    if os.path.exists(target):
        subprocess.Popen(
            ["cmd", "/c", f'ping -n 3 127.0.0.1 >nul & rmdir /s /q "{target}"'],
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True,
        )
    print("voxelfetch removed.")
    return 0


def pause(quiet):
    if quiet:
        return
    try:
        input("Press Enter to close...")
    except EOFError:
        pass


def main():
    parser = argparse.ArgumentParser(prog="voxelfetch-setup")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--model", metavar="FILE")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    exes = find_hosts()
    if not exes:
        print("PowerShell was not found.")
        pause(args.quiet)
        return 1
    code = do_uninstall(exes) if args.uninstall else do_install(exes, args)
    pause(args.quiet)
    return code


if __name__ == "__main__":
    sys.exit(main())
