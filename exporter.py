"""
DayZ Geometry Maker - P3D Exporter
Standalone port of ArmaToolbox MDLExporter + ArmaTools.
Writes Arma MLOD P3D format without any ArmaToolbox dependency.
"""

import bpy
import bpy_extras
import bmesh
import struct
import os

from .properties import GEOMETRY_LODS, needs_resolution, lod_name
from .modelcfg import write_model_cfg
from . import baker_bridge


# ---------------------------------------------------------------------------
# Low-level binary writers
# ---------------------------------------------------------------------------

def _write_byte(f, v):
    f.write(struct.pack("B", v))

def _write_sig(f, s):
    f.write(bytes(s, "UTF-8"))

def _write_ulong(f, v):
    f.write(struct.pack("I", v))

def _write_float(f, v):
    f.write(struct.pack("f", v))

def _write_string(f, v):
    data = v.encode('ASCII')
    f.write(struct.pack('<%ds' % (len(data) + 1), data))

def _write_bytes(f, v):
    f.write(v)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_drive(path):
    if not path:
        return ""
    if os.path.isabs(path):
        p = os.path.splitdrive(path)
        return p[1][1:]
    if path.startswith('\\'):
        return path[1:]
    return path


def _get_face_flags(bm):
    key = 'FHQFaceFlags'
    if key not in bm.faces.layers.int.keys():
        return bm.faces.layers.int.new(key)
    return bm.faces.layers.int[key]


def _convert_weight(w):
    w = max(0.0, min(1.0, w))
    v = round(255 - 254 * w)
    return 0 if v == 255 else v


def _build_face_mat_cache(obj, mat_source=None):
    """
    Build a per-face (rvmat, texture) lookup from selection_mats.
    Two-pass stamp: non-bake selections with a manual texture go first,
    bake selections go last and always overwrite — so baked textures win
    on any face shared between a blank/animation selection and a bake one.
    mat_source: object whose selection_mats to read (defaults to obj).
                Pass the target object so all LODs use the same material config.
    Returns a dict {face_index: (rvmat, texture)} or None to use slot fallback.
    """
    src = mat_source if mat_source is not None else obj
    props = src.dgm_props
    if not props.selection_mats:
        return None

    # Precompute vertex -> [face indices]
    vert_to_faces = {}
    for face in obj.data.polygons:
        for vi in face.vertices:
            vert_to_faces.setdefault(vi, []).append(face.index)

    cache = {}

    def _stamp(sm):
        vg = obj.vertex_groups.get(sm.vgroup_name)
        if not vg:
            return
        entry = (_strip_drive(sm.rv_mat), _strip_drive(sm.texture))
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0:
                    for fi in vert_to_faces.get(v.index, []):
                        cache[fi] = entry

    # Pass 1: manual-texture selections (lower priority)
    for sm in props.selection_mats:
        if not sm.bake_texture and sm.texture.strip():
            _stamp(sm)

    # Pass 2: bake selections (highest priority — always overwrite)
    for sm in props.selection_mats:
        if sm.bake_texture:
            _stamp(sm)

    return cache if cache else None


def _get_material_info(face, obj, face_mat_cache=None):
    # Named-selection-based material (preferred)
    if face_mat_cache is not None:
        return face_mat_cache.get(face.index, ("", ""))

    # Blender material slot fallback
    idx = face.material_index
    if 0 <= idx < len(obj.material_slots):
        mat = obj.material_slots[idx].material
        if mat is None:
            return ("", "#(argb,8,8,3)color(1,0,1,1)")
        mp = mat.dgm_mat
        tex_type = mp.tex_type
        if tex_type == 'Texture':
            tex = _strip_drive(mp.texture)
        elif tex_type == 'Custom':
            tex = mp.color_string
        else:
            tex = "#(argb,8,8,3)color({:.3f},{:.3f},{:.3f},1.0,{})".format(
                mp.color_value[0], mp.color_value[1], mp.color_value[2], mp.color_type)
        return (_strip_drive(mp.rv_mat), tex)
    return ("", "")


def _lod_key(obj):
    p = obj.dgm_props
    if p.lod == '-1.0':
        # Resolution LODs: lod_distance is the index (1.0, 2.0, 3.0...)
        # Sort them before all special LODs (which are >= 1e3)
        return p.lod_distance
    if needs_resolution(p.lod):
        return float(p.lod) + p.lod_distance
    return float(p.lod)


