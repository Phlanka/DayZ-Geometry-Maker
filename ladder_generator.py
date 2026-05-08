"""
DayZ Geometry Maker - Ladder Generator (Type 1 - straight ladder)
=================================================================
Coordinate system:  Z = up,  X = width,  Y = depth.

DayZ standard reference values (checkmark in UI if matched, warning if not):
  GROUND_OFFSET_STD  = 0.340 m   (first rung from ground)
  RUNG_SPACING_STD   = 0.320 m   (rung centre-to-centre)
  TUBE_DIAMETER_STD  = 0.042 m   (42 mm diameter)
  TOP_EXT_STD        = 0.700 m   (stringer extension above last rung)
  VALID_WIDTHS_MM    = 440 or 480 mm (centre-to-centre)

All values are editable. Checkmark = DayZ standard, exclamation = deviation.
"""

import bpy
import bmesh
import math
from mathutils import Vector


# ---------------------------------------------------------------------------
#  DayZ standard reference values
# ---------------------------------------------------------------------------

GROUND_OFFSET_STD = 0.340
RUNG_SPACING_STD  = 0.320
TUBE_DIAMETER_STD = 0.042   # displayed and stored as diameter
TOP_EXT_STD       = 0.700
VALID_WIDTHS_MM   = (440, 480)

_TOL = 1e-4


def _std_icon(value, reference):
    return 'CHECKMARK' if abs(value - reference) < _TOL else 'ERROR'


# ---------------------------------------------------------------------------
#  Geometry primitive — closed manifold tube
# ---------------------------------------------------------------------------

def _make_tube(bm, p0, p1, radius, segs):
    """
    Build a closed (manifold) cylinder from p0 to p1 with the given radius.
    Geometry is added directly into bm.
    """
    p0 = Vector(p0)
    p1 = Vector(p1)
    axis = p1 - p0
    if axis.length < 1e-6:
        return

    axis_n = axis.normalized()
    ref = Vector((0.0, 0.0, 1.0))
    if abs(axis_n.dot(ref)) > 0.99:
        ref = Vector((1.0, 0.0, 0.0))
    tang = axis_n.cross(ref).normalized()
    btan = axis_n.cross(tang).normalized()

    def ring(c):
        verts = []
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            verts.append(bm.verts.new(
                c + tang * math.cos(a) * radius + btan * math.sin(a) * radius))
        return verts

    ra = ring(p0)
    rb = ring(p1)

    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new([ra[i], ra[j], rb[j], rb[i]])

    ca = bm.verts.new(p0)
    cb = bm.verts.new(p1)
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new([ca, ra[j], ra[i]])
        bm.faces.new([cb, rb[i], rb[j]])


# ---------------------------------------------------------------------------
#  Type 1 ladder builder
# ---------------------------------------------------------------------------

def build_ladder_type1(params):
    """
    Build a Type 1 (straight) ladder bmesh.
    Returns (bm, rung_count, total_height).
    Caller must call bm.free() after use.

    Z = up. Ladder base at Z=0, extends upward.
    Stringers run along Z. Rungs are horizontal along X.

    params:
        width           float  - stringer centre-to-centre (m)
        tube_diameter   float  - diameter of all tubes (m)
        rung_count      int    - number of rungs
        rung_spacing    float  - rung centre-to-centre spacing (m)
        ground_offset   float  - first rung height from base (m)
        top_extension   float  - stringer length above last rung (m)
        resolution      int    - tube cross-section segment count
    """
    bm = bmesh.new()

    segs   = max(4, int(params['resolution']))
    r      = float(params['tube_diameter']) / 2.0
    width  = float(params['width'])
    sx     = width / 2.0

    rung_count    = max(1, int(params['rung_count']))
    rung_spacing  = float(params['rung_spacing'])
    ground_offset = float(params['ground_offset'])
    top_ext       = float(params['top_extension'])

    last_rung_z  = ground_offset + (rung_count - 1) * rung_spacing
    total_height = last_rung_z + top_ext

    # Stringers — vertical along Z
    _make_tube(bm, (-sx, 0.0, 0.0), (-sx, 0.0, total_height), r, segs)
    _make_tube(bm,  (sx, 0.0, 0.0),  (sx, 0.0, total_height), r, segs)

    # Rungs — horizontal along X
    for i in range(rung_count):
        z = ground_offset + i * rung_spacing
        _make_tube(bm, (-sx, 0.0, z), (sx, 0.0, z), r, segs)

    # Optional safety cage
    if params.get('cage_enabled', False):
        _build_cage(bm, params, sx, total_height)

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=5e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    return bm, rung_count, total_height


# ---------------------------------------------------------------------------
#  Cage builder — D-arc safety cage
# ---------------------------------------------------------------------------

def _make_arc_tube(bm, arc_pts, radius, segs):
    """
    Build a single continuous tube along a list of centreline points.
    Each junction between segments shares its ring of vertices — no gaps,
    no overlapping end-caps, clean manifold result.

    arc_pts : list of Vector, path of tube centreline
    radius  : tube cross-section radius
    segs    : sides of tube cross-section
    """
    if len(arc_pts) < 2:
        return

    def _tangent(i):
        """Local tangent at point i."""
        if i == 0:
            return (arc_pts[1] - arc_pts[0]).normalized()
        if i == len(arc_pts) - 1:
            return (arc_pts[-1] - arc_pts[-2]).normalized()
        return (arc_pts[i + 1] - arc_pts[i - 1]).normalized()

    def _frame(tang):
        """Stable tangent frame perpendicular to tang.
        Uses Z as primary reference; falls back to X when axis is near Z,
        and to Y when axis is near both Z and X."""
        ref = Vector((0.0, 0.0, 1.0))
        if abs(tang.dot(ref)) > 0.99:
            ref = Vector((1.0, 0.0, 0.0))
            if abs(tang.dot(ref)) > 0.99:
                ref = Vector((0.0, 1.0, 0.0))
        t2 = tang.cross(ref).normalized()
        b2 = tang.cross(t2).normalized()
        return t2, b2

    def _ring(centre, tang):
        verts = []
        t2, b2 = _frame(tang)
        for k in range(segs):
            a = 2.0 * math.pi * k / segs
            verts.append(bm.verts.new(
                centre + t2 * math.cos(a) * radius + b2 * math.sin(a) * radius))
        return verts

    rings = [_ring(arc_pts[i], _tangent(i)) for i in range(len(arc_pts))]

    # Side quads between adjacent rings
    for i in range(len(rings) - 1):
        ra, rb = rings[i], rings[i + 1]
        for k in range(segs):
            j = (k + 1) % segs
            bm.faces.new([ra[k], ra[j], rb[j], rb[k]])

    # End caps only at the two actual ends
    ca = bm.verts.new(arc_pts[0])
    cb = bm.verts.new(arc_pts[-1])
    ra, rb = rings[0], rings[-1]
    for k in range(segs):
        j = (k + 1) % segs
        bm.faces.new([ca, ra[j], ra[k]])
        bm.faces.new([cb, rb[k], rb[j]])


