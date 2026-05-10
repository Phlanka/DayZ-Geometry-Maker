"""
DayZ Geometry Maker - Storage Box / Chest Generator
Generates wooden crates, ammo boxes and storage chests.
Lid is a separate vertex group on the same mesh, ready for DayZ door animation.
"""

import bpy
import bmesh
import math
from mathutils import Vector


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _box_verts(bm, x0, y0, z0, x1, y1, z1):
    """Add a closed box to bm. Return list of 8 BMVerts (or [] if degenerate)."""
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        return []
    v = [
        bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)), bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)), bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)), bm.verts.new((x0, y1, z1)),
    ]
    for fi in ((0,1,2,3), (4,7,6,5), (0,4,5,1), (1,5,6,2), (2,6,7,3), (3,7,4,0)):
        bm.faces.new([v[i] for i in fi])
    return v


def _cylinder_verts(bm, p0, p1, radius, segs=8):
    """Add a capped cylinder between p0 and p1. Return all BMVerts."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = p1 - p0
    if ax.length < 1e-6:
        return []
    ax_n = ax.normalized()
    ref = Vector((0, 0, 1))
    if abs(ax_n.dot(ref)) > 0.99:
        ref = Vector((1, 0, 0))
    t2 = ax_n.cross(ref).normalized()
    b2 = ax_n.cross(t2).normalized()
    all_v = []

    def ring(c):
        vs = [bm.verts.new(
                  c + t2 * math.cos(2 * math.pi * i / segs) * radius
                    + b2 * math.sin(2 * math.pi * i / segs) * radius)
              for i in range(segs)]
        all_v.extend(vs)
        return vs

    ra = ring(p0)
    rb = ring(p1)
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new([ra[i], ra[j], rb[j], rb[i]])
    ca = bm.verts.new(p0); all_v.append(ca)
    cb = bm.verts.new(p1); all_v.append(cb)
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new([ca, ra[j], ra[i]])
        bm.faces.new([cb, rb[i], rb[j]])
    return all_v


# ---------------------------------------------------------------------------
# Chest builder
# ---------------------------------------------------------------------------

def build_chest(params):
    """
    Build a storage chest bmesh.
    Returns (bm, body_indices, lid_indices).

    body_indices / lid_indices: lists of int vertex indices for vertex group assignment.
    Caller must call bm.free() after use.

    Coordinate system: Z=up, X=width, Y=length/depth.
    Body base at Z=0 (or foot_height if feet enabled).
    Lid sits immediately on top of the body.
    Front face = −Y, back (hinge side) = +Y.
    """
    bm = bmesh.new()

    W   = max(0.10, float(params.get('width',          0.60)))
    L   = max(0.10, float(params.get('length',         0.40)))
    BH  = max(0.05, float(params.get('body_height',    0.28)))
    LH  = max(0.02, float(params.get('lid_height',     0.12)))
    WT  = max(0.005, min(float(params.get('wall_thickness', 0.025)), min(W, L) * 0.40))
    GAP = max(0.0,   float(params.get('lid_gap',        0.004)))

    lid_type  = params.get('lid_type', 'flat')
    arch_segs = max(4, int(params.get('arch_segs', 8)))

    has_feet = bool(params.get('feet', True))
    foot_h   = max(0.010, float(params.get('foot_height', 0.040)))
    foot_s   = max(0.010, float(params.get('foot_size',   0.035)))

    has_corners = bool(params.get('corner_iron', True))
    corner_t    = max(0.002, float(params.get('corner_thickness', 0.004)))
    corner_w    = max(0.010, float(params.get('corner_width',     0.040)))

    hinge_count = max(0, min(3, int(params.get('hinge_count',  2))))
    hinge_r     = max(0.003, float(params.get('hinge_radius',  0.007)))
    hinge_len   = max(0.015, float(params.get('hinge_length',  0.030)))

    latch_count  = max(0, min(2, int(params.get('latch_count',  1))))
    handle_count = max(0, min(2, int(params.get('handle_count', 1))))

    hw = W / 2.0
    hl = L / 2.0

    body_idx = []
    lid_idx  = []

    def add_body(*args):
        vs = _box_verts(bm, *args)
        body_idx.extend(v.index for v in vs)

    def add_lid(*args):
        vs = _box_verts(bm, *args)
        lid_idx.extend(v.index for v in vs)

    # -----------------------------------------------------------------------
    # BODY — floor slab + 4 walls
    # -----------------------------------------------------------------------
    bz0 = foot_h if has_feet else 0.0
    bz1 = bz0 + BH

    add_body(-hw, -hl, bz0,      hw,       hl,        bz0 + WT)  # floor
    add_body(-hw, -hl, bz0 + WT, hw,       -hl + WT,  bz1)       # front wall (−Y)
    add_body(-hw, hl - WT, bz0 + WT, hw,   hl,        bz1)       # back wall  (+Y)
    add_body(-hw, -hl + WT, bz0 + WT, -hw + WT, hl - WT, bz1)   # left wall  (−X)
    add_body(hw - WT, -hl + WT, bz0 + WT, hw,  hl - WT,  bz1)   # right wall (+X)

    # -----------------------------------------------------------------------
    # FEET — 4 small corner blocks below body
    # -----------------------------------------------------------------------
    if has_feet:
        eps = 0.003
        for fx, fy in (
            (-hw + eps,          -hl + eps),
            ( hw - eps - foot_s, -hl + eps),
            (-hw + eps,           hl - eps - foot_s),
            ( hw - eps - foot_s,  hl - eps - foot_s),
        ):
            add_body(fx, fy, 0.0, fx + foot_s, fy + foot_s, foot_h)

    # -----------------------------------------------------------------------
    # CORNER REINFORCEMENTS — thin L-shaped strips on outer vertical edges
    # Body height only; placed just outside the wall surfaces.
    # -----------------------------------------------------------------------
    if has_corners:
        ct = corner_t
        cw = min(corner_w, min(W, L) * 0.15)
        zc0, zc1 = bz0, bz1

        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            # Strip sitting on the Y-face (front or back wall), runs along X
            x0 = -hw       if sx < 0 else hw - cw
            x1 = -hw + cw  if sx < 0 else hw
            y0 = -hl - ct  if sy < 0 else hl
            y1 = -hl       if sy < 0 else hl + ct
            add_body(x0, y0, zc0, x1, y1, zc1)

            # Strip sitting on the X-face (left or right wall), runs along Y
            xf0 = -hw - ct if sx < 0 else hw
            xf1 = -hw      if sx < 0 else hw + ct
            yf0 = -hl      if sy < 0 else hl - cw
            yf1 = -hl + cw if sy < 0 else hl
            add_body(xf0, yf0, zc0, xf1, yf1, zc1)

    # -----------------------------------------------------------------------
    # HINGES — small cylinders on back wall at the body-lid joint
    # Placed in body group (static visual; animation is driven by lid vgroup).
    # -----------------------------------------------------------------------
    if hinge_count > 0:
        if hinge_count == 1:
            hx_list = [0.0]
        elif hinge_count == 2:
            hx_list = [-W * 0.25, W * 0.25]
        else:
            step = W / (hinge_count + 1)
            hx_list = [-hw + step * (i + 1) for i in range(hinge_count)]

        for hx in hx_list:
            vs = _cylinder_verts(bm,
                (hx - hinge_len * 0.5, hl, bz1 - hinge_r),
                (hx + hinge_len * 0.5, hl, bz1 - hinge_r),
                hinge_r, segs=6)
            body_idx.extend(v.index for v in vs)

    # -----------------------------------------------------------------------
    # LATCHES — small plate protrusions on the front face of the body
    # -----------------------------------------------------------------------
    if latch_count > 0:
        latch_xs = [0.0] if latch_count == 1 else [-W * 0.28, W * 0.28]
        lw = min(0.028, W * 0.06)
        lh = 0.016
        ld = 0.008
        for lx in latch_xs:
            # Latch plate on front body wall, sticking out in −Y
            add_body(lx - lw, -hl - ld, bz1 - lh * 2.0, lx + lw, -hl, bz1)

    # -----------------------------------------------------------------------
    # LID — always offset by GAP above the body top so it's a distinct
    # selection island in Edit Mode.
    # -----------------------------------------------------------------------
    lz0 = bz1 + GAP  # lid base Z

    if lid_type == 'flat':
        add_lid(-hw, -hl, lz0, hw, hl, lz0 + LH)

    elif lid_type == 'arch':
        # Arch profile along Y: z = lz0 + LH * sin(pi * t) for t in [0,1]
        # front (t=0, y=−hl) and back (t=1, y=+hl) both at z=lz0.
        # peak at centre (t=0.5, y=0) at z = lz0 + LH.
        segs = arch_segs
        left_arch  = []
        right_arch = []
        for i in range(segs + 1):
            t = i / segs
            y = -hl + L * t
            z = lz0 + LH * math.sin(math.pi * t)
            left_arch.append( bm.verts.new((-hw, y, z)))
            right_arch.append(bm.verts.new(( hw, y, z)))

        lid_idx.extend(v.index for v in left_arch + right_arch)

        # Arch surface quads (top skin)
        for i in range(segs):
            bm.faces.new([left_arch[i], left_arch[i + 1],
                          right_arch[i + 1], right_arch[i]])

        # Left endcap (−X face): reversed so normal faces −X
        if len(left_arch) >= 3:
            bm.faces.new(list(reversed(left_arch)))

        # Right endcap (+X face)
        if len(right_arch) >= 3:
            bm.faces.new(right_arch)

    # -----------------------------------------------------------------------
    # HANDLES — U-bar on the front face of the lid
    # -----------------------------------------------------------------------
    if handle_count > 0:
        handle_xs = [0.0] if handle_count == 1 else [-W * 0.28, W * 0.28]
        h_w   = min(0.058, W * 0.11)   # full bar span
        h_r   = 0.006                   # bar tube radius
        h_ext = 0.020                   # how far bar sticks out from face
        # Place handle slightly above lid base so it sits on the front face
        h_z   = lz0 + 0.025

        for hpos in handle_xs:
            # Left and right mount posts (−Y outward)
            for side in (-1, 1):
                px = hpos + side * h_w * 0.4
                vs = _cylinder_verts(bm,
                    (px, -hl,        h_z),
                    (px, -hl - h_ext, h_z),
                    h_r, segs=6)
                lid_idx.extend(v.index for v in vs)
            # Horizontal bar connecting both posts
            vs = _cylinder_verts(bm,
                (hpos - h_w * 0.4, -hl - h_ext, h_z),
                (hpos + h_w * 0.4, -hl - h_ext, h_z),
                h_r, segs=6)
            lid_idx.extend(v.index for v in vs)

    # -----------------------------------------------------------------------
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm, body_idx, lid_idx


def _apply_vgroups(obj, body_idx, lid_idx):
    """Create / refresh 'body' and 'lid' vertex groups on obj."""
    for name in ('body', 'lid'):
        vg = obj.vertex_groups.get(name)
        if vg:
            obj.vertex_groups.remove(vg)
    vg_body = obj.vertex_groups.new(name='body')
    vg_lid  = obj.vertex_groups.new(name='lid')
    if body_idx:
        vg_body.add(list(set(body_idx)), 1.0, 'REPLACE')
    if lid_idx:
        vg_lid.add(list(set(lid_idx)),  1.0, 'REPLACE')


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def _count_scene_chests():
    return sum(1 for o in bpy.data.objects
               if o.type == 'MESH' and o.get('dgm_chest') and o.users_scene
               and '.LOD' not in o.name)


def _is_active_chest(obj):
    return (obj is not None
            and obj.type == 'MESH'
            and bool(obj.get('dgm_chest'))
            and '.LOD' not in obj.name)


def _params_from_obj(obj):
    return dict(
        width=float(obj.get('dgm_p_width',            0.60)),
        length=float(obj.get('dgm_p_length',           0.40)),
        body_height=float(obj.get('dgm_p_body_height', 0.28)),
        lid_height=float(obj.get('dgm_p_lid_height',   0.12)),
        wall_thickness=float(obj.get('dgm_p_wall_thickness', 0.025)),
        lid_gap=float(obj.get('dgm_p_lid_gap',             0.004)),
        lid_type=str(obj.get('dgm_p_lid_type',         'flat')),
        arch_segs=int(obj.get('dgm_p_arch_segs',       8)),
        feet=bool(obj.get('dgm_p_feet',                True)),
        foot_height=float(obj.get('dgm_p_foot_height', 0.040)),
        foot_size=float(obj.get('dgm_p_foot_size',     0.035)),
        corner_iron=bool(obj.get('dgm_p_corner_iron',  True)),
        corner_thickness=float(obj.get('dgm_p_corner_thickness', 0.004)),
        corner_width=float(obj.get('dgm_p_corner_width',         0.040)),
        hinge_count=int(obj.get('dgm_p_hinge_count',   2)),
        hinge_radius=float(obj.get('dgm_p_hinge_radius', 0.007)),
        hinge_length=float(obj.get('dgm_p_hinge_length', 0.030)),
        latch_count=int(obj.get('dgm_p_latch_count',   1)),
        handle_count=int(obj.get('dgm_p_handle_count', 1)),
    )


# ---------------------------------------------------------------------------
# Shared draw helper
# ---------------------------------------------------------------------------

def _draw_props(layout, op):
    is_arch = (op.lid_type == 'arch')

    # ---- Dimensions --------------------------------------------------------
    dim_box = layout.box()
    dim_box.label(text="Dimensions", icon='DRIVER_DISTANCE')
    col = dim_box.column(align=True)
    col.prop(op, 'width')
    col.prop(op, 'length')
    col.prop(op, 'body_height')
    col.prop(op, 'wall_thickness')

    # ---- Lid ---------------------------------------------------------------
    lid_box = layout.box()
    lid_box.label(text="Lid", icon='TRIA_UP')
    lcol = lid_box.column(align=True)
    lcol.prop(op, 'lid_type', text="Shape")
    lcol.prop(op, 'lid_height',
              text="Peak Height" if is_arch else "Lid Height")
    if is_arch:
        lcol.prop(op, 'arch_segs', text="Arch Segments")
    lcol.separator()
    lcol.prop(op, 'lid_gap', text="Gap (body → lid)")

    # ---- Feet --------------------------------------------------------------
    feet_box = layout.box()
    feet_row = feet_box.row(align=True)
    feet_row.prop(op, 'feet', text="Feet", toggle=True,
                  icon='CHECKMARK' if op.feet else 'PANEL_CLOSE')
    if op.feet:
        fc = feet_box.column(align=True)
        fc.prop(op, 'foot_height')
        fc.prop(op, 'foot_size')

    # ---- Corner iron -------------------------------------------------------
    corner_box = layout.box()
    corner_row = corner_box.row(align=True)
    corner_row.prop(op, 'corner_iron', text="Corner Iron", toggle=True,
                    icon='CHECKMARK' if op.corner_iron else 'PANEL_CLOSE')
    if op.corner_iron:
        cc = corner_box.column(align=True)
        cc.prop(op, 'corner_thickness', text="Strip Thickness")
        cc.prop(op, 'corner_width',     text="Strip Width")

    # ---- Hardware ----------------------------------------------------------
    hw_box = layout.box()
    hw_box.label(text="Hardware", icon='TOOL_SETTINGS')
    hcol = hw_box.column(align=True)
    hcol.prop(op, 'hinge_count')
    if op.hinge_count > 0:
        hcol.prop(op, 'hinge_radius')
        hcol.prop(op, 'hinge_length')
    hcol.separator()
    hcol.prop(op, 'latch_count')
    hcol.prop(op, 'handle_count')

    # ---- Info summary ------------------------------------------------------
    info_box = layout.box()
    icol = info_box.column(align=True)
    try:
        total_h = (op.foot_height if op.feet else 0.0) + op.body_height + op.lid_height
        icol.label(text="Total height: {:.0f} mm".format(total_h * 1000), icon='INFO')
        icol.label(text="{}×{}×{} cm (W×L×Body)".format(
            round(op.width * 100), round(op.length * 100), round(op.body_height * 100)))
        icol.label(text="Gap: {:.0f} mm  |  Vgroups: 'body', 'lid' (auto-assigned)".format(
            op.lid_gap * 1000), icon='GROUP_VERTEX')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Add operator
# ---------------------------------------------------------------------------

class DGM_OT_add_chest(bpy.types.Operator):
    bl_idname      = "dgm.add_chest"
    bl_label       = "Add Storage Box"
    bl_description = (
        "Generate a storage box or chest with separate 'body' and 'lid' vertex groups.\n"
        "Lid vertex group is ready for DayZ door animation — "
        "use Memory Points > Lid axis then Lid Rotation Setup to configure it"
    )
    bl_options = {'REGISTER', 'UNDO'}

    # ---- Dimension props ---------------------------------------------------
    width: bpy.props.FloatProperty(
        name="Width", description="Box width along X axis",
        default=0.60, min=0.10, max=5.0, unit='LENGTH')
    length: bpy.props.FloatProperty(
        name="Length", description="Box length/depth along Y axis",
        default=0.40, min=0.10, max=5.0, unit='LENGTH')
    body_height: bpy.props.FloatProperty(
        name="Body Height", description="Height of the body without the lid",
        default=0.28, min=0.05, max=3.0, unit='LENGTH')
    lid_height: bpy.props.FloatProperty(
        name="Lid Height",
        description="Height of a flat lid, or peak height above the body edge for an arched lid",
        default=0.12, min=0.02, max=2.0, unit='LENGTH')
    wall_thickness: bpy.props.FloatProperty(
        name="Wall Thickness", description="Thickness of all walls, floor and lid",
        default=0.025, min=0.005, max=0.30, step=0.1, unit='LENGTH')

    # ---- Lid props ---------------------------------------------------------
    lid_gap: bpy.props.FloatProperty(
        name="Lid Gap",
        description="Air gap between top of body and bottom of lid — keeps lid vertices disconnected from body so you can select the whole lid in Edit Mode with a single click",
        default=0.004, min=0.0, max=0.050, step=0.01, unit='LENGTH')
    lid_type: bpy.props.EnumProperty(
        name="Lid Shape",
        items=[
            ('flat', "Flat",  "Flat rectangular lid"),
            ('arch', "Arch",  "Arched/rounded lid — like a classic pirate chest"),
        ],
        default='flat')
    arch_segs: bpy.props.IntProperty(
        name="Arch Segments",
        description="Number of arc subdivisions — more = smoother curve, higher poly count",
        default=8, min=4, max=32)

    # ---- Feet props --------------------------------------------------------
    feet: bpy.props.BoolProperty(
        name="Feet", description="Add small block feet at the bottom corners",
        default=True)
    foot_height: bpy.props.FloatProperty(
        name="Foot Height", default=0.040, min=0.005, max=0.30, step=0.1, unit='LENGTH')
    foot_size: bpy.props.FloatProperty(
        name="Foot Size", description="Foot block footprint (square)",
        default=0.035, min=0.005, max=0.20, step=0.1, unit='LENGTH')

    # ---- Corner iron props -------------------------------------------------
    corner_iron: bpy.props.BoolProperty(
        name="Corner Iron",
        description="Add thin metal corner reinforcement strips on the outer vertical edges",
        default=True)
    corner_thickness: bpy.props.FloatProperty(
        name="Strip Thickness", default=0.004, min=0.001, max=0.030, step=0.01, unit='LENGTH')
    corner_width: bpy.props.FloatProperty(
        name="Strip Width",
        description="How far each strip runs along the face from the corner",
        default=0.040, min=0.005, max=0.20, step=0.1, unit='LENGTH')

    # ---- Hardware props ----------------------------------------------------
    hinge_count: bpy.props.IntProperty(
        name="Hinges", description="Number of cylindrical hinges on the back wall",
        default=2, min=0, max=3)
    hinge_radius: bpy.props.FloatProperty(
        name="Hinge Radius", default=0.007, min=0.002, max=0.050, step=0.1, unit='LENGTH')
    hinge_length: bpy.props.FloatProperty(
        name="Hinge Length", default=0.030, min=0.010, max=0.150, step=0.1, unit='LENGTH')
    latch_count: bpy.props.IntProperty(
        name="Latches", description="Front latch plates on the body",
        default=1, min=0, max=2)
    handle_count: bpy.props.IntProperty(
        name="Handles", description="U-bar handles on the front face of the lid",
        default=1, min=0, max=2)

    _created_obj_name = ""

    def _get_params(self):
        return dict(
            width=self.width, length=self.length,
            body_height=self.body_height, lid_height=self.lid_height,
            wall_thickness=self.wall_thickness,
            lid_gap=self.lid_gap,
            lid_type=self.lid_type, arch_segs=self.arch_segs,
            feet=self.feet, foot_height=self.foot_height, foot_size=self.foot_size,
            corner_iron=self.corner_iron,
            corner_thickness=self.corner_thickness, corner_width=self.corner_width,
            hinge_count=self.hinge_count,
            hinge_radius=self.hinge_radius, hinge_length=self.hinge_length,
            latch_count=self.latch_count, handle_count=self.handle_count,
        )

    def _create_object(self, context):
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass
        name = "DZ_Chest_{}".format(_count_scene_chests() + 1)
        mesh = bpy.data.meshes.new(name)
        obj  = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj['dgm_chest'] = True
        self._created_obj_name = name
        return obj

    def _rebuild(self, context):
        obj = context.active_object
        if not _is_active_chest(obj):
            return
        bm, body_idx, lid_idx = build_chest(self._get_params())
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        _apply_vgroups(obj, body_idx, lid_idx)

    def _commit(self, context):
        obj = context.active_object
        if not _is_active_chest(obj):
            return
        for k, v in self._get_params().items():
            obj['dgm_p_' + k] = v
        obj['dgm_chest_confirmed'] = True

    def invoke(self, context, event):
        self._create_object(context)
        self._rebuild(context)
        return context.window_manager.invoke_props_dialog(self, width=380)

    def cancel(self, context):
        obj = bpy.data.objects.get(self._created_obj_name)
        if obj:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        self._created_obj_name = ""

    def check(self, context):
        self._rebuild(context)
        return True

    def draw(self, context):
        _draw_props(self.layout, self)

    def execute(self, context):
        if not _is_active_chest(context.active_object):
            self._create_object(context)
        self._rebuild(context)
        self._commit(context)
        self.report({'INFO'}, "Storage box created — vertex groups: 'body', 'lid'")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Edit operator
# ---------------------------------------------------------------------------

class DGM_OT_edit_chest(bpy.types.Operator):
    bl_idname      = "dgm.edit_chest"
    bl_label       = "Edit Storage Box"
    bl_description = "Edit parameters of the selected storage box with live preview"
    bl_options     = {'REGISTER', 'UNDO'}

    width: bpy.props.FloatProperty(
        name="Width", default=0.60, min=0.10, max=5.0, unit='LENGTH')
    length: bpy.props.FloatProperty(
        name="Length", default=0.40, min=0.10, max=5.0, unit='LENGTH')
    body_height: bpy.props.FloatProperty(
        name="Body Height", default=0.28, min=0.05, max=3.0, unit='LENGTH')
    lid_height: bpy.props.FloatProperty(
        name="Lid Height", default=0.12, min=0.02, max=2.0, unit='LENGTH')
    wall_thickness: bpy.props.FloatProperty(
        name="Wall Thickness", default=0.025, min=0.005, max=0.30, step=0.1, unit='LENGTH')
    lid_gap: bpy.props.FloatProperty(
        name="Lid Gap",
        description="Air gap between top of body and bottom of lid",
        default=0.004, min=0.0, max=0.050, step=0.01, unit='LENGTH')
    lid_type: bpy.props.EnumProperty(
        name="Lid Shape",
        items=[('flat', "Flat", "Flat lid"), ('arch', "Arch", "Arched lid")],
        default='flat')
    arch_segs: bpy.props.IntProperty(
        name="Arch Segments", default=8, min=4, max=32)
    feet: bpy.props.BoolProperty(name="Feet", default=True)
    foot_height: bpy.props.FloatProperty(
        name="Foot Height", default=0.040, min=0.005, max=0.30, step=0.1, unit='LENGTH')
    foot_size: bpy.props.FloatProperty(
        name="Foot Size",   default=0.035, min=0.005, max=0.20, step=0.1, unit='LENGTH')
    corner_iron: bpy.props.BoolProperty(name="Corner Iron", default=True)
    corner_thickness: bpy.props.FloatProperty(
        name="Strip Thickness", default=0.004, min=0.001, max=0.030, step=0.01, unit='LENGTH')
    corner_width: bpy.props.FloatProperty(
        name="Strip Width",     default=0.040, min=0.005, max=0.20, step=0.1, unit='LENGTH')
    hinge_count: bpy.props.IntProperty(name="Hinges",  default=2, min=0, max=3)
    hinge_radius: bpy.props.FloatProperty(
        name="Hinge Radius", default=0.007, min=0.002, max=0.050, step=0.1, unit='LENGTH')
    hinge_length: bpy.props.FloatProperty(
        name="Hinge Length", default=0.030, min=0.010, max=0.150, step=0.1, unit='LENGTH')
    latch_count:  bpy.props.IntProperty(name="Latches", default=1, min=0, max=2)
    handle_count: bpy.props.IntProperty(name="Handles", default=1, min=0, max=2)

    _snapshot_mesh = None

    @classmethod
    def poll(cls, context):
        return _is_active_chest(context.active_object)

    def _get_params(self):
        return dict(
            width=self.width, length=self.length,
            body_height=self.body_height, lid_height=self.lid_height,
            wall_thickness=self.wall_thickness,
            lid_gap=self.lid_gap,
            lid_type=self.lid_type, arch_segs=self.arch_segs,
            feet=self.feet, foot_height=self.foot_height, foot_size=self.foot_size,
            corner_iron=self.corner_iron,
            corner_thickness=self.corner_thickness, corner_width=self.corner_width,
            hinge_count=self.hinge_count,
            hinge_radius=self.hinge_radius, hinge_length=self.hinge_length,
            latch_count=self.latch_count, handle_count=self.handle_count,
        )

    def _rebuild(self, context):
        obj = context.active_object
        if not _is_active_chest(obj):
            return
        bm, body_idx, lid_idx = build_chest(self._get_params())
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        _apply_vgroups(obj, body_idx, lid_idx)

    def invoke(self, context, event):
        obj = context.active_object
        p = _params_from_obj(obj)
        for k, v in p.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception:
                    pass
        snap = bmesh.new()
        snap.from_mesh(obj.data)
        self._snapshot_mesh = snap
        return context.window_manager.invoke_props_dialog(self, width=380)

    def cancel(self, context):
        obj = context.active_object
        if obj is not None and self._snapshot_mesh is not None:
            self._snapshot_mesh.to_mesh(obj.data)
            obj.data.update()
            self._snapshot_mesh.free()
            self._snapshot_mesh = None

    def check(self, context):
        self._rebuild(context)
        return True

    def draw(self, context):
        _draw_props(self.layout, self)

    def execute(self, context):
        self._rebuild(context)
        for k, v in self._get_params().items():
            context.active_object['dgm_p_' + k] = v
        if self._snapshot_mesh:
            self._snapshot_mesh.free()
            self._snapshot_mesh = None
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel section (called from operators.py DGM_PT_generators)
# ---------------------------------------------------------------------------

def draw_chest_generator_section(layout, context):
    obj      = context.active_object
    is_chest = _is_active_chest(obj)

    box = layout.box()
    count = _count_scene_chests()
    box.label(
        text="Storage boxes in scene: {}".format(count),
        icon='CHECKMARK' if count > 0 else 'OUTLINER_OB_MESH')

    add_row = box.row(align=True)
    add_row.scale_y = 1.3
    add_row.operator("dgm.add_chest", text="Add Storage Box", icon='ADD')

    if is_chest:
        box.separator(factor=0.5)
        info_col = box.column(align=True)

        w  = obj.get('dgm_p_width',       '?')
        l  = obj.get('dgm_p_length',      '?')
        bh = obj.get('dgm_p_body_height', '?')
        lt = obj.get('dgm_p_lid_type',    'flat')
        try:
            info_col.label(
                text="{}  |  {:.0f}×{:.0f}×{:.0f} cm  |  {}".format(
                    obj.name, w * 100, l * 100, bh * 100, lt.capitalize()),
                icon='MESH_CUBE')
        except Exception:
            info_col.label(text=obj.name, icon='MESH_CUBE')

        # Vertex group status indicators
        vg_row = box.row(align=True)
        for vg_name in ('body', 'lid'):
            exists = obj.vertex_groups.get(vg_name) is not None
            vg_row.label(
                text=vg_name,
                icon='CHECKMARK' if exists else 'ERROR')

        box.operator("dgm.edit_chest", text="Edit Storage Box", icon='PREFERENCES')

        # Guidance for animating the lid
        hint = box.box()
        hint.label(text="To animate the lid:", icon='INFO')
        hint.label(text="1. Add Lid axis in Memory Points", icon='DOT')
        hint.label(text="2. Set vgroup = 'lid' in Lid Rotation Setup", icon='DOT')
        hint.label(text="3. Export — lid is driven as a door animation", icon='DOT')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

chest_classes = (
    DGM_OT_add_chest,
    DGM_OT_edit_chest,
)


def register():
    for cls in chest_classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(chest_classes):
        bpy.utils.unregister_class(cls)
