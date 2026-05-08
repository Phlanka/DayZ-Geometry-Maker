"""
DayZ Geometry Maker - Geometry creation functions.
Implements DayZ/Arma LOD spec from community.bistudio.com/wiki/LOD
"""

import bpy
import bmesh
import mathutils

LOD_VALUES = {
    "Geometry":        "1.000e+13",
    "Geometry PhysX":  "4.000e+13",
    "View Geometry":   "6.000e+15",
    "Fire Geometry":   "7.000e+15",
    "Memory":          "1.000e+15",
    "Land Contact":    "2.000e+15",
    "Roadway":         "3.000e+15",
    "Paths":           "4.000e+15",
    "Hit Points":      "5.000e+15",
    "Shadow Volume":   "1.000e+4",
    "Shadow Volume 2": "1.001e+4",
    "Shadow Buffer":   "1.100e+4",
    "Shadow Buffer 2": "1.101e+4",
    "View Pilot":      "1.100e+3",
    "View Gunner":     "1.000e+3",
    "View Cargo":      "1.200e+3",
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def set_active(obj):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def get_or_create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def move_to_collection(obj, col_name):
    col = get_or_create_collection(col_name)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def set_dgm_props(obj, lod_value, mass=0.0, lod_distance=1.0):
    obj.dgm_props.is_dayz_object = True
    obj.dgm_props.lod = lod_value
    obj.dgm_props.mass = mass
    obj.dgm_props.lod_distance = lod_distance


def add_named_prop(obj, name, value):
    item = obj.dgm_props.named_props.add()
    item.name = name
    item.value = value


def clear_named_props(obj):
    obj.dgm_props.named_props.clear()


def add_fhq_weights(obj, weight=1.0):
    """Add FHQWeights vertex layer required by Geometry LOD for mass distribution."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    key = 'FHQWeights'
    wl = bm.verts.layers.float.get(key) or bm.verts.layers.float.new(key)
    for v in bm.verts:
        v[wl] = weight
    bm.to_mesh(obj.data)
    bm.free()


def get_bbox(obj):
    wm = obj.matrix_world
    corners = [wm @ mathutils.Vector(c) for c in obj.bound_box]
    min_x = min(v.x for v in corners)
    max_x = max(v.x for v in corners)
    min_y = min(v.y for v in corners)
    max_y = max(v.y for v in corners)
    min_z = min(v.z for v in corners)
    max_z = max(v.z for v in corners)
    return min_x, max_x, min_y, max_y, min_z, max_z


def ensure_object_mode():
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def triangulate_object(obj):
    """Triangulate all faces — required for Shadow Volume and Fire Geometry."""
    set_active(obj)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    bpy.ops.object.mode_set(mode='OBJECT')


def mark_all_sharp(obj):
    """Mark all edges sharp — required for Shadow Volume LODs."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for edge in bm.edges:
        edge.smooth = False
    bm.to_mesh(obj.data)
    bm.free()


def assign_default_material(obj, tex="dz\\data\\data\\duha.paa",
                             rvmat="dz\\data\\data\\default.rvmat"):
    """Assign a single default DayZ material to the object."""
    mat_name = "dgm_default_" + obj.name
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.dgm_mat.tex_type = 'Texture'
    mat.dgm_mat.texture = tex
    mat.dgm_mat.rv_mat = rvmat
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def renumber_components(obj):
    """Renumber all ComponentXX vertex groups to be contiguous from 01."""
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


def warn_fire_geo_points(obj, operator=None):
    count = len(obj.data.vertices)
    if count > 3500:
        msg = "Fire Geometry has {} points — DayZ requires < 3500!".format(count)
        if operator:
            operator.report({'WARNING'}, msg)
        else:
            print("WARNING:", msg)


# ---------------------------------------------------------------------------
# Geometry LOD
# ---------------------------------------------------------------------------

def _next_geometry_component_index():
    """Return the next available ComponentXX index by scanning the Geometry collection."""
    used = set()
    col = bpy.data.collections.get("Geometry")
    if col:
        for o in col.objects:
            for vg in o.vertex_groups:
                if vg.name.startswith("Component"):
                    try:
                        used.add(int(vg.name[9:]))
                    except ValueError:
                        pass
    idx = 1
    while idx in used:
        idx += 1
    return idx




def create_geometry_from_selection(operator, mass=100.0):
    """
    Geometry LOD component from selected verts in Edit Mode.
    Reads selected vert world positions, exits Edit Mode, then builds a convex
    hull from those positions and creates a new ComponentXX object from it.
    Falls back to full-object bbox if not in Edit Mode or nothing is selected.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj or original_obj.type != 'MESH':
        operator.report({'ERROR'}, "No target object set.")
        return None

    # Collect selected vert world positions while still in Edit Mode
    selected_world_verts = []
    if original_obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(original_obj.data)
        bm.verts.ensure_lookup_table()
        wm = original_obj.matrix_world
        selected_world_verts = [wm @ v.co.copy() for v in bm.verts if v.select]
        # Do NOT free bm from edit mesh

    if len(selected_world_verts) < 4:
        operator.report({'WARNING'}, "Select at least 4 vertices for a convex hull. Falling back to full object bbox.")
        ensure_object_mode()
        return create_geometry(mass=mass)

    # Exit Edit Mode before creating new objects
    bpy.ops.object.mode_set(mode='OBJECT')

    # Build convex hull from selected positions using bmesh
    hull_bm = bmesh.new()
    for co in selected_world_verts:
        hull_bm.verts.new(co)
    hull_bm.verts.ensure_lookup_table()
    result = bmesh.ops.convex_hull(hull_bm, input=hull_bm.verts)

    # Remove geometry not on the hull (interior verts/faces)
    for geom in result.get("geom_interior", []):
        if isinstance(geom, bmesh.types.BMVert):
            hull_bm.verts.remove(geom)

    # Create new mesh and object from the hull
    hull_mesh = bpy.data.meshes.new("hull_tmp")
    hull_bm.to_mesh(hull_mesh)
    hull_bm.free()

    comp_idx = _next_geometry_component_index()
    comp_name = "Component{:02d}".format(comp_idx)

    obj = bpy.data.objects.new("Geometry_{}".format(comp_name), hull_mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    vg = obj.vertex_groups.new(name=comp_name)
    vg.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')

    add_fhq_weights(obj, weight=mass / max(len(obj.data.vertices), 1))

    set_dgm_props(obj, LOD_VALUES["Geometry"], mass=mass)
    clear_named_props(obj)
    add_named_prop(obj, "autocenter", "0")
    add_named_prop(obj, "canbeoccluded", "1")
    add_named_prop(obj, "canocclude", "0")

    assign_default_material(obj)
    move_to_collection(obj, "Geometry")

    operator.report({'INFO'}, "Created {} from {} selected verts.".format(comp_name, len(selected_world_verts)))
    return obj


def create_geometry(mass=100.0):
    """
    Geometry LOD: one cube per call, each named ComponentXX.
    Each cube is a separate object so it can be reshaped independently.
    On export all Geometry objects are joined into one LOD with transforms applied.
    Wiki: must be closed+convex, ComponentXX named, must have Mass (min 10 for
    character collision). autocenter named property controls centering.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj or original_obj.type != 'MESH':
        return None

    comp_idx = _next_geometry_component_index()
    comp_name = "Component{:02d}".format(comp_idx)

    min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
    cx = (max_x + min_x) / 2
    cy = (max_y + min_y) / 2
    cz = (max_z + min_z) / 2

    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    obj = bpy.context.object
    obj.name = "Geometry_{}".format(comp_name)
    obj.scale = (max_x - min_x, max_y - min_y, max_z - min_z)
    bpy.ops.object.transform_apply(scale=True)

    vg = obj.vertex_groups.new(name=comp_name)
    vg.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')

    # FHQWeights — mass distributed evenly across verts
    add_fhq_weights(obj, weight=mass / max(len(obj.data.vertices), 1))

    set_dgm_props(obj, LOD_VALUES["Geometry"], mass=mass)
    clear_named_props(obj)
    add_named_prop(obj, "autocenter", "0")
    add_named_prop(obj, "canbeoccluded", "1")
    add_named_prop(obj, "canocclude", "0")

    assign_default_material(obj)
    move_to_collection(obj, "Geometry")
    return obj


# ---------------------------------------------------------------------------
# View Geometry LOD
# ---------------------------------------------------------------------------

def create_view_geometry():
    """
    View Geometry: defines object visibility for AI and players.
    Wiki: if absent, Geometry LOD is used instead. Can be a bounding box.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj or original_obj.type != 'MESH':
        return None

    min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
    cx = (max_x + min_x) / 2
    cy = (max_y + min_y) / 2
    cz = (max_z + min_z) / 2

    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    obj = bpy.context.object
    obj.name = "View Geometry"
    obj.scale = (max_x - min_x, max_y - min_y, max_z - min_z)
    bpy.ops.object.transform_apply(scale=True)

    vg = obj.vertex_groups.new(name="Component01")
    vg.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')

    set_dgm_props(obj, LOD_VALUES["View Geometry"])
    assign_default_material(obj)
    move_to_collection(obj, "View Geometry")
    return obj


# ---------------------------------------------------------------------------
# Fire Geometry LOD
# ---------------------------------------------------------------------------

def _get_geometry_components():
    """Return all Geometry_ComponentXX objects from the Geometry collection."""
    col = bpy.data.collections.get("Geometry")
    if not col:
        return []
    return [o for o in col.objects if o.type == 'MESH' and o.name.startswith("Geometry_Component")]


def create_fire_geometry(operator=None, quality=2):
    """
    Fire Geometry: defines bullet/rocket collision.
    Wiki: ComponentXX named, closed+convex, < 3500 points.

    Reuses the Geometry component boxes — they are already convex by definition.
    Each box becomes a ComponentXX in the Fire Geometry LOD.
    Falls back to a single bounding-box cube if no geometry components exist yet.
    """
    ensure_object_mode()

    geo_components = _get_geometry_components()

    if geo_components:
        # Duplicate each geometry component box as a fire geometry component
        copies = []
        for src in geo_components:
            tmp = src.copy()
            tmp.data = src.data.copy()
            bpy.context.scene.collection.objects.link(tmp)
            # Apply transforms so the copy is positioned correctly
            bpy.context.view_layer.objects.active = tmp
            tmp.select_set(True)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            copies.append(tmp)

        # Join all copies into one object
        bpy.ops.object.select_all(action='DESELECT')
        for c in copies:
            c.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()

        obj = bpy.context.active_object
        obj.name = "Fire Geometry"

        # Renumber ComponentXX groups to be contiguous
        renumber_components(obj)

    else:
        # No geometry components yet — fall back to single bbox cube
        original_obj = bpy.context.scene.dgm_target_object
        if not original_obj or original_obj.type != 'MESH':
            return None

        min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
        cx = (max_x + min_x) / 2
        cy = (max_y + min_y) / 2
        cz = (max_z + min_z) / 2

        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
        obj = bpy.context.object
        obj.name = "Fire Geometry"
        obj.scale = (max_x - min_x, max_y - min_y, max_z - min_z)
        bpy.ops.object.transform_apply(scale=True)

        vg = obj.vertex_groups.new(name="Component01")
        vg.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')

        if operator:
            operator.report({'INFO'}, "No Geometry components found — created single bbox. Add Geometry components first for better coverage.")

    set_dgm_props(obj, LOD_VALUES["Fire Geometry"])
    assign_default_material(obj)
    move_to_collection(obj, "Fire Geometry")

    warn_fire_geo_points(obj, operator)
    return obj


# ---------------------------------------------------------------------------
# Shadow Volume LODs
# ---------------------------------------------------------------------------

def create_shadow_volumes():
    """
    Shadow Volume LODs: cast shadows on ground and objects.
    Wiki: must be closed, triangulated, all edges sharp.
    Two are needed: close-range (detailed) and far (simple).
    Shadow Volume is slightly shrunk from res LOD to avoid self-shadowing.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj or original_obj.type != 'MESH':
        return

    ensure_object_mode()

    for i, (lod_val, suffix, scale_factor) in enumerate([
        (LOD_VALUES["Shadow Volume"],  "Shadow Volume",    0.99),
        (LOD_VALUES["Shadow Volume 2"], "Shadow Volume 2",  0.97),
    ]):
        sv_obj = original_obj.copy()
        sv_obj.data = original_obj.data.copy()
        sv_obj.name = suffix

        col = get_or_create_collection("Shadow")
        for c in list(sv_obj.users_collection):
            c.objects.unlink(sv_obj)
        col.objects.link(sv_obj)

        bpy.context.view_layer.objects.active = sv_obj
        sv_obj.select_set(True)

        # Slightly shrink to prevent self-shadowing artifacts
        sv_obj.scale = (sv_obj.scale.x * scale_factor,
                        sv_obj.scale.y * scale_factor,
                        sv_obj.scale.z * scale_factor)
        bpy.ops.object.transform_apply(scale=True)

        # Wiki requirements: triangulated + all edges sharp
        triangulate_object(sv_obj)
        mark_all_sharp(sv_obj)

        set_dgm_props(sv_obj, lod_val)
        assign_default_material(sv_obj)

        bpy.ops.object.select_all(action='DESELECT')


# ---------------------------------------------------------------------------
# Memory LOD
# ---------------------------------------------------------------------------

def get_memory_object():
    """Find the existing Memory LOD object, or return None."""
    col = bpy.data.collections.get("Memory")
    if col:
        for o in col.objects:
            if o.type == 'MESH' and o.dgm_props.is_dayz_object:
                return o
    return None


def memory_point_exists(point_names):
    """Return True if ALL named vertex groups exist on the Memory object."""
    mem = get_memory_object()
    if not mem:
        return False
    existing = {vg.name for vg in mem.vertex_groups}
    if isinstance(point_names, str):
        return point_names in existing
    return all(n in existing for n in point_names)


def _get_or_create_memory_object():
    """Return the Memory LOD object, creating it if needed."""
    mem = get_memory_object()
    if mem:
        return mem
    mesh = bpy.data.meshes.new("Memory")
    mem = bpy.data.objects.new("Memory", mesh)
    bpy.context.scene.collection.objects.link(mem)
    set_dgm_props(mem, LOD_VALUES["Memory"])
    move_to_collection(mem, "Memory")
    return mem


def _remove_memory_groups(mem_obj, names):
    """Remove vertex groups (and their verts) from the memory object by name."""
    ensure_object_mode()
    groups_to_remove = [vg for vg in mem_obj.vertex_groups if vg.name in names]
    if not groups_to_remove:
        return

    keep_names = {vg.name for vg in mem_obj.vertex_groups} - set(names)
    keep_verts = set()
    remove_verts = set()

    for v in mem_obj.data.vertices:
        v_groups = {mem_obj.vertex_groups[g.group].name for g in v.groups}
        if v_groups & keep_names:
            keep_verts.add(v.index)
        elif v_groups & set(names):
            remove_verts.add(v.index)

    for vg in groups_to_remove:
        mem_obj.vertex_groups.remove(vg)

    if remove_verts:
        bm = bmesh.new()
        bm.from_mesh(mem_obj.data)
        bm.verts.ensure_lookup_table()
        to_del = [v for v in bm.verts if v.index in remove_verts]
        bmesh.ops.delete(bm, geom=to_del, context='VERTS')
        bm.to_mesh(mem_obj.data)
        bm.free()
        mem_obj.data.update()


def _add_memory_verts(mem_obj, points):
    """
    Add vertices and vertex groups to the memory object.
    points: list of (group_name, co) or (group_name, [co, co, ...]) for multi-vert groups.
    """
    ensure_object_mode()
    base = len(mem_obj.data.vertices)

    all_cos = []
    group_assignments = []

    for item in points:
        name, co_data = item
        if isinstance(co_data[0], (list, tuple)):
            indices = list(range(base + len(all_cos), base + len(all_cos) + len(co_data)))
            all_cos.extend(co_data)
        else:
            indices = [base + len(all_cos)]
            all_cos.append(co_data)
        group_assignments.append((name, indices))

    if not all_cos:
        return

    mem_obj.data.vertices.add(len(all_cos))
    for i, co in enumerate(all_cos):
        mem_obj.data.vertices[base + i].co = co
    mem_obj.data.update()

    for name, indices in group_assignments:
        vg = mem_obj.vertex_groups.get(name) or mem_obj.vertex_groups.new(name=name)
        vg.add(indices, 1.0, 'REPLACE')


def _bbox_data():
    """Return bbox values and derived positions for the target object."""
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj:
        return None
    min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
    cx = (max_x + min_x) / 2
    cy = (max_y + min_y) / 2
    cz = (max_z + min_z) / 2
    corners = [
        (max_x, max_y, max_z), (max_x, max_y, min_z),
        (max_x, min_y, max_z), (max_x, min_y, min_z),
        (min_x, max_y, max_z), (min_x, max_y, min_z),
        (min_x, min_y, max_z), (min_x, min_y, min_z),
    ]
    center = mathutils.Vector((cx, cy, cz))
    sphere_r = max((mathutils.Vector(c) - center).length for c in corners)
    return {
        'min_x': min_x, 'max_x': max_x,
        'min_y': min_y, 'max_y': max_y,
        'min_z': min_z, 'max_z': max_z,
        'cx': cx, 'cy': cy, 'cz': cz,
        'sphere_r': sphere_r,
    }


def add_memory_bbox():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['boundingbox_max', 'boundingbox_min'])
    _add_memory_verts(mem, [
        ('boundingbox_max', (b['max_x'], b['min_y'], b['max_z'])),
        ('boundingbox_min', (b['min_x'], b['max_y'], b['min_z'])),
    ])


