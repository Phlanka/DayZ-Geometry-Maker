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
    for mod_name in ("bl_ext.user_default.phlanka_library_beta", "phlanka_library_beta"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            return mod
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
            rel = full
            if os.path.isabs(rel):
                drive, rest = os.path.splitdrive(rel)
                rel = rest.lstrip("\\/")
            return rel.replace("/", "\\")
    return ""


def _find_baked_rvmat(output_dir: str, base_name: str) -> str:
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

    temp_stripped = re.sub(r'^[A-Za-z]:[/\\]', '', os.path.normpath(temp_dir)).lower().replace("/", "\\")
    print("[DGM] RVMAT fix: temp_stripped='{}'  file='{}'".format(temp_stripped, rvmat_path))

    base = "{}_{}".format(model_name, sel_name) if model_name else sel_name

    _TAGS = ("_co", "_nohq", "_smdi", "_em", "_as")

    def _replace_path(match):
        raw = match.group(1)
        no_drive = re.sub(r'^[A-Za-z]:[/\\]', '', raw).replace("/", "\\")
        no_drive_norm = os.path.normpath(no_drive).lower()
        print("[DGM]   checking: '{}' startswith '{}' -> {}".format(
            no_drive_norm, temp_stripped, no_drive_norm.startswith(temp_stripped)))
        if not no_drive_norm.startswith(temp_stripped):
            return match.group(0)

        stem_lower = os.path.splitext(os.path.basename(no_drive))[0].lower()

        matched_tag = next((t for t in _TAGS if stem_lower.endswith(t)), None)
        if matched_tag:
            new_name = base + matched_tag + ".paa"
        else:
            new_name = base + ".paa"

        new_rel = os.path.join(final_dir, new_name)
        new_rel = re.sub(r'^[A-Za-z]:[/\\]', '', new_rel)
        new_rel = new_rel.replace("/", "\\")

        return match.group(0).replace(match.group(1), new_rel)

    content = re.sub(r'"([^"]+\.(?:paa|png|tga|bmp|rvmat))"', _replace_path, content, flags=re.IGNORECASE)

    try:
        with open(rvmat_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except Exception as e:
        print("[DGM] Could not write fixed RVMAT '{}': {}".format(rvmat_path, e))


def _baker_is_running() -> bool:
    """Return True if the baker modal operator is still active."""
    try:
        from bl_ext.user_default.phlanka_library_beta.texture_baker.ops import (
            DAYZTEXTTOOLS_OT_TextureBakerRun as _BakerOp
        )
        return getattr(_BakerOp, '_active_instance', None) is not None
    except Exception:
        return False


def _set_baker_output(path: str) -> None:
    """Point the baker output path at the given directory."""
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


def _restore_baker_output(path: str) -> None:
    """Point the baker output path back to the given directory."""
    _set_baker_output(path)


def _isolate_selection_as_object(target_obj, sel_name: str):
    """
    Duplicate target_obj, delete all vertices NOT in vertex group sel_name,
    return the new isolated object (or None on failure).
    The new object is in Object Mode when returned.
    """
    import bmesh

    # Ensure we're in object mode first
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Deselect all, select + activate target
    bpy.ops.object.select_all(action='DESELECT')
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj

    # Duplicate
    bpy.ops.object.duplicate(linked=False)
    dup = bpy.context.active_object
    dup.name = "__dgm_bake_tmp__"

    # Get the vertex group index for this selection
    vg = dup.vertex_groups.get(sel_name)
    if vg is None:
        # No matching vertex group — delete dup and bail
        bpy.data.objects.remove(dup, do_unlink=True)
        return None

    vg_idx = vg.index

    # Enter edit mode on the duplicate to delete non-group vertices
    bpy.context.view_layer.objects.active = dup
    bpy.ops.object.mode_set(mode='EDIT')

    bm = bmesh.from_edit_mesh(dup.data)
    bm.verts.ensure_lookup_table()

    deform_layer = bm.verts.layers.deform.active
    verts_to_delete = []

    if deform_layer is not None:
        for v in bm.verts:
            weight = v[deform_layer].get(vg_idx, 0.0)
            if weight == 0.0:
                verts_to_delete.append(v)
    else:
        # No deform data — remove all verts (nothing to bake)
        verts_to_delete = list(bm.verts)

    bmesh.ops.delete(bm, geom=verts_to_delete, context='VERTS')
    bmesh.update_edit_mesh(dup.data)

    bpy.ops.object.mode_set(mode='OBJECT')

    # If nothing left, remove and bail
    if len(dup.data.vertices) == 0:
        bpy.data.objects.remove(dup, do_unlink=True)
        return None

    return dup


def run_baker_and_assign(operator, objects: list, model_name: str, p3d_filepath: str = "") -> bool:
    """
    Per-selection bake flow:
      For each named selection with a vertex group:
        1. Duplicate the target object, isolate to just that vertex group's verts
        2. Set as active, point baker at data_temp/
        3. Baker runs modally
        4. On completion: copy/rename files to data/, fix RVMAT paths, delete temp object
        5. Move to next selection
      After all selections: restore baker output path, assign final paths to selection_mats
    """
    if not baker_licensed():
        operator.report(
            {'ERROR'},
            "DayZ Texture Tools baker is not available or not licensed. "
            "Check phlanka_library_beta is installed and activated."
        )
        return False

    # Resolve the final data/ dir
    final_dir = baker_output_path()
    if not final_dir:
        if p3d_filepath:
            final_dir = os.path.join(os.path.dirname(bpy.path.abspath(p3d_filepath)), "data")
        else:
            operator.report({'ERROR'}, "No bake output path set and no P3D path known.")
            return False

    final_dir = bpy.path.abspath(final_dir)
    os.makedirs(final_dir, exist_ok=True)

    temp_dir = os.path.join(os.path.dirname(final_dir), "data_temp")
    os.makedirs(temp_dir, exist_ok=True)

    # Collect all selection names that have a vertex group on the target object
    target_obj = bpy.context.scene.dgm_target_object
    if not target_obj:
        # Fallback: scan dgm objects for any target
        for obj in bpy.data.objects:
            props = getattr(obj, "dgm_props", None)
            if props and props.is_dayz_object:
                target_obj = obj
                break

    sel_names = []
    if target_obj:
        for sm_obj in bpy.data.objects:
            props = getattr(sm_obj, "dgm_props", None)
            if props is None or not props.is_dayz_object:
                continue
            for sm in props.selection_mats:
                name = _selection_base_name(sm)
                if name and name not in sel_names:
                    # Only include if there's a matching vertex group on the target
                    if target_obj.vertex_groups.get(name):
                        sel_names.append(name)

    if not sel_names:
        operator.report({'WARNING'}, "No named selections with vertex groups found to bake.")
        return False

    bake_rvmat = getattr(bpy.context.scene, "dayz_bake_rvmat", False)

    # Queue state — captured by the timer closures
    queue = list(sel_names)  # mutable list, pop from front
    state = {
        "phase": "idle",          # idle | baking | collecting
        "current_sel": None,
        "temp_obj": None,
        "pre_files": set(),
        "total_assigned": 0,
        "original_active": bpy.context.view_layer.objects.active,
        "original_selected": [o for o in bpy.context.selected_objects],
    }

    _STEM_TAGS = ("_co", "_nohq", "_smdi", "_em", "_as")
    _TEXTURE_EXTS = (".paa", ".png", ".tga", ".bmp")

    def _copy_files_for_sel(new_files, sel_name):
        import shutil
        base = "{}_{}".format(model_name, sel_name) if model_name else sel_name
        os.makedirs(final_dir, exist_ok=True)

        tagged = {}
        rv_src = None
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

        for tag, (src, actual_ext) in tagged.items():
            dst = os.path.join(final_dir, base + tag + actual_ext)
            try:
                shutil.copy2(src, dst)
                print("[DGM] Copied {} -> {}".format(os.path.basename(src), os.path.basename(dst)))
            except Exception as e:
                print("[DGM] Could not copy {} to '{}': {}".format(tag, dst, e))

        if rv_src:
            rv_dst = os.path.join(final_dir, base + ".rvmat")
            try:
                shutil.copy2(rv_src, rv_dst)
                _fix_rvmat_paths(rv_dst, temp_dir, final_dir, model_name, sel_name)
            except Exception as e:
                print("[DGM] Could not copy/fix RVMAT to '{}': {}".format(rv_dst, e))

    def _clean_temp():
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print("[DGM] Could not remove temp dir: {}".format(e))

    def _remove_temp_obj():
        tmp = state.get("temp_obj")
        if tmp and tmp.name in bpy.data.objects:
            bpy.data.objects.remove(tmp, do_unlink=True)
        state["temp_obj"] = None

    def _assign_all_paths():
        assigned = 0
        for obj in bpy.data.objects:
            props = getattr(obj, "dgm_props", None)
            if props is None or not props.is_dayz_object:
                continue
            for sm in props.selection_mats:
                name = _selection_base_name(sm)
                if not name:
                    continue
                co_path, rv_path = predict_texture_paths(final_dir, model_name, name)
                if co_path:
                    sm.texture = co_path
                    assigned += 1
                if bake_rvmat and rv_path:
                    sm.rv_mat = rv_path
        print("[DGM] Bake complete — assigned paths to {} named selections.".format(assigned))

    def _start_next():
        """Pop next selection from queue, isolate geometry, start baker. Returns timer interval or None."""
        if not queue:
            # All done
            _restore_baker_output(final_dir)
            _assign_all_paths()
            print("[DGM] Per-selection bake complete.")
            return None

        sel_name = queue.pop(0)
        state["current_sel"] = sel_name
        print("[DGM] Baking selection: '{}'".format(sel_name))

        # Isolate this selection's geometry
        tmp_obj = _isolate_selection_as_object(target_obj, sel_name)
        if tmp_obj is None:
            print("[DGM] No geometry for selection '{}', skipping.".format(sel_name))
            return 0.1  # skip to next immediately

        state["temp_obj"] = tmp_obj

        # Set isolated object as active for baker
        bpy.ops.object.select_all(action='DESELECT')
        tmp_obj.select_set(True)
        bpy.context.view_layer.objects.active = tmp_obj

        # Point baker at temp_dir
        _set_baker_output(temp_dir)

        # Snapshot existing files
        state["pre_files"] = set(os.listdir(temp_dir))

        # Launch baker
        try:
            result = bpy.ops.dayztexturetools.texture_baker_run('INVOKE_DEFAULT')
        except Exception as exc:
            print("[DGM] Baker failed for '{}': {}".format(sel_name, exc))
            _remove_temp_obj()
            return 0.1  # try next selection

        if 'CANCELLED' in result:
            print("[DGM] Baker cancelled for '{}'".format(sel_name))
            _remove_temp_obj()
            return 0.1

        state["phase"] = "baking"
        return 0.5  # start polling

    def _tick():
        """Timer callback — drives the per-selection bake state machine."""
        phase = state["phase"]

        if phase == "idle":
            return _start_next()

        if phase == "baking":
            if _baker_is_running():
                return 0.5  # still running, keep polling

            # Baker finished for this selection
            sel_name = state["current_sel"]
            new_files = _collect_new_files(temp_dir, state["pre_files"])
            if new_files:
                _copy_files_for_sel(new_files, sel_name)
            else:
                print("[DGM] No output files for selection '{}'".format(sel_name))

            _clean_temp()
            _remove_temp_obj()

            state["phase"] = "idle"
            return _start_next()

        # Unknown phase — stop
        return None

    # Kick off the first selection via timer (needs main thread)
    state["phase"] = "idle"
    bpy.app.timers.register(_tick, first_interval=0.1)
    operator.report({'INFO'}, "Baking {} selection(s) individually...".format(len(sel_names)))
    return True
