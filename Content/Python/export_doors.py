"""Export every BP_DoorMarker placed in the open level to a nanos world Lua file.

The nanos world server doesn't run Unreal, so doors placed in a map only
exist on clients. This editor-only script turns the placed markers into a
MapDoors.lua that the map package's server script requires; it calls
BaseDoor.SpawnFromList() from the `door` package to spawn real,
server-authoritative doors at the same spots.

Run it in the Unreal Editor with the level open:
    Tools > Execute Python Script... > export_doors.py
(needs the "Python Editor Script Plugin", enabled by default in UE 5.7).
"""

import datetime
import glob
import os

import unreal

# Any placed actor whose Blueprint class name starts with this is exported
# (so child Blueprints like BP_DoorMarker_Metal are picked up too).
MARKER_CLASS_PREFIX = "BP_DoorMarker"

# Where to write the Lua file. Leave empty to write to
# <Project>/Saved/NanosDoor/<LevelName>_MapDoors.lua, or point it straight at
# your map package, eg. r"E:\...\Packages\my-map\Server\MapDoors.lua".
OUTPUT_PATH = ""

# The server's Assets/ folder, used to turn a marker's DoorMesh (a UE asset)
# into its nanos world path ("pack::AssetKey") by reading every pack's
# Assets.toml. Leave empty to fall back to "<first folder, lowercased>::<name>".
SERVER_ASSETS_DIR = r""

# Machine-specific overrides of the settings above (eg. your own server path)
# go in export_doors_local.py next to this file. It's git-ignored, so your
# paths never end up in the shared repo. Example content:
#   OUTPUT_PATH = r"E:\...\Packages\my-map\Server\MapDoors.lua"
#   SERVER_ASSETS_DIR = r"E:\...\nanos-world-server\Assets"
_LOCAL_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_doors_local.py")
if os.path.isfile(_LOCAL_CONFIG):
    with open(_LOCAL_CONFIG, encoding="utf-8") as _file:
        exec(_file.read())

# Engine basic shapes the ADK previews with, mapped to nanos world's own
# default assets (DoorMesh left empty previews /Engine/BasicShapes/Plane).
ENGINE_SHAPES = {
    "/Engine/BasicShapes/Plane": "nanos-world::SM_Plane",
    "/Engine/BasicShapes/Cube": "nanos-world::SM_Cube",
    "/Engine/BasicShapes/Sphere": "nanos-world::SM_Sphere",
    "/Engine/BasicShapes/Cylinder": "nanos-world::SM_Cylinder",
    "/Engine/BasicShapes/Cone": "nanos-world::SM_Cone",
}


def _load_asset_index():
    """Map "Unreal/relative/path" -> "pack::key" from the server's Assets.toml files."""
    index = {}
    if not SERVER_ASSETS_DIR:
        return index
    try:
        import tomllib
    except ImportError:
        unreal.log_warning("[NanosDoor] tomllib unavailable (Python < 3.11), SERVER_ASSETS_DIR ignored.")
        return index
    for toml_path in glob.glob(os.path.join(SERVER_ASSETS_DIR, "*", "Assets.toml")):
        pack = os.path.basename(os.path.dirname(toml_path))
        try:
            with open(toml_path, "rb") as file:
                assets = tomllib.load(file).get("assets", {})
        except Exception as error:
            unreal.log_warning("[NanosDoor] Can't read {}: {}".format(toml_path, error))
            continue
        for category in assets.values():
            if isinstance(category, dict):
                for key, value in category.items():
                    index[str(value)] = "{}::{}".format(pack, key)
    return index


def _nanos_asset_path(mesh, asset_index):
    # "/Max-ilsland/Meshes/SM_Door.SM_Door" -> package "/Max-ilsland/Meshes/SM_Door"
    package = mesh.get_path_name().split(".")[0]
    if package in ENGINE_SHAPES:
        return ENGINE_SHAPES[package]

    parts = package.strip("/").split("/")
    if parts[0] == "Game" and len(parts) > 2 and parts[1] == "NanosWorld":
        return "nanos-world::" + parts[-1]

    # Assets.toml values are relative to Content/ ("/Game/Fab/X" -> "Fab/X")
    # or include the plugin name ("/Max-ilsland/Maps/port" -> "Max-ilsland/Maps/port").
    relative = "/".join(parts[1:] if parts[0] == "Game" else parts)
    if relative in asset_index:
        return asset_index[relative]

    guess = "{}::{}".format(relative.split("/")[0].lower(), parts[-1])
    unreal.log_warning("[NanosDoor] {} not found in any Assets.toml, guessing '{}'. Set SERVER_ASSETS_DIR, "
                       "or set DoorAsset on the marker.".format(package, guess))
    return guess