def add_memory_invview():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['invview'])
    _add_memory_verts(mem, [
        ('invview', (b['cx'], b['min_y'] - b['sphere_r'] * 1.75, b['cz'])),
    ])


def add_memory_center():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['ce_center'])
    _add_memory_verts(mem, [
        ('ce_center', (b['cx'], b['cy'], b['cz'])),
    ])


def add_memory_radius():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['ce_radius'])
    _add_memory_verts(mem, [
        ('ce_radius', (b['cx'] - b['sphere_r'], b['cy'], b['cz'])),
    ])


def add_memory_bullet():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['konec hlavne', 'usti hlavne'])
    _add_memory_verts(mem, [
        ('konec hlavne', (-0.214730, -0.001864, 0.113638)),
        ('usti hlavne',  (-0.725986, -0.001864, 0.113638)),
    ])


def add_memory_bolt():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['bolt_axis'])
    _add_memory_verts(mem, [
        ('bolt_axis', [(-0.027365, 0.000002, 0.129440),
                       ( 0.156166, 0.000002, 0.129440)]),
    ])


def add_memory_eject():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['nabojnicestart', 'nabojniceend'])
    _add_memory_verts(mem, [
        ('nabojnicestart', (-0.110412, -0.024278, 0.144729)),
        ('nabojniceend',   (-0.110412, -0.068180, 0.145269)),
    ])


