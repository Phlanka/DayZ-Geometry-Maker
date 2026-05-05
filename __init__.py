"""
DayZ Geometry Maker v2.1
Author: Phlanka
License: MIT
GitHub: https://github.com/Phlanka/DayZ-Geometry-Maker

Standalone addon for creating DayZ/Arma P3D geometry LODs, memory points,
and exporting to P3D format. No ArmaToolbox dependency required.
"""

bl_info = {
    "name": "DayZ Geometry Maker",
    "author": "Phlanka",
    "version": (2, 1, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > DayZ",
    "description": "Create DayZ geometry LODs and export P3D files without ArmaToolbox",
    "category": "Object",
    "doc_url": "https://github.com/Phlanka/DayZ-Geometry-Maker",
    "tracker_url": "https://github.com/Phlanka/DayZ-Geometry-Maker/issues",
}

from . import properties, exporter, operators, updater


def register():
    properties.register()
    exporter.register()
    operators.register()
    updater.register()


def unregister():
    updater.unregister()
    operators.unregister()
    exporter.unregister()
    properties.unregister()
