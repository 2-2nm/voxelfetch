<h1 align="center">voxelfetch</h1>

<p align="center">
  <img src="https://img.shields.io/badge/VERSION-1.0.0-ff6b6b?style=for-the-badge" alt="version">
  <img src="https://img.shields.io/badge/PYTHON-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="python">
  <img src="https://img.shields.io/badge/SHELL-POWERSHELL-5391fe?style=for-the-badge&logo=powershell&logoColor=white" alt="shell">
  <img src="https://img.shields.io/badge/PLATFORM-WINDOWS%2010%20%2F%2011-0078d4?style=for-the-badge" alt="platform">
  <img src="https://img.shields.io/badge/LICENSE-MIT-a3e635?style=for-the-badge" alt="license">
</p>

<p align="center">
  A terminal system fetch with a rotating ASCII 3D model.
</p>

---

<p align="center">
  <img width="800" height="450" alt="download" src="https://github.com/user-attachments/assets/dc0959c2-3a0f-415f-97fc-80de8447bd5e" />

</p>

## What is it?

voxelfetch shows your system info (OS, CPU, GPU, memory, disk, uptime and more) in your PowerShell, next to a 3D wireframe model that spins in real time. Models are plain `.vxl` files, so you can swap in your own.

## Install

1. Download `voxelfetch-setup.exe` from the [latest release](../../releases/latest) and run it.
2. If Windows SmartScreen shows "Windows protected your PC", click **More info → Run anyway**. The installer is not code-signed yet.
3. If PowerShell blocks profile scripts, the installer asks to set the execution policy to `RemoteSigned` for your user. Answer `Y`.
4. Open a new PowerShell window.

No admin rights and no Python needed. It installs to `%LOCALAPPDATA%\voxelfetch` and adds a marked block to your PowerShell profile. Your existing profile content is left untouched, and a backup is saved next to it as `.voxelfetch.bak`.

## Usage

```powershell
voxelfetch                      # show once
voxelfetch --spin               # spin until a key is pressed
voxelfetch --spin 5             # spin for 5 seconds
voxelfetch --pin                # keep the animated header pinned at the top
voxelfetch --unpin              # release a pinned header
voxelfetch --speed 2            # rotation speed multiplier
voxelfetch path\to\model.vxl    # use a specific model
```

## Custom models

Models are `.vxl` files. You can make your own with my other app, [VoxelText-ASCII-](https://github.com/2-2nm/VoxelText-ASCII-), and export a `3dmodel.vxl`.

To use it, open your PowerShell profile (`notepad $PROFILE`), find the voxelfetch block, uncomment the `VOXELFETCH_MODEL` line and set the path:

```powershell
$env:VOXELFETCH_MODEL = "C:\path\to\3dmodel.vxl"
```

Some presets are included in [`vxl files`](vxl%20files).

## Configuration

Edit `%LOCALAPPDATA%\voxelfetch\config.json` to choose which rows are shown, their order, labels and formats. See [CONFIG.md](voxelfetch/CONFIG.md) for every option. To use a config from somewhere else, set `VOXELFETCH_CONFIG` or pass `--config FILE`.

## Uninstall

Settings → Apps → voxelfetch, or run:

```powershell
voxelfetch-setup.exe --uninstall
```

## Build from source

Requires Python and PyInstaller.

```powershell
git clone https://github.com/2-2nm/voxelfetch
cd voxelfetch
build.bat
```

The installer is created at `dist\voxelfetch-setup.exe`.

## License

[MIT](LICENSE)