def add_memory_eye():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['eye'])
    _add_memory_verts(mem, [
        ('eye', (0.219703, -0.001609, 0.185810)),
    ])


def add_memory_trigger():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['trigger'])
    _add_memory_verts(mem, [
        ('trigger', (0.0, 0.0, 0.05)),
    ])


def add_memory_magazine():
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['magazine'])
    _add_memory_verts(mem, [
        ('magazine', (0.0, 0.0, 0.0)),
    ])


def _parse_p3d_lod(filepath):
    """
    Parse a single-LOD MLOD P3D file.
    Returns (verts, faces, named_selections, resolution) where:
      verts            : list of (x, y, z) in Blender space (Arma XZY -> Blender XYZ)
      faces            : list of vertex-index lists (quads or tris)
      named_selections : dict  name -> {'verts': [...], 'faces': [...]}
      resolution       : float LOD resolution value
    """
    import struct, os

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Bundled P3D not found: {filepath}")

    data = open(filepath, "rb").read()
    pos = 0

    assert data[pos:pos+4] == b'MLOD', "Not a valid MLOD P3D"
    pos += 12  # sig(4) + version(4) + nlods(4)

    assert data[pos:pos+4] == b'P3DM', "Expected P3DM LOD"
    pos += 4 + 8  # sig + version_major + version_minor

    npoints, nnormals, nfaces = struct.unpack_from('<III', data, pos)
    pos += 16  # 3 counts + flags

    # Vertices stored as (x, z, y, flags) — swap z/y for Blender
    verts = []
    for _ in range(npoints):
        x, z, y, _flag = struct.unpack_from('<fffI', data, pos); pos += 16
        verts.append((x, y, z))

    pos += nnormals * 12  # skip normals

    faces = []
    for _ in range(nfaces):
        count_sides = struct.unpack_from('<I', data, pos)[0]; pos += 4
        fv = []
        for _ in range(count_sides):
            vi, _ni, _u, _v = struct.unpack_from('<IIff', data, pos); pos += 16
            fv.append(vi)
        if count_sides < 4:
            pos += 16  # triangle padding slot
        pos += 4  # face flags
        pos = data.index(b'\x00', pos) + 1  # texture string
        pos = data.index(b'\x00', pos) + 1  # material string
        faces.append(fv)

    named_selections = {}
    while pos < len(data):
        active = data[pos]; pos += 1
        if active == 0:
            break
        end = data.index(b'\x00', pos)
        name = data[pos:end].decode('ascii', errors='replace'); pos = end + 1
        length = struct.unpack_from('<I', data, pos)[0]; pos += 4
        tagg_data = data[pos:pos+length]; pos += length
        if name == '#EndOfFile#':
            break
        if name.startswith('#'):
            continue
        named_selections[name] = {
            'verts': [i for i, w in enumerate(tagg_data[:npoints]) if w > 0],
            'faces': [i for i, s in enumerate(tagg_data[npoints:npoints+nfaces]) if s > 0],
        }

    resolution = struct.unpack_from('<f', data, pos)[0]
    return verts, faces, named_selections, resolution


