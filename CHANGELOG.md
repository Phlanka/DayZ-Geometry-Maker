# Changelog

## [Unreleased]

### Added
- **Model Generator panel** — new standalone *DayZ Object Generator* panel in the N-panel, positioned between *DayZ Object Properties* and *DayZ Geometry Maker*. Designed to hold procedural model generators; more will be added over time.
- **Ladder Generator** — procedural DayZ ladder generator inside the Model Generator panel.
  - One-click **Add Ladder** button; all dimensions correct for DayZ climbing animations by default (320 mm rung spacing, 340 mm first rung, 42 mm tube diameter, 440 / 480 mm width).
  - Live viewport preview — every parameter rebuilds the mesh instantly via `check()` callback.
  - Adjustable: rung count, width (440 / 480 mm), top extension, tube segments. All values editable with checkmark / warning icon showing deviation from DayZ standard.
  - Maximum 3 ladders per scene enforced in the UI (DayZ engine limit), with live counter.
  - **Edit Selected Ladder** — re-opens the parameter dialog for any selected ladder. Cancel correctly restores the previous mesh.
  - **Geometry integrity check** — panel detects manual edits, scale changes and Apply Scale by comparing actual bounding box dimensions against the stored expected values. Shows a red warning with actual vs expected measurements.
  - **Restore Ladder** — one-click rebuild from stored parameters, preserving world position and rotation.
  - **Generate Collision** — adds two stringer box components (left + right rail) into the shared Geometry LOD object. Components are tracked per ladder via a JSON map; regenerating removes only that ladder's old components. Button is disabled once collision exists and re-enables if components are manually deleted.
  - **Memory points and View Geometry** — placed at the correct world position based on the Target Object bounding box. Memory points use fixed semantic offsets from the first and last rung (not scaling), so `ladder1_top_front` always sits exactly on the last rung regardless of rung count.
  - View Geometry scaled to match actual ladder total height.
  - Component and ladder named selections correctly numbered: Ladder 1 → Component01 + ladder1, Ladder 2 → Component02 + ladder2, Ladder 3 → Component03 + ladder3.
  - Generated objects named **DZ_Ladder_1 / 2 / 3**.

## [2.1.2] - 2026-05-08

### Added
- **Ladder Generator** — new "DayZ Object Generator" panel in the viewport. Generate a procedural Type 1 (straight) ladder to DayZ standard measurements without modelling by hand. Rung spacing, tube diameter, width, rung count, top extension and tube segments are all configurable. Parameters show a checkmark when they match DayZ standards, or a warning icon if they deviate.
- **Safety Cage** — optional D-arc safety cage add-on for generated ladders. Adjustable depth, hoop spacing, start height and vertical bars. Cage width always follows ladder width automatically.
- **Cabin Generator** — procedural low-poly cabin shell (walls, gable roof, floor, door and windows) added to the same panel as the Ladder Generator. Live preview included.
- **Multi-ladder support** — up to 3 independent ladder groups per model, each with its own add, delete and rotate controls. Ladders are offset on the Z axis automatically so they don't overlap.
- **Ladder collision generation** — automatically generates two collision boxes (left and right stringer) into the Geometry LOD with correct ComponentXX naming.
- **Ladder integrity check** — the panel detects if a generated ladder has been manually edited or scaled and shows a red warning with actual vs expected dimensions. A Restore Ladder button rebuilds the mesh from the stored parameters without moving it.
- **Live preview** — all generators show a live viewport preview as you adjust parameters.

### Fixed
- Ladder memory points and view geometry now sit correctly at the first and last rung positions regardless of rung count.
- Resolution LOD naming now includes the source object name to prevent LODs from different objects overwriting each other.
- View geometry correctly named per ladder slot (ladder1/2/3) with Component01 selection preserved.
- Rotation now applies around the ladder's own centre rather than the world origin.
- P3D export path select button was missing — restored.

---

## [2.0.6] - 2026-05-01

### Added
- **Memory LOD — individual Add/Update buttons** — each memory point type (bounding box, inventory camera, center, radius, muzzle, bolt axis, case eject, eye/ADS, trigger, magazine, ladder, lights, damage hide, door axis) now has its own Add/Update button instead of a single "Create Selected Points" checkbox list. Points already present in the Memory LOD show a filled dot icon; missing points show hollow. Clicking Add creates the point; clicking Update removes and recreates it at the current target object's position.
- **Move memory points in the viewport** — each existing memory point has a cursor-icon Move button. Clicking it selects that vertex group in Edit Mode on the Memory LOD and activates the Move tool so you can reposition it freely. Click the button again or press Tab to return to Object Mode.
- **Door rotation setup panel** — once door axis points (`door_N_axis_1` / `door_N_axis_2`) exist in the Memory LOD, a Rotation Setup box appears per door. Pick the door's vertex group on the target mesh, click Enter Rotate Mode, and a temporary wireframe preview of the door geometry appears in the viewport rotating around the hinge axis. Click Set Closed and Set Open to record the angles, then Done to confirm. The recorded angles are written directly into the model.cfg on export.
- **Remove Named Property button** — each entry in the Object Properties Named Properties list now has an X button to delete it individually.

### Changed
- **Memory LOD panel redesigned** — the flat checkbox list is replaced with grouped sections (Inventory & Bounds, Weapon Points, Building & Structure, Effects & Lighting), each showing per-point status and move controls.
- **model.cfg door axis format** — door animation entries now emit `axis = "<bone>_axis_1","<bone>_axis_2";` referencing both axis vertex groups, and use the recorded closed/open angles from the door rotation setup instead of hardcoded 0 / 3.14159.
- **Door axis vgroup names** — on export, Memory LOD axis vertex groups are renamed from the internal `door_N_axis_1/2` names to `<doorvgroup>_axis_1/2` (e.g. `leftdoor_axis_1`, `leftdoor_axis_2`) so they match the door's named selection in Object Builder.

### Removed
- **"Create Selected Memory Points" operator** — replaced by the individual per-point Add/Update buttons described above.
- Old boolean scene properties for memory point toggles (`dgm_memory_bbox`, `dgm_memory_invview`, `dgm_memory_bullet`, etc.) — no longer needed.

---

## [2.0.5] - 2026-04-30

### Added
- **No Texture** toggle on each named selection — marks a selection as geometry-only or shared-UV with no texture. Hides texture/RVMAT fields, excludes it from baking, and prevents it being stamped with predicted paths on export.

### Fixed
- Named selection sync now always pre-fills the hidden selection name from the vertex group name, including on existing entries that previously had a blank name.
- `Add Geometry` no longer crashes with "context is incorrect" when called from the dialog — scale is now applied directly to the mesh data instead of via `bpy.ops.object.transform_apply`.
- Per-selection baking now correctly respects the `bake_texture` toggle — selections without it ticked are skipped entirely rather than being baked as part of the whole mesh.

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
