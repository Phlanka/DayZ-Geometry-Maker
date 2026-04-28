"""
DayZ Geometry Maker - Texture Baker Bridge
Integrates with phlanka_library_beta (DayZ Texture Tools) baker
to auto-bake and assign textures before P3D export.
"""

import os
import bpy


# ---------------------------------------------------------------------------
# License / availability checks
# ---------------------------------------------------------------------------

def _get_phlanka_module():
    """Return the phlanka_library_beta top-level module, or None."""
    import sys
    # Try exact match first (Blender 5 extension path)
    for mod_name in ("bl_ext.user_default.phlanka_library_beta", "phlanka_library_beta"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            return mod
    # Fallback: scan for any loaded module whose tail is phlanka_library_beta
    for mod_name, mod in sys.modules.items():
        if mod_name.endswith("phlanka_library_beta") and "." not in mod_name.split("phlanka_library_beta")[0].rstrip("."):
            return mod
    return None


def _get_phlanka_addon_state() -> dict:
    mod = _get_phlanka_module()
    if mod is None:
        return {}
    state = getattr(mod, "_addon_state", None)
    return state if isinstance(state, dict) else {}


def baker_addon_available() -> bool:
    """True if phlanka_library_beta is loaded in sys.modules."""
    return _get_phlanka_module() is not None


def baker_licensed() -> bool:
    """
    True if texture_baker is in owned_tool_slugs inside phlanka_library_beta._addon_state.
    This is set after the license validation thread completes.
    """
    state = _get_phlanka_addon_state()
    owned = state.get("owned_tool_slugs", set())
    return "texture_baker" in owned


def baker_output_path() -> str:
    """Return the output path currently set in the baker panel."""
    scene = bpy.context.scene
    try:
        return getattr(scene, "dayz_baker_output", "") or ""
    except Exception:
        return scene.get("dayz_baker_output", "") or ""


# ---------------------------------------------------------------------------
# Post-bake texture assignment
# ---------------------------------------------------------------------------

def _find_baked_co(output_dir: str, base_name: str) -> str:
    """
    Look for a CO (color) texture in output_dir that matches base_name.
    The baker writes <base_name>_co.paa (after TexConv) or <base_name>_co.png
    as an intermediate. Returns the P: drive relative path if found, else "".
    """
    if not output_dir or not base_name:
        return ""

    candidates = [
        base_name + "_co.paa",
        base_name + "_CO.paa",
        base_name + "_co.png",
        base_name + "_CO.png",
        base_name + ".paa",
        base_name + ".png",
    ]
    for name in candidates:
        full = os.path.join(output_dir, name)
        if os.path.exists(full):
            # Convert to P: drive relative path (strip drive letter + leading slash)
            rel = full
            if os.path.isabs(rel):
                drive, rest = os.path.splitdrive(rel)
                rel = rest.lstrip("\\/")
            return rel.replace("/", "\\")
    return ""


def _find_baked_rvmat(output_dir: str, base_name: str) -> str:
    """Look for a baked .rvmat alongside the CO texture."""
    if not output_dir or not base_name:
        return ""
    candidates = [
        base_name + ".rvmat",
        base_name + "_mat.rvmat",
    ]
    for name in candidates:
        full = os.path.join(output_dir, name)
        if os.path.exists(full):
            drive, rest = os.path.splitdrive(full)
            rel = rest.lstrip("\\/")
            return rel.replace("/", "\\")
    return ""


def _selection_base_name(sm) -> str:
    """Return the export name for a selection_mat — hidden_selection if set, else vgroup_name."""
    return (sm.hidden_selection or sm.vgroup_name or "").strip()


def _strip_drive(path: str) -> str:
    """Remove drive letter (e.g. P:\\) so paths are P:-drive relative."""
    if not path:
        return ""
    if os.path.isabs(path):
        _, rest = os.path.splitdrive(path)
        return rest.lstrip("\\/").replace("\\", "\\")
    if path.startswith("\\"):
        return path[1:]
    return path


def predict_texture_paths(output_dir: str, model_name: str, sel_name: str) -> tuple:
    """
    Return (co_path, rvmat_path) relative strings (no drive letter).
    Filename pattern: <model_name>_<sel_name>_co.paa / <model_name>_<sel_name>.rvmat
    """
    if not output_dir or not sel_name:
        return ("", "")
    base = "{}_{}".format(model_name, sel_name) if model_name else sel_name
    co_abs = os.path.join(output_dir, base + "_co.paa")
    rv_abs = os.path.join(output_dir, base + ".rvmat")
    return (_strip_drive(co_abs), _strip_drive(rv_abs))


def pre_assign_bake_paths(objects: list, output_dir: str, model_name: str, bake_rvmat: bool) -> None:
    """
    Stamp predicted CO/RVMAT paths onto every selection_mat before the P3D is
    written, so the file contains correct paths even before the images exist.
    """
    for obj in objects:
        props = getattr(obj, "dgm_props", None)
        if props is None or not props.is_dayz_object:
            continue
        for sm in props.selection_mats:
            sel_name = _selection_base_name(sm)
            if not sel_name:
                continue
            co_path, rv_path = predict_texture_paths(output_dir, model_name, sel_name)
            if co_path:
                sm.texture = co_path
            if bake_rvmat and rv_path:
                sm.rv_mat = rv_path


def assign_baked_textures_to_lods(operator, objects: list, output_dir: str, model_name: str) -> bool:
    """
    After baking, re-stamp the predicted paths so any selections added after
    pre_assign_bake_paths also get covered.  Returns True if anything was set.
    """
    assigned = 0
    bake_rvmat = getattr(bpy.context.scene, "dayz_bake_rvmat", False)

    for obj in objects:
        props = getattr(obj, "dgm_props", None)
        if props is None or not props.is_dayz_object:
            continue
        for sm in props.selection_mats:
            sel_name = _selection_base_name(sm)
            if not sel_name:
                continue
            co_path, rv_path = predict_texture_paths(output_dir, model_name, sel_name)
            if co_path:
                sm.texture = co_path
                assigned += 1
            if bake_rvmat and rv_path:
                sm.rv_mat = rv_path

    if assigned:
        operator.report({'INFO'}, "Assigned bake texture paths to {} named selections.".format(assigned))
    else:
        operator.report({'WARNING'}, "No named selections found to assign bake paths to.")
    return assigned > 0


# ---------------------------------------------------------------------------
# Run baker then assign
# ---------------------------------------------------------------------------

def _collect_new_files(temp_dir: str, pre_files: set) -> list:
    """Return all new files written to temp_dir since pre_files snapshot."""
    try:
        return [
            os.path.join(temp_dir, f)
            for f in os.listdir(temp_dir)
            if f not in pre_files
        ]
    except Exception:
        return []


def _fix_rvmat_paths(rvmat_path: str, temp_dir: str, final_dir: str, model_name: str, sel_name: str) -> None:
    """
    Rewrite every texture= / rvmat= path inside an RVMAT that still points at
    temp_dir.  Each reference is replaced with the correctly named final path:
      <final_dir>/<model_name>_<sel_name><original_suffix>
    All drive letters are stripped so paths are P:-drive relative.
    """
    import re

    try:
        with open(rvmat_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except Exception as e:
        print("[DGM] Could not read RVMAT '{}': {}".format(rvmat_path, e))
        return

    # Build a normalised, drive-stripped version of temp_dir for matching.
    # Normalise to backslashes so os.path.normpath on Windows gives consistent results.
    temp_stripped = re.sub(r'^[A-Za-z]:[/\\]', '', os.path.normpath(temp_dir)).lower().replace("/", "\\")
    print("[DGM] RVMAT fix: temp_stripped='{}'  file='{}'".format(temp_stripped, rvmat_path))

    base = "{}_{}".format(model_name, sel_name) if model_name else sel_name

    # Known suffix tags the baker writes
    _TAGS = ("_co", "_nohq", "_smdi", "_em", "_as")

    def _replace_path(match):
        raw = match.group(1)
        # Strip drive letter if present (P:\... or p:\...) then normalise slashes
        no_drive = re.sub(r'^[A-Za-z]:[/\\]', '', raw).replace("/", "\\")
        no_drive_norm = os.path.normpath(no_drive).lower()
        print("[DGM]   checking: '{}' startswith '{}' -> {}".format(
            no_drive_norm, temp_stripped, no_drive_norm.startswith(temp_stripped)))
        # Only rewrite paths that live inside the temp folder
        if not no_drive_norm.startswith(temp_stripped):
            return match.group(0)

        # Identify which suffix tag this file carries
        stem_lower = os.path.splitext(os.path.basename(no_drive))[0].lower()
        ext = os.path.splitext(no_drive)[1].lower() or ".paa"
        # Keep actual extension — baker may write .png if PAA conversion is off

        matched_tag = next((t for t in _TAGS if stem_lower.endswith(t)), None)
        if matched_tag:
            new_name = base + matched_tag + ext
        else:
            # Unknown suffix — keep original filename but move to final dir
            new_name = base + ext

        new_rel = os.path.join(final_dir, new_name)
        # Strip drive letter from final path
        new_rel = re.sub(r'^[A-Za-z]:[/\\]', '', new_rel)
        new_rel = new_rel.replace("/", "\\")

        return match.group(0).replace(match.group(1), new_rel)

    # Match anything inside quotes that looks like a file path
    content = re.sub(r'"([^"]+\.(?:paa|png|tga|bmp|rvmat))"', _replace_path, content, flags=re.IGNORECASE)

    try:
        with open(rvmat_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except Exception as e:
        print("[DGM] Could not write fixed RVMAT '{}': {}".format(rvmat_path, e))


def run_baker_and_assign(operator, objects: list, model_name: str, p3d_filepath: str = "") -> bool:
    """
    Bake flow:
      1. Point the baker at a data_temp folder (never overwrites data/)
      2. Baker runs modally
      3. On completion: for each selection, copy temp files to data/ with the
         correct modelname_selectionname_co.paa name, fix RVMAT internal paths,
         delete the temp folder, then assign the final paths to selection_mats
    """
    if not baker_licensed():
        operator.report(
            {'ERROR'},
            "DayZ Texture Tools baker is not available or not licensed. "
            "Check phlanka_library_beta is installed and activated."
        )
        return False

    # Resolve the final data/ dir from the baker panel setting or the P3D location
    final_dir = baker_output_path()
    if not final_dir:
        if p3d_filepath:
            final_dir = os.path.join(os.path.dirname(bpy.path.abspath(p3d_filepath)), "data")
        else:
            operator.report({'ERROR'}, "No bake output path set and no P3D path known.")
            return False

    final_dir = bpy.path.abspath(final_dir)
    os.makedirs(final_dir, exist_ok=True)

    # Bake into data_temp — a sibling folder that won't overwrite data/
    temp_dir = os.path.join(os.path.dirname(final_dir), "data_temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Point the baker at the temp folder for this bake
    mod = _get_phlanka_module()
    if mod is not None:
        try:
            import importlib
            sh = importlib.import_module(mod.__name__ + ".state_helpers")
            sh.set_baker_output_path(bpy.context.scene, temp_dir)
        except Exception:
            bpy.context.scene["dayz_baker_output"] = temp_dir
    else:
        bpy.context.scene["dayz_baker_output"] = temp_dir

    pre_files = set(os.listdir(temp_dir))

    try:
        result = bpy.ops.dayztexturetools.texture_baker_run('INVOKE_DEFAULT')
    except Exception as exc:
        operator.report({'ERROR'}, "Baker failed: {}".format(exc))
        return False

    if 'CANCELLED' in result:
        operator.report({'WARNING'}, "Baker was cancelled.")
        return False

    bake_rvmat = getattr(bpy.context.scene, "dayz_bake_rvmat", False)
    sel_names = []
    for obj in bpy.data.objects:
        props = getattr(obj, "dgm_props", None)
        if props is None or not props.is_dayz_object:
            continue
        for sm in props.selection_mats:
            name = _selection_base_name(sm)
            if name and name not in sel_names:
                sel_names.append(name)

    _temp   = temp_dir
    _final  = final_dir
    _model  = model_name
    _pre    = pre_files
    _rvmat  = bake_rvmat

    def _process_when_done():
        try:
            from bl_ext.user_default.phlanka_library_beta.texture_baker.ops import (
                DAYZTEXTTOOLS_OT_TextureBakerRun as _BakerOp
            )
            if getattr(_BakerOp, '_active_instance', None) is not None:
                return 0.5  # still running
        except Exception:
            pass

        import shutil

        new_files = _collect_new_files(_temp, _pre)
        if not new_files:
            print("[DGM] Baker finished but no new files found in '{}'".format(_temp))
            _restore_baker_output(_final)
            return None

        # Map each new file to its suffix tag (stem only, no extension).
        # The baker may write .paa or .png depending on addon preferences.
        # We keep the actual file extension when copying — the P3D paths always
        # say .paa so the user can convert manually if needed.
        _STEM_TAGS = ("_co", "_nohq", "_smdi", "_em", "_as")
        _TEXTURE_EXTS = (".paa", ".png", ".tga", ".bmp")

        # Bucket each new file by stem tag  ->  (src_path, actual_ext)
        tagged = {}       # stem_tag -> (src_path, actual_ext)
        rv_src = None
        temp_stem = ""
        for fpath in new_files:
            fname = os.path.basename(fpath)
            fname_lower = fname.lower()
            if fname_lower.endswith(".rvmat"):
                rv_src = fpath
                continue
            stem_lower, ext_lower = os.path.splitext(fname_lower)
            if ext_lower not in _TEXTURE_EXTS:
                continue
            matched_tag = next((t for t in _STEM_TAGS if stem_lower.endswith(t)), None)
            if matched_tag:
                tagged[matched_tag] = (fpath, ext_lower)
                if matched_tag == "_co" and not temp_stem:
                    temp_stem = fname[:len(fname) - len(matched_tag) - len(ext_lower)]

        os.makedirs(_final, exist_ok=True)

        assigned = 0
        for sel_name in sel_names:
            base = "{}_{}".format(_model, sel_name) if _model else sel_name

            # Copy every tagged texture map, preserving actual file extension
            for tag, (src, actual_ext) in tagged.items():
                dst = os.path.join(_final, base + tag + actual_ext)
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    print("[DGM] Could not copy {} to '{}': {}".format(tag, dst, e))

            # Copy and fix RVMAT
            if rv_src:
                rv_dst = os.path.join(_final, base + ".rvmat")
                try:
                    shutil.copy2(rv_src, rv_dst)
                    _fix_rvmat_paths(rv_dst, _temp, _final, _model, sel_name)
                except Exception as e:
                    print("[DGM] Could not copy/fix RVMAT to '{}': {}".format(rv_dst, e))

        # Delete the temp folder contents
        try:
            shutil.rmtree(_temp)
            print("[DGM] Removed temp bake folder: {}".format(_temp))
        except Exception as e:
            print("[DGM] Could not remove temp folder '{}': {}".format(_temp, e))

        # Restore the baker output path back to the real data/ folder
        _restore_baker_output(_final)

        # Assign final paths to all selection_mats
        for obj in bpy.data.objects:
            props = getattr(obj, "dgm_props", None)
            if props is None or not props.is_dayz_object:
                continue
            for sm in props.selection_mats:
                name = _selection_base_name(sm)
                if not name:
                    continue
                co_path, rv_path = predict_texture_paths(_final, _model, name)
                if co_path:
                    sm.texture = co_path
                    assigned += 1
                if _rvmat and rv_path:
                    sm.rv_mat = rv_path

        print("[DGM] Bake complete — assigned paths to {} named selections.".format(assigned))
        return None

    bpy.app.timers.register(_process_when_done, first_interval=1.0)
    operator.report({'INFO'}, "Baker started — output will be moved from data_temp/ to data/ when done.")
    return True


def _restore_baker_output(path: str) -> None:
    """Point the baker output path back to the given directory."""
    mod = _get_phlanka_module()
    if mod is not None:
        try:
            import importlib
            sh = importlib.import_module(mod.__name__ + ".state_helpers")
            sh.set_baker_output_path(bpy.context.scene, path)
            return
        except Exception:
            pass
    try:
        bpy.context.scene["dayz_baker_output"] = path
    except Exception:
        pass