def _assets_path(filename):
    import os
    return os.path.join(os.path.dirname(__file__), "assets", filename)



# ---------------------------------------------------------------------------
# Ladder Collision Geometry
# ---------------------------------------------------------------------------

def _get_or_create_geometry_object():
    """Return the shared Geometry LOD object, creating it if it does not exist."""
    col = bpy.data.collections.get("Geometry")
    if col:
        for o in col.objects:
            if o.name == "Geometry" and o.type == 'MESH':
                return o
    mesh = bpy.data.meshes.new("Geometry")
    obj  = bpy.data.objects.new("Geometry", mesh)
    bpy.context.scene.collection.objects.link(obj)
    set_dgm_props(obj, LOD_VALUES["Geometry"], mass=0.0)
    clear_named_props(obj)
    add_named_prop(obj, "autocenter", "0")
    add_named_prop(obj, "canbeoccluded", "1")
    add_named_prop(obj, "canocclude", "0")
    assign_default_material(obj)
    move_to_collection(obj, "Geometry")
    return obj


def _make_box_verts(cx, cy, cz, sx, sy, sz):
    """Return 8 corner vertices of a box centred at (cx,cy,cz) with half-extents sx,sy,sz."""
    return [
        (cx - sx, cy - sy, cz - sz), (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz), (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz), (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz), (cx - sx, cy + sy, cz + sz),
    ]

BOX_FACES = [
    (0,1,2,3), (4,7,6,5),
    (0,4,5,1), (1,5,6,2),
    (2,6,7,3), (3,7,4,0),
]


