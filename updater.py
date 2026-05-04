"""
DayZ Geometry Maker - GitHub Auto-Updater
Checks https://github.com/Phlanka/DayZ-Geometry-Maker for a newer release tag
on Blender startup and notifies the user if one is available.

Also supports Early Access mode: checks the live main branch for source file
changes since the last pull and lets the user download them individually.
"""

import bpy
import urllib.request
import json
import threading
import os

GITHUB_API        = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/releases/latest"
GITHUB_COMMITS    = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/commits"
GITHUB_RAW        = "https://raw.githubusercontent.com/Phlanka/DayZ-Geometry-Maker/main/{}"
ADDON_DIR         = os.path.dirname(os.path.abspath(__file__))
BETA_TIMESTAMP_FILE = os.path.join(ADDON_DIR, "beta_last_check.json")

# Set from bl_info at register time
CURRENT_VERSION = (2, 0, 7)
ADDON_BL_IDNAME = "bl_ext.user_default.dayz_geometry_maker"

_update_available    = False
_latest_version_str  = ""
_latest_download_url = ""

# Early access state
_beta_changed_files  = []   # list of {filename, sha, date} dicts from last check
_beta_check_done     = False
_beta_check_running  = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_version(tag):
    tag = tag.lstrip("vV")
    try:
        return tuple(int(x) for x in tag.split("."))
    except Exception:
        return (0, 0, 0)


def _request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "DayZ-Geometry-Maker-Updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _read_beta_timestamp():
    """Return ISO timestamp string of last beta pull, or None."""
    try:
        with open(BETA_TIMESTAMP_FILE, "r") as f:
            return json.load(f).get("last_pull")
    except Exception:
        return None


def _write_beta_timestamp(iso_str):
    with open(BETA_TIMESTAMP_FILE, "w") as f:
        json.dump({"last_pull": iso_str}, f)


def _latest_release_date():
    """Return the published_at ISO string of the latest release, or None."""
    try:
        data = _request(GITHUB_API)
        return data.get("published_at")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Release update check
# ---------------------------------------------------------------------------

def _check_thread():
    global _update_available, _latest_version_str, _latest_download_url
    try:
        data = _request(GITHUB_API)
        tag = data.get("tag_name", "")
        remote = _parse_version(tag)
        print("[DGM] Updater: current={} remote={} tag={}".format(CURRENT_VERSION, remote, tag))
        if remote > CURRENT_VERSION:
            _update_available = True
            _latest_version_str = tag
            assets = data.get("assets", [])
            for asset in assets:
                if asset.get("name", "").endswith(".zip"):
                    _latest_download_url = asset.get("browser_download_url", "")
                    break
            if not _latest_download_url:
                _latest_download_url = data.get("zipball_url", "")
    except Exception:
        pass


def _poll_for_update():
    global _poll_count
    _poll_count = getattr(_poll_for_update, "_count", 0) + 1
    _poll_for_update._count = _poll_count

    if _update_available:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        print("[DGM] Updater: update {} available.".format(_latest_version_str))
        return None

    if _poll_count >= 60:
        return None
    return 0.5


def check_for_update():
    _poll_for_update._count = 0
    t = threading.Thread(target=_check_thread, daemon=True)
    t.start()
    bpy.app.timers.register(_poll_for_update, first_interval=1.0)


# ---------------------------------------------------------------------------
# Release install
# ---------------------------------------------------------------------------