def _build_cage(bm, params, sx, total_height):
    """
    Add a safety cage hoop to an existing bmesh.

    Shape per hoop (top view):
      - Two straight arms extending perpendicular to the ladder plane (-Y direction),
        one from the right stringer and one from the left stringer.
        Arm length = cage_arm_length (the green part in the sketch).
      - A semicircular arc connecting the two arm ends.
        Arc radius = sx  (so the full arc width = ladder width).
        Arc deepest point = cage_arm_length + sx behind the ladder.

    This means:
      cage_arm_length = adjustable (how far the straight part extends)
      arc radius      = always equals sx (half ladder width)
      total depth     = cage_arm_length + sx

    Coordinate system: Z=up, X=width, Y=depth (front=+Y, back=-Y).
    Right stringer at (+sx, 0), left at (-sx, 0).

    params:
        cage_depth      float  - length of straight arm section (m), default 0.350
        cage_bar_count  int    - vertical bars, default 5
        hoop_spacing    float  - vertical spacing between hoops, default 0.900
        cage_start_z    float  - Z where cage begins, default 2.200
        cage_tube_d     float  - cage tube diameter, default 0.025
        resolution      int    - tube cross-section segments
    """
    arm_len      = max(0.010, float(params.get('cage_depth',    0.350)))
    # User sets visible bar count. Internally add 2 for the stringer positions
    # (index 0 and last_idx) which land on stringers and are not drawn separately.
    bar_count    = int(params.get('cage_bar_count', 5)) + 2
    hoop_spacing = float(params.get('hoop_spacing',  0.900))
    cage_start_z = float(params.get('cage_start_z',  2.200))
    cage_tube_r  = float(params.get('cage_tube_d',   0.025)) / 2.0
    segs         = max(4, int(params.get('resolution', 8)))
    arc_segs     = max(10, segs * 2)

    # Arc: semicircle of radius sx, centred at (0, -arm_len)
    # Connects (-sx, -arm_len) through (0, -arm_len - sx) to (+sx, -arm_len)
    arc_cx, arc_cy = 0.0, -arm_len
    arc_r = sx  # arc radius = half ladder width

    def hoop_points(z):
        """
        Return ordered list of centreline points for one complete hoop at height z.
        Path: right stringer (sx,0) -> straight arm to (sx,-arm_len)
              -> semicircle to (-sx,-arm_len) -> straight arm back to (-sx,0)
        """
        pts = []
        arm_steps = max(2, int(arm_len / 0.05))
        arc_steps = arc_segs

        # Right straight arm: from (sx, 0) to (sx, -arm_len)
        for i in range(arm_steps + 1):
            t = i / arm_steps
            pts.append(Vector((sx, -t * arm_len, z)))

        # Semicircle: from (sx, -arm_len) clockwise to (-sx, -arm_len)
        # Circle centre at (0, -arm_len), radius sx
        # Right end: angle = 0  (cos0=1, sin0=0 -> x=sx, y=arc_cy)
        # Left end:  angle = pi (cos pi=-1 -> x=-sx, y=arc_cy)
        # Go clockwise = decreasing angle (0 -> -pi)
        for i in range(1, arc_steps + 1):
            a = -math.pi * i / arc_steps   # 0 to -pi
            x = arc_cx + arc_r * math.cos(a)
            y = arc_cy + arc_r * math.sin(a)
            pts.append(Vector((x, y, z)))

        # Left straight arm: from (-sx, -arm_len) back to (-sx, 0)
        for i in range(1, arm_steps + 1):
            t = i / arm_steps
            pts.append(Vector((-sx, -(1.0 - t) * arm_len, z)))

        return pts

    # Hoop heights
    hoop_zs = []
    hz = cage_start_z
    while hz <= total_height + 1e-5:
        hoop_zs.append(hz)
        hz += hoop_spacing
    if not hoop_zs:
        return

    # Build hoops
    for hz in hoop_zs:
        pts = hoop_points(hz)
        _make_arc_tube(bm, pts, cage_tube_r, segs)

    # Vertical bars — evenly distributed across the ENTIRE hoop perimeter
    # (both straight arms + arc). Index 0 = right stringer, last = left stringer.
    # Example: 3 bars -> right stringer, arc midpoint, left stringer.
    if len(hoop_zs) > 1 and bar_count > 0:
        # Compute bar XY positions geometrically — independent of arc_segs/resolution.
        # Path: right arm (sx,0)->(sx,-arm_len), arc, left arm (-sx,-arm_len)->(-sx,0)
        # Total arc length (approximate): 2*arm_len + pi*sx
        # Parameterise t in [0,1] over the full path, compute XY directly.
        arm_l   = arm_len
        arc_len = math.pi * sx
        total_l = 2.0 * arm_l + arc_len

        def bar_xy(t):
            """Return (x, y) for parameter t in [0,1] along the hoop centreline."""
            dist = t * total_l
            if dist <= arm_l:
                # Right arm: x=sx, y goes from 0 to -arm_len
                frac = dist / arm_l if arm_l > 1e-6 else 0.0
                return (sx, -frac * arm_l)
            dist -= arm_l
            if dist <= arc_len:
                # Arc: from (sx, -arm_len) clockwise to (-sx, -arm_len)
                a = -(math.pi * dist / arc_len)  # 0 to -pi
                x = arc_cx + sx * math.cos(a)
                y = arc_cy + sx * math.sin(a)
                return (x, y)
            dist -= arc_len
            # Left arm: x=-sx, y goes from -arm_len to 0
            frac = dist / arm_l if arm_l > 1e-6 else 1.0
            return (-sx, -(1.0 - frac) * arm_l)

        bar_positions = [bar_xy(b / (bar_count - 1)) if bar_count > 1 else bar_xy(0.5)
                         for b in range(bar_count)]

        for (bx, by) in bar_positions:
            for k in range(len(hoop_zs) - 1):
                p0 = Vector((bx, by, hoop_zs[k]))
                p1 = Vector((bx, by, hoop_zs[k + 1]))
                _make_tube(bm, p0, p1, cage_tube_r, segs)