def create_ladder_collision(ladder_obj, mass_per_stringer=20.0):
    """
    Create Geometry LOD collision for a ladder — two box components (left+right stringer)
    added into the shared Geometry object.

    Tracking which ComponentXX belongs to which ladder is done via a custom property
    'dgm_ladder_col_map' on the Geometry object — a dict {ladder_name: [comp_name, ...]}
    No extra vertex groups are created beyond the required ComponentXX groups.
    """
    width        = ladder_obj.get('dgm_p_width',         0.440)
    tube_d       = ladder_obj.get('dgm_p_tube_diameter', 0.042)
    total_height = ladder_obj.get('dgm_ladder_height',   6.0)

    sx_local = width / 2.0

    # World-space ladder position — use matrix_world to transform local stringer centres
    # This handles translation, rotation and scale correctly.
    mw = ladder_obj.matrix_world
    # Left and right stringer world positions (local X=±sx, Y=0, Z=0)
    origin_world  = mw @ mathutils.Vector((0.0,        0.0, 0.0))
    right_stringer = mw @ mathutils.Vector(( sx_local,  0.0, 0.0))
    left_stringer  = mw @ mathutils.Vector((-sx_local,  0.0, 0.0))

    wc       = [mw @ mathutils.Vector(c) for c in ladder_obj.bound_box]
    base_z   = min(c.z for c in wc)
    cx_world = origin_world.x   # X centre of ladder (at origin)
    cy_world = origin_world.y   # Y = stringer plane, not bbox centre

    geo = _get_or_create_geometry_object()

    # Remove previously generated components for this ladder using the map
    import json
    col_map_raw = geo.get('dgm_ladder_col_map', '{}')
    try:
        col_map = json.loads(col_map_raw)
    except Exception:
        col_map = {}

    ladder_name = ladder_obj.name
    old_comps = col_map.get(ladder_name, [])
    if old_comps:
        old_vg_names = set(old_comps)
        keep_names   = {vg.name for vg in geo.vertex_groups} - old_vg_names
        remove_verts = set()
        for v in geo.data.vertices:
            v_grp_names = {geo.vertex_groups[g.group].name for g in v.groups}
            if v_grp_names & old_vg_names and not v_grp_names & keep_names:
                remove_verts.add(v.index)
        for vg_name in old_comps:
            vg = geo.vertex_groups.get(vg_name)
            if vg:
                geo.vertex_groups.remove(vg)
        if remove_verts:
            bm_del = bmesh.new()
            bm_del.from_mesh(geo.data)
            bm_del.verts.ensure_lookup_table()
            del_v = [bm_del.verts[i] for i in remove_verts if i < len(bm_del.verts)]
            bmesh.ops.delete(bm_del, geom=del_v, context='VERTS')
            bm_del.to_mesh(geo.data)
            bm_del.free()
            geo.data.update()

    # Build both stringer boxes
    bm = bmesh.new()
    bm.from_mesh(geo.data)
    bm.verts.ensure_lookup_table()

    hl = tube_d / 2.0
    hh = total_height / 2.0
    cz = base_z + hh

    # Reserve both component indices up front so they are sequential (01+02, 03+04, etc.)
    # _next_geometry_component_index scans existing vertex groups — calling it twice in a
    # loop would return the same index both times because the first group isn't written yet.
    idx_a = _next_geometry_component_index()
    # Temporarily mark idx_a as used by inserting a placeholder group
    _placeholder = geo.vertex_groups.new(name="Component{:02d}".format(idx_a))
    idx_b = _next_geometry_component_index()
    geo.vertex_groups.remove(_placeholder)   # remove placeholder — real group added later

    comp_names = ["Component{:02d}".format(idx_a), "Component{:02d}".format(idx_b)]

    new_comps   = []
    vert_ranges = []
    for comp_name, stringer_world_pos in zip(comp_names, (left_stringer, right_stringer)):
        cx = stringer_world_pos.x
        cy = stringer_world_pos.y

        base_idx  = len(bm.verts)
        new_verts = [bm.verts.new(mathutils.Vector(co))
                     for co in _make_box_verts(cx, cy, cz, hl, hl, hh)]
        for fi in BOX_FACES:
            bm.faces.new([new_verts[i] for i in fi])

        new_comps.append(comp_name)
        vert_ranges.append((comp_name, base_idx, base_idx + 8))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(geo.data)
    bm.free()
    geo.data.update()

    # Assign ComponentXX vertex groups only — no tag groups
    total_verts = len(geo.data.vertices)
    for comp_name, v_start, v_end in vert_ranges:
        vert_indices = list(range(v_start, min(v_end, total_verts)))
        vg = geo.vertex_groups.new(name=comp_name)
        vg.add(vert_indices, 1.0, 'REPLACE')
        w = mass_per_stringer / max(len(vert_indices), 1)
        add_fhq_weights(geo, weight=w)

    # Save the map so we can find these components later
    col_map[ladder_name] = new_comps
    geo['dgm_ladder_col_map'] = json.dumps(col_map)

    existing_mass = geo.get("dgm_mass", 0.0)
    set_dgm_props(geo, LOD_VALUES["Geometry"],
                  mass=existing_mass + mass_per_stringer * 2)

    return geo