def _do_install(operator):
    import zipfile, shutil, tempfile
    if not _latest_download_url:
        operator.report({'ERROR'}, "No download URL found.")
        return {'CANCELLED'}
    try:
        tmp_zip = tempfile.mktemp(suffix=".zip")
        req = urllib.request.Request(
            _latest_download_url,
            headers={"User-Agent": "DayZ-Geometry-Maker-Updater"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(tmp_zip, 'wb') as f:
                f.write(resp.read())

        parent_dir = os.path.dirname(ADDON_DIR)
        addon_id   = os.path.basename(ADDON_DIR)

        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            names = zf.namelist()
            top = names[0].split('/')[0] if names else ""
            zf.extractall(parent_dir)

        extracted = os.path.join(parent_dir, top)
        target    = os.path.join(parent_dir, addon_id)
        if os.path.isdir(extracted) and extracted != target:
            if os.path.isdir(target):
                shutil.rmtree(target)
            shutil.move(extracted, target)

        os.remove(tmp_zip)
        operator.report({'INFO'}, "Updated to {}! Please restart Blender.".format(_latest_version_str))
        return {'FINISHED'}
    except Exception as e:
        operator.report({'ERROR'}, "Update failed: " + str(e))
        return {'CANCELLED'}


# ---------------------------------------------------------------------------
# Early access — check live branch for changed files
# ---------------------------------------------------------------------------

def _beta_check_thread(since_iso):
    """
    Fetch commits on main since `since_iso`, collect all unique files touched,
    and store them in _beta_changed_files.
    """
    global _beta_changed_files, _beta_check_done, _beta_check_running
    try:
        url = GITHUB_COMMITS + "?sha=main&per_page=100"
        if since_iso:
            url += "&since=" + since_iso

        commits = _request(url)
        seen = {}  # filename -> date of most recent commit touching it

        for commit in commits:
            sha  = commit.get("sha", "")
            date = commit.get("commit", {}).get("author", {}).get("date", "")
            detail_url = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/commits/" + sha
            try:
                detail = _request(detail_url)
                for f in detail.get("files", []):
                    fname = f.get("filename", "")
                    if fname and fname not in seen:
                        seen[fname] = {"filename": fname, "sha": sha, "date": date}
            except Exception:
                pass

        _beta_changed_files = list(seen.values())
        print("[DGM] Early Access: {} changed file(s) found.".format(len(_beta_changed_files)))
    except Exception as e:
        print("[DGM] Early Access check failed:", e)
    finally:
        _beta_check_done    = True
        _beta_check_running = False
        # Redraw preferences area
        try:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type in ('PREFERENCES', 'VIEW_3D'):
                        area.tag_redraw()
        except Exception:
            pass


def start_beta_check():
    global _beta_check_done, _beta_check_running, _beta_changed_files
    if _beta_check_running:
        return

    _beta_check_done    = False
    _beta_check_running = True
    _beta_changed_files = []

    # On first check, use the latest release date so we see everything since release
    since = _read_beta_timestamp() or _latest_release_date()
    t = threading.Thread(target=_beta_check_thread, args=(since,), daemon=True)
    t.start()


def _do_beta_pull(operator, filenames):
    """Download each listed file from main branch and overwrite local copy."""
    from datetime import datetime, timezone
    failed = []
    for fname in filenames:
        url = GITHUB_RAW.format(fname)
        local_path = os.path.join(ADDON_DIR, fname)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DayZ-Geometry-Maker-Updater"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(content)
        except Exception as e:
            failed.append("{}: {}".format(fname, e))

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_beta_timestamp(now_iso)

    if failed:
        operator.report({'WARNING'}, "Some files failed: " + "; ".join(failed))
    else:
        operator.report({'INFO'}, "Downloaded {} file(s). Please restart Blender.".format(len(filenames)))
    return {'FINISHED'}


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class DGM_OT_install_update(bpy.types.Operator):
    bl_idname = "dgm.install_update"
    bl_label = "Install Update"
    bl_description = "Download and install the latest DayZ Geometry Maker release from GitHub"

    def execute(self, context):
        return _do_install(self)


class DGM_OT_check_update(bpy.types.Operator):
    bl_idname = "dgm.check_update"
    bl_label = "Check for Updates"
    bl_description = "Check GitHub for a newer release of DayZ Geometry Maker"

    def execute(self, context):
        check_for_update()
        self.report({'INFO'}, "Checking for updates...")
        return {'FINISHED'}


class DGM_OT_beta_check(bpy.types.Operator):
    bl_idname = "dgm.beta_check"
    bl_label = "Check for Early Access Changes"
    bl_description = "Check the live GitHub source for files changed since your last pull"

    def execute(self, context):
        start_beta_check()
        self.report({'INFO'}, "Checking GitHub source...")
        return {'FINISHED'}


class DGM_OT_beta_pull(bpy.types.Operator):
    bl_idname = "dgm.beta_pull"
    bl_label = "Download Changes"
    bl_description = "Download all changed source files from the live GitHub branch"

    def execute(self, context):
        if not _beta_changed_files:
            self.report({'WARNING'}, "No changed files to download.")
            return {'CANCELLED'}
        filenames = [f["filename"] for f in _beta_changed_files]
        return _do_beta_pull(self, filenames)


updater_classes = (
    DGM_OT_install_update,
    DGM_OT_check_update,
    DGM_OT_beta_check,
    DGM_OT_beta_pull,
)


# ---------------------------------------------------------------------------
# Preferences panel
# ---------------------------------------------------------------------------

class DGMAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_BL_IDNAME

    early_access: bpy.props.BoolProperty(
        name="Early Access",
        description="Check the live GitHub source branch for unreleased file changes",
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        # ---- Release update ----
        box = layout.box()
        row = box.row()
        row.label(text="Release Updates", icon='URL')
        row.operator("dgm.check_update", text="Check Now")

        # ---- Early access ----
        ea_box = layout.box()
        ea_row = ea_box.row()
        ea_row.prop(self, "early_access", text="Early Access Mode")

        if self.early_access:
            ts = _read_beta_timestamp()
            if ts:
                ea_box.label(text="Last pull: " + ts, icon='TIME')
            else:
                ea_box.label(text="No pull yet — will check since latest release", icon='INFO')

            if _beta_check_running:
                ea_box.label(text="Checking GitHub...", icon='SORTTIME')
            elif _beta_check_done:
                if _beta_changed_files:
                    ea_box.label(
                        text="{} changed file(s) available:".format(len(_beta_changed_files)),
                        icon='FILE_REFRESH'
                    )
                    col = ea_box.column(align=True)
                    for f in _beta_changed_files:
                        col.label(text="  " + f["filename"], icon='DOT')
                    ea_box.operator("dgm.beta_pull", text="Download All Changes", icon='IMPORT')
                else:
                    ea_box.label(text="No new changes since last pull.", icon='CHECKMARK')
            else:
                ea_box.operator("dgm.beta_check", text="Check for Changes", icon='FILE_REFRESH')


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(DGMAddonPreferences)
    for cls in updater_classes:
        bpy.utils.register_class(cls)
    check_for_update()


def unregister():
    for cls in reversed(updater_classes):
        bpy.utils.unregister_class(cls)
    bpy.utils.unregister_class(DGMAddonPreferences)
