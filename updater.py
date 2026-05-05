"""
DayZ Geometry Maker - Updater

Two modes, switchable in Edit > Preferences > Add-ons > DayZ Geometry Maker:

  main branch (default)
    Checks GitHub Releases for a newer tagged version on startup.
    One-click install downloads and installs the release zip.

  dev branch
    No release tags — instead compares every file in the remote dev branch
    against your local copy by SHA. Shows which files differ and lets you
    pull them all down with one click, overwriting local files.
    Restart Blender after pulling to load the changes.
"""

import bpy
import urllib.request
import json
import threading
import os

GITHUB_API_RELEASE  = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/releases/latest"
GITHUB_TREE         = "https://api.github.com/repos/Phlanka/DayZ-Geometry-Maker/git/trees/{branch}?recursive=1"
GITHUB_RAW          = "https://raw.githubusercontent.com/Phlanka/DayZ-Geometry-Maker/{branch}/{path}"
ADDON_DIR           = os.path.dirname(os.path.abspath(__file__))
# Safety check: if updater.py ended up directly in user_default/ (bad install),
# correct the path to the actual addon subfolder
if os.path.basename(ADDON_DIR) not in ("dayz_geometry_maker",):
    _candidate = os.path.join(ADDON_DIR, "dayz_geometry_maker")
    if os.path.isdir(_candidate):
        ADDON_DIR = _candidate
ADDON_BL_IDNAME     = "bl_ext.user_default.dayz_geometry_maker"

CURRENT_VERSION     = (2, 1, 1)  # keep in sync with bl_info in __init__.py

# Files that live in the repo but not in the local addon folder - skip these
REPO_ONLY_FILES = {
    ".gitignore",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "scripts/install_dev.bat",
    "scripts/install_dev.sh",
}

# ---------------------------------------------------------------------------
# Shared state  (written from background threads, read on main thread)
# ---------------------------------------------------------------------------

# -- Release (main branch) state --
_update_available    = False
_release_check_done  = False
_latest_version_str  = ""
_latest_download_url = ""
_latest_changelog    = ""   # body text from the GitHub release

# -- Dev branch state --
_dev_check_running   = False
_dev_check_done      = False
_dev_changed_files   = []   # list of repo-relative file paths that differ locally


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


def _local_sha(filepath):
    """
    Compute the git blob SHA for a local file.
    Git blob SHA = sha1("blob <size>\0<content>").
    Returns hex string, or None if file doesn't exist.
    """
    import hashlib
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "rb") as f:
        content = f.read()
    header = "blob {}\0".format(len(content)).encode()
    return hashlib.sha1(header + content).hexdigest()


def _redraw_prefs():
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in ('PREFERENCES', 'VIEW_3D'):
                    area.tag_redraw()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Release update check  (main branch - background thread + poll timer)
# ---------------------------------------------------------------------------

def _release_check_thread():
    global _update_available, _release_check_done, _latest_version_str, _latest_download_url, _latest_changelog
    try:
        data = _request(GITHUB_API_RELEASE)
        tag  = data.get("tag_name", "")
        remote = _parse_version(tag)
        print("[DGM] Release check: local={} remote={} tag={}".format(CURRENT_VERSION, remote, tag))
        _latest_version_str = tag
        _latest_changelog   = data.get("body", "").strip()
        if remote > CURRENT_VERSION:
            _update_available = True
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".zip"):
                    _latest_download_url = asset["browser_download_url"]
                    break
            if not _latest_download_url:
                _latest_download_url = data.get("zipball_url", "")
    except Exception as e:
        print("[DGM] Release check failed:", e)
    finally:
        _release_check_done = True
        _redraw_prefs()


def _poll_for_update():
    _poll_for_update._count = getattr(_poll_for_update, "_count", 0) + 1
    if _update_available:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        print("[DGM] Update {} available.".format(_latest_version_str))
        return None
    if _poll_for_update._count >= 60:
        return None
    return 0.5


def check_for_update():
    global _release_check_done
    _poll_for_update._count = 0
    _release_check_done = False
    t = threading.Thread(target=_release_check_thread, daemon=True)
    t.start()
    bpy.app.timers.register(_poll_for_update, first_interval=1.0)