def _calc_expected_depth(params):
    """
    Calculate expected bounding box Y depth for the integrity check.
    Coordinate system: Y = depth, cage goes into -Y, stringers sit at Y=0.

    Without cage: bounding box Y = tube_diameter (just the stringer tube)
    With cage:    front = +tube_r (front of stringer)
                  back  = -(arm_len + arc_r + tube_r)
                         = -(cage_depth + sx + tube_r)
                  total = cage_depth + sx + 2 * tube_r
    """
    td = float(params['tube_diameter'])
    if params.get('cage_enabled', False):
        sx       = float(params['width']) / 2.0
        arm_len  = float(params.get('cage_depth', 0.35))
        arc_r    = sx   # arc radius equals half ladder width
        total    = arm_len + arc_r + td   # front tube_r + back depth + back tube_r
        return round(total, 4)
    return round(td, 4)


def _count_scene_ladders():
    """Count DZ_Ladder objects in the current scene, excluding Resolution LOD copies."""
    return sum(1 for o in bpy.data.objects
               if o.get('dgm_ladder') is True
               and o.users_scene
               and '.LOD' not in o.name)

def _is_active_ladder(obj):
    """True if obj is a tracked ladder object (not a LOD copy)."""
    return (obj is not None
            and obj.type == 'MESH'
            and obj.get('dgm_ladder') is True
            and '.LOD' not in obj.name)

# ---------------------------------------------------------------------------
#  Main operator — Type 1
# ---------------------------------------------------------------------------