def _fixup_resolution(lod, offset):
    if lod < 8.0e15:
        return lod + offset
    exp = format(lod, ".3e")
    suffix = exp[-2:]
    if suffix == "15":
        return float(exp[0:2] + format(offset, "02.0f") + "e+15")
    if suffix == '16':
        return float(exp[0:3] + format(offset, "02.0f") + "e+16")
    return float(exp)


def _renumber_components(obj):
    tmp = "__DGM_TMP__"
    idx = 1
    for grp in obj.vertex_groups:
        if grp.name.startswith("Component"):
            grp.name = tmp + str(idx)
            idx += 1
    idx = 1
    for grp in obj.vertex_groups:
        if grp.name.startswith(tmp):
            grp.name = "Component{:02d}".format(idx)
            idx += 1


def _optimize_export_lod(obj):
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')


# ---------------------------------------------------------------------------
# LOD writers
# ---------------------------------------------------------------------------

def _write_vertices(f, mesh):
    for v in mesh.vertices:
        _write_float(f, v.co.x)
        _write_float(f, v.co.z)
        _write_float(f, v.co.y)
        _write_ulong(f, 0)


def _build_normals_table(mesh):
    """
    Build a deduplicated normals array and a loop→normal_index mapping,
    exactly as Arma3ObjectBuilder does it.
    Returns (normals_list, loop_to_normal_idx).
    normals_list: list of (x, y, z) in Arma coordinate space (-x, -z, -y).
    loop_to_normal_idx: dict {loop_index: index_into_normals_list}
    """
    normals_list = []
    normal_index = {}       # frozen vector -> index
    loop_to_normal_idx = {}

    for poly in mesh.polygons:
        for li in poly.loop_indices:
            n = mesh.corner_normals[li].vector
            arma_n = (-n[0], -n[2], -n[1])
            key = arma_n
            if key not in normal_index:
                normal_index[key] = len(normals_list)
                normals_list.append(arma_n)
            loop_to_normal_idx[li] = normal_index[key]

    return normals_list, loop_to_normal_idx


def _write_normals(f, normals_list):
    for n in normals_list:
        _write_float(f, n[0])
        _write_float(f, n[1])
        _write_float(f, n[2])


def _write_faces(f, obj, mesh, loop_to_normal_idx, face_mat_cache=None):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    ff_layer = _get_face_flags(bm)

    for idx, face in enumerate(mesh.polygons):
        if len(face.vertices) > 4:
            bm.free()
            raise RuntimeError("Object '{}' contains n-gons and cannot be exported".format(obj.name))

        face_flags = bm.faces[idx][ff_layer]
        mat_name, tex_name = _get_material_info(face, obj, face_mat_cache)
        _write_ulong(f, len(face.vertices))

        loop_indices = list(face.loop_indices)
        for i, li in enumerate(loop_indices):
            try:
                uv = mesh.uv_layers[0].data[li].uv
            except IndexError:
                uv = [0.0, 0.0]

            v_idx = face.vertices[i]
            n_idx = loop_to_normal_idx.get(li, 0)
            _write_ulong(f, v_idx)
            _write_ulong(f, n_idx)
            _write_float(f, uv[0])
            _write_float(f, 1.0 - uv[1])

        if len(face.vertices) == 3:
            _write_ulong(f, 0)
            _write_ulong(f, 0)
            _write_float(f, 0.0)
            _write_float(f, 0.0)

        _write_ulong(f, face_flags)
        _write_string(f, tex_name)
        _write_string(f, mat_name)

    bm.free()


def _build_hidden_selection_map(obj):
    """Map vertex group name -> exported selection name (hidden_selection if set, else vgroup name)."""
    result = {}
    props = obj.dgm_props
    sm_lookup = {sm.vgroup_name: sm.hidden_selection for sm in props.selection_mats}
    for vg in obj.vertex_groups:
        hidden = sm_lookup.get(vg.name, "")
        result[vg.name] = hidden if hidden.strip() else vg.name
    return result


