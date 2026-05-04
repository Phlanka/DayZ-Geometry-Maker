# Changelog

## [2.0.8] - 2026-05-04

### Added
- **HouseNoDestruct config template** — Export section now has a Config Template dropdown. Choose between `Container Base`, `House (Static Obj)` (inherits `HouseNoDestruct`), or `None`. Only one can be selected at a time. The house template includes a full `DamageSystem` with projectile/melee set to zero damage (indestructible static object)
- **Auto-generated `class Doors {}` block** — When doors are configured in the panel, the container `config.cpp` now includes a `class Doors {}` entry per door with `component`, `soundPos`, `animPeriod`, and default sound sets. Component name matches the door vertex group name
- **Auto-generated `DamageZones` per door** — Container `config.cpp` now includes a `class DamageZones` block inside `DamageSystem` with one entry per configured door, using `componentNames[]` matching the door vertex group name
- **Add Door Geometry now creates all three geometry LODs** — Fire Geometry and View Geometry door meshes are created alongside the Geometry LOD mesh. Each carries only the door vertex group name as its named selection (no `ComponentXX`) — the named selection is what DayZ uses to animate collision with the door
- **Preferences panel** — Addon now has a proper preferences panel (Edit > Preferences > Add-ons > DayZ Geometry Maker) with release update check and Early Access section
- **Early Access mode** — Toggle in preferences. When enabled, a Check for Changes button checks the live GitHub main branch for source files changed since your last pull. Shows a list of changed files and a Download button that overwrites local copies and prompts a Blender restart

### Changed
- **Fire Geometry** now skips door geometry objects when copying from the Geometry collection — door geometry is handled separately by Add Door Geometry
- **View Geometry** now copies `ComponentXX` objects from the Geometry collection instead of creating a single bounding box over the whole model. Falls back to bounding box only if no geometry components exist yet

### Fixed
- **Update banner showing incorrectly** — Version numbers were out of sync across `bl_info`, `blender_manifest.toml`, and `updater.py`, causing the update banner to always appear. All version references are now consistent

---

## [2.0.5] - 2026-05-02

### Added
- **Mod export system** — Export section now has P3D path picker, Textures folder, and Scripts folder. All config and script files are generated automatically on export
- **config.cpp generation** — Exports a combined config next to the P3D containing CfgPatches, CfgMods (with correct script paths), and CfgVehicles (Container_Base)
- **4_World scripts generation** — Entity class, ActionOpen, ActionClose, and moddedActionConstructor scripts generated from templates with class name substitution
- **model.cfg sections** — Door bone names (leftdoor, rightdoor etc.) now included in `sections[]` alongside texture selections
- **Add Door Geometry** — New button in the Memory Points door section creates a Geometry LOD convex hull for each configured door vertex group (10kg, named after the door)
- **Fire Geometry** now includes door geometry objects alongside ComponentXX objects when building from the Geometry collection
- **Door angle inversion** — model.cfg angle0/angle1 values are negated to match DayZ's sign convention

### Contributors
- [7ooWORKS](https://github.com/7ooWORKS) — contributed to the mod export and config generation system

---

## [2.0.4] - 2026-04-29

### Fixed
- Baked textures now always output to a `data/` folder next to the exported P3D file. Previously the baker panel output path (set in the Phlanka addon) was used instead, causing textures to land in the wrong location regardless of where the P3D was saved.
- The texture path preview shown in the export dialog now correctly reflects the P3D save location.
- Per-selection baking no longer crashes on the second selection when the vertex group name differs from the hidden selection export name — the isolate step now correctly looks up the vertex group by its Blender name rather than the export name.
- `data_temp/` folder is recreated between selections so subsequent bakes don't error with a missing directory.

---

## [2.0.3] - 2026-04-29

### Fixed
- Auto-updater now correctly shows the update banner in the panel when a newer version is available. Previously the background check detected the update but the UI never refreshed — a main-thread polling timer now triggers a redraw as soon as the check completes.
- Per-selection baking: when a target object has multiple material slots / vertex groups, the baker now bakes each named selection individually (isolate geometry → bake → collect files → rejoin), so each selection gets its own correctly named texture set instead of all selections sharing the same baked output.
- `data_temp/` folder is now fully removed after baking completes rather than leaving an empty directory behind.

---

## [2.0.2] - 2026-04-28

### Added
- **Geometry from Selection** — go into Edit Mode on your target mesh, select any vertices or faces, and click the new button to create a convex hull geometry component wrapping exactly that selection. Useful for complex shapes like pillars, arches, or individual parts of a scan mesh. Falls back to full bounding box if fewer than 4 verts are selected.
- Improved tooltip descriptions on all geometry buttons so their purpose is clear on hover.

### Fixed
- Shadow Volume 2 no longer decimates the mesh. Both shadow volumes now use the full geometry, only scaled slightly (0.99 / 0.97) to prevent self-shadowing. Previously the 0.3 ratio was distorting low-poly models.
- Baked texture files are now copied to `data/` with their original extension (`.png` or `.paa`). P3D and RVMAT texture path references always use `.paa` — if the baker wrote `.png`, convert it externally.

---

## [2.0.1] - 2026-04-28

### Fixed
- Fixed `CURRENT_VERSION` mismatch that prevented the auto-updater from ever notifying users of new releases.

---

## [2.0.0] - 2026-04-28

Initial public release.

### Features
- P3D export to Arma MLOD format — no ArmaToolbox required
- Resolution LODs with automatic decimation (up to 6)
- Geometry, Fire Geometry, and Roadway LOD generation
- Memory LOD — bounding box, inventory camera, doors, lights, weapon points
- Named selections synced from vertex groups
- model.cfg generation
- Correct deduplicated split normals — no F5 needed in Object Builder
- Optional texture baking integration with DayZ Texture Tools
- GitHub auto-updater — checks for new releases on Blender startup