def add_memory_ladder(ladder_idx=1):
    """
    Import ladder Memory and View Geometry LODs from bundled P3D assets.
    ladder_idx (1-3) controls which prefix is used: ladder1, ladder2, ladder3.
    Named selections from the P3D (always 'ladder1' prefix) are renamed to match
    the requested index.
    """
    ensure_object_mode()

    prefix = "ladder{}".format(ladder_idx)
    point_names = [
        prefix,
        prefix + '_bottom_front',
        prefix + '_con',
        prefix + '_con_dir',
        prefix + '_dir',
        prefix + '_top_front',
    ]

    # --- Memory LOD ---
    try:
        verts, faces, named_selections, _ = _parse_p3d_lod(_assets_path("ladder_memory.p3d"))
    except Exception as e:
        print(f"[DGM] Failed to load ladder Memory P3D: {e}")
        return

    mem = _get_or_create_memory_object()

    # Remove any existing selections for this ladder slot
    _remove_memory_groups(mem, point_names)

    import mathutils

    # Align spawn to target object:
    #   X/Y = world bounding box centre
    #   Z   = target min Z + 0.340 m (first rung height) — same for all ladder slots
    target_obj = bpy.context.scene.dgm_target_object
    if target_obj is not None:
        world_corners = [target_obj.matrix_world @ mathutils.Vector(c)
                         for c in target_obj.bound_box]
        target_cx    = sum(c.x for c in world_corners) / 8.0
        target_cy    = sum(c.y for c in world_corners) / 8.0
        target_min_z = min(c.z for c in world_corners)
    else:
        target_cx, target_cy, target_min_z = 0.0, 0.0, 0.0

    # Place memory points at fixed offsets from first_rung and last_rung.
    # NO scaling — each point has a fixed semantic position:
    #
    #  P3D vert offsets (measured from asset, Y=up in P3D = Z in Blender):
    #    vert[0]: first_rung_z - 0.021  (dir point near ground)
    #    vert[1]: first_rung_z + 0.000  (bottom_front — exactly first rung)
    #    vert[2]: first_rung_z + 0.912  (con — interaction start)
    #    vert[3]: last_rung_z  + 0.306  (ladder1 top — above last rung)
    #    vert[4]: last_rung_z  + 0.000  (top_front — exactly last rung)
    #    vert[5]: last_rung_z  + 0.004  (con_dir top)
    #
    # X and Z (depth) offsets from the P3D are kept as-is.

    # Get actual ladder dimensions from target object
    target_ladder = bpy.context.scene.dgm_target_object
    if target_ladder is not None and target_ladder.get('dgm_ladder'):
        rung_count    = int(target_ladder.get('dgm_ladder_rungs',   15))
        rung_spacing  = float(target_ladder.get('dgm_p_rung_spacing',  0.320))
        ground_offset = float(target_ladder.get('dgm_p_ground_offset', 0.340))
    else:
        rung_count, rung_spacing, ground_offset = 15, 0.320, 0.340

    actual_first_rung = ground_offset
    actual_last_rung  = ground_offset + (rung_count - 1) * rung_spacing

    # Fixed Z offsets per vertex index (from P3D asset analysis)
    # Y position = stringer plane (local Y=0), not bbox centre
    _tgt = bpy.context.scene.dgm_target_object
    _stringer_cy = (_tgt.matrix_world @ mathutils.Vector((0.0, 0.0, 0.0))).y \
                   if _tgt is not None else 0.0

    VERT_Z_OFFSETS = [
        actual_first_rung - 0.021,   # 0
        actual_first_rung + 0.000,   # 1
        actual_first_rung + 0.912,   # 2
        actual_last_rung  + 0.306,   # 3
        actual_last_rung  + 0.000,   # 4
        actual_last_rung  + 0.004,   # 5
    ]

    base = len(mem.data.vertices)
    mem.data.vertices.add(len(verts))
    for i, co in enumerate(verts):
        z = target_min_z + VERT_Z_OFFSETS[i] if i < len(VERT_Z_OFFSETS)             else target_min_z + actual_last_rung
        # Rotate 180° around Z so memory faces the ladder front (cage is behind)
        mem.data.vertices[base + i].co = mathutils.Vector((
            -co[0] + target_cx,
            -co[1] + _stringer_cy,
            z,
        ))
    mem.data.update()

    # The P3D always uses 'ladder1' prefix — remap to the requested index
    for sel_name, sel_data in named_selections.items():
        # Skip any corrupted/internal selection names (e.g. "AGG\x01...")
        if not sel_name.isascii() or '\x01' in sel_name:
            continue
        remapped = sel_name.replace("ladder1", prefix, 1)
        shifted = [i + base for i in sel_data['verts']]
        vg = mem.vertex_groups.get(remapped) or mem.vertex_groups.new(name=remapped)
        if shifted:
            vg.add(shifted, 1.0, 'REPLACE')

    # --- View Geometry LOD ---
    create_view_geometry_ladder(ladder_idx=ladder_idx)


def remove_memory_ladder(ladder_idx=1):
    """Remove all memory points and View Geometry for a ladder group by index.

    If the Memory object ends up with no vertex groups after removal, the object
    itself and its collection are also deleted.
    """
    ensure_object_mode()
    prefix = "ladder{}".format(ladder_idx)
    point_names = [
        prefix,
        prefix + '_bottom_front',
        prefix + '_con',
        prefix + '_con_dir',
        prefix + '_dir',
        prefix + '_top_front',
    ]
    mem = get_memory_object()
    if mem:
        _remove_memory_groups(mem, point_names)
        # If Memory object now has no vertex groups, remove it and the collection
        if len(mem.vertex_groups) == 0:
            bpy.data.objects.remove(mem, do_unlink=True)
            _cleanup_empty_collection("Memory")
    remove_view_geometry_ladder(ladder_idx=ladder_idx)