def _write_named_selections(f, obj, mesh):
    hidden_map = _build_hidden_selection_map(obj)
    selections = {}
    selections_face = {}
    for vg in obj.vertex_groups:
        selections[vg.name] = set()
        selections_face[vg.name] = set()

    for vertex in mesh.vertices:
        for grp in vertex.groups:
            name = obj.vertex_groups[grp.group].name
            selections[name].add((vertex.index, grp.weight))

    for face in mesh.polygons:
        groups = set(grp.group for v in face.vertices for grp in mesh.vertices[v].groups)
        for gi in groups:
            weights = [grp.weight > 0 for v in face.vertices for grp in mesh.vertices[v].groups if grp.group == gi]
            if all(weights) and len(weights) == len(face.vertices):
                name = obj.vertex_groups[gi].name
                selections_face[name].add(face.index)

    for name in selections:
        _write_byte(f, 1)
        _write_string(f, hidden_map.get(name, name))
        _write_ulong(f, len(mesh.vertices) + len(mesh.polygons))

        vert_blob = bytearray(len(mesh.vertices))
        for vi, w in selections[name]:
            vert_blob[vi] = _convert_weight(w)
        _write_bytes(f, vert_blob)

        poly_blob = bytearray(len(mesh.polygons))
        for fi in selections_face[name]:
            poly_blob[fi] = 1
        _write_bytes(f, poly_blob)


def _write_sharp_edges(f, mesh):
    edges = [e for face in mesh.polygons if not face.use_smooth for e in face.edge_keys]
    for edge in mesh.edges:
        if edge.use_edge_sharp:
            v1, v2 = edge.vertices[0], edge.vertices[1]
            pair = (v1, v2) if v1 < v2 else (v2, v1)
            edges.append(pair)
    edges = list(set(edges))

    if edges:
        _write_byte(f, 1)
        _write_string(f, '#SharpEdges#')
        _write_ulong(f, len(edges) * 2 * 4)
        for e in edges:
            _write_ulong(f, e[0])
            _write_ulong(f, e[1])


def _write_mass(f, obj, mesh):
    _write_byte(f, 1)
    _write_string(f, "#Mass#")
    total = len(mesh.vertices)
    _write_ulong(f, total * 4)
    if total > 0:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        key = 'FHQWeights'
        if key in bm.verts.layers.float.keys():
            wl = bm.verts.layers.float[key]
        else:
            wl = bm.verts.layers.float.new(key)
        for i in range(len(bm.verts)):
            _write_float(f, bm.verts[i][wl])
        bm.free()


def _write_named_property(f, name, value):
    _write_byte(f, 1)
    _write_string(f, "#Property#")
    _write_ulong(f, 128)
    f.write(struct.pack("<64s", name.encode("ASCII")))
    f.write(struct.pack("<64s", value.encode("ASCII")))


def _write_uv_set(f, mesh, total_uvs, idx):
    _write_byte(f, 1)
    _write_string(f, "#UVSet#")
    _write_ulong(f, 4 + total_uvs * 8)
    _write_ulong(f, idx)
    for poly in mesh.polygons:
        for v_idx, li in enumerate(poly.loop_indices):
            try:
                uv = mesh.uv_layers[idx].data[li].uv
            except Exception:
                uv = [0.0, 0.0]
            _write_float(f, uv[0])
            _write_float(f, 1.0 - uv[1])


def _recalc_normals(obj):
    """Recalculate face normals outward before export so Arma gets clean flat normals."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')


def _triangulate_ngons(obj):
    """Triangulate any n-gon faces (5+ sides) on the export copy. Quads are left as-is."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_face_by_sides(number=4, type='GREATER')
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    bpy.ops.object.mode_set(mode='OBJECT')


def _prepare_normals(obj):
    """
    Reproduce what Arma3ObjectBuilder does before reading normals:
    1. Clear any custom split normals so we start clean
    2. Apply a Weighted Normal modifier (weight=50, keep_sharp=True)
       which produces correct smooth/hard edge normals without needing F5 in OB
    """
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Clear custom split normals — same as Faces > Clear Custom Split Normals in edit mode
    with bpy.context.temp_override(active_object=obj, object=obj):
        try:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        except Exception:
            pass

    # Weighted Normal modifier bakes correct normals respecting sharp edges
    mod = obj.modifiers.new("_dgm_weighted_normal", 'WEIGHTED_NORMAL')
    mod.weight = 50
    mod.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier="_dgm_weighted_normal")