# ---------------------------------------------------------------------------
# Release install
# ---------------------------------------------------------------------------

def _do_install_release(operator):
    import zipfile, shutil, tempfile
    if not _latest_download_url:
        operator.report({'ERROR'}, "No download URL - run Check for Updates first.")
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
            top   = names[0].split('/')[0] if names else ""
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
        operator.report({'ERROR'}, "Install failed: " + str(e))
        return {'CANCELLED'}


# ---------------------------------------------------------------------------
# Dev branch - file-level SHA diff + pull
# ---------------------------------------------------------------------------

def _dev_check_thread():
    """
    Fetch the full file tree from the dev branch, compare each blob SHA
    against the local file SHA, and store changed/new files in _dev_changed_files.
    Skips repo-only files that do not belong in the local addon folder.
    """
    global _dev_changed_files, _dev_check_done, _dev_check_running
    try:
        url  = GITHUB_TREE.format(branch="dev")
        data = _request(url)
        tree = data.get("tree", [])

        changed = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item["path"]
            if path in REPO_ONLY_FILES:
                continue
            remote_sha = item.get("sha", "")
            local_path = os.path.join(ADDON_DIR, path)
            local_sha  = _local_sha(local_path)
            if local_sha != remote_sha:
                changed.append(path)
                print("[DGM] Dev diff: {} (local={} remote={})".format(
                    path, local_sha or "missing", remote_sha[:8]))

        _dev_changed_files = changed
        print("[DGM] Dev check done: {} file(s) differ.".format(len(changed)))
    except Exception as e:
        print("[DGM] Dev check failed:", e)
    finally:
        _dev_check_done    = True
        _dev_check_running = False
        _redraw_prefs()


def start_dev_check():
    global _dev_check_done, _dev_check_running, _dev_changed_files
    if _dev_check_running:
        return
    _dev_check_done    = False
    _dev_check_running = True
    _dev_changed_files = []
    t = threading.Thread(target=_dev_check_thread, daemon=True)
    t.start()


def _do_dev_pull(operator):
    """Download every changed file from the dev branch and overwrite local copies."""
    if not _dev_changed_files:
        operator.report({'WARNING'}, "No changes to pull.")
        return {'CANCELLED'}

    failed = []
    for path in _dev_changed_files:
        url        = GITHUB_RAW.format(branch="dev", path=path)
        local_path = os.path.join(ADDON_DIR, path)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DayZ-Geometry-Maker-Updater"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(content)
            print("[DGM] Pulled: {}".format(path))
        except Exception as e:
            failed.append("{}: {}".format(path, e))

    if failed:
        operator.report({'WARNING'}, "Some files failed: " + "; ".join(failed))
    else:
        operator.report({'INFO'}, "Pulled {} file(s) from dev. Please restart Blender.".format(
            len(_dev_changed_files)))
    return {'FINISHED'}


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class DGM_OT_check_update(bpy.types.Operator):
    bl_idname      = "dgm.check_update"
    bl_label       = "Check for Updates"
    bl_description = "Check GitHub Releases for a newer version"

    def execute(self, context):
        check_for_update()
        self.report({'INFO'}, "Checking for updates...")
        return {'FINISHED'}


class DGM_OT_install_update(bpy.types.Operator):
    bl_idname      = "dgm.install_update"
    bl_label       = "Install Update"
    bl_description = "Download and install the latest release from GitHub"

    def execute(self, context):
        return _do_install_release(self)


class DGM_OT_dev_check(bpy.types.Operator):
    bl_idname      = "dgm.dev_check"
    bl_label       = "Check dev branch for changes"
    bl_description = "Compare local addon files against the dev branch on GitHub"

    def execute(self, context):
        start_dev_check()
        self.report({'INFO'}, "Checking dev branch...")
        return {'FINISHED'}


class DGM_OT_dev_pull(bpy.types.Operator):
    bl_idname      = "dgm.dev_pull"
    bl_label       = "Pull Changes from dev"
    bl_description = "Download all changed files from the dev branch and overwrite local copies. Restart Blender after."

    def execute(self, context):
        return _do_dev_pull(self)


