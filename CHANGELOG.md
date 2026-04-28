# Changelog

## [Unreleased]

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