def _export_lod(f, obj, idx, mat_source=None):
    _triangulate_ngons(obj)
    _prepare_normals(obj)
    _optimize_export_lod(obj)
    _write_sig(f, 'P3DM')
    _write_ulong(f, 0x1C)
    _write_ulong(f, 0x100)

    mesh = obj.data
    lod = _lod_key(obj)
    if lod < 0:
        lod = -lod

    # Build deduplicated normals table — loop index → normals array index
    # This matches the Arma3ObjectBuilder approach exactly.
    normals_list, loop_to_normal_idx = _build_normals_table(mesh)

    _write_ulong(f, len(mesh.vertices))
    _write_ulong(f, len(normals_list))
    _write_ulong(f, len(mesh.polygons))
    _write_ulong(f, 0)

    face_mat_cache = _build_face_mat_cache(obj, mat_source=mat_source)

    _write_vertices(f, mesh)
    _write_normals(f, normals_list)
    _write_faces(f, obj, mesh, loop_to_normal_idx, face_mat_cache)

    _write_sig(f, 'TAGG')
    _write_named_selections(f, obj, mesh)
    _write_sharp_edges(f, mesh)

    if lod == 1.000e+13:
        _write_mass(f, obj, mesh)

    for prop in obj.dgm_props.named_props:
        _write_named_property(f, prop.name, prop.value)

    total_uvs = sum(len(p.vertices) for p in mesh.polygons)
    for i, layer in enumerate(mesh.uv_layers):
        _write_uv_set(f, mesh, total_uvs, i)

    _write_byte(f, True)
    _write_string(f, '#EndOfFile#')
    _write_ulong(f, 0)

    p = obj.dgm_props
    if p.lod == '-1.0':
        # Custom LOD: lod_distance IS the final index value (1.000, 2.000, 3.000...)
        _write_float(f, p.lod_distance)
    elif needs_resolution(p.lod):
        # Built-in resolution types (Shadow Buffer, View Cargo etc.) need offset applied
        _write_float(f, _fixup_resolution(lod, p.lod_distance))
    else:
        _write_float(f, lod)


def _duplicate_for_export(obj):
    new_obj = obj.copy()
    new_obj.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(new_obj)
    return new_obj


def _join_group_for_export(group, tmp_col):
    """
    Duplicate every object in group, apply transforms on each, then join them
    into one mesh. Returns the joined object. The first object in the group
    is treated as canonical for dgm_props (named props, mass, lod).
    """
    if len(group) == 1:
        tmp = _duplicate_for_export(group[0])
        tmp_col.objects.link(tmp)
        return tmp

    duplicates = []
    for src in group:
        tmp = _duplicate_for_export(src)
        tmp_col.objects.link(tmp)
        # Apply transforms so the world-space positions bake into the mesh
        bpy.context.view_layer.objects.active = tmp
        tmp.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        duplicates.append(tmp)

    # Select all duplicates, make the first one active, then join
    bpy.ops.object.select_all(action='DESELECT')
    for tmp in duplicates:
        tmp.select_set(True)
    bpy.context.view_layer.objects.active = duplicates[0]
    bpy.ops.object.join()

    joined = bpy.context.active_object
    # Renumber all ComponentXX groups to be contiguous after join
    _renumber_components(joined)
    return joined