class DGM_OT_ladder_type1(bpy.types.Operator):
    bl_idname      = "dgm.ladder_type1"
    bl_label       = "Add Ladder"
    bl_description = "DayZ ladder with correct animation dimensions (440/480 mm wide, 320 mm rung spacing, 42 mm tube diameter)."
    bl_options = {'REGISTER', 'UNDO'}

    width: bpy.props.FloatProperty(
        name="Width",
        description=(
            "Stringer centre-to-centre distance.\n"
            "DayZ standard: 440 mm or 480 mm.\n"
            "Other values will trigger a warning icon."
        ),
        default=0.440, min=0.100, max=2.000, step=1,
        unit='LENGTH',
    )
    tube_diameter: bpy.props.FloatProperty(
        name="Tube Diameter",
        description=(
            "Outer diameter of all tubes (stringers and rungs).\n"
            "DayZ standard: 42 mm (radius 21 mm).\n"
            "Changing this affects collision thickness."
        ),
        default=TUBE_DIAMETER_STD, min=0.002, max=0.400, step=0.1,
        unit='LENGTH',
    )
    rung_count: bpy.props.IntProperty(
        name="Rung Count",
        description=(
            "Total number of rungs (steps).\n"
            "Total ladder height is calculated automatically:\n"
            "  height = first_rung + (count - 1) x spacing + top_extension"
        ),
        default=16, min=1, max=120,
    )
    rung_spacing: bpy.props.FloatProperty(
        name="Rung Spacing",
        description=(
            "Centre-to-centre distance between rungs.\n"
            "DayZ standard: 320 mm.\n"
            "Must match the animation controller spacing for correct climbing."
        ),
        default=RUNG_SPACING_STD, min=0.050, max=1.000, step=1,
        unit='LENGTH',
    )
    ground_offset: bpy.props.FloatProperty(
        name="First Rung Height",
        description=(
            "Height of the first rung above the ladder base (Z=0).\n"
            "DayZ standard: 340 mm minimum.\n"
            "Too low and the player animation will clip the ground."
        ),
        default=GROUND_OFFSET_STD, min=0.010, max=2.000, step=1,
        unit='LENGTH',
    )
    top_extension: bpy.props.FloatProperty(
        name="Top Extension",
        description=(
            "Stringer length extending above the last rung.\n"
            "DayZ standard: 700 mm.\n"
            "Used as grab rail when player reaches the top."
        ),
        default=TOP_EXT_STD, min=0.0, max=5.000, step=1,
        unit='LENGTH',
    )
    resolution: bpy.props.IntProperty(
        name="Tube Segments",
        description=(
            "Number of sides on each tube cross-section.\n"
            "4 = square, 8 = octagon, 16+ = visually round.\n"
            "Higher values produce smoother tubes but heavier meshes."
        ),
        default=10, min=4, max=24,
    )

    # ── Cage properties ───────────────────────────────────────────────────────
    cage_enabled: bpy.props.BoolProperty(
        name="Safety Cage",
        description=(
            "Add an industrial D-arc safety cage around the ladder.\n"
            "The cage is a 180° semicircle behind the ladder, open at the front.\n"
            "Cage is part of the same mesh object."
        ),
        default=False,
    )
    cage_start_z: bpy.props.FloatProperty(
        name="Cage Start Height",
        description=(
            "Height above base where the cage begins.\n"
            "Standard: 2200 mm — falls below this height are survivable."
        ),
        default=2.200, min=0.0, max=20.0, step=1, unit='LENGTH',
    )
    cage_depth: bpy.props.FloatProperty(
        name="Cage Depth",
        description=(
            "How deep the cage extends behind the ladder — \n"
            "essentially how much space a person has inside the cage.\n"
            "The arc width is always tied to the ladder width.\n"
            "Reference model: ~700 mm."
        ),
        default=0.700, min=0.100, max=2.000, step=1, unit='LENGTH',
    )
    hoop_spacing: bpy.props.FloatProperty(
        name="Hoop Spacing",
        description="Vertical distance between cage hoops. Standard: 900 mm.",
        default=0.900, min=0.200, max=3.000, step=1, unit='LENGTH',
    )
    cage_bar_count: bpy.props.IntProperty(
        name="Vertical Bars",
        description="Number of vertical bars along the cage arc connecting hoops.",
        default=5, min=0, max=12,
    )


    def _get_params(self):
        return dict(
            width=self.width,
            tube_diameter=self.tube_diameter,
            rung_count=self.rung_count,
            rung_spacing=self.rung_spacing,
            ground_offset=self.ground_offset,
            top_extension=self.top_extension,
            resolution=self.resolution,
            cage_enabled=self.cage_enabled,
            cage_start_z=self.cage_start_z,
            cage_depth=self.cage_depth,
            hoop_spacing=self.hoop_spacing,
            cage_bar_count=self.cage_bar_count,
            cage_tube_d=self.tube_diameter,  # cage uses same tube diameter as ladder
        )

    def _rebuild(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or not obj.get('dgm_ladder'):
            return
        params = self._get_params()
        bm, rung_count, total_height = build_ladder_type1(params)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        # Write display counters — but NOT dgm_p_* or confirmed flag
        # so integrity check doesn't trigger during live preview
        obj['dgm_ladder_rungs']  = rung_count
        obj['dgm_ladder_height'] = round(total_height, 4)

    def _commit(self, context):
        """Write all stored params and expected dimensions — called only from execute()."""
        obj = context.active_object
        if obj is None or not obj.get('dgm_ladder'):
            return
        params = self._get_params()
        _, rung_count, total_height = build_ladder_type1(params)
        obj['dgm_ladder_rungs']           = rung_count
        obj['dgm_ladder_height']          = round(total_height, 4)
        obj['dgm_ladder_expected_height'] = round(total_height, 4)
        obj['dgm_ladder_expected_width']  = round(params['width'] + params['tube_diameter'], 4)
        obj['dgm_ladder_expected_depth']  = _calc_expected_depth(params)
        obj['dgm_p_cage_enabled']  = params.get('cage_enabled',  False)
        obj['dgm_p_cage_start_z']  = params.get('cage_start_z',  2.200)
        obj['dgm_p_cage_depth']    = params.get('cage_depth',    0.350)
        obj['dgm_p_hoop_spacing']  = params.get('hoop_spacing',  0.900)
        obj['dgm_p_cage_bar_count']= params.get('cage_bar_count', 5)
        obj['dgm_p_width']         = params['width']
        obj['dgm_p_tube_diameter'] = params['tube_diameter']
        obj['dgm_p_rung_count']    = params['rung_count']
        obj['dgm_p_rung_spacing']  = params['rung_spacing']
        obj['dgm_p_ground_offset'] = params['ground_offset']
        obj['dgm_p_top_extension'] = params['top_extension']
        obj['dgm_p_resolution']    = params['resolution']
        obj['dgm_ladder_confirmed'] = True

    @classmethod
    def poll(cls, context):
        return _count_scene_ladders() < 3

    _created_obj_name: str = ""   # track the object we created so cancel can delete it

    def invoke(self, context, event):
        # Always create a brand new ladder object — never reuse existing
        # Find the lowest unused DZ_Ladder_N name (1, 2, 3)
        ladder_num = next(n for n in range(1, 4)
                          if not bpy.data.objects.get('DZ_Ladder_{}'.format(n)))
        obj_name = "DZ_Ladder_{}".format(ladder_num)
        mesh = bpy.data.meshes.new(obj_name)
        obj  = bpy.data.objects.new(obj_name, mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        for o in bpy.context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        obj['dgm_ladder']      = True
        obj['dgm_ladder_type'] = 1
        self._created_obj_name = obj_name
        self._rebuild(context)
        return context.window_manager.invoke_props_dialog(self, width=400)

    def cancel(self, context):
        """User pressed Escape or Cancel — delete the preview object."""
        obj = bpy.data.objects.get(self._created_obj_name)
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        self._created_obj_name = ""

    def check(self, context):
        self._rebuild(context)
        return True

    def draw(self, context):
        layout = self.layout
        params = self._get_params()

        box = layout.box()
        box.label(text="Straight Ladder", icon='MESH_CYLINDER')

        col = box.column(align=True)

        def prop_row(prop_name, std_value):
            row = col.row(align=True)
            row.prop(self, prop_name)
            row.label(text="", icon=_std_icon(getattr(self, prop_name), std_value))

        # Width — valid if 440 or 480 mm
        row_w = col.row(align=True)
        row_w.prop(self, 'width')
        w_icon = 'CHECKMARK' if round(self.width * 1000) in VALID_WIDTHS_MM else 'ERROR'
        row_w.label(text="", icon=w_icon)

        col.separator()
        prop_row('tube_diameter',  TUBE_DIAMETER_STD)
        col.separator()
        prop_row('rung_spacing',   RUNG_SPACING_STD)
        prop_row('ground_offset',  GROUND_OFFSET_STD)
        prop_row('top_extension',  TOP_EXT_STD)
        col.separator()
        col.prop(self, 'rung_count')

        # Info
        bm_info, rung_count, total_height = build_ladder_type1(params)
        bm_info.free()
        last_rung_z = params['ground_offset'] + (rung_count - 1) * params['rung_spacing']

        info_box = layout.box()
        icol = info_box.column(align=True)
        icol.label(text="Rungs: {}".format(rung_count), icon='INFO')
        icol.label(text="Total height:  {:.3f} m".format(total_height))
        icol.label(text="Last rung at:  {:.3f} m".format(last_rung_z))
        icol.label(text="Width:  {:.0f} mm".format(params['width'] * 1000))

        # ── Safety Cage ──────────────────────────────────────────────────────
        cage_box = layout.box()
        cage_header = cage_box.row(align=True)
        cage_text = "Remove Safety Cage" if self.cage_enabled else "Add Safety Cage"
        cage_icon = 'X' if self.cage_enabled else 'ADD'
        cage_header.prop(self, 'cage_enabled', text=cage_text, icon=cage_icon)
        if self.cage_enabled:
            ccol = cage_box.column(align=True)
            ccol.prop(self, 'cage_start_z')
            ccol.prop(self, 'cage_depth')
            ccol.separator()
            ccol.prop(self, 'hoop_spacing')
            ccol.prop(self, 'cage_bar_count')
            # Cage info
            hoop_count = max(0, int((total_height - self.cage_start_z) / self.hoop_spacing) + 1)                          if self.cage_start_z < total_height else 0
            ccol.separator()
            info_row = ccol.row()
            info_row.enabled = False
            total_depth = self.cage_depth + params['width'] / 2.0
            info_row.label(text="Hoops: {}  |  Total depth: {:.0f} mm".format(
                hoop_count, total_depth * 1000),
                icon='INFO')

        # Mesh quality — compact single row
        q_row = layout.row(align=True)
        q_row.label(text="Tube Segments:", icon='MESH_CIRCLE')
        q_row.prop(self, 'resolution', text="")

    def execute(self, context):
        self._rebuild(context)
        self._commit(context)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Edit operator — edits the currently selected ladder object
# ---------------------------------------------------------------------------

class DGM_OT_ladder_edit(bpy.types.Operator):
    bl_idname      = "dgm.ladder_edit"
    bl_label       = "Edit Ladder"
    bl_description = "Edit parameters of the selected ladder object"
    bl_options     = {'REGISTER', 'UNDO'}

    # Same properties as Type 1 operator — identical descriptions for consistent tooltips
    width: bpy.props.FloatProperty(
        name="Width",
        description=(
            "Stringer centre-to-centre distance.\n"
            "DayZ standard: 440 mm or 480 mm.\n"
            "Other values will trigger a warning icon."
        ),
        default=0.440, min=0.100, max=2.000, step=1, unit='LENGTH')
    tube_diameter: bpy.props.FloatProperty(
        name="Tube Diameter",
        description=(
            "Outer diameter of all tubes (stringers and rungs).\n"
            "DayZ standard: 42 mm (radius 21 mm).\n"
            "Changing this affects collision thickness."
        ),
        default=TUBE_DIAMETER_STD, min=0.002, max=0.400, step=0.1, unit='LENGTH')
    rung_count: bpy.props.IntProperty(
        name="Rung Count",
        description=(
            "Total number of rungs (steps).\n"
            "Total ladder height is calculated automatically:\n"
            "  height = first_rung + (count - 1) x spacing + top_extension"
        ),
        default=16, min=1, max=120)
    rung_spacing: bpy.props.FloatProperty(
        name="Rung Spacing",
        description=(
            "Centre-to-centre distance between rungs.\n"
            "DayZ standard: 320 mm.\n"
            "Must match the animation controller spacing for correct climbing."
        ),
        default=RUNG_SPACING_STD, min=0.050, max=1.000, step=1, unit='LENGTH')
    ground_offset: bpy.props.FloatProperty(
        name="First Rung Height",
        description=(
            "Height of the first rung above the ladder base (Z=0).\n"
            "DayZ standard: 340 mm minimum.\n"
            "Too low and the player animation will clip the ground."
        ),
        default=GROUND_OFFSET_STD, min=0.010, max=2.000, step=1, unit='LENGTH')
    top_extension: bpy.props.FloatProperty(
        name="Top Extension",
        description=(
            "Stringer length extending above the last rung.\n"
            "DayZ standard: 700 mm.\n"
            "Used as grab rail when player reaches the top."
        ),
        default=TOP_EXT_STD, min=0.0, max=5.000, step=1, unit='LENGTH')
    resolution: bpy.props.IntProperty(
        name="Tube Segments",
        description=(
            "Number of sides on each tube cross-section.\n"
            "4 = square, 8 = octagon, 16+ = visually round.\n"
            "Higher values produce smoother tubes but heavier meshes."
        ),
        default=10, min=4, max=24)

    # Cage bpy.props — required for Blender to show these in the dialog
    cage_enabled: bpy.props.BoolProperty(
        name="Safety Cage",
        description="Enable D-arc safety cage around the ladder.",
        default=False)
    cage_start_z: bpy.props.FloatProperty(
        name="Cage Start Height",
        description="Height above base where cage begins.",
        default=2.200, min=0.0, max=20.0, step=1, unit='LENGTH')
    cage_depth: bpy.props.FloatProperty(
        name="Cage Depth",
        description="How far cage extends behind ladder.",
        default=0.350, min=0.100, max=2.000, step=1, unit='LENGTH')
    hoop_spacing: bpy.props.FloatProperty(
        name="Hoop Spacing",
        description="Vertical distance between cage hoops.",
        default=0.900, min=0.200, max=3.000, step=1, unit='LENGTH')
    cage_bar_count: bpy.props.IntProperty(
        name="Vertical Bars",
        description="Number of vertical bars along the cage.",
        default=5, min=0, max=12)

    @classmethod
    def poll(cls, context):
        return _is_active_ladder(context.active_object)

    def _get_params(self):
        return dict(
            width=self.width,
            tube_diameter=self.tube_diameter,
            rung_count=self.rung_count,
            rung_spacing=self.rung_spacing,
            ground_offset=self.ground_offset,
            top_extension=self.top_extension,
            resolution=self.resolution,
            cage_enabled=self.cage_enabled,
            cage_start_z=self.cage_start_z,
            cage_depth=self.cage_depth,
            hoop_spacing=self.hoop_spacing,
            cage_bar_count=self.cage_bar_count,
            cage_tube_d=self.tube_diameter,  # cage uses same tube diameter as ladder
        )

    # Snapshot storage for cancel restoration
    _snapshot_mesh   = None   # bmesh copy taken on invoke
    _snapshot_params = None   # param dict taken on invoke

    def _rebuild(self, context, commit=False):
        """
        Rebuild the ladder mesh from current properties.
        Dispatches to the correct builder based on dgm_ladder_type.
        commit=False  : live preview only — no expected_* or dgm_p_* written.
        commit=True   : final save — write all properties to object.
        """
        obj = context.active_object
        if obj is None or obj.type != 'MESH' or not obj.get('dgm_ladder'):
            return
        params = self._get_params()
        ladder_type = obj.get('dgm_ladder_type', 1)
        if ladder_type == 2:
            bm, rung_count, total_height = build_ladder_type2(params)
        else:
            bm, rung_count, total_height = build_ladder_type1(params)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        # Always update display counters (these are cosmetic, not validated)
        obj['dgm_ladder_rungs']  = rung_count
        obj['dgm_ladder_height'] = round(total_height, 4)
        if commit:
            # Only write expected_* and dgm_p_* on confirmed OK
            obj['dgm_ladder_expected_height'] = round(total_height, 4)
            obj['dgm_ladder_expected_width']  = round(params['width'] + params['tube_diameter'], 4)
            obj['dgm_ladder_expected_depth']  = _calc_expected_depth(params)
            obj['dgm_p_width']         = self.width
            obj['dgm_p_tube_diameter'] = self.tube_diameter
            obj['dgm_p_rung_count']    = self.rung_count
            obj['dgm_p_rung_spacing']  = self.rung_spacing
            obj['dgm_p_ground_offset'] = self.ground_offset
            obj['dgm_p_top_extension'] = self.top_extension
            obj['dgm_p_resolution']    = self.resolution
            obj['dgm_p_cage_enabled']  = self.cage_enabled
            obj['dgm_p_cage_start_z']  = self.cage_start_z
            obj['dgm_p_cage_depth']    = self.cage_depth
            obj['dgm_p_hoop_spacing']  = self.hoop_spacing
            obj['dgm_p_cage_bar_count']= self.cage_bar_count


    def _snapshot(self, obj):
        """Take a bmesh snapshot of the current mesh and ALL properties for cancel restoration."""
        snap = bmesh.new()
        snap.from_mesh(obj.data)
        self._snapshot_mesh = snap
        self._snapshot_params = dict(
            width            = obj.get('dgm_p_width',                self.width),
            tube_diameter    = obj.get('dgm_p_tube_diameter',        self.tube_diameter),
            rung_count       = obj.get('dgm_p_rung_count',           self.rung_count),
            rung_spacing     = obj.get('dgm_p_rung_spacing',         self.rung_spacing),
            ground_offset    = obj.get('dgm_p_ground_offset',        self.ground_offset),
            top_extension    = obj.get('dgm_p_top_extension',        self.top_extension),
            resolution       = obj.get('dgm_p_resolution',           self.resolution),
            cage_enabled     = obj.get('dgm_p_cage_enabled',         False),
            cage_start_z     = obj.get('dgm_p_cage_start_z',         2.200),
            cage_depth       = obj.get('dgm_p_cage_depth',           0.350),
            hoop_spacing     = obj.get('dgm_p_hoop_spacing',         0.900),
            cage_bar_count   = obj.get('dgm_p_cage_bar_count',       5),
            rungs            = obj.get('dgm_ladder_rungs',           self.rung_count),
            height           = obj.get('dgm_ladder_height',          0.0),
            expected_height  = obj.get('dgm_ladder_expected_height', None),
            expected_width   = obj.get('dgm_ladder_expected_width',  None),
            expected_depth   = obj.get('dgm_ladder_expected_depth',  None),
        )

    def _restore_snapshot(self, context):
        """Restore mesh and params from snapshot (used on cancel)."""
        obj = context.active_object
        if obj is None or self._snapshot_mesh is None:
            return
        self._snapshot_mesh.to_mesh(obj.data)
        obj.data.update()
        p = self._snapshot_params
        obj['dgm_p_width']         = p['width']
        obj['dgm_p_tube_diameter'] = p['tube_diameter']
        obj['dgm_p_rung_count']    = p['rung_count']
        obj['dgm_p_rung_spacing']  = p['rung_spacing']
        obj['dgm_p_ground_offset'] = p['ground_offset']
        obj['dgm_p_top_extension'] = p['top_extension']
        obj['dgm_p_resolution']    = p['resolution']
        obj['dgm_p_cage_enabled']  = p.get('cage_enabled',  False)
        obj['dgm_p_cage_start_z']  = p.get('cage_start_z',  2.200)
        obj['dgm_p_cage_depth']    = p.get('cage_depth',    0.350)
        obj['dgm_p_hoop_spacing']  = p.get('hoop_spacing',  0.900)
        obj['dgm_p_cage_bar_count']= p.get('cage_bar_count',5)
        obj['dgm_ladder_rungs']    = p['rungs']
        obj['dgm_ladder_height']   = p['height']
        # Restore expected_* so the integrity check doesn't fire after cancel
        if p['expected_height'] is not None:
            obj['dgm_ladder_expected_height'] = p['expected_height']
        if p['expected_width'] is not None:
            obj['dgm_ladder_expected_width']  = p['expected_width']
        if p['expected_depth'] is not None:
            obj['dgm_ladder_expected_depth']  = p['expected_depth']
        self._snapshot_mesh.free()
        self._snapshot_mesh   = None
        self._snapshot_params = None

    def invoke(self, context, event):
        obj = context.active_object
        # Load saved params from object
        self.width          = obj.get('dgm_p_width',         0.440)
        self.tube_diameter  = obj.get('dgm_p_tube_diameter', TUBE_DIAMETER_STD)
        self.rung_spacing   = obj.get('dgm_p_rung_spacing',  RUNG_SPACING_STD)
        self.ground_offset  = obj.get('dgm_p_ground_offset', GROUND_OFFSET_STD)
        self.top_extension  = obj.get('dgm_p_top_extension', TOP_EXT_STD)
        self.resolution     = obj.get('dgm_p_resolution',    10)
        stored_rungs = obj.get('dgm_p_rung_count', None)
        self.rung_count = stored_rungs if stored_rungs is not None                           else obj.get('dgm_ladder_rungs', 16)
        # Load cage params if editing a Type 2
        self.cage_enabled    = obj.get('dgm_p_cage_enabled',   False)
        self.cage_start_z    = obj.get('dgm_p_cage_start_z',   2.200)
        self.cage_depth      = obj.get('dgm_p_cage_depth',     0.350)
        self.hoop_spacing    = obj.get('dgm_p_hoop_spacing',   0.900)
        self.cage_bar_count  = obj.get('dgm_p_cage_bar_count', 5)
        # Take snapshot BEFORE opening dialog so cancel can restore
        self._snapshot(obj)
        # Do NOT call _rebuild here — mesh stays untouched until user edits something
        return context.window_manager.invoke_props_dialog(self, width=400)

    def cancel(self, context):
        """Called when user presses Escape or Cancel — restore original mesh."""
        self._restore_snapshot(context)

    def check(self, context):
        self._rebuild(context, commit=False)
        return True

    def draw(self, context):
        layout = self.layout
        params = self._get_params()

        obj = context.active_object
        obj_name = obj.name if obj else "?"

        box = layout.box()
        box.label(text="Editing: {}".format(obj_name), icon='MESH_CYLINDER')

        col = box.column(align=True)

        def prop_row(prop_name, std_value):
            row = col.row(align=True)
            row.prop(self, prop_name)
            row.label(text="", icon=_std_icon(getattr(self, prop_name), std_value))

        row_w = col.row(align=True)
        row_w.prop(self, 'width')
        w_icon = 'CHECKMARK' if round(self.width * 1000) in VALID_WIDTHS_MM else 'ERROR'
        row_w.label(text="", icon=w_icon)

        col.separator()
        prop_row('tube_diameter',  TUBE_DIAMETER_STD)
        col.separator()
        prop_row('rung_spacing',   RUNG_SPACING_STD)
        prop_row('ground_offset',  GROUND_OFFSET_STD)
        prop_row('top_extension',  TOP_EXT_STD)
        col.separator()
        col.prop(self, 'rung_count')

        bm_info, rung_count, total_height = build_ladder_type1(params)
        bm_info.free()
        last_rung_z = params['ground_offset'] + (rung_count - 1) * params['rung_spacing']

        info_box = layout.box()
        icol = info_box.column(align=True)
        icol.label(text="Rungs: {}".format(rung_count), icon='INFO')
        icol.label(text="Total height:  {:.3f} m".format(total_height))
        icol.label(text="Last rung at:  {:.3f} m".format(last_rung_z))
        icol.label(text="Width:  {:.0f} mm".format(params['width'] * 1000))

        # Safety cage section
        cage_box = layout.box()
        cage_text = "Remove Safety Cage" if self.cage_enabled else "Add Safety Cage"
        cage_icon = 'X' if self.cage_enabled else 'ADD'
        cage_box.prop(self, 'cage_enabled', text=cage_text, icon=cage_icon)
        if self.cage_enabled:
            ccol = cage_box.column(align=True)
            ccol.prop(self, 'cage_start_z')
            ccol.prop(self, 'cage_depth')
            ccol.separator()
            ccol.prop(self, 'hoop_spacing')
            ccol.prop(self, 'cage_bar_count')

        q_row = layout.row(align=True)
        q_row.label(text="Tube Segments:", icon='MESH_CIRCLE')
        q_row.prop(self, 'resolution', text="")

    def execute(self, context):
        self._rebuild(context, commit=True)
        if self._snapshot_mesh:
            self._snapshot_mesh.free()
            self._snapshot_mesh   = None
            self._snapshot_params = None
        return {'FINISHED'}




# ---------------------------------------------------------------------------
#  Collision generator operator
# ---------------------------------------------------------------------------

class DGM_OT_ladder_collision(bpy.types.Operator):
    bl_idname      = "dgm.ladder_collision"
    bl_label       = "Generate Collision"
    bl_description = (
        "Generate Geometry LOD collision boxes for the selected ladder. "
        "Creates two stringer boxes (left + right rail), each 42 mm square, "
        "full ladder height, 20 kg each."
    )
    bl_options = {'REGISTER', 'UNDO'}

    mass_per_stringer: bpy.props.FloatProperty(
        name="Mass per Stringer (kg)",
        description="Collision mass of each stringer box in kg. Default: 20 kg.",
        default=20.0, min=1.0, max=500.0, step=10,
    )

    @classmethod
    def poll(cls, context):
        return _is_active_ladder(context.active_object)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Ladder Collision Settings", icon='MESH_CUBE')
        col = box.column(align=True)
        col.prop(self, 'mass_per_stringer')
        col.separator()
        col.label(text="2 components will be created:", icon='INFO')
        col.label(text="  Left stringer  —  {} kg".format(self.mass_per_stringer))
        col.label(text="  Right stringer —  {} kg".format(self.mass_per_stringer))
        col.label(text="  Total mass: {} kg".format(self.mass_per_stringer * 2))

    def execute(self, context):
        from . import geometry
        obj = context.active_object
        geo = geometry.create_ladder_collision(obj, self.mass_per_stringer)
        if geo is not None:
            self.report({'INFO'},
                "Collision created — 2 components, {} kg each".format(
                    self.mass_per_stringer))
        else:
            self.report({'WARNING'}, "No collision components created")
        return {'FINISHED'}

# ---------------------------------------------------------------------------
#  Restore operator — silently rebuilds ladder from stored params, no dialog
# ---------------------------------------------------------------------------

class DGM_OT_ladder_restore(bpy.types.Operator):
    bl_idname      = "dgm.ladder_restore"
    bl_label       = "Restore Ladder"
    bl_description = (
        "Restore ladder geometry to the correct dimensions stored in the object. "
        "Fixes any manual edits, scale changes, or Apply Scale issues."
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_active_ladder(context.active_object)

    def execute(self, context):
        obj = context.active_object

        # Save current transform — restore only mesh, not position/rotation
        saved_location = obj.location.copy()
        saved_rotation = obj.rotation_euler.copy()
        saved_scale    = obj.scale.copy()

        # Reset scale so mesh dimensions match the stored values exactly
        obj.scale = (1.0, 1.0, 1.0)

        # Rebuild mesh from stored params — including cage if it was enabled
        cage_enabled = obj.get('dgm_p_cage_enabled', False)
        params = dict(
            width         = obj.get('dgm_p_width',         0.440),
            tube_diameter = obj.get('dgm_p_tube_diameter', TUBE_DIAMETER_STD),
            rung_count    = obj.get('dgm_p_rung_count',    16),
            rung_spacing  = obj.get('dgm_p_rung_spacing',  RUNG_SPACING_STD),
            ground_offset = obj.get('dgm_p_ground_offset', GROUND_OFFSET_STD),
            top_extension = obj.get('dgm_p_top_extension', TOP_EXT_STD),
            resolution    = obj.get('dgm_p_resolution',    10),
            cage_enabled  = cage_enabled,
            cage_start_z  = obj.get('dgm_p_cage_start_z',  2.200),
            cage_depth    = obj.get('dgm_p_cage_depth',    0.350),
            hoop_spacing  = obj.get('dgm_p_hoop_spacing',  0.900),
            cage_bar_count= obj.get('dgm_p_cage_bar_count',5),
            cage_tube_d   = obj.get('dgm_p_tube_diameter', TUBE_DIAMETER_STD),
        )

        bm, rung_count, total_height = build_ladder_type1(params)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

        # Restore position and rotation — only scale stays at 1,1,1
        obj.location       = saved_location
        obj.rotation_euler = saved_rotation

        # Refresh stored dimensions (same logic as _rebuild)
        obj['dgm_ladder_rungs']           = rung_count
        obj['dgm_ladder_height']          = round(total_height, 4)
        obj['dgm_ladder_expected_height'] = round(total_height, 4)
        obj['dgm_ladder_expected_width']  = round(params['width'] + params['tube_diameter'], 4)
        obj['dgm_ladder_expected_depth']  = _calc_expected_depth(params)

        self.report({'INFO'}, "Ladder restored to {:.3f} m".format(total_height))
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Panel section (called from operators.py)
# ---------------------------------------------------------------------------

def draw_ladder_generator_section(layout, context):
    obj       = context.active_object
    is_ladder = _is_active_ladder(obj)

    box = layout.box()
    # Collapsible header
    scene = context.scene
    header = box.row(align=True)
    header.prop(scene, "dgm_show_ladder_gen",
                icon='TRIA_DOWN' if scene.dgm_show_ladder_gen else 'TRIA_RIGHT',
                emboss=False, text="")
    header.label(text="Ladder Generator", icon='MESH_CYLINDER')

    if not scene.dgm_show_ladder_gen:
        return

    # Add Ladder button + counter
    ladder_count = _count_scene_ladders()
    count_row = box.row(align=True)
    count_row.label(text="Ladders in scene: {}/3".format(ladder_count),
                    icon='CHECKMARK' if ladder_count < 3 else 'ERROR')

    add_row = box.row(align=True)
    add_row.enabled = ladder_count < 3
    add_row.scale_y = 1.3
    add_row.operator("dgm.ladder_type1", text="Add Ladder", icon='ADD')

    # Selected ladder info + Edit button — only when a ladder is selected
    if is_ladder:
        box.separator(factor=0.5)
        ladder_type = obj.get('dgm_ladder_type', 1)
        rungs       = obj.get('dgm_ladder_rungs', '?')
        height      = obj.get('dgm_ladder_height', '?')

        all_std = (
            round(obj.get('dgm_p_width', 0.440) * 1000) in VALID_WIDTHS_MM
            and abs(obj.get('dgm_p_tube_diameter', TUBE_DIAMETER_STD) - TUBE_DIAMETER_STD) < _TOL
            and abs(obj.get('dgm_p_rung_spacing',  RUNG_SPACING_STD)  - RUNG_SPACING_STD)  < _TOL
            and abs(obj.get('dgm_p_ground_offset', GROUND_OFFSET_STD) - GROUND_OFFSET_STD) < _TOL
            and abs(obj.get('dgm_p_top_extension', TOP_EXT_STD)       - TOP_EXT_STD)       < _TOL
        )
        status_icon = 'CHECKMARK' if all_std else 'ERROR'
        icol = box.column(align=True)
        icol.label(
            text="{}  |  {} rungs  |  {} m".format(obj.name, rungs, height),
            icon=status_icon)

        box.operator("dgm.ladder_edit", text="Edit Selected Ladder", icon='PREFERENCES')

        # Collision button — check if collision already exists for this ladder
        import json
        geo_obj = bpy.data.objects.get("Geometry")
        col_map = {}
        if geo_obj:
            try:
                col_map = json.loads(geo_obj.get('dgm_ladder_col_map', '{}'))
            except Exception:
                col_map = {}

        existing_comps = col_map.get(obj.name, [])
        # Verify the component vertex groups actually still exist
        if geo_obj and existing_comps:
            existing_comps = [c for c in existing_comps if geo_obj.vertex_groups.get(c)]

        col_row = box.row(align=True)
        if existing_comps:
            col_row.enabled = False
            col_row.operator("dgm.ladder_collision",
                text="Collision: {} ✓".format(", ".join(existing_comps)),
                icon='CHECKMARK')
        else:
            col_row.operator("dgm.ladder_collision",
                text="Generate Collision", icon='MESH_CUBE')

        # Geometry integrity check — detect scale, manual mesh edits, Apply Scale, etc.
        # Only active after object is confirmed (OK pressed at least once).
        # Consider confirmed if explicitly flagged OR if params were ever saved
        # Only trust confirmed flag or dgm_p_width (written only in execute/_commit)
        # Never use dgm_ladder_rungs — it's written during live preview too
        _is_confirmed = (obj.get('dgm_ladder_confirmed', False)
                         or obj.get('dgm_p_width') is not None)
        if _is_confirmed:
            import mathutils as _mu

            # Check 1: scale must be (1,1,1)
            sx_scale, sy_scale, sz_scale = obj.scale
            scale_ok = (abs(sx_scale - 1.0) < 1e-4
                        and abs(sy_scale - 1.0) < 1e-4
                        and abs(sz_scale - 1.0) < 1e-4)

            # Check 2: recalculate expected from stored params and compare bounding box
            _p = dict(
                width         = obj.get('dgm_p_width',         0.440),
                tube_diameter = obj.get('dgm_p_tube_diameter', 0.042),
                rung_count    = obj.get('dgm_p_rung_count',    16),
                rung_spacing  = obj.get('dgm_p_rung_spacing',  0.320),
                ground_offset = obj.get('dgm_p_ground_offset', 0.340),
                top_extension = obj.get('dgm_p_top_extension', 0.700),
                resolution    = obj.get('dgm_p_resolution',    8),
                cage_enabled  = obj.get('dgm_p_cage_enabled',  False),
                cage_depth    = obj.get('dgm_p_cage_depth',    0.350),
                cage_tube_d   = obj.get('dgm_p_tube_diameter', 0.042),
            )
            # Use local bounding box (no matrix_world) so scale is detected separately
            local_corners = [_mu.Vector(c) for c in obj.bound_box]
            lxs = [c.x for c in local_corners]
            lys = [c.y for c in local_corners]
            lzs = [c.z for c in local_corners]
            actual_h = max(lzs) - min(lzs)
            actual_w = max(lxs) - min(lxs)
            actual_d = max(lys) - min(lys)

            _, _, _total_h = build_ladder_type1(_p)
            expected_h = round(_total_h, 4)
            expected_w = round(_p['width'] + _p['tube_diameter'], 4)
            expected_d = _calc_expected_depth(_p)

            TOL = 0.005  # 5 mm tolerance
            height_ok = abs(actual_h - expected_h) < TOL
            width_ok  = abs(actual_w - expected_w) < TOL
            depth_ok  = abs(actual_d - expected_d) < TOL

            if not scale_ok or not (height_ok and width_ok and depth_ok):
                warn = box.box()
                warn.alert = True
                wcol = warn.column(align=True)
                wcol.label(text="Ladder geometry was modified!", icon='ERROR')
                if not scale_ok:
                    wcol.label(
                        text="Scale: X={:.3f} Y={:.3f} Z={:.3f}  (must be 1,1,1)".format(
                            sx_scale, sy_scale, sz_scale),
                        icon='DOT')
                if not height_ok:
                    wcol.label(
                        text="Height: {:.3f} m  (expected {:.3f} m)".format(
                            actual_h, expected_h),
                        icon='DOT')
                if not width_ok:
                    wcol.label(
                        text="Width:  {:.3f} m  (expected {:.3f} m)".format(
                            actual_w, expected_w),
                        icon='DOT')
                if not depth_ok:
                    wcol.label(
                        text="Depth:  {:.3f} m  (expected {:.3f} m)".format(
                            actual_d, expected_d),
                        icon='DOT')
                wcol.separator()
                wcol.label(text="Click to restore correct geometry:", icon='INFO')
                wcol.operator("dgm.ladder_restore", text="Restore Ladder", icon='FILE_REFRESH')




# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------

ladder_classes = (
    DGM_OT_ladder_type1,
    DGM_OT_ladder_edit,
    DGM_OT_ladder_restore,
    DGM_OT_ladder_collision,
)


def register():
    for cls in ladder_classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dgm_show_ladder_gen = bpy.props.BoolProperty(
        name="Show Ladder Generator", default=False)


def unregister():
    for cls in reversed(ladder_classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.dgm_show_ladder_gen


if __name__ == "__main__":
    register()

# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------
