"""
DayZ Geometry Maker - GitHub Auto-Updater
Checks https://github.com/Phlanka/DayZ-Geometry-Maker for a newer version tag
on Blender startup and notifies the user if one is available.
Downloads and installs automatically if confirmed.
"""

import bpy
import urllib.request
import json
import threading
import os
import zipfile
import shutil

GITHUB_API = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/releases/latest"
CURRENT_VERSION = (2, 0, 3)
ADDON_ID = "dayz_geometry_maker"

_update_available = False
_latest_version_str = ""
_latest_download_url = ""


def _parse_version(tag):
    tag = tag.lstrip("vV")
    try:
        parts = tuple(int(x) for x in tag.split("."))
        return parts
    except Exception:
        return (0, 0, 0)


def _check_thread():
    global _update_available, _latest_version_str, _latest_download_url
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"User-Agent": "DayZ-Geometry-Maker-Updater"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        tag = data.get("tag_name", "")
        remote = _parse_version(tag)
        print("[DGM] Updater: current={} remote={} tag={}".format(CURRENT_VERSION, remote, tag))
        if remote > CURRENT_VERSION:
            _update_available = True
            _latest_version_str = tag
            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".zip"):
                    _latest_download_url = asset.get("browser_download_url", "")
                    break
            if not _latest_download_url:
                _latest_download_url = data.get("zipball_url", "")
    except Exception:
        pass


def _poll_for_update():
    """
    Timer callback running on the main thread.
    Polls until the background check thread has set _update_available,
    then tags all VIEW_3D regions for redraw so the banner appears.
    Returns None (stop) once the flag is set or after ~30s of polling.
    """
    global _poll_count
    _poll_count = getattr(_poll_for_update, "_count", 0) + 1
    _poll_for_update._count = _poll_count

    if _update_available:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        print("[DGM] Updater: update {} available — panel redrawn.".format(_latest_version_str))
        return None  # stop polling

    if _poll_count >= 60:  # 60 × 0.5s = 30s timeout
        return None

    return 0.5  # check again in 0.5s


def check_for_update():
    _poll_for_update._count = 0
    t = threading.Thread(target=_check_thread, daemon=True)
    t.start()
    bpy.app.timers.register(_poll_for_update, first_interval=1.0)


def _do_install(operator):
    if not _latest_download_url:
        operator.report({'ERROR'}, "No download URL found for the latest release.")
        return {'CANCELLED'}

    try:
        import tempfile
        tmp_zip = tempfile.mktemp(suffix=".zip")
        req = urllib.request.Request(
            _latest_download_url,
            headers={"User-Agent": "DayZ-Geometry-Maker-Updater"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(tmp_zip, 'wb') as f:
                f.write(resp.read())

        addon_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(addon_dir)

        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            names = zf.namelist()
            top = names[0].split('/')[0] if names else ""
            zf.extractall(parent_dir)

        extracted = os.path.join(parent_dir, top)
        target = os.path.join(parent_dir, ADDON_ID)

        if os.path.isdir(extracted) and extracted != target:
            if os.path.isdir(target):
                shutil.rmtree(target)
            shutil.move(extracted, target)

        os.remove(tmp_zip)

        operator.report({'INFO'}, "DayZ Geometry Maker updated! Please restart Blender.")
        return {'FINISHED'}

    except Exception as e:
        operator.report({'ERROR'}, "Update failed: " + str(e))
        return {'CANCELLED'}


class DGM_OT_install_update(bpy.types.Operator):
    bl_idname = "dgm.install_update"
    bl_label = "Install Update"
    bl_description = "Download and install the latest DayZ Geometry Maker from GitHub"

    def execute(self, context):
        return _do_install(self)


class DGM_OT_check_update(bpy.types.Operator):
    bl_idname = "dgm.check_update"
    bl_label = "Check for Updates"
    bl_description = "Check GitHub for a newer version of DayZ Geometry Maker"

    def execute(self, context):
        check_for_update()
        self.report({'INFO'}, "Checking for updates in the background...")
        return {'FINISHED'}


updater_classes = (DGM_OT_install_update, DGM_OT_check_update)


def register():
    for cls in updater_classes:
        bpy.utils.register_class(cls)
    check_for_update()


def unregister():
    for cls in reversed(updater_classes):
        bpy.utils.unregister_class(cls)