def _apply_modifiers(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for mod in obj.modifiers:
        bpy.ops.object.modifier_apply(modifier=mod.name)


def _merge_door_axes_on_duplicate(scene, dup):
    """
    On the export duplicate of the Memory LOD, merge each door's axis_1/axis_2
    vertex groups into a single <doorvgroup>_axis group, then remove the
    individual axis_1/axis_2 groups from the duplicate only.
    The original scene objects are never touched.
    """
    for di in range(1, 9):
        door_vg = getattr(scene, 'dgm_door_{}_vgroup'.format(di), "").strip()
        if not door_vg:
            continue
        vg1 = dup.vertex_groups.get('door_{}_axis_1'.format(di))
        vg2 = dup.vertex_groups.get('door_{}_axis_2'.format(di))
        if not vg1 or not vg2:
            continue

        indices = set()
        for v in dup.data.vertices:
            for g in v.groups:
                if g.group in (vg1.index, vg2.index):
                    indices.add(v.index)

        if not indices:
            continue

        merged_name = '{}_axis'.format(door_vg)
        merged_vg = dup.vertex_groups.get(merged_name) or dup.vertex_groups.new(name=merged_name)
        merged_vg.add(list(indices), 1.0, 'REPLACE')

        for vg in (vg1, vg2):
            dup.vertex_groups.remove(vg)


def export_objects_as_p3d(operator, filepath, objects,
                          apply_modifiers=True,
                          merge_same_lod=True,
                          renumber_components=True,
                          apply_transforms=True,
                          write_model_cfg_file=True):
    """Export a list of DayZ/Arma mesh objects to a P3D MLOD file."""

    objects = [o for o in objects if o.type == 'MESH' and o.dgm_props.is_dayz_object]
    if not objects:
        operator.report({'ERROR'}, "No DayZ objects found to export")
        return {'CANCELLED'}

    # Use the target object as the authoritative source of material/selection settings.
    # All LODs inherit material assignments from it so stale selection_mats on
    # duplicated/auto-synced LOD objects never bleed wrong texture paths into the P3D.
    mat_source = bpy.context.scene.dgm_target_object

    objects = sorted(objects, key=_lod_key)

    # Group objects by LOD key. Multiple objects with the same key (e.g. several
    # Geometry_ComponentXX cubes all marked as Geometry LOD) get joined into one
    # mesh before export so they become a single LOD in the P3D.
    from collections import OrderedDict
    lod_groups = OrderedDict()
    for o in objects:
        k = _lod_key(o)
        lod_groups.setdefault(k, []).append(o)
    # The canonical object for each group is the first one (carries named props / mass)
    objects = [group[0] for group in lod_groups.values()]

    bpy.ops.object.mode_set(mode='OBJECT')

    tmp_col = bpy.data.collections.get("__dgm_tmp__")
    if tmp_col is None:
        tmp_col = bpy.data.collections.new("__dgm_tmp__")
    if tmp_col.name not in [c.name for c in bpy.context.scene.collection.children]:
        bpy.context.scene.collection.children.link(tmp_col)

    wm = bpy.context.window_manager
    wm.progress_begin(0, len(objects) * 5)

    try:
        with open(filepath, "wb") as f:
            _write_sig(f, 'MLOD')
            _write_ulong(f, 0x101)
            _write_ulong(f, len(objects))

            for idx, obj in enumerate(objects):
                k = _lod_key(obj)
                group = lod_groups[k]

                # Join all objects sharing this LOD key into one mesh for export
                tmp = _join_group_for_export(group, tmp_col)

                # Merge door axis pairs into combined named selections on the
                # export duplicate only — scene objects are never modified.
                if obj.dgm_props.lod == "1.000e+15":
                    _merge_door_axes_on_duplicate(bpy.context.scene, tmp)

                if apply_modifiers:
                    _apply_modifiers(tmp)

                if apply_transforms:
                    bpy.context.view_layer.objects.active = tmp
                    tmp.select_set(True)
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

                if renumber_components and obj.dgm_props.lod in GEOMETRY_LODS:
                    _renumber_components(tmp)

                _export_lod(f, tmp, idx, mat_source=mat_source)
                wm.progress_update(idx * 5 + 4)

                bpy.ops.object.select_all(action='DESELECT')
                bpy.context.view_layer.objects.active = tmp
                tmp.select_set(True)
                bpy.ops.object.delete()

    except Exception as e:
        operator.report({'ERROR'}, "Export failed: " + str(e))
        return {'CANCELLED'}
    finally:
        obs = [o for o in tmp_col.objects if o.users == 1]
        for o in obs:
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(tmp_col)
        wm.progress_end()

    if write_model_cfg_file:
        try:
            cfg_path = write_model_cfg(filepath, objects)
            operator.report({'INFO'}, "model.cfg written: " + cfg_path)
        except Exception as e:
            operator.report({'WARNING'}, "model.cfg write failed: " + str(e))

    return {'FINISHED'}


# ---------------------------------------------------------------------------
# Script / config.cpp template export
# ---------------------------------------------------------------------------

def _build_animsources(scene):
    """Return AnimationSources config block string from door panel settings."""
    lines = []
    door_count = getattr(scene, "dgm_memory_doors_count", 0)
    for di in range(1, door_count + 1):
        vg = getattr(scene, "dgm_door_{}_vgroup".format(di), "").strip()
        period = getattr(scene, "dgm_door_{}_anim_period".format(di), 0.15)
        if vg:
            lines.append(
                "\t\tclass " + vg + "\n"
                "\t\t{\n"
                "\t\t\tsource=\"user\";\n"
                "\t\t\tinitPhase=0;\n"
                "\t\t\tanimPeriod=" + "{:.2f}".format(period) + ";\n"
                "\t\t};"
            )
    if not lines:
        return ""
    return "\t\tclass AnimationSources\n\t\t{\n" + "\n".join(lines) + "\n\t\t};\n"


def _build_animphases(scene):
    """Return SetAnimationPhase lines for UpdateVisualState in scripts."""
    lines = []
    door_count = getattr(scene, "dgm_memory_doors_count", 0)
    for di in range(1, door_count + 1):
        vg = getattr(scene, "dgm_door_{}_vgroup".format(di), "").strip()
        if vg:
            lines.append('SetAnimationPhase("' + vg + '", phase);')
    if not lines:
        return "// no door animations configured"
    return ("\n\t\t").join(lines)


def _build_damage_zones(scene):
    """Return per-door DamageZones entries, or empty string if no doors configured."""
    lines = []
    door_count = getattr(scene, "dgm_memory_doors_count", 0)
    for di in range(1, door_count + 1):
        vg = getattr(scene, "dgm_door_{}_vgroup".format(di), "").strip()
        if not vg:
            continue
        lines.append(
            "\t\t\t\tclass {vg}\n"
            "\t\t\t\t{{\n"
            "\t\t\t\t\tclass Health\n"
            "\t\t\t\t\t{{\n"
            "\t\t\t\t\t\thitpoints=1000;\n"
            "\t\t\t\t\t\ttransferToGlobalCoef=0;\n"
            "\t\t\t\t\t}};\n"
            "\t\t\t\t\tcomponentNames[]={{\"{vg}\"}};\n"
            "\t\t\t\t\tfatalInjuryCoef=-1;\n"
            "\t\t\t\t\tclass ArmorType\n"
            "\t\t\t\t\t{{\n"
            "\t\t\t\t\t\tclass Projectile\n"
            "\t\t\t\t\t\t{{\n"
            "\t\t\t\t\t\t\tclass Health {{ damage=2; }};\n"
            "\t\t\t\t\t\t\tclass Blood {{ damage=0; }};\n"
            "\t\t\t\t\t\t\tclass Shock {{ damage=0; }};\n"
            "\t\t\t\t\t\t}};\n"
            "\t\t\t\t\t\tclass Melee\n"
            "\t\t\t\t\t\t{{\n"
            "\t\t\t\t\t\t\tclass Health {{ damage=2.5; }};\n"
            "\t\t\t\t\t\t\tclass Blood {{ damage=0; }};\n"
            "\t\t\t\t\t\t\tclass Shock {{ damage=0; }};\n"
            "\t\t\t\t\t\t}};\n"
            "\t\t\t\t\t}};\n"
            "\t\t\t\t}};".format(vg=vg)
        )
    if not lines:
        return ""
    return "\t\t\t\tclass DamageZones\n\t\t\t\t{\n" + "\n".join(lines) + "\n\t\t\t\t};\n"


def _build_doors_block(scene):
    """Return a class Doors {} block from door panel settings, or empty string."""
    lines = []
    door_count = getattr(scene, "dgm_memory_doors_count", 0)
    for di in range(1, door_count + 1):
        vg = getattr(scene, "dgm_door_{}_vgroup".format(di), "").strip()
        period = getattr(scene, "dgm_door_{}_anim_period".format(di), 0.15)
        if not vg:
            continue
        lines.append(
            "\t\tclass {vg}\n"
            "\t\t{{\n"
            "\t\t\tdisplayName=\"{vg}\";\n"
            "\t\t\tcomponent=\"{vg}\";\n"
            "\t\t\tsoundPos=\"{vg}_action\";\n"
            "\t\t\tanimPeriod={period:.2f};\n"
            "\t\t\tinitPhase=0.0;\n"
            "\t\t\tinitOpened=0.0;\n"
            "\t\t\tsoundOpen=\"doorWoodenSmallOpen\";\n"
            "\t\t\tsoundClose=\"doorWoodenSmallClose\";\n"
            "\t\t\tsoundLocked=\"doorWoodenSmallRattle\";\n"
            "\t\t\tsoundOpenABit=\"doorWoodenSmallOpenABit\";\n"
            "\t\t}};".format(vg=vg, period=period)
        )
    if not lines:
        return ""
    return "\t\tclass Doors\n\t\t{\n" + "\n".join(lines) + "\n\t\t};\n"


def _build_cfgmods(class_name, scripts_root):
    """Build the CfgMods block using the actual scripts folder path, or return empty string."""
    if not scripts_root:
        return ""
    # scripts_root is e.g. P:\MyMod\scripts — parent folder name is the mod dir name
    mod_folder = os.path.basename(os.path.dirname(os.path.abspath(scripts_root)))
    scripts_rel = mod_folder + "/scripts"
    return (
        "class CfgMods\n"
        "{{\n"
        "\tclass {cn}\n"
        "\t{{\n"
        "\t\tdir = \"{cn}\";\n"
        "\t\tpicture = \"\";\n"
        "\t\taction = \"\";\n"
        "\t\thideName = 1;\n"
        "\t\thidePicture = 1;\n"
        "\t\tname = \"{cn}\";\n"
        "\t\tcredits = \"Phlanka\";\n"
        "\t\tauthor = \"\";\n"
        "\t\tauthorID = \"0\";\n"
        "\t\tversion = \"1.0\";\n"
        "\t\ttype = \"mod\";\n"
        "\t\tdependencies[] = {{\"Game\", \"World\", \"Mission\"}};\n"
        "\t\tclass defs\n"
        "\t\t{{\n"
        "\t\t\tclass gameScriptModule\n"
        "\t\t\t{{\n"
        "\t\t\t\tvalue = \"\";\n"
        "\t\t\t\tfiles[] = {{\"{sp}/3_Game\"}};\n"
        "\t\t\t}};\n"
        "\t\t\tclass worldScriptModule\n"
        "\t\t\t{{\n"
        "\t\t\t\tvalue = \"\";\n"
        "\t\t\t\tfiles[] = {{\"{sp}/4_World\"}};\n"
        "\t\t\t}};\n"
        "\t\t\tclass missionScriptModule\n"
        "\t\t\t{{\n"
        "\t\t\t\tvalue = \"\";\n"
        "\t\t\t\tfiles[] = {{\"{sp}/5_Mission\"}};\n"
        "\t\t\t}};\n"
        "\t\t}};\n"
        "\t}};\n"
        "}};\n"
    ).format(cn=class_name, sp=scripts_rel)


def _export_mod_files(p3d_path, class_name, scene, scripts_root, config_template):
    """Write config.cpp and scripts next to the p3d.

    config_template: 'container_base', 'house_no_destruct', or 'none'.
    """
    if config_template == 'none':
        return

    addon_dir = os.path.dirname(__file__)
    template_base = os.path.join(addon_dir, "templates", config_template)
    model_dir = os.path.dirname(p3d_path)

    use_scripts = (config_template == 'container_base' and scripts_root)
    cfgmods = _build_cfgmods(class_name, scripts_root) if use_scripts else ""

    # Model path: absolute path stripped of drive, backslashes, no leading slash
    model_path = os.path.abspath(p3d_path)
    model_path = os.path.splitdrive(model_path)[1].lstrip("\\/")

    replacements = {
        "CLASSNAME": class_name,
        "MODELPATH": model_path,
        "CFGMODS\n": cfgmods,
        "ANIMSOURCES": _build_animsources(scene),
        "ANIMPHASES": _build_animphases(scene),
        "DOORS\n": _build_doors_block(scene),
        "DAMAGEZONES\n": _build_damage_zones(scene),
    }

    def _write_template(src_path, dst_path):
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(content)

    # config.cpp next to the p3d
    _write_template(
        os.path.join(template_base, "model", "config.cpp"),
        os.path.join(model_dir, "config.cpp"),
    )

    # 4_World scripts — container_base only
    if use_scripts:
        scripts_template = os.path.join(template_base, "4_World")
        scripts_out = os.path.join(scripts_root, "4_World")
        for dirpath, dirnames, filenames in os.walk(scripts_template):
            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                rel = os.path.relpath(src_path, scripts_template)
                rel = rel.replace("CLASSNAME", class_name)
                _write_template(src_path, os.path.join(scripts_out, rel))






# ---------------------------------------------------------------------------
# P3D path picker (file browser only — saves path to scene, does not export)
# ---------------------------------------------------------------------------

class DGM_OT_pick_p3d_path(bpy.types.Operator):
    bl_idname = "dgm.pick_p3d_path"
    bl_label = "Set P3D Save Path"
    bl_description = "Choose where to save the P3D file"

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default="*.p3d", options={'HIDDEN'})

    def invoke(self, context, event):
        scene = context.scene
        existing = getattr(scene, "dgm_p3d_path", "").strip()
        if existing:
            self.filepath = bpy.path.abspath(existing)
        else:
            blend = bpy.path.basename(bpy.data.filepath)
            default_name = os.path.splitext(blend)[0] if blend else "yourmodel"
            self.filepath = default_name + ".p3d"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        context.scene.dgm_p3d_path = self.filepath
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Export Operator — reads paths from scene, no dialog
# ---------------------------------------------------------------------------

