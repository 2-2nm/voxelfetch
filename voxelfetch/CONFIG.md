# voxelfetch config

Edit `config.json` (installed at `%USERPROFILE%\.voxelfetch\config.json`). Lookup order:
`--config FILE` -> `$VOXELFETCH_CONFIG` -> `config.json` next to the program -> built-in defaults.
The installer never overwrites an existing `config.json`.

## `modules`

The rows, top to bottom. Each entry is a name (`"cpu"`) or an object (`{"type": "cpu", ...}`).
Remove an entry to hide it, reorder to move it. Rows that cannot be detected are hidden automatically.

| type | default key | fields for `format` |
|---|---|---|
| `title` | | `{user}` `{host}` |
| `separator` | | options: `char`, `length` |
| `break` | | blank line |
| `colors` | | option: `style` = `block` / `circle` |
| `os` | OS | `{name}` `{version}` `{arch}` |
| `host` | Host | `{model}` |
| `kernel` | Kernel | `{name}` `{version}` |
| `uptime` | Uptime | `{text}` |
| `packages` | Packages | `{text}` (scoop, choco) |
| `shell` | Shell | `{name}` |
| `display` | Display | `{width}` `{height}` `{hz}` |
| `de` `wm` `wmtheme` `cursor` `terminal` `locale` | | `{name}` |
| `theme` | Theme | `{apps}` `{system}` (Light/Dark) |
| `cpu` | CPU | `{name}` `{cores}` `{freq}` `{freq_mhz}` |
| `gpu` | GPU | `{name}` `{vram}` |
| `memory` `swap` | Memory / Swap | `{used}` `{total}` `{pct}` |
| `disk` | Disk ({mount}) | `{used}` `{total}` `{pct}` `{fs}` `{mount}` |
| `localip` | Local IP | `{ip}` |
| `battery` | Battery | `{level}` `{status}` |
| `date` | Date | `{text}`; option `strftime` |
| `custom` | | static text: `{"type":"custom","key":"Hi","format":"hello"}` |

Per-entry options: `key` (label; may use fields, e.g. `"Disk ({mount})"`), `format`, `keyColor`.
`{pct}` is coloured green/yellow/red by how full it is. Empty fields drop out cleanly
(`"{name} ({cores}) @ {freq}"` with no freq becomes `"{name} ({cores})"`).

CPU clock: `{"type":"cpu","freq":"max"}` (default) shows the max boost clock only;
`"none"` hides it; a number (GHz) forces a value, e.g. `"freq": 5.1`.

## `display`

`separator`, `keyPrefix`, `keyWidth` (0 = no alignment), `indent`, and the colours
`keyColor` `titleColor` `textColor` `separatorColor` (`#rrggbb`).

Old voxelfetch look:
`"display": {"separator": " ➔ ", "keyPrefix": "▸ ", "keyWidth": 9, "indent": 2}`