def _create_lod_from_p3d(filepath, obj_name, collection_name, lod_key):
    """
    Parse a P3D and create a Blender mesh object registered as a DayZ LOD.
    Named selections are recreated as vertex groups.
    """
    verts, faces, named_selections, _ = _parse_p3d_lod(filepath)

    mesh = bpy.data.meshes.new(obj_name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(obj_name, mesh)
    bpy.context.scene.collection.objects.link(obj)

    for sel_name, sel_data in named_selections.items():
        if not sel_name.isascii() or '\x01' in sel_name:
            continue
        vg = obj.vertex_groups.new(name=sel_name)
        if sel_data['verts']:
            vg.add(sel_data['verts'], 1.0, 'REPLACE')

    set_dgm_props(obj, LOD_VALUES[lod_key])
    assign_default_material(obj)
    set_active(obj)
    move_to_collection(obj, collection_name)
    return obj

def _ladder_vg_obj_name(ladder_idx):
    """Canonical object name for a ladder View Geometry object."""
    return "View Geometry.ladder{}".format(ladder_idx)


def _cleanup_empty_collection(col_name):
    """Remove a scene collection if it exists and contains no objects."""
    col = bpy.data.collections.get(col_name)
    if col is None:
        return
    # Count all objects recursively
    total = len(col.all_objects)
    if total == 0:
        # Unlink from every parent that holds it
        for parent in list(bpy.data.collections) + [bpy.context.scene.collection]:
            if col.name in [c.name for c in getattr(parent, 'children', [])]:
                try:
                    parent.children.unlink(col)
                except Exception:
                    pass
        bpy.data.collections.remove(col)


def create_view_geometry_ladder(ladder_idx=1):
    """Import the bundled ladder View Geometry P3D as a DayZ LOD object.

    The created object is named 'View Geometry.ladderN' so it can be found
    and deleted when the corresponding memory group is removed.
    Each index is offset upward on Z to match the memory point placement.
    The named selection 'Component01' is renamed to 'ladderN' to match the index.
    """
    obj_name = _ladder_vg_obj_name(ladder_idx)

    # Remove any existing object for this slot first
    existing = bpy.data.objects.get(obj_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    try:
        obj = _create_lod_from_p3d(
            _assets_path("ladder_view_geometry.p3d"),
            obj_name=obj_name,
            collection_name="View Geometry",
            lod_key="View Geometry",
        )
    except Exception as e:
        print(f"[DGM] Failed to load ladder View Geometry P3D: {e}")
        return None

    if obj is not None:
        # Align view geometry:
        #   X/Y = target world bounding box centre
        #   Z   = target min Z (no first-rung offset, no per-index offset)
        import mathutils
        target_obj = bpy.context.scene.dgm_target_object
        if target_obj is not None:
            world_corners = [target_obj.matrix_world @ mathutils.Vector(c)
                             for c in target_obj.bound_box]
            target_cx    = sum(c.x for c in world_corners) / 8.0
            target_min_z = min(c.z for c in world_corners)
            # Use stringer Y (local Y=0) — cage shifts the bounding box centre
            target_cy    = (target_obj.matrix_world @ mathutils.Vector((0.0, 0.0, 0.0))).y
        else:
            target_cx, target_cy, target_min_z = 0.0, 0.0, 0.0
        # Scale view geometry Z to match actual last_rung_z.
        # Asset view geometry height = 5.584 m (= 15 rungs * 0.320 + 0.340 + 0.700 - 0.320)
        # We scale so the top of the view geometry aligns with actual total_height.
        ASSET_VG_HEIGHT = 5.584   # view geometry P3D total height (Y range)
        if target_obj is not None and target_obj.get('dgm_ladder'):
            rung_count2    = int(target_obj.get('dgm_ladder_rungs',   15))
            rung_spacing2  = float(target_obj.get('dgm_p_rung_spacing',  0.320))
            ground_offset2 = float(target_obj.get('dgm_p_ground_offset', 0.340))
            top_ext2       = float(target_obj.get('dgm_p_top_extension', 0.700))
            actual_height  = ground_offset2 + (rung_count2 - 1) * rung_spacing2 + top_ext2
        else:
            actual_height = ASSET_VG_HEIGHT
        vg_scale = actual_height / ASSET_VG_HEIGHT if ASSET_VG_HEIGHT > 0 else 1.0
        obj.scale = (1.0, 1.0, vg_scale)
        bpy.ops.object.transform_apply(scale=True)

        obj.location.x = target_cx
        obj.location.y = target_cy
        obj.location.z = target_min_z

        # Rename vertex groups to match the requested ladder index.
        # P3D asset always uses 'ladder1' and 'Component01' — remap both.
        vg_ladder = obj.vertex_groups.get("ladder1")
        if vg_ladder:
            vg_ladder.name = "ladder{}".format(ladder_idx)

        vg_comp = obj.vertex_groups.get("Component01")
        if vg_comp:
            vg_comp.name = "Component{:02d}".format(ladder_idx)

    return obj


def remove_view_geometry_ladder(ladder_idx=1):
    """Delete the View Geometry object for a given ladder index, then clean up empty collections."""
    obj_name = _ladder_vg_obj_name(ladder_idx)
    obj = bpy.data.objects.get(obj_name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
    _cleanup_empty_collection("View Geometry")


def add_memory_lights(count=1):
    import math
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    names = ['light_{}'.format(i) for i in range(1, count + 1)]
    _remove_memory_groups(mem, names)
    points = []
    r = (b['max_x'] - b['min_x']) * 0.35
    for i, name in enumerate(names):
        angle = (2 * math.pi / max(count, 1)) * i
        points.append((name, (
            b['cx'] + r * math.cos(angle),
            b['cy'] + r * math.sin(angle),
            b['max_z'],
        )))
    _add_memory_verts(mem, points)


def add_memory_damage():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['damageHide'])
    _add_memory_verts(mem, [
        ('damageHide', (b['cx'], b['cy'], b['cz'])),
    ])


def add_memory_doors(count=1):
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    names = ['door_{}_axis_{}'.format(i, p) for i in range(1, count + 1) for p in (1, 2)]
    _remove_memory_groups(mem, names)
    points = []
    for i in range(1, count + 1):
        points.extend([
            ('door_{}_axis_1'.format(i), (b['cx'], b['cy'], b['max_z'])),
            ('door_{}_axis_2'.format(i), (b['cx'], b['cy'], b['min_z'])),
        ])
    _add_memory_verts(mem, points)


# ---------------------------------------------------------------------------
# Resolution LODs
# ---------------------------------------------------------------------------

# Default real-world view distances per LOD step (meters).
# Wiki: should roughly halve polygon count each step.
# Lowest LOD should be ~500 polys with as few sections as possible.
DEFAULT_LOD_DISTANCES = {
    1: 1.0,
    2: 2.0,
    3: 3.0,
    4: 4.0,
    5: 5.0,
    6: 6.0,
}

# Decimate ratio per LOD level — each step ~halves the polygon count
DECIMATE_RATIOS = {
    2: 0.5,
    3: 0.25,
    4: 0.125,
    5: 0.06,
    6: 0.03,
}


def create_lod_meshes():
    """
    Resolution LODs: visible model at various view distances.
    LOD 1 is a full copy of the source mesh (no decimation).
    Higher LODs attempt progressive decimation but will never go below the
    face count of a cube (6 quads / 12 tris) — if the mesh is already simple,
    all LODs get the same geometry.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj:
        return

    set_active(original_obj)
    scene = bpy.context.scene

    lod_settings = [
        (scene.dgm_lod1, 1, scene.dgm_lod1_dist),
        (scene.dgm_lod2, 2, scene.dgm_lod2_dist),
        (scene.dgm_lod3, 3, scene.dgm_lod3_dist),
        (scene.dgm_lod4, 4, scene.dgm_lod4_dist),
        (scene.dgm_lod5, 5, scene.dgm_lod5_dist),
        (scene.dgm_lod6, 6, scene.dgm_lod6_dist),
    ]

    col = get_or_create_collection("Resolution LODs")

    for enabled, lod_num, distance in lod_settings:
        if not enabled:
            continue

        ensure_object_mode()

        # Name includes the source object name so multiple objects can each have
        # their own LOD set without overwriting each other.
        existing_name = "{}.LOD{}".format(original_obj.name, lod_num)

        # Remove any existing LOD with this exact name (regenerate)
        if existing_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[existing_name], do_unlink=True)

        lod_obj = original_obj.copy()
        lod_obj.data = original_obj.data.copy()
        lod_obj.name = existing_name
        col.objects.link(lod_obj)

        set_dgm_props(lod_obj, "-1.0", lod_distance=float(distance))
        clear_named_props(lod_obj)

        if lod_num == 1:
            add_named_prop(lod_obj, "forcenotalpha", "1")
            add_named_prop(lod_obj, "LodNoShadow", "1")

        # Copy and isolate materials per LOD
        for slot in lod_obj.material_slots:
            if slot.material:
                new_mat = slot.material.copy()
                new_mat.name = "LOD{}_{}".format(lod_num, slot.material.name)
                slot.material = new_mat

        if lod_num == 1:
            # LOD1 is the full-detail copy — no decimation
            continue

        # Only decimate if the mesh has enough faces to reduce meaningfully.
        # A cube has 6 faces — anything at or below that minimum stays as-is.
        source_face_count = len(lod_obj.data.polygons)
        MIN_FACES = 6
        if source_face_count <= MIN_FACES:
            # Mesh is already as simple as it can be — keep it identical to LOD1
            continue

        ratio = DECIMATE_RATIOS.get(lod_num, 0.5 ** (lod_num - 1))
        target_faces = max(int(source_face_count * ratio), MIN_FACES)
        # Recalculate ratio so decimate hits the floor rather than going below it
        safe_ratio = target_faces / source_face_count

        bpy.context.view_layer.objects.active = lod_obj
        lod_obj.select_set(True)
        dec = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
        dec.decimate_type = 'COLLAPSE'
        dec.ratio = safe_ratio
        bpy.ops.object.modifier_apply(modifier="Decimate")

        if lod_num >= 4 and len(lod_obj.data.materials) > 1:
            assign_default_material(lod_obj)

        bpy.ops.object.select_all(action='DESELECT')


# ---------------------------------------------------------------------------
# View Pilot / Gunner / Cargo
# ---------------------------------------------------------------------------

def create_view_interior(lod_type="View Pilot"):
    """
    Interior view LODs: what the pilot/gunner/cargo sees of the cockpit/cab.
    Wiki: for Car class, View Pilot is used for ALL positions unless View Cargo
    is defined. Players position is determined by proxy position.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj:
        return

    ensure_object_mode()
    set_active(original_obj)

    interior = original_obj.copy()
    interior.data = original_obj.data.copy()
    interior.name = lod_type

    lod_val = LOD_VALUES.get(lod_type, "1.100e+3")
    set_dgm_props(interior, lod_val)

    for slot in interior.material_slots:
        if slot.material:
            new_mat = slot.material.copy()
            new_mat.name = "{}_{}".format(lod_type.replace(" ", ""), slot.material.name)
            slot.material = new_mat

    move_to_collection(interior, lod_type)
    return interior


# ---------------------------------------------------------------------------
# Land Contact LOD
# ---------------------------------------------------------------------------

def create_land_contact():
    """
    Land Contact LOD: single vertex per ground contact point.
    Wiki: defines where the object touches the ground.
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj:
        return

    min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
    cx = (max_x + min_x) / 2
    cy = (max_y + min_y) / 2

    mesh = bpy.data.meshes.new("Land Contact")
    lc_obj = bpy.data.objects.new("Land Contact", mesh)

    # Four ground contact points at corners of base
    contact_points = [
        (min_x, min_y, min_z),
        (max_x, min_y, min_z),
        (max_x, max_y, min_z),
        (min_x, max_y, min_z),
    ]
    mesh.vertices.add(len(contact_points))
    mesh.vertices.foreach_set("co", [c for v in contact_points for c in v])
    mesh.update()

    bpy.context.collection.objects.link(lc_obj)
    set_dgm_props(lc_obj, LOD_VALUES["Land Contact"])
    move_to_collection(lc_obj, "Land Contact")
    return lc_obj


# ---------------------------------------------------------------------------
# Roadway LOD
# ---------------------------------------------------------------------------

def create_roadway():
    """
    Roadway LOD: surface units can stand on top of.
    Wiki: required for infantry to stand on the object, defines sound surface.
    Must not overlap with Geometry LOD (causes wobble). Max ~36m from origin.
    255 point limit if animated.

    Extracts all upward-facing faces (normal Z > 0.5) from the Geometry component
    boxes and raises them by 0.01m so they sit just above the collision geometry
    without overlapping. This correctly handles steps and multi-level surfaces
    because each box contributes its own top face at its own height.

    Falls back to a single top-of-bbox plane if no geometry components exist.
    """
    ensure_object_mode()

    geo_components = _get_geometry_components()

    if geo_components:
        # Collect all upward-facing faces from every geometry component box
        # by duplicating and deleting all non-top faces
        copies = []
        for src in geo_components:
            tmp = src.copy()
            tmp.data = src.data.copy()
            bpy.context.scene.collection.objects.link(tmp)
            bpy.context.view_layer.objects.active = tmp
            tmp.select_set(True)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            copies.append(tmp)

        # Join into one mesh
        bpy.ops.object.select_all(action='DESELECT')
        for c in copies:
            c.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()

        rw_obj = bpy.context.active_object
        rw_obj.name = "Roadway"

        # Delete all faces that don't point upward (normal Z <= 0.5 in world space)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(rw_obj.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            # Keep only faces whose world-space normal points mostly upward
            face.select = face.normal.z <= 0.5
        bm.to_mesh(rw_obj.data)
        bm.free()

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.delete(type='FACE')
        bpy.ops.object.mode_set(mode='OBJECT')

        # Raise surviving faces 0.01m so they don't overlap the Geometry LOD
        bm = bmesh.new()
        bm.from_mesh(rw_obj.data)
        for v in bm.verts:
            v.co.z += 0.01
        bm.to_mesh(rw_obj.data)
        bm.free()
        rw_obj.data.update()

    else:
        # No geometry components — fall back to flat top-of-bbox plane
        original_obj = bpy.context.scene.dgm_target_object
        if not original_obj or original_obj.type != 'MESH':
            return None

        min_x, max_x, min_y, max_y, min_z, max_z = get_bbox(original_obj)
        cx = (max_x + min_x) / 2
        cy = (max_y + min_y) / 2

        bpy.ops.mesh.primitive_plane_add(size=1, location=(cx, cy, max_z + 0.01))
        rw_obj = bpy.context.object
        rw_obj.name = "Roadway"
        rw_obj.scale = (max_x - min_x, max_y - min_y, 1.0)
        bpy.ops.object.transform_apply(scale=True)

    set_dgm_props(rw_obj, LOD_VALUES["Roadway"])
    assign_default_material(rw_obj)
    move_to_collection(rw_obj, "Roadway")
    return rw_obj