class DGM_OT_export_p3d(bpy.types.Operator):
    bl_idname = "dgm.export_p3d"
    bl_label = "Export DayZ Mod"
    bl_description = "Export P3D, model.cfg, config.cpp and scripts"

    def execute(self, context):
        scene = context.scene

        raw = getattr(scene, "dgm_p3d_path", "").strip()
        if not raw:
            self.report({'ERROR'}, "Set the P3D path first (click the folder icon next to P3D)")
            return {'CANCELLED'}

        p3d_path = bpy.path.abspath(raw)
        if not p3d_path.lower().endswith(".p3d"):
            p3d_path += ".p3d"

        class_name = os.path.splitext(os.path.basename(p3d_path))[0]
        model_dir = os.path.dirname(p3d_path)
        os.makedirs(model_dir, exist_ok=True)

        # Textures directory
        tex_path_raw = getattr(scene, "dgm_textures_path", "").strip()
        textures_dir = bpy.path.abspath(tex_path_raw) if tex_path_raw else ""

        # Scripts directory
        scripts_path_raw = getattr(scene, "dgm_scripts_path", "").strip()
        scripts_dir = bpy.path.abspath(scripts_path_raw) if scripts_path_raw else ""
        config_template = getattr(scene, "dgm_config_template", "container_base")

        # Ensure there is an active object
        target = getattr(scene, "dgm_target_object", None)
        if target is None:
            for obj in scene.objects:
                if obj.type == 'MESH':
                    target = obj
                    break
        if target is not None:
            for obj in scene.objects:
                obj.select_set(False)
            target.select_set(True)
            context.view_layer.objects.active = target

        objects = list(bpy.data.objects)

        # Pre-assign texture paths so the P3D is written with correct paths
        has_bake = target and hasattr(target, "dgm_props") and any(
            sm.bake_texture for sm in target.dgm_props.selection_mats
        )
        bake_rvmat = getattr(scene, "dayz_bake_rvmat", False)
        if has_bake and textures_dir:
            os.makedirs(textures_dir, exist_ok=True)
            baker_bridge.pre_assign_bake_paths(objects, textures_dir, class_name, bake_rvmat)

        result = export_objects_as_p3d(
            self, p3d_path, objects,
            apply_modifiers=True,
            merge_same_lod=True,
            renumber_components=True,
            apply_transforms=True,
            write_model_cfg_file=getattr(scene, "dgm_write_model_cfg", True),
        )

        if 'FINISHED' not in result:
            return result

        # Bake textures after P3D is written
        if has_bake and baker_bridge.baker_licensed():
            for obj in scene.objects:
                obj.select_set(False)
            if target:
                target.select_set(True)
                context.view_layer.objects.active = target
            baked = baker_bridge.run_baker_and_assign(
                self, objects, class_name, p3d_filepath=p3d_path
            )
            if not baked:
                self.report({'WARNING'}, "Texture bake failed — check DayZ Texture Tools panel")

        # Write config files and scripts
        try:
            _export_mod_files(p3d_path, class_name, scene, scripts_dir, config_template)
        except Exception as e:
            self.report({'WARNING'}, "Config/script export failed: " + str(e))

        self.report({'INFO'}, "Export complete: " + p3d_path)
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(DGM_OT_export_p3d.bl_idname, text="DayZ P3D (.p3d)")


export_classes = (DGM_OT_pick_p3d_path, DGM_OT_export_p3d,)


def register():
    for cls in export_classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(export_classes):
        bpy.utils.unregister_class(cls)
