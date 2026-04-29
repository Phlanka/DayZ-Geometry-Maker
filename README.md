# DayZ Geometry Maker

A free, open-source Blender 5.0 extension for creating and exporting DayZ / Arma P3D models — no ArmaToolbox required.

Built and maintained by [Phlanka](https://phlanka.com).

---

## Features

- **P3D Export** — Export directly to the Arma MLOD P3D format from Blender
- **Resolution LODs** — Generate up to 6 resolution LODs with automatic decimation
- **Geometry LOD** — Add convex geometry components with one click, or select faces/verts in Edit Mode and generate a convex hull component from exactly that selection
- **Fire Geometry** — Reuses your geometry boxes automatically
- **Roadway LOD** — Extracts upward-facing faces from geometry boxes for accurate walkable surfaces
- **Memory LOD** — Bounding box, inventory camera, doors, lights, weapon points and more
- **Named Selections** — Synced from vertex groups, with hidden selection export names
- **model.cfg generation** — Writes a CfgModels / CfgSkeletons config alongside the P3D
- **Correct normals** — Deduplicated split normals written with proper Arma axis mapping — no F5 needed in Object Builder
- **Texture Baker integration** — Optional integration with [DayZ Texture Tools](https://beta.phlanka.com/) to bake and assign textures at export time

---

## Requirements

- Blender **5.0** or later (minimum 4.2)
- No other addons required for core P3D export

### Optional — Texture Baking

To use the built-in texture baking workflow you need the **Phlanka Blender addon** with the **Texture Baker module** installed and licensed.

Get it at: [beta.phlanka.com](https://beta.phlanka.com/)

---

## Installation

1. Download the latest release `.zip` from the [Releases](https://github.com/Phlanka/DayZ-Geometry-Maker/releases) page
2. **Drag and drop** the `.zip` directly into the Blender window — it will install automatically

   *Alternatively:* go to **Edit → Preferences → Extensions**, click **Install from Disk** and select the `.zip`

The panel will appear in the **3D Viewport → N Panel → DayZ** tab.

---

## Quick Start

1. Select or create a mesh object
2. Set it as the **Target Object** in the DayZ panel
3. Use **Add Geometry** to create geometry components
4. Use the **LODs** section to generate resolution LODs
5. Add named selections via vertex groups and the **Named Selections** panel
6. Click **Export P3D** to export

---

## Texture Baking (with DayZ Texture Tools)

If you have the Phlanka Texture Baker addon installed and licensed:

1. Add vertex groups to your mesh and sync them as named selections
2. Toggle **Bake** on the selections you want to bake
3. Set bake options (resolution, CO/NOHQ/SMDI/EM/AS/RVMAT) in the Named Selections panel
4. Export your P3D — the baker runs automatically after the file is written
5. Baked images are placed in a `data/` folder next to your P3D, named `modelname_selectionname_co.paa` etc.

---

## Support

Maintaining and improving this project takes time.  
If it's helped you, you can support its development here:

[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/PhlankaGB)

---

## License

This project is licensed under the **GNU General Public License v3.0** with additional terms:

- You may use, modify, and share this addon freely
- **You may not sell** this addon or any derivative as a standalone or bundled product
- Any derivative work must be released as open source under the same license
- See [LICENSE](LICENSE) for full terms

---

## Contributing

Pull requests are welcome. Please keep changes focused and open source.

For bug reports and feature requests, open an issue on GitHub.

---

## Credits

- Export pipeline informed by [Arma3ObjectBuilder](https://github.com/MrClock8163/Arma3ObjectBuilder) (GPL-3.0) by MrClock8163
- Built for the DayZ modding community
