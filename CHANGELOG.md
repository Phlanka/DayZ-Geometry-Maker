# Changelog

## [Unreleased]

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
