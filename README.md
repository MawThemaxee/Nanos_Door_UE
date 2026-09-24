# Nanos Door — Unreal mapping kit

Place doors directly in your Unreal Engine 5.7 map, then export them so the
`door` nanos world package spawns real, networked doors at the same spots.

This repository is an Unreal **content plugin** (`nanos-door`), the same layout as any asset pack in
the nanos world ADK. It only holds the Unreal side (a marker Blueprint + an export script). The door
logic itself (open/close, trigger vs. interact key, locking) lives in the separate `door` Lua
package, in the Nanos Door repository.

## Why a marker + export, not a "live" Blueprint door?

The nanos world **server doesn't run Unreal**. Anything placed in a map only exists on clients, so
a Blueprint door placed in the level couldn't be opened/locked by the server, or kept in sync
between players. Instead:

1. You place `BP_DoorMarker` actors in your level. They're **editor-only**, so they're never cooked
   into the map.
2. `Content/Python/export_doors.py` reads every marker (position, rotation, settings) and writes a
   `MapDoors.lua` file.
3. Your map package's server script requires that file, and the `door` package spawns the real doors.

It follows the same idea as the ADK's own `WBP_LuaCodeGenerator` (placeholders scanned into Lua
spawn code), but carries door-specific settings (type, trigger/interact mode, lock).

## Requirements

- Unreal Engine **5.7** (the version nanos world requires)
- The nanos world ADK (Steam app "nanos world ADK", or
  [GitHub](https://github.com/nanos-world/assets-development-kit))
- The **Python Editor Script Plugin**: `nanos-door.uplugin` declares it as a dependency, so it's
  enabled with the plugin
- [Git LFS](https://git-lfs.com/): `.uasset`/`.umap` files are stored with LFS
- On the server: the `door` package, version with `BaseDoor.SpawnFromList`

## Install

Clone this repo **into your ADK's `Plugins/` folder** as `nanos-door`:

```bash
cd <path-to-ADK>/Plugins
git lfs install
git clone <this-repo-url> nanos-door
```

Or keep the clone elsewhere and link it in (Windows, PowerShell, no admin needed):

```powershell
New-Item -ItemType Junction -Path "<path-to-ADK>\Plugins\nanos-door" -Target "<path-to-clone>"
```

Restart the editor. The plugin is `EnabledByDefault`, and its content shows up in the Content Browser
under **Plugins > nanos-door Content** (enable *Show Plugin Content* in the browser settings if hidden).
Never put anything inside the ADK's `Content/NanosWorld/`: the ADK must not be modified there.

## Creating `BP_DoorMarker` (one-time, maintainer only)

Blueprints are binary assets, so this is done once in the editor and then committed. Everyone else
just gets it with `git pull`.

1. In the Content Browser, go to `nanos-door Content/Blueprints/` (create the folder). Right-click **Blueprint Class**,
   pick **Actor**, and name it `BP_DoorMarker`.
2. **Components**: add an **Arrow** (points toward the door's forward axis) and a **Billboard**, so
   the marker is visible and selectable in the viewport.
3. **Class Defaults**: tick **Is Editor Only Actor** (so it's never cooked) and **Actor Hidden In
   Game**.
4. **Variables**: add them with these exact names, and tick the eye icon (**Instance Editable**) on
   each:

   | Name           | Type    | Default       | Meaning                                                 |
   |----------------|---------|---------------|---------------------------------------------------------|
   | `DoorType`     | String  | `Hinge`       | `Hinge` or `Sliding` (any type registered in `door`)    |
   | `Interactable` | Boolean | false         | false = trigger (walk in), true = look at it + press E  |
   | `StartLocked`  | Boolean | false         | Spawn the door locked                                   |
   | `DoorAsset`    | String  | *(empty)*     | Mesh asset, eg. `nanos-world::SM_Cube`; empty = default |
   | `DoorScale`    | Vector  | `0, 0, 0`     | Panel scale; `0,0,0` = the door type's default          |
   | `SlideOffset`  | Vector  | `0, 100, 0`   | Sliding only: how far it slides, in the door's local space |

5. Compile, save, then commit `BP_DoorMarker.uasset`.

Variable names must match exactly: the export script reads them by name.

## Mapping workflow

1. Drag `BP_DoorMarker` into your level wherever you want a door and rotate it. For a `Hinge`
   door, the marker is the **hinge** (the panel is attached 50 units along its X axis). For a
   `Sliding` door, the marker is the panel's center.
2. Set its variables in the **Details** panel.
3. **Tools > Execute Python Script...** and pick `<path-to-ADK>/Plugins/nanos-door/Content/Python/export_doors.py`.
   The Output Log prints where the file was written: by default
   `<Project>/Saved/NanosDoor/<LevelName>_MapDoors.lua`. Set `OUTPUT_PATH` at the top of the script
   to write straight into your map package.
4. Copy that file into your map package as `Server/MapDoors.lua`, and require it from
   `Server/Index.lua`:

   ```lua
   Package.Require("MapDoors.lua")
   ```

5. In the map package's `Package.toml`, list `door` so it loads first:

   ```toml
   [map]
       packages_requirements = [ "door" ]
   ```

Re-run the export every time you move, add or remove a marker. The output is sorted by actor
label, so an unchanged map exports an identical file (except the date line).

## Notes & known limitations

- The default `Hinge` panel is `nanos-world::SM_Plane`, which lies flat, so a hinge door using the
  default mesh needs the marker rotated **Roll = 90** to stand upright. With a custom `DoorAsset`
  that is already upright, keep Roll at 0.
- The markers don't preview the final panel mesh/size in the viewport: check placement in game.
- `export_doors.py` is only tested against a mocked `unreal` module so far; report any Python API
  error from the Output Log.