def _snake_case(name):
    out = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def _get(actor, name, default=None):
    # Blueprint variables are reachable by their exact name; snake_case is
    # tried too since Python-exposed property names are sometimes converted.
    for candidate in (name, _snake_case(name)):
        try:
            return actor.get_editor_property(candidate)
        except Exception:
            pass
    return default


def _num(value):
    text = "{:.3f}".format(value).rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _lua_string(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _lua_vector(vector):
    return "Vector({}, {}, {})".format(_num(vector.x), _num(vector.y), _num(vector.z))


def _lua_rotator(rotator):
    # nanos world's Rotator takes (pitch, yaw, roll).
    return "Rotator({}, {}, {})".format(_num(rotator.pitch), _num(rotator.yaw), _num(rotator.roll))


def _is_zero(vector):
    return vector is None or (vector.x == 0 and vector.y == 0 and vector.z == 0)


def _door_spec(actor, asset_index):
    fields = [
        "type = " + _lua_string(_get(actor, "DoorType", "Hinge") or "Hinge"),
        "location = " + _lua_vector(actor.get_actor_location()),
        "rotation = " + _lua_rotator(actor.get_actor_rotation()),
    ]

    # InteractionMode (any mode name registered in Lua, eg. a custom
    # "keycard") wins over the Interactable checkbox when set.
    mode = str(_get(actor, "InteractionMode", "") or "")
    if not mode:
        mode = "interact" if _get(actor, "Interactable", False) else "trigger"
    fields.append("mode = " + _lua_string(mode))

    trigger_radius = _get(actor, "TriggerRadius", 0) or 0
    if trigger_radius > 0:
        fields.append("trigger_extent = " + _num(trigger_radius))

    # DoorAsset (typed path) wins over DoorMesh (picked asset) when both are set.
    asset = str(_get(actor, "DoorAsset", "") or "")
    mesh = _get(actor, "DoorMesh")
    if not asset and mesh is not None:
        asset = _nanos_asset_path(mesh, asset_index)
    if asset:
        fields.append("asset = " + _lua_string(asset))

    scale = _get(actor, "DoorScale")
    if not _is_zero(scale):
        fields.append("scale = " + _lua_vector(scale))

    slide_offset = _get(actor, "SlideOffset")
    if not _is_zero(slide_offset):
        fields.append("slide_offset = " + _lua_vector(slide_offset))

    if _get(actor, "StartLocked", False):
        fields.append("locked = true")

    return "    {{ {} }}, -- {}".format(", ".join(fields), actor.get_actor_label())


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    level_name = world.get_name()

    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    markers = [a for a in actors if a.get_class().get_name().startswith(MARKER_CLASS_PREFIX)]
    # Stable order so re-exporting an unchanged map produces an identical file.
    markers.sort(key=lambda a: a.get_actor_label())

    lines = [
        "-- Generated by nanos-door/Content/Python/export_doors.py from level '{}' on {}.".format(
            level_name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        "-- Do not edit by hand: move the BP_DoorMarker actors in Unreal and re-export.",
        "-- Requires the `door` package (list it in packages_requirements).",
        "return BaseDoor.SpawnFromList({",
    ]
    asset_index = _load_asset_index()
    lines += [_door_spec(actor, asset_index) for actor in markers]
    lines.append("})")

    output = OUTPUT_PATH or os.path.join(
        unreal.Paths.project_saved_dir(), "NanosDoor", level_name + "_MapDoors.lua")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")

    unreal.log("[NanosDoor] Exported {} door(s) from '{}' to {}".format(len(markers), level_name, output))
    if not markers:
        unreal.log_warning("[NanosDoor] No actor whose class starts with '{}' found in the level.".format(
            MARKER_CLASS_PREFIX))


main()