updater_classes = (
    DGM_OT_check_update,
    DGM_OT_install_update,
    DGM_OT_dev_check,
    DGM_OT_dev_pull,
)


# ---------------------------------------------------------------------------
# Preferences panel
# ---------------------------------------------------------------------------

class DGMAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_BL_IDNAME

    use_dev_branch: bpy.props.BoolProperty(
        name="Use dev branch",
        description=(
            "Switch to the dev branch for updates. "
            "Dev builds are unreleased and may be unstable. "
            "Updates are pulled as individual files rather than release zips"
        ),
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        # ---- Branch selector ----
        branch_box = layout.box()
        row = branch_box.row(align=True)
        row.label(text="Branch:", icon='FILEBROWSER')
        row.prop(self, "use_dev_branch", text="dev" if self.use_dev_branch else "main", toggle=True)

        if self.use_dev_branch:
            branch_box.label(text="Tracking: dev branch  (unreleased builds)", icon='ERROR')
        else:
            branch_box.label(
                text="Tracking: main branch  (v{}.{}.{})".format(*CURRENT_VERSION),
                icon='CHECKMARK',
            )

        layout.separator()

        if not self.use_dev_branch:
            # ---- main: release update ----
            box = layout.box()
            box.label(text="Release Updates", icon='URL')

            if _update_available:
                row = box.row(align=True)
                row.label(text="Update available: {}".format(_latest_version_str), icon='INFO')
                row.operator("dgm.install_update", text="Install Now", icon='IMPORT')
                if _latest_changelog:
                    box.separator()
                    box.label(text="What's new:", icon='TEXT')
                    col = box.column(align=True)
                    for line in _latest_changelog.splitlines():
                        line = line.strip()
                        if line:
                            col.label(text=line[:80])
                box.operator("dgm.check_update", text="Re-check", icon='FILE_REFRESH')

            elif _release_check_done:
                box.label(
                    text="You are up to date  (v{}.{}.{})".format(*CURRENT_VERSION),
                    icon='CHECKMARK',
                )
                if _latest_changelog:
                    box.separator()
                    box.label(text="Latest release notes:", icon='TEXT')
                    col = box.column(align=True)
                    for line in _latest_changelog.splitlines():
                        line = line.strip()
                        if line:
                            col.label(text=line[:80])
                box.operator("dgm.check_update", text="Re-check", icon='FILE_REFRESH')

            else:
                box.label(text="Checking for updates...", icon='FILE_REFRESH')
                box.operator("dgm.check_update", text="Check Now", icon='FILE_REFRESH')

        else:
            # ---- dev: file-level diff + pull ----
            box = layout.box()
            box.label(text="Dev Branch Updates", icon='SCRIPT')

            if _dev_check_running:
                box.label(text="Checking dev branch...", icon='FILE_REFRESH')

            elif _dev_check_done:
                if _dev_changed_files:
                    box.label(
                        text="{} file(s) differ from dev branch:".format(len(_dev_changed_files)),
                        icon='ERROR',
                    )
                    col = box.column(align=True)
                    for f in _dev_changed_files:
                        col.label(text=f, icon='DOT')
                    box.separator()
                    row = box.row(align=True)
                    row.operator("dgm.dev_pull", text="Pull All Changes", icon='IMPORT')
                    row.operator("dgm.dev_check", text="Re-check", icon='FILE_REFRESH')
                else:
                    box.label(text="Up to date with dev branch.", icon='CHECKMARK')
                    box.operator("dgm.dev_check", text="Re-check", icon='FILE_REFRESH')

            else:
                box.label(text="Click below to compare with dev branch.", icon='INFO')
                box.operator("dgm.dev_check", text="Check dev branch", icon='FILE_REFRESH')


# ---------------------------------------------------------------------------
# Register / Unregister
# ---------------------------------------------------------------------------

def register():
    for cls in updater_classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_class(DGMAddonPreferences)
    check_for_update()


def unregister():
    bpy.utils.unregister_class(DGMAddonPreferences)
    for cls in reversed(updater_classes):
        bpy.utils.unregister_class(cls)
