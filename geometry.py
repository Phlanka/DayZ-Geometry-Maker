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
    Copies the ComponentXX geometry components (skipping door pieces) so it
    matches the actual collision shape. Falls back to a bounding box if no
    geometry components exist yet.
    """
    geo_components = [o for o in _get_geometry_components()
                      if not o.name.startswith("Geometry_door_")]

    if geo_components:
        copies = []
        for src in geo_components:
            tmp = src.copy()
            tmp.data = src.data.copy()
            bpy.context.scene.collection.objects.link(tmp)
            bpy.context.view_layer.objects.active = tmp
            tmp.select_set(True)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            copies.append(tmp)

        bpy.ops.object.select_all(action='DESELECT')
        for c in copies:
            c.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()

        obj = bpy.context.active_object
        obj.name = "View Geometry"
        renumber_components(obj)

    else:
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
    """Return all mesh objects from the Geometry collection."""
    col = bpy.data.collections.get("Geometry")
    if not col:
        return []
    return [o for o in col.objects if o.type == 'MESH']


def create_fire_geometry(operator=None, quality=2):
    """
    Fire Geometry: defines bullet/rocket collision.
    Wiki: ComponentXX named, closed+convex, < 3500 points.

    Reuses the Geometry component boxes — they are already convex by definition.
    Each box becomes a ComponentXX in the Fire Geometry LOD.
    Falls back to a single bounding-box cube if no geometry components exist yet.
    """
    ensure_object_mode()

    geo_components = [o for o in _get_geometry_components()
                      if not o.name.startswith("Geometry_door_")]

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
# Door Geometry LOD
# ---------------------------------------------------------------------------

def create_door_geometry():
    """
    Create Geometry, Fire Geometry, and View Geometry LOD meshes for each
    configured door. Each mesh is a convex hull of the door vertex group and
    carries only the vgroup name as its named selection — no ComponentXX.
    The named selection is what DayZ uses to animate collision with the door.
    Existing door geometry objects are removed and recreated fresh each call.
    """
    scene = bpy.context.scene
    target = scene.dgm_target_object
    if not target or target.type != 'MESH':
        return 0

    door_count = getattr(scene, 'dgm_memory_doors_count', 0)
    created = 0

    # (object_name_prefix, lod_key, collection_name, named_props)
    LOD_SPECS = [
        ("Geometry_door_{}",      "Geometry",      "Geometry",      [("autocenter","0"),("canbeoccluded","1"),("canocclude","0")]),
        ("FireGeometry_door_{}",  "Fire Geometry", "Fire Geometry", []),
        ("ViewGeometry_door_{}",  "View Geometry", "View Geometry", []),
    ]

    for di in range(1, door_count + 1):
        vgroup_name = getattr(scene, 'dgm_door_{}_vgroup'.format(di), "").strip()
        if not vgroup_name:
            continue

        vg = target.vertex_groups.get(vgroup_name)
        if not vg:
            continue

        # Collect world-space positions of verts in this group
        wm = target.matrix_world
        world_verts = []
        for v in target.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    world_verts.append(wm @ v.co.copy())
                    break

        if len(world_verts) < 4:
            continue

        # Build convex hull once, reuse mesh data for all three LODs
        hull_bm = bmesh.new()
        for co in world_verts:
            hull_bm.verts.new(co)
        hull_bm.verts.ensure_lookup_table()
        result = bmesh.ops.convex_hull(hull_bm, input=hull_bm.verts)
        for geom in result.get("geom_interior", []):
            if isinstance(geom, bmesh.types.BMVert):
                hull_bm.verts.remove(geom)

        for name_tmpl, lod_key, col_name, named_props in LOD_SPECS:
            obj_name = name_tmpl.format(vgroup_name)

            existing = bpy.data.objects.get(obj_name)
            if existing:
                bpy.data.objects.remove(existing, do_unlink=True)

            hull_mesh = bpy.data.meshes.new(obj_name)
            hull_bm.to_mesh(hull_mesh)

            obj = bpy.data.objects.new(obj_name, hull_mesh)
            bpy.context.scene.collection.objects.link(obj)

            # Only the vgroup name — no ComponentXX needed for door pieces
            door_vg = obj.vertex_groups.new(name=vgroup_name)
            door_vg.add([v.index for v in obj.data.vertices], 1.0, 'REPLACE')

            mass = 10.0
            add_fhq_weights(obj, weight=mass / max(len(obj.data.vertices), 1))

            set_dgm_props(obj, LOD_VALUES[lod_key], mass=mass)
            clear_named_props(obj)
            for prop_name, prop_val in named_props:
                add_named_prop(obj, prop_name, prop_val)

            assign_default_material(obj)
            move_to_collection(obj, col_name)

        hull_bm.free()
        created += 1

    return created


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


def add_memory_ladder():
    b = _bbox_data()
    if not b:
        return
    mem = _get_or_create_memory_object()
    _remove_memory_groups(mem, ['ladder_top', 'ladder_bottom'])
    _add_memory_verts(mem, [
        ('ladder_top',    (b['cx'], b['cy'], b['max_z'])),
        ('ladder_bottom', (b['cx'], b['cy'], b['min_z'])),
    ])


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

        # Remove any existing LOD with this index so we don't get duplicates
        existing_name = "LOD{}".format(lod_num)
        if existing_name in bpy.data.objects:
            old = bpy.data.objects[existing_name]
            bpy.data.objects.remove(old, do_unlink=True)

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
