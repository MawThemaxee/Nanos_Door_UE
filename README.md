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
   the marker is visible and selectable in the viewport, plus a **Static Mesh** component named
   `Preview` (Details > Collision Presets: **NoCollision**). The Construction Script (step 6) fills
   it in.
3. **Class Defaults**: tick **Is Editor Only Actor** (so it's never cooked) and **Actor Hidden In
   Game**.
4. **Variables**: add them with these exact names, and tick the eye icon (**Instance Editable**) on
   each:

   | Name           | Type    | Default       | Meaning                                                 |
   |----------------|---------|---------------|---------------------------------------------------------|
   | `DoorType`     | String  | `Hinge`       | `Hinge` or `Sliding` (any type registered in `door`)    |
   | `Interactable` | Boolean | false         | false = trigger (walk in), true = look at it + press E  |
   | `StartLocked`  | Boolean | false         | Spawn the door locked                                   |
   | `InteractionMode` | String | *(empty)*   | *Optional.* A mode name registered in Lua (`manual`, or a custom one like `timed`). Overrides `Interactable` when set |
   | `TriggerRadius` | Float  | `0`           | *Optional.* Trigger sphere radius; `0` = default (150)  |
   | `DoorMesh`     | Static Mesh (Object Reference) | *(none)* | Door mesh picked visually, previewed in the viewport and converted to its nanos path on export; none = default plane |
   | `DoorAsset`    | String  | *(empty)*     | Manual nanos path, eg. `nanos-world::SM_Cube`. Overrides `DoorMesh` when set |
   | `DoorScale`    | Vector  | `0, 0, 0`     | Panel scale; `0,0,0` = the door type's default          |
   | `SlideOffset`  | Vector  | `0, 100, 0`   | Sliding only: how far it slides, in the door's local space |

5. Compile.
6. **Construction Script** (the tab next to *Event Graph*): chain these three nodes after the purple
   *Construction Script* node, all with `Preview` as **Target**:

   - **Set Static Mesh**, *New Mesh* =
     `Select` (Index = `Is Valid(DoorMesh)`, **True** = `DoorMesh`,
     **False** = `Plane` from `/Engine/BasicShapes/`, tick *Show Engine Content* in the picker's
     settings to see it).
   - **Set Relative Location**, *New Location* =
     `Select` (Index = `DoorType == "Hinge"` with an *Equal (String)* node,
     **True** = `50, 0, 0`, **False** = `0, 0, 0`).
   - **Set Relative Scale 3D**, *New Scale* =
     `Select` (Index = `DoorScale == 0,0,0` with an *Equal (Vector)* node,
     **False** = `DoorScale`,
     **True** = another `Select` on `DoorType == "Hinge"`: **True** = `1, 2, 1`, **False** = `1, 2, 0.1`).

   These mirror the Lua side (`HingeDoor` panel offset 50 on X, `HingeDoor.DEFAULT_SCALE` /
   `SlidingDoor.DEFAULT_SCALE`). If you change those defaults in the `door` package, update them here too.
7. Compile, save, then commit `BP_DoorMarker.uasset`.

Variable names must match exactly: the export script reads them by name.

## Mapping workflow

1. Drag `BP_DoorMarker` into your level wherever you want a door and rotate it. For a `Hinge`
   door, the marker is the **hinge** (the panel is attached 50 units along its X axis). For a
   `Sliding` door, the marker is the panel's center.
2. Set its variables in the **Details** panel. The `Preview` mesh updates live, so what you see is
   where the door panel will be in game (closed).
3. **Tools > Execute Python Script...** and pick `<path-to-ADK>/Plugins/nanos-door/Content/Python/export_doors.py`.
   The Output Log prints where the file was written: by default
   `<Project>/Saved/NanosDoor/<LevelName>_MapDoors.lua`. To change that, create
   `Content/Python/export_doors_local.py` next to the script (git-ignored, so your paths stay on your
   machine) and set `OUTPUT_PATH` there to write straight into your map package, and
   `SERVER_ASSETS_DIR` to your server's `Assets/`
   folder so each `DoorMesh` is converted to its exact nanos path (`pack::AssetKey`, read from the
   packs' `Assets.toml`). Without it, the script guesses `<first folder, lowercased>::<asset name>`
   and logs a warning.
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

- The default panel is `nanos-world::SM_Plane`, which lies flat, so a door using the default mesh
  needs the marker rotated **Roll = 90** to stand upright (the preview shows it). With a custom
  mesh that is already upright, keep Roll at 0.
- A `DoorMesh` must also be cooked into an asset pack loaded by the server, or the door won't show
  in game. Engine basic shapes (`/Engine/BasicShapes/...`) are mapped to nanos world's own
  `SM_Plane`/`SM_Cube`/... automatically.
- The preview shows the closed position only.
- `export_doors.py` is only tested against a mocked `unreal` module so far; report any Python API
  error from the Output Log.
