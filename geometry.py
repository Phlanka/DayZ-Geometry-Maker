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

        # For shadow 2 (far), decimate heavily
        if i == 1:
            dec = sv_obj.modifiers.new("Decimate", 'DECIMATE')
            dec.decimate_type = 'COLLAPSE'
            dec.ratio = 0.3
            bpy.ops.object.modifier_apply(modifier="Decimate")

        # Wiki requirements: triangulated + all edges sharp
        triangulate_object(sv_obj)
        mark_all_sharp(sv_obj)

        set_dgm_props(sv_obj, lod_val)
        assign_default_material(sv_obj)

        bpy.ops.object.select_all(action='DESELECT')


# ---------------------------------------------------------------------------
# Memory LOD
# ---------------------------------------------------------------------------

def create_memory_points():
    """
    Memory LOD: named selections as single vertices defining lights,
    entry points, animation control points, inventory view, etc.

    DayZ-specific named selections:
      boundingbox_min / boundingbox_max  — object bounds for inventory
      invview                            — camera pos for inventory view
      ce_center                          — center of mass / center point
      ce_radius                          — bounding sphere radius reference
      konec hlavne / usti hlavne         — bullet start/end (muzzle)
      bolt_axis                          — bolt travel axis (2 vertices)
      nabojnicestart / nabojniceend      — case ejection start/end
      eye                                — ADS eye position
      trigger                            — trigger position (weapons)
      magazine                           — magazine attachment point
    """
    original_obj = bpy.context.scene.dgm_target_object
    if not original_obj:
        return

    set_active(original_obj)

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

    # Find existing Memory object to append to
    existing_memory = None
    if "Memory" in bpy.data.collections:
        for o in bpy.data.collections["Memory"].objects:
            if o.name.startswith("Memory"):
                existing_memory = o
                break

    existing_groups = set()
    if existing_memory:
        existing_groups = {vg.name for vg in existing_memory.vertex_groups}

    scene = bpy.context.scene
    vertices = []
    vgroups = []  # list of (name, int_index_or_list)

    # --- Bounding box points ---
    if scene.dgm_memory_bbox:
        if 'boundingbox_max' not in existing_groups:
            vertices.append((max_x, min_y, max_z))
            vgroups.append(("boundingbox_max", len(vertices) - 1))
        if 'boundingbox_min' not in existing_groups:
            vertices.append((min_x, max_y, min_z))
            vgroups.append(("boundingbox_min", len(vertices) - 1))

    # --- Inventory camera ---
    if scene.dgm_memory_invview:
        if 'invview' not in existing_groups:
            vertices.append((cx, min_y - sphere_r * 1.75, cz))
            vgroups.append(("invview", len(vertices) - 1))

    # --- Center of mass ---
    if scene.dgm_memory_center and 'ce_center' not in existing_groups:
        vertices.append((cx, cy, cz))
        vgroups.append(("ce_center", len(vertices) - 1))

    # --- Bounding sphere radius reference ---
    if scene.dgm_memory_radius and 'ce_radius' not in existing_groups:
        # Place at center, offset by sphere radius in -X
        vertices.append((cx - sphere_r, cy, cz))
        vgroups.append(("ce_radius", len(vertices) - 1))

    # --- Bullet travel (muzzle): konec=breech end, usti=muzzle/barrel end ---
    if scene.dgm_memory_bullet:
        if 'konec hlavne' not in existing_groups:
            vertices.append((-0.214730, -0.001864, 0.113638))
            vgroups.append(("konec hlavne", len(vertices) - 1))
        if 'usti hlavne' not in existing_groups:
            vertices.append((-0.725986, -0.001864, 0.113638))
            vgroups.append(("usti hlavne", len(vertices) - 1))

    # --- Bolt axis: two verts defining bolt travel direction ---
    if scene.dgm_memory_bolt and 'bolt_axis' not in existing_groups:
        si = len(vertices)
        vertices.extend([
            (-0.027365, 0.000002, 0.129440),
            (0.156166,  0.000002, 0.129440),
        ])
        vgroups.append(("bolt_axis", [si, si + 1]))

    # --- Bullet casing ejection ---
    if scene.dgm_memory_eject:
        if 'nabojnicestart' not in existing_groups:
            vertices.append((-0.110412, -0.024278, 0.144729))
            vgroups.append(("nabojnicestart", len(vertices) - 1))
        if 'nabojniceend' not in existing_groups:
            vertices.append((-0.110412, -0.068180, 0.145269))
            vgroups.append(("nabojniceend", len(vertices) - 1))

    # --- ADS eye position ---
    if scene.dgm_memory_eye and 'eye' not in existing_groups:
        vertices.append((0.219703, -0.001609, 0.185810))
        vgroups.append(("eye", len(vertices) - 1))

    # --- Trigger position ---
    if scene.dgm_memory_trigger and 'trigger' not in existing_groups:
        vertices.append((0.0, 0.0, 0.05))
        vgroups.append(("trigger", len(vertices) - 1))

    # --- Magazine attachment point ---
    if scene.dgm_memory_magazine and 'magazine' not in existing_groups:
        vertices.append((0.0, 0.0, 0.0))
        vgroups.append(("magazine", len(vertices) - 1))

    # --- Ladder top/bottom (for building ladders) ---
    if scene.dgm_memory_ladder:
        if 'ladder_top' not in existing_groups:
            vertices.append((cx, cy, max_z))
            vgroups.append(("ladder_top", len(vertices) - 1))
        if 'ladder_bottom' not in existing_groups:
            vertices.append((cx, cy, min_z))
            vgroups.append(("ladder_bottom", len(vertices) - 1))

    # --- Light positions (light_1 .. light_N) ---
    if scene.dgm_memory_lights:
        count = scene.dgm_memory_lights_count
        for i in range(1, count + 1):
            lname = "light_{:d}".format(i)
            if lname not in existing_groups:
                # Spread lights evenly around the top surface
                import math
                angle = (2 * math.pi / count) * (i - 1)
                r = (max_x - min_x) * 0.35
                vertices.append((cx + r * math.cos(angle), cy + r * math.sin(angle), max_z))
                vgroups.append((lname, len(vertices) - 1))

    # --- Damage / destruction ---
    if scene.dgm_memory_damage:
        if 'damageHide' not in existing_groups:
            vertices.append((cx, cy, cz))
            vgroups.append(("damageHide", len(vertices) - 1))

    # --- Door / action points ---
    if scene.dgm_memory_doors:
        count = scene.dgm_memory_doors_count
        for i in range(1, count + 1):
            for suffix in ("_axis_begin", "_axis_end", "_open_pos", "_closed_pos"):
                dname = "door_{:d}{}".format(i, suffix)
                if dname not in existing_groups:
                    vertices.append((cx, cy, cz))
                    vgroups.append((dname, len(vertices) - 1))

    if not vertices:
        return

    if existing_memory:
        ensure_object_mode()
        base = len(existing_memory.data.vertices)
        existing_memory.data.vertices.add(len(vertices))
        for i, co in enumerate(vertices):
            existing_memory.data.vertices[base + i].co = co
        for name, idx_data in vgroups:
            vg = existing_memory.vertex_groups.new(name=name)
            if isinstance(idx_data, list):
                for idx in idx_data:
                    vg.add([base + idx], 1.0, 'REPLACE')
            else:
                vg.add([base + idx_data], 1.0, 'REPLACE')
        existing_memory.data.update()
    else:
        mesh = bpy.data.meshes.new("Memory")
        mem_obj = bpy.data.objects.new("Memory", mesh)
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set("co", [c for v in vertices for c in v])
        mesh.update()

        bpy.context.collection.objects.link(mem_obj)
        bpy.context.view_layer.objects.active = mem_obj
        mem_obj.select_set(True)

        for name, idx_data in vgroups:
            vg = mem_obj.vertex_groups.new(name=name)
            if isinstance(idx_data, list):
                for idx in idx_data:
                    vg.add([idx], 1.0, 'REPLACE')
            else:
                vg.add([idx_data], 1.0, 'REPLACE')

        set_dgm_props(mem_obj, LOD_VALUES["Memory"])
        move_to_collection(mem_obj, "Memory")


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
