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
from mathutils import Vector, Matrix


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

    # Optional top hook arches
    if params.get('hook_enabled', False):
        _build_top_hook(bm, params, sx, total_height)

    # Optional wall-mounting brackets
    if params.get('bracket_enabled', False):
        _build_wall_brackets(bm, params, sx, total_height)

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

    tangents = [_tangent(i) for i in range(len(arc_pts))]

    # Build one initial perpendicular frame, then parallel-transport it along
    # the path.  This prevents the cross-section from flipping when the tube
    # tangent is close to global Z (the top-hook U bend case).
    t0 = tangents[0]
    ref = Vector((1.0, 0.0, 0.0))
    if abs(t0.dot(ref)) > 0.95:
        ref = Vector((0.0, 1.0, 0.0))
    normal = (ref - t0 * ref.dot(t0)).normalized()
    binormal = t0.cross(normal).normalized()

    frames = [(normal.copy(), binormal.copy())]
    prev_t = t0
    for tang in tangents[1:]:
        axis = prev_t.cross(tang)
        if axis.length > 1e-7:
            angle = max(-1.0, min(1.0, prev_t.dot(tang)))
            rot = Matrix.Rotation(math.acos(angle), 4, axis.normalized())
            normal = rot @ normal
            binormal = rot @ binormal

        # Re-orthonormalize lightly so accumulated float drift cannot squash
        # the tube after many segments.
        normal = (normal - tang * normal.dot(tang)).normalized()
        binormal = tang.cross(normal).normalized()
        frames.append((normal.copy(), binormal.copy()))
        prev_t = tang

    def _ring(centre, frame):
        verts = []
        t2, b2 = frame
        for k in range(segs):
            a = 2.0 * math.pi * k / segs
            verts.append(bm.verts.new(
                centre + t2 * math.cos(a) * radius + b2 * math.sin(a) * radius))
        return verts

    rings = [_ring(arc_pts[i], frames[i]) for i in range(len(arc_pts))]

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
    max_hoops    = max(0, int(params.get('cage_max_hoops', 0)))
    cage_start_z = float(params.get('cage_start_z',  2.200))
    cage_tube_r  = float(params.get('cage_tube_d',   0.025)) / 2.0
    segs         = max(4, int(params.get('resolution', 8)))
    arc_segs     = max(3, int(params.get('bend_segments', 10)))

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
        arc_steps = arc_segs

        # Right straight arm: one clean segment from stringer to arc start.
        # The arc is segmented; the straight part does not need intermediate
        # rings every few centimetres.
        pts.append(Vector((sx, 0.0, z)))
        pts.append(Vector((sx, -arm_len, z)))

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

        # Left straight arm: also one clean segment.
        pts.append(Vector((-sx, 0.0, z)))

        return pts

    # Hoop heights. With Top Hook enabled the cage may start higher than the
    # straight ladder body, so use the visual top including hook rise/radius.
    cage_top_z = _hook_total_height(params, total_height)
    hoop_zs = []
    hz = cage_start_z
    while hz <= cage_top_z + 1e-5:
        hoop_zs.append(hz)
        if max_hoops > 0 and len(hoop_zs) >= max_hoops:
            break
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
    Coordinate system: Y = depth.
      - Cage always extends into -Y (cage side, climber side).
      - Hook extends to ±Y depending on mount_side (cage side by default).
      - Brackets extend to ±Y depending on mount_side (wall side by default).

    Depth  =  max_Y  -  min_Y   (always positive)
    """
    td   = float(params['tube_diameter'])
    tr   = td / 2.0
    sign = -1.0 if params.get('mount_side', 'STANDARD') == 'INVERTED' else +1.0

    max_y = +tr   # front face of stringer tube
    min_y = -tr   # back face of stringer tube

    if params.get('cage_enabled', False):
        sx      = float(params['width']) / 2.0
        arm_len = float(params.get('cage_depth', 0.35))
        min_y   = min(min_y, -(arm_len + sx + tr))

    if params.get('hook_enabled', False):
        hook_r = float(params.get('hook_radius', 0.150))
        # Hook now curves to side = +1 * sign (wall side by default).
        # End point of arch is at y = 2 · hook_r · sign.
        hook_y = 2.0 * hook_r * sign
        # If end-bracket is enabled the horizontal plate extends pl_h/2 in
        # both ±Y directions around hook_y, so the bbox can reach further.
        extra = 0.0
        if params.get('hook_end_bracket', True):
            extra = float(params.get('hook_plate_depth', 0.120)) / 2.0
        if hook_y > 0:
            max_y = max(max_y, hook_y + extra + tr)
            min_y = min(min_y, hook_y - extra - tr)
        else:
            min_y = min(min_y, hook_y - extra - tr)
            max_y = max(max_y, hook_y + extra + tr)

    if params.get('bracket_enabled', False):
        pl_d_total = float(params.get('bracket_depth',           0.060))
        pl_thick   = float(params.get('bracket_plate_thickness', 0.012))
        standoff   = max(0.001, pl_d_total - pl_thick)
        screw_len  = max(pl_thick * 1.6, 0.012)
        # Brackets extend to side = +1 * sign (wall side by default).
        b_y = (tr + standoff + pl_thick + screw_len) * sign
        if b_y > 0:
            max_y = max(max_y, b_y)
        else:
            min_y = min(min_y, b_y)

    return round(max_y - min_y, 4)


# ---------------------------------------------------------------------------
#  Box primitive — manifold closed box
# ---------------------------------------------------------------------------

def _make_box(bm, cx, cy, cz, hx, hy, hz):
    """
    Manifold axis-aligned box.
    Centre at (cx, cy, cz), half-sizes hx/hy/hz along X/Y/Z.
    Normals are recalculated later by build_ladder_type1.
    """
    v = [
        bm.verts.new((cx - hx, cy - hy, cz - hz)),  # 0  ---
        bm.verts.new((cx + hx, cy - hy, cz - hz)),  # 1  +--
        bm.verts.new((cx + hx, cy + hy, cz - hz)),  # 2  ++-
        bm.verts.new((cx - hx, cy + hy, cz - hz)),  # 3  -+-
        bm.verts.new((cx - hx, cy - hy, cz + hz)),  # 4  --+
        bm.verts.new((cx + hx, cy - hy, cz + hz)),  # 5  +-+
        bm.verts.new((cx + hx, cy + hy, cz + hz)),  # 6  +++
        bm.verts.new((cx - hx, cy + hy, cz + hz)),  # 7  -++
    ]
    bm.faces.new([v[0], v[3], v[2], v[1]])  # bottom  -Z
    bm.faces.new([v[4], v[5], v[6], v[7]])  # top     +Z
    bm.faces.new([v[0], v[1], v[5], v[4]])  # front   -Y
    bm.faces.new([v[2], v[3], v[7], v[6]])  # back    +Y
    bm.faces.new([v[0], v[4], v[7], v[3]])  # left    -X
    bm.faces.new([v[1], v[2], v[6], v[5]])  # right   +X


# ---------------------------------------------------------------------------
#  Mount-side helper
# ---------------------------------------------------------------------------
#
#  Cage arc is hard-coded to extend toward -Y (see _build_cage).
#  By convention:
#     -Y  =  CAGE SIDE   (climber stands here, back toward open air)
#     +Y  =  WALL SIDE   (the surface the ladder is mounted to)
#
#  `mount_side` lets the user mirror hook + brackets to the opposite
#  Y direction in case they imported the ladder rotated 180° about Z
#  or want a non-standard configuration.
#
#  Returned value is +1.0 / -1.0 — multiply the natural direction by it.

def _mount_sign(params):
    """Return +1.0 for default orientation, -1.0 to flip hook+brackets."""
    return -1.0 if params.get('mount_side', 'STANDARD') == 'INVERTED' else +1.0


MIN_SCREW_AXIS_LENGTH = 0.110
MIN_FOUR_SCREW_AXIS_LENGTH = 0.220
DAYZ_HOOK_EXTENSION = 0.700
DAYZ_HOOK_RADIUS = 0.250


def _screws_allowed(length):
    """Screws are only generated when the chosen plate axis is at least 11 cm."""
    return float(length) >= MIN_SCREW_AXIS_LENGTH


def _screw_count_for_axis(count, axis_len):
    count = 4 if int(count) >= 4 else 2
    if count == 4 and float(axis_len) < MIN_FOUR_SCREW_AXIS_LENGTH:
        return 2
    return count


def _screw_count_id(value):
    return '4' if int(value) >= 4 else '2'


# ---------------------------------------------------------------------------
#  Top hook builder — inverted-U grab arches at stringer tops
# ---------------------------------------------------------------------------

def _build_top_hook(bm, params, sx, total_height):
    """
    Build a pair of inverted-U (∩-shaped) grab arches, one per stringer.

    Shape per stringer (Y-Z plane at x = ±sx, default direction = +Y / wall side):

         apex                        (y = side·hook_r,   z = top + ext + hook_r)
          _____
         /     \\
        |       |   <-- half-circle arc, centre (x, side·hook_r, top + ext)
        |       |
        |       |   <-- optional straight rise (hook_extension)
        |       |   <-- optional straight drop (hook_drop)  on far leg
        |
       stringer top   (y = 0, z = total_height)

    The path is *continuous*:
        (y=0, z=top)  →  (y=0, z=top+ext)
                      →  arc up & over to (y=2·side·hook_r, z=top+ext)
                      →  drop to (y=2·side·hook_r, z=top+ext-drop)

    Default side = +1 (wall side) — the user reaches OVER the wall edge to grab
    the hook when stepping off onto a roof.  mount_side='INVERTED' flips to -Y.

    If hook_end_bracket=True a wall-mounting plate with screws is built at the
    bottom of the drop tube (delegated to _build_hook_end_bracket).
    """
    segs       = max(4, int(params.get('resolution', 8)))
    r          = float(params['tube_diameter']) / 2.0
    hook_r     = float(params.get('hook_radius',    0.150))
    hook_ext   = float(params.get('hook_extension', 0.080))
    hook_drop  = float(params.get('hook_drop',      0.080))
    pl_thick   = float(params.get('hook_plate_thickness', 0.012))
    end_brk    = bool(params.get('hook_end_bracket', True))
    sign       = _mount_sign(params)
    arc_segs   = max(3, int(params.get('bend_segments', 10)))

    # Hook curves toward WALL side (+Y) by default; INVERTED flips to cage side.
    side = +1.0 * sign
    cz   = total_height + hook_ext

    def hook_pts(x):
        pts = []
        # 1. Straight rise from stringer top up to (x, 0, cz)
        if hook_ext > 1e-6:
            pts.append(Vector((x, 0.0, total_height)))
        pts.append(Vector((x, 0.0, cz)))

        # 2. Half-circle arch — parameterised so the START matches the
        #    straight section's end exactly (no horizontal jump).
        #    t ∈ [0,1], a = π·t        (0 → π)
        #    y(t) = side · hook_r · (1 − cos a)        0 → 2·side·hook_r
        #    z(t) = cz + hook_r · sin a                cz → cz+hook_r → cz
        for i in range(1, arc_segs + 1):
            t = i / arc_segs
            a = math.pi * t
            y = side * hook_r * (1.0 - math.cos(a))
            z = cz   + hook_r * math.sin(a)
            pts.append(Vector((x, y, z)))

        # 3. Optional straight drop on the far leg.  When the end bracket is
        #    enabled, extend the drop tube DOWN past the top of the plate by
        #    half a plate thickness so the bottom cap is buried inside the
        #    horizontal plate (no visible disk).
        if hook_drop > 1e-6:
            drop_z = cz - hook_drop
            if end_brk:
                drop_z -= pl_thick / 2.0
            pts.append(Vector((x, side * 2.0 * hook_r, drop_z)))

        return pts

    _make_arc_tube(bm, hook_pts(-sx), r, segs)
    _make_arc_tube(bm, hook_pts( sx), r, segs)

    # Optional end bracket — HORIZONTAL plate with hex bolts on top
    if end_brk and hook_drop > 1e-6:
        _build_hook_end_bracket(bm, params, sx, total_height, side)


def _build_hook_end_bracket(bm, params, sx, total_height, side):
    """
    Horizontal mounting plate at the bottom of each hook drop tube.

    The plate lies FLAT (in the X-Y plane); the drop tube enters its top
    surface and is buried halfway through the plate so there is no visible
    end cap.  Hex-headed bolts protrude UPWARD from the plate top — "screws
    from above" — and are anchored just inside the plate, so their bases
    are also hidden.  Bolt geometry is FIXED size (does not depend on
    plate thickness).

    Plate orientation:           Bolt orientation:

           ▓▓▓▓▓▓▓▓ ←top         ⬢ ⬢   <- visible hex heads (screw_head_len)
           ▓▓▓▓▓▓▓▓ ←bottom      │ │   <- buried in plate (SCREW_BURIED)
           drop tube enters ↓    ▓▓▓▓
    """
    segs       = max(4, int(params.get('resolution', 8)))
    tube_r     = float(params['tube_diameter']) / 2.0
    hook_r     = float(params.get('hook_radius',    0.150))
    hook_ext   = float(params.get('hook_extension', 0.080))
    hook_drop  = float(params.get('hook_drop',      0.080))

    pl_w     = float(params.get('hook_plate_width',     0.120))
    pl_h     = float(params.get('hook_plate_depth',     0.120))
    pl_thick = float(params.get('hook_plate_thickness', 0.012))
    screws_enabled = bool(params.get('hook_screws_enabled', True))
    screw_n  = int(params.get('hook_screw_count', 2))
    screw_axis = params.get('hook_screw_axis', 'X')

    # Hex bolt heads — same FIXED geometry as the regular wall brackets
    SCREW_HEAD_R   = max(tube_r * 0.55, 0.005)
    SCREW_HEAD_LEN = 0.010
    SCREW_BURIED   = 0.002
    SCREW_SEGS     = 6

    # Plate centre Y matches drop-tube end Y; plate spans pl_h in Y so the
    # tube enters near the centre of the plate footprint.
    z_plate_top    = total_height + hook_ext - hook_drop
    z_plate_bot    = z_plate_top - pl_thick
    z_plate_centre = (z_plate_top + z_plate_bot) / 2.0
    y_plate_centre = side * 2.0 * hook_r

    for x in (-sx, sx):
        # 1) Horizontal plate
        _make_box(
            bm,
            x, y_plate_centre, z_plate_centre,
            pl_w  / 2.0,    # half-X (along ladder width)
            pl_h  / 2.0,    # half-Y (depth into wall)
            pl_thick / 2.0, # half-Z (vertical thickness)
        )

        # 2) Hex bolt heads on TOP of the plate. They can be distributed
        #    along X or along Y, and are generated only when the chosen plate
        #    dimension is at least 11 cm.
        axis_len = pl_w if screw_axis == 'X' else pl_h
        if screws_enabled and screw_n > 0 and _screws_allowed(axis_len):
            screw_n = _screw_count_for_axis(screw_n, axis_len)
            min_clear = tube_r + SCREW_HEAD_R + 0.003
            max_off = max(axis_len / 2.0 - SCREW_HEAD_R - 0.003, min_clear)

            if screw_n == 1:
                offs = [0.0]
            elif screw_n == 2:
                offs = [-max_off, +max_off]
            else:
                span = max_off * 2.0
                offs = [-max_off + span * i / (screw_n - 1) for i in range(screw_n)]

            head_anchor_z = z_plate_top - SCREW_BURIED
            head_tip_z    = z_plate_top + SCREW_HEAD_LEN

            for off in offs:
                xoff = off if screw_axis == 'X' else 0.0
                yoff = 0.0 if screw_axis == 'X' else off
                _make_tube(
                    bm,
                    (x + xoff, y_plate_centre + yoff, head_anchor_z),
                    (x + xoff, y_plate_centre + yoff, head_tip_z),
                    SCREW_HEAD_R, SCREW_SEGS,
                )


# ---------------------------------------------------------------------------
#  Wall bracket builder — wall plates with stand-off rods and screws
# ---------------------------------------------------------------------------

def _build_wall_brackets(bm, params, sx, total_height):
    """
    Build wall-mounting bracket pairs along the stringers.

    Each bracket pair (one per stringer side, at every height) has three parts:

         stringer ────► [ stand-off rod ] ────► [ wall plate ] ────► [ screws ]
                                                       │
                                                       └── screws extend further
                                                           in +Y (into the wall)

      - A short stand-off rod connects the stringer surface to the back of the
        wall plate.  Length = (bracket_depth − bracket_plate_thickness).
      - The wall plate is a flat slab against the wall — wide in X, tall in Z,
        thin in Y.
      - Screws are short cylinders that protrude from the wall-facing (+Y)
        side of the plate into the wall.

    By default brackets point toward +Y (wall side, opposite the cage).  Setting
    mount_side='INVERTED' flips them to -Y.

    params:
        bracket_spacing         float  - vertical distance between bracket rows (m)
        bracket_start_z         float  - Z height of first bracket row (m)
        bracket_plate_width     float  - plate width in X (m)
        bracket_depth           float  - total stand-off + plate thickness in Y (m)
        bracket_plate_height    float  - plate height in Z (m)
        bracket_plate_thickness float  - flat plate thickness in Y (m)
        bracket_screw_count     int    - screw bolts per plate (0–4)
        mount_side              str    - 'STANDARD' (wall side) or 'INVERTED'
        tube_diameter           float  - stringer tube diameter (m)
        resolution              int    - tube segment count
    """
    segs        = max(4, int(params.get('resolution', 8)))
    tube_r      = float(params['tube_diameter']) / 2.0
    br_spacing  = float(params.get('bracket_spacing',         1.500))
    br_start_z  = float(params.get('bracket_start_z',         1.000))
    br_max_count = max(0, int(params.get('bracket_max_count', 0)))
    pl_w        = float(params.get('bracket_plate_width',     0.120))
    pl_d_total  = float(params.get('bracket_depth',           0.060))
    pl_h        = float(params.get('bracket_plate_height',    0.120))
    pl_thick    = float(params.get('bracket_plate_thickness', 0.012))
    screws_enabled = bool(params.get('bracket_screws_enabled', True))
    screw_n     = int(params.get('bracket_screw_count',       2))
    screw_axis  = params.get('bracket_screw_axis', 'X')
    sign        = _mount_sign(params)
    side        = +1.0 * sign                    # +1 (wall side) by default

    rod_r    = tube_r                            # rod uses ladder tube diameter
    standoff = max(0.001, pl_d_total - pl_thick)

    # ── Hex bolt heads (segs=6) — FIXED dimensions, independent of plate ──
    SCREW_HEAD_R   = max(tube_r * 0.55, 0.005)   # ~5–12 mm depending on tube
    SCREW_HEAD_LEN = 0.010                       # 10 mm visible head height
    SCREW_BURIED   = 0.002                       # 2 mm anchor inside plate
    SCREW_SEGS     = 6                           # hexagonal cross-section

    # Y positions
    y_stringer_axis = 0.0                                     # rod cap hidden inside stringer
    y_plate_inner   = (tube_r + standoff) * side              # plate's cage-facing face
    y_plate_outer   = (tube_r + standoff + pl_thick) * side   # plate's wall-facing face
    plate_y_centre  = (y_plate_inner + y_plate_outer) / 2.0

    # Build the list of bracket heights
    bracket_zs = []
    z = br_start_z
    while z <= total_height + 1e-5:
        bracket_zs.append(z)
        if br_max_count > 0 and len(bracket_zs) >= br_max_count:
            break
        z += br_spacing
    if not bracket_zs:
        return

    for bz in bracket_zs:
        for x in (-sx, sx):
            # 1) Stand-off rod — runs from the stringer's central axis
            #    (cap buried inside stringer) all the way to the centre of
            #    the plate (cap buried inside plate).  No visible end caps,
            #    no flickering disks at the surfaces.
            _make_tube(
                bm,
                (x, y_stringer_axis, bz),
                (x, plate_y_centre,  bz),
                rod_r, segs,
            )

            # 2) Wall plate (flat slab, thin in Y)
            _make_box(
                bm,
                x, plate_y_centre, bz,
                pl_w / 2.0,
                pl_thick / 2.0,
                pl_h / 2.0,
            )

            # 3) Hex bolt heads on the cage-facing side of the plate.
            #    Heads are hexagonal cylinders, anchored 2 mm inside the
            #    plate (so the base disk is hidden) and protrude 10 mm out
            #    toward the cage.  Length is FIXED — it does not grow with
            #    plate thickness.
            axis_len = pl_w if screw_axis == 'X' else pl_h
            if screws_enabled and screw_n > 0 and _screws_allowed(axis_len):
                screw_n = _screw_count_for_axis(screw_n, axis_len)
                if screw_n == 1:
                    offs = [0.0]
                elif screw_n == 2:
                    offs = [-axis_len * 0.30, +axis_len * 0.30]
                else:
                    span = axis_len * 0.70
                    offs = [-span / 2.0 + span * i / (screw_n - 1) for i in range(screw_n)]

                head_anchor = y_plate_inner + side * SCREW_BURIED      # buried inside plate
                head_tip    = y_plate_inner - side * SCREW_HEAD_LEN    # outside, toward cage
                for off in offs:
                    xoff = off if screw_axis == 'X' else 0.0
                    zoff = 0.0 if screw_axis == 'X' else off
                    _make_tube(
                        bm,
                        (x + xoff, head_anchor, bz + zoff),
                        (x + xoff, head_tip,    bz + zoff),
                        SCREW_HEAD_R, SCREW_SEGS,
                    )


def _hook_total_height(params, base_height):
    """Return visual top height including optional top hook geometry."""
    if not params.get('hook_enabled', False):
        return base_height
    hook_ext = float(params.get('hook_extension', 0.080))
    hook_r = float(params.get('hook_radius', 0.150))
    return base_height + hook_ext + hook_r


def _bbox_from_bm(bm):
    """
    Return (width_x, depth_y, height_z) of the bmesh's bounding box, in
    *local* coordinates (i.e. before any object transform is applied).

    Used at commit time to capture the EXACT geometry that was just built,
    so the integrity check can later detect if the user mutated the mesh.
    """
    if not bm.verts:
        return (0.0, 0.0, 0.0)
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


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
    bend_segments: bpy.props.IntProperty(
        name="Bend Segments",
        description=(
            "Number of length segments used to build curved bends.\n"
            "3 = low-poly bend, 12 = balanced, higher values are smoother but heavier."
        ),
        default=10, min=3, max=48,
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
    cage_max_hoops: bpy.props.IntProperty(
        name="Max Hoops",
        description="Maximum generated cage hoops. 0 means no limit.",
        default=0, min=0, max=128,
    )
    cage_bar_count: bpy.props.IntProperty(
        name="Vertical Bars",
        description="Number of vertical bars along the cage arc connecting hoops.",
        default=5, min=0, max=12,
    )

    # ── Top hook properties ───────────────────────────────────────────────────
    hook_enabled: bpy.props.BoolProperty(
        name="Top Hook",
        description=(
            "Add a pair of inverted-U (∩-shaped) grab arches at the top.\n"
            "Each arch starts at a stringer top, rises straight by Hook Extension,\n"
            "sweeps a half circle of radius Hook Radius, and returns down on the\n"
            "opposite side — like a shepherd's crook. By default the arches point\n"
            "toward the cage side, where the climber can grab them."
        ),
        default=False,
    )
    hook_radius: bpy.props.FloatProperty(
        name="Hook Radius",
        description=(
            "Radius of the half-circle at the top of the arch.\n"
            "Recommended DayZ roof hook value: 25 cm.\n"
            "The arch's horizontal reach equals 2 × this value, and its peak\n"
            "sits this far above the straight extension."
        ),
        default=0.150, min=0.030, max=0.500, step=1, unit='LENGTH',
    )
    hook_extension: bpy.props.FloatProperty(
        name="Hook Extension",
        description=(
            "Length of the straight vertical section at the top of the stringer\n"
            "before the curve begins. Recommended DayZ roof-exit value: 70 cm\n"
            "above the last rung. Set to 0 for a pure half-circle arch."
        ),
        default=0.080, min=0.000, max=1.000, step=1, unit='LENGTH',
    )
    hook_dayz_extension: bpy.props.BoolProperty(
        name="DayZ 70 cm Extension",
        description="Lock Hook Extension to the recommended DayZ roof-exit value: 70 cm.",
        default=True,
    )
    hook_dayz_radius: bpy.props.BoolProperty(
        name="DayZ 25 cm Radius",
        description="Lock Hook Radius to the recommended DayZ roof hook radius: 25 cm.",
        default=True,
    )
    hook_drop: bpy.props.FloatProperty(
        name="Hook Drop",
        description=(
            "Length of the straight vertical tube on the FAR leg of the arch,\n"
            "after the curve comes back down. The end-bracket plate (if enabled)\n"
            "is mounted at the bottom of this drop."
        ),
        default=0.080, min=0.000, max=1.000, step=1, unit='LENGTH',
    )
    hook_end_bracket: bpy.props.BoolProperty(
        name="End Plate with Screws",
        description=(
            "Add a wall-mounting plate with screws at the bottom of the hook's\n"
            "drop tube."
        ),
        default=True,
    )
    hook_plate_width: bpy.props.FloatProperty(
        name="Hook Plate Width",
        description="Width of the top hook end plate along X.",
        default=0.120, min=0.020, max=0.400, step=1, unit='LENGTH',
    )
    hook_plate_depth: bpy.props.FloatProperty(
        name="Hook Plate Depth",
        description="Depth of the top hook end plate along Y.",
        default=0.120, min=0.020, max=0.400, step=1, unit='LENGTH',
    )
    hook_plate_thickness: bpy.props.FloatProperty(
        name="Hook Plate Thickness",
        description="Vertical thickness of the horizontal top hook plate.",
        default=0.012, min=0.003, max=0.050, step=1, unit='LENGTH',
    )
    hook_screws_enabled: bpy.props.BoolProperty(
        name="Hook Plate Screws",
        description="Generate hex screw heads on the top hook end plate.",
        default=True,
    )
    hook_screw_axis: bpy.props.EnumProperty(
        name="Hook Screw Axis",
        description="Axis used to distribute screws on the horizontal hook plate.",
        items=[
            ('X', "X Axis", "Place screws across plate width"),
            ('Y', "Y Axis", "Place screws across plate depth"),
        ],
        default='X',
    )
    hook_screw_count: bpy.props.EnumProperty(
        name="Hook Screws",
        description="Number of screw bolts on each top hook plate.",
        items=[
            ('2', "2 Screws", "Use two screws"),
            ('4', "4 Screws", "Use four screws; requires selected axis at least 22 cm"),
        ],
        default='2',
    )

    # ── Wall bracket properties ───────────────────────────────────────────────
    bracket_enabled: bpy.props.BoolProperty(
        name="Wall Brackets",
        description=(
            "Add wall-mounting brackets at regular intervals along the stringers.\n"
            "Each bracket has a stand-off rod from the stringer to a flat wall\n"
            "plate, with screws protruding into the wall."
        ),
        default=False,
    )
    bracket_spacing: bpy.props.FloatProperty(
        name="Bracket Spacing",
        description="Vertical distance between bracket rows.",
        default=1.500, min=0.200, max=5.000, step=1, unit='LENGTH',
    )
    bracket_max_count: bpy.props.IntProperty(
        name="Max Bracket Rows",
        description="Maximum number of wall bracket rows. 0 means no limit.",
        default=0, min=0, max=64,
    )
    bracket_start_z: bpy.props.FloatProperty(
        name="First Bracket Height",
        description="Height above ladder base of the first bracket row.",
        default=1.000, min=0.0, max=20.0, step=1, unit='LENGTH',
    )
    bracket_plate_width: bpy.props.FloatProperty(
        name="Plate Width",
        description="Width of the wall plate along X (ladder width direction).",
        default=0.120, min=0.020, max=0.300, step=1, unit='LENGTH',
    )
    bracket_depth: bpy.props.FloatProperty(
        name="Stand-off Depth",
        description=(
            "Total depth from the stringer surface to the wall (Y direction).\n"
            "Equal to the stand-off rod length plus the plate thickness."
        ),
        default=0.060, min=0.015, max=1.000, step=1, unit='LENGTH',
    )
    bracket_plate_height: bpy.props.FloatProperty(
        name="Plate Height",
        description="Height of the wall plate in Z.",
        default=0.120, min=0.020, max=0.250, step=1, unit='LENGTH',
    )
    bracket_plate_thickness: bpy.props.FloatProperty(
        name="Plate Thickness",
        description=(
            "Thickness of the flat wall plate in Y.\n"
            "The remaining stand-off depth becomes the rod length connecting\n"
            "the plate to the stringer."
        ),
        default=0.012, min=0.003, max=0.050, step=1, unit='LENGTH',
    )
    bracket_screw_count: bpy.props.EnumProperty(
        name="Screws per Plate",
        description="Number of screw bolts on each wall plate.",
        items=[
            ('2', "2 Screws", "Use two screws"),
            ('4', "4 Screws", "Use four screws; requires selected axis at least 22 cm"),
        ],
        default='2',
    )
    bracket_screws_enabled: bpy.props.BoolProperty(
        name="Wall Plate Screws",
        description="Generate hex screw heads on wall bracket plates.",
        default=True,
    )
    bracket_screw_axis: bpy.props.EnumProperty(
        name="Wall Screw Axis",
        description="Axis used to distribute screws on the vertical wall plate.",
        items=[
            ('X', "Horizontal", "Place screws along plate width"),
            ('Z', "Vertical", "Place screws along plate height"),
        ],
        default='X',
    )

    # ── Mount side toggle ─────────────────────────────────────────────────────
    mount_side: bpy.props.EnumProperty(
        name="Mount Side",
        description=(
            "Which side of the ladder the hook and brackets point to.\n"
            "STANDARD = hook on cage side, brackets on wall side (default).\n"
            "INVERTED = mirror both to the opposite Y direction.\n"
            "Use INVERTED if your scene has the wall on the opposite side\n"
            "from where the cage extends."
        ),
        items=[
            ('STANDARD', "Standard",
             "Hook + brackets on wall side (+Y), opposite the cage"),
            ('INVERTED', "Inverted",
             "Hook + brackets on cage side (-Y) — for ladders rotated 180°"),
        ],
        default='STANDARD',
    )

    def _get_params(self):
        if self.hook_enabled:
            self.top_extension = 0.0
        elif abs(self.top_extension) < _TOL:
            self.top_extension = TOP_EXT_STD
        if self.hook_dayz_radius:
            self.hook_radius = DAYZ_HOOK_RADIUS
        if self.hook_dayz_extension:
            self.hook_extension = DAYZ_HOOK_EXTENSION
        return dict(
            width=self.width,
            tube_diameter=self.tube_diameter,
            rung_count=self.rung_count,
            rung_spacing=self.rung_spacing,
            ground_offset=self.ground_offset,
            top_extension=self.top_extension,
            resolution=self.resolution,
            bend_segments=self.bend_segments,
            cage_enabled=self.cage_enabled,
            cage_start_z=self.cage_start_z,
            cage_depth=self.cage_depth,
            hoop_spacing=self.hoop_spacing,
            cage_max_hoops=self.cage_max_hoops,
            cage_bar_count=self.cage_bar_count,
            cage_tube_d=self.tube_diameter,
            hook_enabled=self.hook_enabled,
            hook_radius=DAYZ_HOOK_RADIUS if self.hook_dayz_radius else self.hook_radius,
            hook_extension=DAYZ_HOOK_EXTENSION if self.hook_dayz_extension else self.hook_extension,
            hook_dayz_radius=self.hook_dayz_radius,
            hook_dayz_extension=self.hook_dayz_extension,
            hook_drop=self.hook_drop,
            hook_end_bracket=self.hook_end_bracket,
            hook_plate_width=self.hook_plate_width,
            hook_plate_depth=self.hook_plate_depth,
            hook_plate_thickness=self.hook_plate_thickness,
            hook_screws_enabled=self.hook_screws_enabled,
            hook_screw_axis=self.hook_screw_axis,
            hook_screw_count=self.hook_screw_count,
            bracket_enabled=self.bracket_enabled,
            bracket_spacing=self.bracket_spacing,
            bracket_max_count=self.bracket_max_count,
            bracket_start_z=self.bracket_start_z,
            bracket_plate_width=self.bracket_plate_width,
            bracket_depth=self.bracket_depth,
            bracket_plate_height=self.bracket_plate_height,
            bracket_plate_thickness=self.bracket_plate_thickness,
            bracket_screw_count=self.bracket_screw_count,
            bracket_screws_enabled=self.bracket_screws_enabled,
            bracket_screw_axis=self.bracket_screw_axis,
            mount_side=self.mount_side,
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
        bm, rung_count, total_height = build_ladder_type1(params)
        bbox_w, bbox_d, bbox_h = _bbox_from_bm(bm)
        bm.free()
        obj['dgm_ladder_rungs']           = rung_count
        obj['dgm_ladder_height']          = round(total_height, 4)
        obj['dgm_ladder_expected_height'] = round(bbox_h, 4)
        obj['dgm_ladder_expected_width']  = round(bbox_w, 4)
        obj['dgm_ladder_expected_depth']  = round(bbox_d, 4)
        obj['dgm_p_cage_enabled']         = params.get('cage_enabled',         False)
        obj['dgm_p_cage_start_z']         = params.get('cage_start_z',         2.200)
        obj['dgm_p_cage_depth']           = params.get('cage_depth',           0.350)
        obj['dgm_p_hoop_spacing']         = params.get('hoop_spacing',         0.900)
        obj['dgm_p_cage_max_hoops']       = params.get('cage_max_hoops',       0)
        obj['dgm_p_cage_bar_count']       = params.get('cage_bar_count',       5)
        obj['dgm_p_hook_enabled']             = params.get('hook_enabled',             False)
        obj['dgm_p_hook_radius']              = params.get('hook_radius',              0.150)
        obj['dgm_p_hook_extension']           = params.get('hook_extension',           0.080)
        obj['dgm_p_hook_dayz_radius']         = params.get('hook_dayz_radius',         True)
        obj['dgm_p_hook_dayz_extension']      = params.get('hook_dayz_extension',      True)
        obj['dgm_p_hook_drop']                = params.get('hook_drop',                0.080)
        obj['dgm_p_hook_end_bracket']         = params.get('hook_end_bracket',         True)
        obj['dgm_p_hook_plate_width']         = params.get('hook_plate_width',         0.120)
        obj['dgm_p_hook_plate_depth']         = params.get('hook_plate_depth',         0.120)
        obj['dgm_p_hook_plate_thickness']     = params.get('hook_plate_thickness',     0.012)
        obj['dgm_p_hook_screws_enabled']      = params.get('hook_screws_enabled',      True)
        obj['dgm_p_hook_screw_axis']          = params.get('hook_screw_axis',          'X')
        obj['dgm_p_hook_screw_count']         = params.get('hook_screw_count',         2)
        obj['dgm_p_bracket_enabled']          = params.get('bracket_enabled',          False)
        obj['dgm_p_bracket_spacing']          = params.get('bracket_spacing',          1.500)
        obj['dgm_p_bracket_max_count']        = params.get('bracket_max_count',        0)
        obj['dgm_p_bracket_start_z']          = params.get('bracket_start_z',          1.000)
        obj['dgm_p_bracket_plate_width']      = params.get('bracket_plate_width',      0.120)
        obj['dgm_p_bracket_depth']            = params.get('bracket_depth',            0.060)
        obj['dgm_p_bracket_plate_height']     = params.get('bracket_plate_height',     0.120)
        obj['dgm_p_bracket_plate_thickness']  = params.get('bracket_plate_thickness',  0.012)
        obj['dgm_p_bracket_screw_count']      = params.get('bracket_screw_count',      2)
        obj['dgm_p_bracket_screws_enabled']   = params.get('bracket_screws_enabled',   True)
        obj['dgm_p_bracket_screw_axis']       = params.get('bracket_screw_axis',       'X')
        obj['dgm_p_mount_side']               = params.get('mount_side',               'STANDARD')
        obj['dgm_p_width']                = params['width']
        obj['dgm_p_tube_diameter']        = params['tube_diameter']
        obj['dgm_p_rung_count']           = params['rung_count']
        obj['dgm_p_rung_spacing']         = params['rung_spacing']
        obj['dgm_p_ground_offset']        = params['ground_offset']
        obj['dgm_p_top_extension']        = params['top_extension']
        obj['dgm_p_resolution']           = params['resolution']
        obj['dgm_p_bend_segments']        = params.get('bend_segments', 10)
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
        row_top = col.row(align=True)
        row_top.enabled = not self.hook_enabled
        row_top.prop(self, 'top_extension')
        row_top.label(text="", icon='CHECKMARK' if self.hook_enabled else _std_icon(getattr(self, 'top_extension'), TOP_EXT_STD))
        if self.hook_enabled:
            note = col.row()
            note.enabled = False
            note.label(text="Top Extension is forced to 0 when Top Hook is enabled", icon='INFO')
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
            ccol.prop(self, 'cage_max_hoops')
            ccol.prop(self, 'cage_bar_count')
            cage_top_z = _hook_total_height(params, total_height)
            hoop_count = (max(0, int((cage_top_z - self.cage_start_z) / self.hoop_spacing) + 1)
                          if self.cage_start_z <= cage_top_z else 0)
            if self.cage_max_hoops > 0:
                hoop_count = min(hoop_count, self.cage_max_hoops)
            info_row = ccol.row()
            info_row.enabled = False
            info_row.label(text="Hoops: {}  |  Cage top limit: {:.3f} m".format(
                hoop_count, cage_top_z), icon='INFO')
            cage_top_z = _hook_total_height(params, total_height)
            hoop_count = (max(0, int((cage_top_z - self.cage_start_z) / self.hoop_spacing) + 1)
                          if self.cage_start_z <= cage_top_z else 0)
            if self.cage_max_hoops > 0:
                hoop_count = min(hoop_count, self.cage_max_hoops)
            ccol.separator()
            info_row = ccol.row()
            info_row.enabled = False
            total_depth = self.cage_depth + params['width'] / 2.0
            info_row.label(text="Hoops: {}  |  Total depth: {:.0f} mm".format(
                hoop_count, total_depth * 1000),
                icon='INFO')

        # ── Top Hook ─────────────────────────────────────────────────────────
        hook_box = layout.box()
        hook_header = hook_box.row(align=True)
        hook_text = "Remove Top Hook" if self.hook_enabled else "Add Top Hook"
        hook_icon = 'X' if self.hook_enabled else 'ADD'
        hook_header.prop(self, 'hook_enabled', text=hook_text, icon=hook_icon)
        if self.hook_enabled:
            hcol = hook_box.column(align=True)
            hcol.prop(self, 'hook_dayz_radius')
            row = hcol.row()
            row.enabled = not self.hook_dayz_radius
            row.prop(self, 'hook_radius')
            hcol.prop(self, 'hook_dayz_extension')
            row = hcol.row()
            row.enabled = not self.hook_dayz_extension
            row.prop(self, 'hook_extension')
            hcol.prop(self, 'hook_drop')
            hcol.separator()
            hcol.prop(self, 'hook_end_bracket')
            if self.hook_end_bracket:
                hcol.prop(self, 'hook_plate_width')
                hcol.prop(self, 'hook_plate_depth')
                hcol.prop(self, 'hook_plate_thickness')
                hcol.separator()
                hcol.prop(self, 'hook_screws_enabled')
                if self.hook_screws_enabled:
                    hcol.prop(self, 'hook_screw_axis', expand=True)
                    hcol.prop(self, 'hook_screw_count')
                    hook_axis_len = self.hook_plate_width if self.hook_screw_axis == 'X' else self.hook_plate_depth
                    if not _screws_allowed(hook_axis_len):
                        warn = hcol.row()
                        warn.alert = True
                        warn.label(text="Hook screw axis needs at least 11 cm", icon='ERROR')
                    elif int(self.hook_screw_count) == 4 and hook_axis_len < MIN_FOUR_SCREW_AXIS_LENGTH:
                        warn = hcol.row()
                        warn.alert = True
                        warn.label(text="4 hook screws need at least 22 cm; using 2", icon='ERROR')
            info_row = hcol.row()
            info_row.enabled = False
            arch_top = self.hook_extension + self.hook_radius
            info_row.label(
                text="Rise: {:.0f} mm  |  Reach: {:.0f} mm  |  Drop: {:.0f} mm".format(
                    arch_top * 1000, self.hook_radius * 2000, self.hook_drop * 1000),
                icon='INFO')

        # ── Wall Brackets ─────────────────────────────────────────────────────
        br_box = layout.box()
        br_header = br_box.row(align=True)
        br_text = "Remove Wall Brackets" if self.bracket_enabled else "Add Wall Brackets"
        br_icon = 'X' if self.bracket_enabled else 'ADD'
        br_header.prop(self, 'bracket_enabled', text=br_text, icon=br_icon)
        if self.bracket_enabled:
            bcol = br_box.column(align=True)
            bcol.prop(self, 'bracket_start_z')
            bcol.prop(self, 'bracket_spacing')
            bcol.prop(self, 'bracket_max_count')
            bcol.separator()
            bcol.prop(self, 'bracket_plate_width')
            bcol.prop(self, 'bracket_plate_height')
            bcol.prop(self, 'bracket_plate_thickness')
            bcol.prop(self, 'bracket_depth')
            bcol.separator()
            bcol.prop(self, 'bracket_screws_enabled')
            if self.bracket_screws_enabled:
                bcol.prop(self, 'bracket_screw_axis', expand=True)
                bcol.prop(self, 'bracket_screw_count')
                bracket_axis_len = self.bracket_plate_width if self.bracket_screw_axis == 'X' else self.bracket_plate_height
                if not _screws_allowed(bracket_axis_len):
                    warn = bcol.row()
                    warn.alert = True
                    warn.label(text="Wall screw axis needs at least 11 cm", icon='ERROR')
                elif int(self.bracket_screw_count) == 4 and bracket_axis_len < MIN_FOUR_SCREW_AXIS_LENGTH:
                    warn = bcol.row()
                    warn.alert = True
                    warn.label(text="4 wall screws need at least 22 cm; using 2", icon='ERROR')
            # Validation: plate thickness must fit within stand-off depth
            if self.bracket_plate_thickness >= self.bracket_depth:
                warn = bcol.row()
                warn.alert = True
                warn.label(
                    text="Plate thickness must be less than stand-off depth",
                    icon='ERROR')
            br_count = (max(0, int((total_height - self.bracket_start_z) / self.bracket_spacing) + 1)
                        if self.bracket_start_z <= total_height else 0)
            if self.bracket_max_count > 0:
                br_count = min(br_count, self.bracket_max_count)
            info_row = bcol.row()
            info_row.enabled = False
            standoff_len = max(0.0, self.bracket_depth - self.bracket_plate_thickness)
            screw_axis_len = self.bracket_plate_width if self.bracket_screw_axis == 'X' else self.bracket_plate_height
            screw_count = _screw_count_for_axis(self.bracket_screw_count, screw_axis_len)
            screw_total = (br_count * 2 * screw_count
                           if self.bracket_screws_enabled and _screws_allowed(screw_axis_len) else 0)
            info_row.label(
                text="Pairs: {}  |  Stand-off rod: {:.0f} mm  |  Screws: {}".format(
                    br_count, standoff_len * 1000, screw_total),
                icon='INFO')

        # ── Mount Side toggle (only relevant when hook or brackets enabled) ──
        if self.hook_enabled or self.bracket_enabled:
            ms_box = layout.box()
            ms_box.label(text="Mount Side", icon='ORIENTATION_VIEW')
            ms_box.prop(self, 'mount_side', expand=True)

        # Mesh quality — compact single row
        q_row = layout.row(align=True)
        q_row.label(text="Tube Segments:", icon='MESH_CIRCLE')
        q_row.prop(self, 'resolution', text="")
        b_row = layout.row(align=True)
        b_row.label(text="Bend Segments:", icon='MOD_CURVE')
        b_row.prop(self, 'bend_segments', text="")

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
    bend_segments: bpy.props.IntProperty(
        name="Bend Segments",
        description=(
            "Number of length segments used to build curved bends.\n"
            "3 = low-poly bend, 12 = balanced, higher values are smoother but heavier."
        ),
        default=10, min=3, max=48)

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
    cage_max_hoops: bpy.props.IntProperty(
        name="Max Hoops",
        description="Maximum generated cage hoops. 0 means no limit.",
        default=0, min=0, max=128)
    cage_bar_count: bpy.props.IntProperty(
        name="Vertical Bars",
        description="Number of vertical bars along the cage.",
        default=5, min=0, max=12)

    # ── Top hook ─────────────────────────────────────────────────────────────
    hook_enabled: bpy.props.BoolProperty(
        name="Top Hook",
        description="Add inverted-U grab arches at the top of the ladder.",
        default=False)
    hook_radius: bpy.props.FloatProperty(
        name="Hook Radius",
        description="Radius of the half-circle at the top of the arch. Recommended DayZ value: 25 cm.",
        default=0.150, min=0.030, max=0.500, step=1, unit='LENGTH')
    hook_extension: bpy.props.FloatProperty(
        name="Hook Extension",
        description="Straight rise from stringer top before the curve begins. Recommended DayZ value: 70 cm.",
        default=0.080, min=0.000, max=1.000, step=1, unit='LENGTH')
    hook_dayz_extension: bpy.props.BoolProperty(
        name="DayZ 70 cm Extension",
        description="Lock Hook Extension to the recommended DayZ roof-exit value: 70 cm.",
        default=True)
    hook_dayz_radius: bpy.props.BoolProperty(
        name="DayZ 25 cm Radius",
        description="Lock Hook Radius to the recommended DayZ roof hook radius: 25 cm.",
        default=True)
    hook_drop: bpy.props.FloatProperty(
        name="Hook Drop",
        description="Straight drop on the far leg of the arch, after the curve.",
        default=0.080, min=0.000, max=1.000, step=1, unit='LENGTH')
    hook_end_bracket: bpy.props.BoolProperty(
        name="End Plate with Screws",
        description="Mount a wall plate with screws at the end of the hook drop tube.",
        default=True)
    hook_plate_width: bpy.props.FloatProperty(
        name="Hook Plate Width",
        description="Width of the top hook end plate along X.",
        default=0.120, min=0.020, max=0.400, step=1, unit='LENGTH')
    hook_plate_depth: bpy.props.FloatProperty(
        name="Hook Plate Depth",
        description="Depth of the top hook end plate along Y.",
        default=0.120, min=0.020, max=0.400, step=1, unit='LENGTH')
    hook_plate_thickness: bpy.props.FloatProperty(
        name="Hook Plate Thickness",
        description="Vertical thickness of the horizontal top hook plate.",
        default=0.012, min=0.003, max=0.050, step=1, unit='LENGTH')
    hook_screws_enabled: bpy.props.BoolProperty(
        name="Hook Plate Screws",
        description="Generate hex screw heads on the top hook end plate.",
        default=True)
    hook_screw_axis: bpy.props.EnumProperty(
        name="Hook Screw Axis",
        description="Axis used to distribute screws on the horizontal hook plate.",
        items=[
            ('X', "X Axis", "Place screws across plate width"),
            ('Y', "Y Axis", "Place screws across plate depth"),
        ],
        default='X')
    hook_screw_count: bpy.props.EnumProperty(
        name="Hook Screws",
        description="Number of screw bolts on each top hook plate.",
        items=[
            ('2', "2 Screws", "Use two screws"),
            ('4', "4 Screws", "Use four screws; requires selected axis at least 22 cm"),
        ],
        default='2')

    # ── Wall brackets ─────────────────────────────────────────────────────────
    bracket_enabled: bpy.props.BoolProperty(
        name="Wall Brackets",
        description="Add wall-mounting brackets with stand-off rod, plate and screws.",
        default=False)
    bracket_spacing: bpy.props.FloatProperty(
        name="Bracket Spacing",
        description="Vertical distance between bracket rows.",
        default=1.500, min=0.200, max=5.000, step=1, unit='LENGTH')
    bracket_max_count: bpy.props.IntProperty(
        name="Max Bracket Rows",
        description="Maximum number of wall bracket rows. 0 means no limit.",
        default=0, min=0, max=64)
    bracket_start_z: bpy.props.FloatProperty(
        name="First Bracket Height",
        description="Height of the first bracket row above ladder base.",
        default=1.000, min=0.0, max=20.0, step=1, unit='LENGTH')
    bracket_plate_width: bpy.props.FloatProperty(
        name="Plate Width",
        description="Width of the wall plate in X.",
        default=0.120, min=0.020, max=0.300, step=1, unit='LENGTH')
    bracket_depth: bpy.props.FloatProperty(
        name="Stand-off Depth",
        description="Total depth from stringer surface to wall (rod + plate).",
        default=0.060, min=0.015, max=1.000, step=1, unit='LENGTH')
    bracket_plate_height: bpy.props.FloatProperty(
        name="Plate Height",
        description="Height of the wall plate in Z.",
        default=0.120, min=0.020, max=0.250, step=1, unit='LENGTH')
    bracket_plate_thickness: bpy.props.FloatProperty(
        name="Plate Thickness",
        description="Thickness of the flat wall plate in Y.",
        default=0.012, min=0.003, max=0.050, step=1, unit='LENGTH')
    bracket_screw_count: bpy.props.EnumProperty(
        name="Screws per Plate",
        description="Number of screw bolts per wall plate.",
        items=[
            ('2', "2 Screws", "Use two screws"),
            ('4', "4 Screws", "Use four screws; requires selected axis at least 22 cm"),
        ],
        default='2')
    bracket_screws_enabled: bpy.props.BoolProperty(
        name="Wall Plate Screws",
        description="Generate hex screw heads on wall bracket plates.",
        default=True)
    bracket_screw_axis: bpy.props.EnumProperty(
        name="Wall Screw Axis",
        description="Axis used to distribute screws on the vertical wall plate.",
        items=[
            ('X', "Horizontal", "Place screws along plate width"),
            ('Z', "Vertical", "Place screws along plate height"),
        ],
        default='X')

    # ── Mount Side ───────────────────────────────────────────────────────────
    mount_side: bpy.props.EnumProperty(
        name="Mount Side",
        description="Direction the hook and brackets point in.",
        items=[
            ('STANDARD', "Standard",
             "Hook + brackets on wall side (+Y), opposite the cage"),
            ('INVERTED', "Inverted",
             "Hook + brackets on cage side (-Y) — for ladders rotated 180°"),
        ],
        default='STANDARD')

    @classmethod
    def poll(cls, context):
        return _is_active_ladder(context.active_object)

    def _get_params(self):
        if self.hook_enabled:
            self.top_extension = 0.0
        elif abs(self.top_extension) < _TOL:
            self.top_extension = TOP_EXT_STD
        if self.hook_dayz_radius:
            self.hook_radius = DAYZ_HOOK_RADIUS
        if self.hook_dayz_extension:
            self.hook_extension = DAYZ_HOOK_EXTENSION
        return dict(
            width=self.width,
            tube_diameter=self.tube_diameter,
            rung_count=self.rung_count,
            rung_spacing=self.rung_spacing,
            ground_offset=self.ground_offset,
            top_extension=self.top_extension,
            resolution=self.resolution,
            bend_segments=self.bend_segments,
            cage_enabled=self.cage_enabled,
            cage_start_z=self.cage_start_z,
            cage_depth=self.cage_depth,
            hoop_spacing=self.hoop_spacing,
            cage_max_hoops=self.cage_max_hoops,
            cage_bar_count=self.cage_bar_count,
            cage_tube_d=self.tube_diameter,
            hook_enabled=self.hook_enabled,
            hook_radius=DAYZ_HOOK_RADIUS if self.hook_dayz_radius else self.hook_radius,
            hook_extension=DAYZ_HOOK_EXTENSION if self.hook_dayz_extension else self.hook_extension,
            hook_dayz_radius=self.hook_dayz_radius,
            hook_dayz_extension=self.hook_dayz_extension,
            hook_drop=self.hook_drop,
            hook_end_bracket=self.hook_end_bracket,
            hook_plate_width=self.hook_plate_width,
            hook_plate_depth=self.hook_plate_depth,
            hook_plate_thickness=self.hook_plate_thickness,
            hook_screws_enabled=self.hook_screws_enabled,
            hook_screw_axis=self.hook_screw_axis,
            hook_screw_count=self.hook_screw_count,
            bracket_enabled=self.bracket_enabled,
            bracket_spacing=self.bracket_spacing,
            bracket_max_count=self.bracket_max_count,
            bracket_start_z=self.bracket_start_z,
            bracket_plate_width=self.bracket_plate_width,
            bracket_depth=self.bracket_depth,
            bracket_plate_height=self.bracket_plate_height,
            bracket_plate_thickness=self.bracket_plate_thickness,
            bracket_screw_count=self.bracket_screw_count,
            bracket_screws_enabled=self.bracket_screws_enabled,
            bracket_screw_axis=self.bracket_screw_axis,
            mount_side=self.mount_side,
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
        # Capture the EXACT bbox of the freshly built mesh BEFORE freeing bm.
        bbox_w, bbox_d, bbox_h = _bbox_from_bm(bm)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        # Always update display counters (these are cosmetic, not validated)
        obj['dgm_ladder_rungs']  = rung_count
        obj['dgm_ladder_height'] = round(total_height, 4)
        if commit:
            # Only write expected_* and dgm_p_* on confirmed OK
            obj['dgm_ladder_expected_height'] = round(bbox_h, 4)
            obj['dgm_ladder_expected_width']  = round(bbox_w, 4)
            obj['dgm_ladder_expected_depth']  = round(bbox_d, 4)
            obj['dgm_p_width']                = self.width
            obj['dgm_p_tube_diameter']        = self.tube_diameter
            obj['dgm_p_rung_count']           = self.rung_count
            obj['dgm_p_rung_spacing']         = self.rung_spacing
            obj['dgm_p_ground_offset']        = self.ground_offset
            obj['dgm_p_top_extension']        = self.top_extension
            obj['dgm_p_resolution']           = self.resolution
            obj['dgm_p_bend_segments']        = self.bend_segments
            obj['dgm_p_cage_enabled']         = self.cage_enabled
            obj['dgm_p_cage_start_z']         = self.cage_start_z
            obj['dgm_p_cage_depth']           = self.cage_depth
            obj['dgm_p_hoop_spacing']         = self.hoop_spacing
            obj['dgm_p_cage_max_hoops']       = self.cage_max_hoops
            obj['dgm_p_cage_bar_count']       = self.cage_bar_count
            obj['dgm_p_hook_enabled']             = self.hook_enabled
            obj['dgm_p_hook_radius']              = params.get('hook_radius', self.hook_radius)
            obj['dgm_p_hook_extension']           = params.get('hook_extension', self.hook_extension)
            obj['dgm_p_hook_dayz_radius']         = self.hook_dayz_radius
            obj['dgm_p_hook_dayz_extension']      = self.hook_dayz_extension
            obj['dgm_p_hook_drop']                = self.hook_drop
            obj['dgm_p_hook_end_bracket']         = self.hook_end_bracket
            obj['dgm_p_hook_plate_width']         = self.hook_plate_width
            obj['dgm_p_hook_plate_depth']         = self.hook_plate_depth
            obj['dgm_p_hook_plate_thickness']     = self.hook_plate_thickness
            obj['dgm_p_hook_screws_enabled']      = self.hook_screws_enabled
            obj['dgm_p_hook_screw_axis']          = self.hook_screw_axis
            obj['dgm_p_hook_screw_count']         = self.hook_screw_count
            obj['dgm_p_bracket_enabled']          = self.bracket_enabled
            obj['dgm_p_bracket_spacing']          = self.bracket_spacing
            obj['dgm_p_bracket_max_count']        = self.bracket_max_count
            obj['dgm_p_bracket_start_z']          = self.bracket_start_z
            obj['dgm_p_bracket_plate_width']      = self.bracket_plate_width
            obj['dgm_p_bracket_depth']            = self.bracket_depth
            obj['dgm_p_bracket_plate_height']     = self.bracket_plate_height
            obj['dgm_p_bracket_plate_thickness']  = self.bracket_plate_thickness
            obj['dgm_p_bracket_screw_count']      = self.bracket_screw_count
            obj['dgm_p_bracket_screws_enabled']   = self.bracket_screws_enabled
            obj['dgm_p_bracket_screw_axis']       = self.bracket_screw_axis
            obj['dgm_p_mount_side']               = self.mount_side


    def _snapshot(self, obj):
        """Take a bmesh snapshot of the current mesh and ALL properties for cancel restoration."""
        snap = bmesh.new()
        snap.from_mesh(obj.data)
        self._snapshot_mesh = snap
        self._snapshot_params = dict(
            width                = obj.get('dgm_p_width',                self.width),
            tube_diameter        = obj.get('dgm_p_tube_diameter',        self.tube_diameter),
            rung_count           = obj.get('dgm_p_rung_count',           self.rung_count),
            rung_spacing         = obj.get('dgm_p_rung_spacing',         self.rung_spacing),
            ground_offset        = obj.get('dgm_p_ground_offset',        self.ground_offset),
            top_extension        = obj.get('dgm_p_top_extension',        self.top_extension),
            resolution           = obj.get('dgm_p_resolution',           self.resolution),
            bend_segments        = obj.get('dgm_p_bend_segments',        10),
            cage_enabled         = obj.get('dgm_p_cage_enabled',         False),
            cage_start_z         = obj.get('dgm_p_cage_start_z',         2.200),
            cage_depth           = obj.get('dgm_p_cage_depth',           0.350),
            hoop_spacing         = obj.get('dgm_p_hoop_spacing',         0.900),
            cage_max_hoops       = obj.get('dgm_p_cage_max_hoops',       0),
            cage_bar_count       = obj.get('dgm_p_cage_bar_count',       5),
            hook_enabled            = obj.get('dgm_p_hook_enabled',            False),
            hook_radius             = obj.get('dgm_p_hook_radius',             0.150),
            hook_extension          = obj.get('dgm_p_hook_extension',          0.080),
            hook_dayz_radius        = obj.get('dgm_p_hook_dayz_radius',        True),
            hook_dayz_extension     = obj.get('dgm_p_hook_dayz_extension',     True),
            hook_drop               = obj.get('dgm_p_hook_drop',               0.080),
            hook_end_bracket        = obj.get('dgm_p_hook_end_bracket',        True),
            hook_plate_width        = obj.get('dgm_p_hook_plate_width',        0.120),
            hook_plate_depth        = obj.get('dgm_p_hook_plate_depth',        0.120),
            hook_plate_thickness    = obj.get('dgm_p_hook_plate_thickness',    0.012),
            hook_screws_enabled     = obj.get('dgm_p_hook_screws_enabled',     True),
            hook_screw_axis         = obj.get('dgm_p_hook_screw_axis',         'X'),
            hook_screw_count        = obj.get('dgm_p_hook_screw_count',        2),
            bracket_enabled         = obj.get('dgm_p_bracket_enabled',         False),
            bracket_spacing         = obj.get('dgm_p_bracket_spacing',         1.500),
            bracket_max_count       = obj.get('dgm_p_bracket_max_count',       0),
            bracket_start_z         = obj.get('dgm_p_bracket_start_z',         1.000),
            bracket_plate_width     = obj.get('dgm_p_bracket_plate_width',     0.120),
            bracket_depth           = obj.get('dgm_p_bracket_depth',           0.060),
            bracket_plate_height    = obj.get('dgm_p_bracket_plate_height',    0.120),
            bracket_plate_thickness = obj.get('dgm_p_bracket_plate_thickness', 0.012),
            bracket_screw_count     = obj.get('dgm_p_bracket_screw_count',     2),
            bracket_screws_enabled  = obj.get('dgm_p_bracket_screws_enabled',  True),
            bracket_screw_axis      = obj.get('dgm_p_bracket_screw_axis',      'X'),
            mount_side              = obj.get('dgm_p_mount_side',              'STANDARD'),
            rungs                = obj.get('dgm_ladder_rungs',            self.rung_count),
            height               = obj.get('dgm_ladder_height',           0.0),
            expected_height      = obj.get('dgm_ladder_expected_height',  None),
            expected_width       = obj.get('dgm_ladder_expected_width',   None),
            expected_depth       = obj.get('dgm_ladder_expected_depth',   None),
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
        obj['dgm_p_bend_segments'] = p.get('bend_segments', 10)
        obj['dgm_p_cage_enabled']         = p.get('cage_enabled',         False)
        obj['dgm_p_cage_start_z']         = p.get('cage_start_z',         2.200)
        obj['dgm_p_cage_depth']           = p.get('cage_depth',           0.350)
        obj['dgm_p_hoop_spacing']         = p.get('hoop_spacing',         0.900)
        obj['dgm_p_cage_max_hoops']       = p.get('cage_max_hoops',       0)
        obj['dgm_p_cage_bar_count']       = p.get('cage_bar_count',       5)
        obj['dgm_p_hook_enabled']             = p.get('hook_enabled',            False)
        obj['dgm_p_hook_radius']              = p.get('hook_radius',             0.150)
        obj['dgm_p_hook_extension']           = p.get('hook_extension',          0.080)
        obj['dgm_p_hook_dayz_radius']         = p.get('hook_dayz_radius',        True)
        obj['dgm_p_hook_dayz_extension']      = p.get('hook_dayz_extension',     True)
        obj['dgm_p_hook_drop']                = p.get('hook_drop',               0.080)
        obj['dgm_p_hook_end_bracket']         = p.get('hook_end_bracket',        True)
        obj['dgm_p_hook_plate_width']         = p.get('hook_plate_width',        0.120)
        obj['dgm_p_hook_plate_depth']         = p.get('hook_plate_depth',        0.120)
        obj['dgm_p_hook_plate_thickness']     = p.get('hook_plate_thickness',    0.012)
        obj['dgm_p_hook_screws_enabled']      = p.get('hook_screws_enabled',     True)
        obj['dgm_p_hook_screw_axis']          = p.get('hook_screw_axis',         'X')
        obj['dgm_p_hook_screw_count']         = p.get('hook_screw_count',        2)
        obj['dgm_p_bracket_enabled']          = p.get('bracket_enabled',         False)
        obj['dgm_p_bracket_spacing']          = p.get('bracket_spacing',         1.500)
        obj['dgm_p_bracket_max_count']        = p.get('bracket_max_count',       0)
        obj['dgm_p_bracket_start_z']          = p.get('bracket_start_z',         1.000)
        obj['dgm_p_bracket_plate_width']      = p.get('bracket_plate_width',     0.120)
        obj['dgm_p_bracket_depth']            = p.get('bracket_depth',           0.060)
        obj['dgm_p_bracket_plate_height']     = p.get('bracket_plate_height',    0.120)
        obj['dgm_p_bracket_plate_thickness']  = p.get('bracket_plate_thickness', 0.012)
        obj['dgm_p_bracket_screw_count']      = p.get('bracket_screw_count',     2)
        obj['dgm_p_bracket_screws_enabled']   = p.get('bracket_screws_enabled',  True)
        obj['dgm_p_bracket_screw_axis']       = p.get('bracket_screw_axis',      'X')
        obj['dgm_p_mount_side']               = p.get('mount_side',              'STANDARD')
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
        self.bend_segments  = obj.get('dgm_p_bend_segments', 10)
        stored_rungs = obj.get('dgm_p_rung_count', None)
        self.rung_count = stored_rungs if stored_rungs is not None                           else obj.get('dgm_ladder_rungs', 16)
        # Load cage params
        self.cage_enabled    = obj.get('dgm_p_cage_enabled',   False)
        self.cage_start_z    = obj.get('dgm_p_cage_start_z',   2.200)
        self.cage_depth      = obj.get('dgm_p_cage_depth',     0.350)
        self.hoop_spacing    = obj.get('dgm_p_hoop_spacing',   0.900)
        self.cage_max_hoops  = obj.get('dgm_p_cage_max_hoops', 0)
        self.cage_bar_count  = obj.get('dgm_p_cage_bar_count', 5)
        # Load hook params
        self.hook_enabled     = obj.get('dgm_p_hook_enabled',     False)
        self.hook_radius      = obj.get('dgm_p_hook_radius',      0.150)
        self.hook_extension   = obj.get('dgm_p_hook_extension',   0.080)
        self.hook_dayz_radius = obj.get('dgm_p_hook_dayz_radius', True)
        self.hook_dayz_extension = obj.get('dgm_p_hook_dayz_extension', True)
        self.hook_drop        = obj.get('dgm_p_hook_drop',        0.080)
        self.hook_end_bracket = obj.get('dgm_p_hook_end_bracket', True)
        self.hook_plate_width     = obj.get('dgm_p_hook_plate_width',     0.120)
        self.hook_plate_depth     = obj.get('dgm_p_hook_plate_depth',     0.120)
        self.hook_plate_thickness = obj.get('dgm_p_hook_plate_thickness', 0.012)
        self.hook_screws_enabled  = obj.get('dgm_p_hook_screws_enabled',  True)
        self.hook_screw_axis      = obj.get('dgm_p_hook_screw_axis',      'X')
        self.hook_screw_count     = _screw_count_id(obj.get('dgm_p_hook_screw_count', 2))
        # Load bracket params
        self.bracket_enabled         = obj.get('dgm_p_bracket_enabled',         False)
        self.bracket_spacing         = obj.get('dgm_p_bracket_spacing',         1.500)
        self.bracket_max_count       = obj.get('dgm_p_bracket_max_count',       0)
        self.bracket_start_z         = obj.get('dgm_p_bracket_start_z',         1.000)
        self.bracket_plate_width     = obj.get('dgm_p_bracket_plate_width',     0.120)
        self.bracket_depth           = obj.get('dgm_p_bracket_depth',           0.060)
        self.bracket_plate_height    = obj.get('dgm_p_bracket_plate_height',    0.120)
        self.bracket_plate_thickness = obj.get('dgm_p_bracket_plate_thickness', 0.012)
        self.bracket_screw_count     = _screw_count_id(obj.get('dgm_p_bracket_screw_count', 2))
        self.bracket_screws_enabled  = obj.get('dgm_p_bracket_screws_enabled',  True)
        self.bracket_screw_axis      = obj.get('dgm_p_bracket_screw_axis',      'X')
        # Load mount side
        self.mount_side      = obj.get('dgm_p_mount_side',     'STANDARD')
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
        row_top = col.row(align=True)
        row_top.enabled = not self.hook_enabled
        row_top.prop(self, 'top_extension')
        row_top.label(text="", icon='CHECKMARK' if self.hook_enabled else _std_icon(getattr(self, 'top_extension'), TOP_EXT_STD))
        if self.hook_enabled:
            note = col.row()
            note.enabled = False
            note.label(text="Top Extension is forced to 0 when Top Hook is enabled", icon='INFO')
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
            ccol.prop(self, 'cage_max_hoops')
            ccol.prop(self, 'cage_bar_count')

        # ── Top Hook ──────────────────────────────────────────────────────────
        hook_box = layout.box()
        hook_text = "Remove Top Hook" if self.hook_enabled else "Add Top Hook"
        hook_icon = 'X' if self.hook_enabled else 'ADD'
        hook_box.prop(self, 'hook_enabled', text=hook_text, icon=hook_icon)
        if self.hook_enabled:
            hcol = hook_box.column(align=True)
            hcol.prop(self, 'hook_dayz_radius')
            row = hcol.row()
            row.enabled = not self.hook_dayz_radius
            row.prop(self, 'hook_radius')
            hcol.prop(self, 'hook_dayz_extension')
            row = hcol.row()
            row.enabled = not self.hook_dayz_extension
            row.prop(self, 'hook_extension')
            hcol.prop(self, 'hook_drop')
            hcol.separator()
            hcol.prop(self, 'hook_end_bracket')
            if self.hook_end_bracket:
                hcol.prop(self, 'hook_plate_width')
                hcol.prop(self, 'hook_plate_depth')
                hcol.prop(self, 'hook_plate_thickness')
                hcol.separator()
                hcol.prop(self, 'hook_screws_enabled')
                if self.hook_screws_enabled:
                    hcol.prop(self, 'hook_screw_axis', expand=True)
                    hcol.prop(self, 'hook_screw_count')
                    hook_axis_len = self.hook_plate_width if self.hook_screw_axis == 'X' else self.hook_plate_depth
                    if not _screws_allowed(hook_axis_len):
                        warn = hcol.row()
                        warn.alert = True
                        warn.label(text="Hook screw axis needs at least 11 cm", icon='ERROR')
                    elif int(self.hook_screw_count) == 4 and hook_axis_len < MIN_FOUR_SCREW_AXIS_LENGTH:
                        warn = hcol.row()
                        warn.alert = True
                        warn.label(text="4 hook screws need at least 22 cm; using 2", icon='ERROR')
            info_row = hcol.row()
            info_row.enabled = False
            arch_top = self.hook_extension + self.hook_radius
            info_row.label(
                text="Rise: {:.0f} mm  |  Reach: {:.0f} mm  |  Drop: {:.0f} mm".format(
                    arch_top * 1000, self.hook_radius * 2000, self.hook_drop * 1000),
                icon='INFO')

        # ── Wall Brackets ─────────────────────────────────────────────────────
        br_box = layout.box()
        br_text = "Remove Wall Brackets" if self.bracket_enabled else "Add Wall Brackets"
        br_icon = 'X' if self.bracket_enabled else 'ADD'
        br_box.prop(self, 'bracket_enabled', text=br_text, icon=br_icon)
        if self.bracket_enabled:
            bcol = br_box.column(align=True)
            bcol.prop(self, 'bracket_start_z')
            bcol.prop(self, 'bracket_spacing')
            bcol.prop(self, 'bracket_max_count')
            bcol.separator()
            bcol.prop(self, 'bracket_plate_width')
            bcol.prop(self, 'bracket_plate_height')
            bcol.prop(self, 'bracket_plate_thickness')
            bcol.prop(self, 'bracket_depth')
            bcol.separator()
            bcol.prop(self, 'bracket_screws_enabled')
            if self.bracket_screws_enabled:
                bcol.prop(self, 'bracket_screw_axis', expand=True)
                bcol.prop(self, 'bracket_screw_count')
                bracket_axis_len = self.bracket_plate_width if self.bracket_screw_axis == 'X' else self.bracket_plate_height
                if not _screws_allowed(bracket_axis_len):
                    warn = bcol.row()
                    warn.alert = True
                    warn.label(text="Wall screw axis needs at least 11 cm", icon='ERROR')
                elif int(self.bracket_screw_count) == 4 and bracket_axis_len < MIN_FOUR_SCREW_AXIS_LENGTH:
                    warn = bcol.row()
                    warn.alert = True
                    warn.label(text="4 wall screws need at least 22 cm; using 2", icon='ERROR')
            if self.bracket_plate_thickness >= self.bracket_depth:
                warn = bcol.row()
                warn.alert = True
                warn.label(
                    text="Plate thickness must be less than stand-off depth",
                    icon='ERROR')
            bm_info2, _, total_height2 = build_ladder_type1(params)
            bm_info2.free()
            br_count = (max(0, int((total_height2 - self.bracket_start_z) / self.bracket_spacing) + 1)
                        if self.bracket_start_z <= total_height2 else 0)
            if self.bracket_max_count > 0:
                br_count = min(br_count, self.bracket_max_count)
            standoff_len = max(0.0, self.bracket_depth - self.bracket_plate_thickness)
            screw_axis_len = self.bracket_plate_width if self.bracket_screw_axis == 'X' else self.bracket_plate_height
            screw_count = _screw_count_for_axis(self.bracket_screw_count, screw_axis_len)
            screw_total = (br_count * 2 * screw_count
                           if self.bracket_screws_enabled and _screws_allowed(screw_axis_len) else 0)
            info_row = bcol.row()
            info_row.enabled = False
            info_row.label(
                text="Pairs: {}  |  Stand-off rod: {:.0f} mm  |  Screws: {}".format(
                    br_count, standoff_len * 1000, screw_total),
                icon='INFO')

        # ── Mount Side ────────────────────────────────────────────────────────
        if self.hook_enabled or self.bracket_enabled:
            ms_box = layout.box()
            ms_box.label(text="Mount Side", icon='ORIENTATION_VIEW')
            ms_box.prop(self, 'mount_side', expand=True)

        q_row = layout.row(align=True)
        q_row.label(text="Tube Segments:", icon='MESH_CIRCLE')
        q_row.prop(self, 'resolution', text="")
        b_row = layout.row(align=True)
        b_row.label(text="Bend Segments:", icon='MOD_CURVE')
        b_row.prop(self, 'bend_segments', text="")

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

        # Rebuild mesh from stored params — including all optional parts
        params = dict(
            width                = obj.get('dgm_p_width',                0.440),
            tube_diameter        = obj.get('dgm_p_tube_diameter',        TUBE_DIAMETER_STD),
            rung_count           = obj.get('dgm_p_rung_count',           16),
            rung_spacing         = obj.get('dgm_p_rung_spacing',         RUNG_SPACING_STD),
            ground_offset        = obj.get('dgm_p_ground_offset',        GROUND_OFFSET_STD),
            top_extension        = obj.get('dgm_p_top_extension',        TOP_EXT_STD),
            resolution           = obj.get('dgm_p_resolution',           10),
            bend_segments        = obj.get('dgm_p_bend_segments',        10),
            cage_enabled         = obj.get('dgm_p_cage_enabled',         False),
            cage_start_z         = obj.get('dgm_p_cage_start_z',         2.200),
            cage_depth           = obj.get('dgm_p_cage_depth',           0.350),
            hoop_spacing         = obj.get('dgm_p_hoop_spacing',         0.900),
            cage_max_hoops       = obj.get('dgm_p_cage_max_hoops',       0),
            cage_bar_count       = obj.get('dgm_p_cage_bar_count',       5),
            cage_tube_d          = obj.get('dgm_p_tube_diameter',        TUBE_DIAMETER_STD),
            hook_enabled            = obj.get('dgm_p_hook_enabled',            False),
            hook_radius             = obj.get('dgm_p_hook_radius',             0.150),
            hook_extension          = obj.get('dgm_p_hook_extension',          0.080),
            hook_dayz_radius        = obj.get('dgm_p_hook_dayz_radius',        True),
            hook_dayz_extension     = obj.get('dgm_p_hook_dayz_extension',     True),
            hook_drop               = obj.get('dgm_p_hook_drop',               0.080),
            hook_end_bracket        = obj.get('dgm_p_hook_end_bracket',        True),
            hook_plate_width        = obj.get('dgm_p_hook_plate_width',        0.120),
            hook_plate_depth        = obj.get('dgm_p_hook_plate_depth',        0.120),
            hook_plate_thickness    = obj.get('dgm_p_hook_plate_thickness',    0.012),
            hook_screws_enabled     = obj.get('dgm_p_hook_screws_enabled',     True),
            hook_screw_axis         = obj.get('dgm_p_hook_screw_axis',         'X'),
            hook_screw_count        = obj.get('dgm_p_hook_screw_count',        2),
            bracket_enabled         = obj.get('dgm_p_bracket_enabled',         False),
            bracket_spacing         = obj.get('dgm_p_bracket_spacing',         1.500),
            bracket_max_count       = obj.get('dgm_p_bracket_max_count',       0),
            bracket_start_z         = obj.get('dgm_p_bracket_start_z',         1.000),
            bracket_plate_width     = obj.get('dgm_p_bracket_plate_width',     0.120),
            bracket_depth           = obj.get('dgm_p_bracket_depth',           0.060),
            bracket_plate_height    = obj.get('dgm_p_bracket_plate_height',    0.120),
            bracket_plate_thickness = obj.get('dgm_p_bracket_plate_thickness', 0.012),
            bracket_screw_count     = obj.get('dgm_p_bracket_screw_count',     2),
            bracket_screws_enabled  = obj.get('dgm_p_bracket_screws_enabled',  True),
            bracket_screw_axis      = obj.get('dgm_p_bracket_screw_axis',      'X'),
            mount_side              = obj.get('dgm_p_mount_side',              'STANDARD'),
        )

        bm, rung_count, total_height = build_ladder_type1(params)
        bbox_w, bbox_d, bbox_h = _bbox_from_bm(bm)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()

        # Restore position and rotation — only scale stays at 1,1,1
        obj.location       = saved_location
        obj.rotation_euler = saved_rotation

        # Refresh stored dimensions from the ACTUAL just-built mesh
        obj['dgm_ladder_rungs']           = rung_count
        obj['dgm_ladder_height']          = round(total_height, 4)
        obj['dgm_ladder_expected_height'] = round(bbox_h, 4)
        obj['dgm_ladder_expected_width']  = round(bbox_w, 4)
        obj['dgm_ladder_expected_depth']  = round(bbox_d, 4)

        self.report({'INFO'}, "Ladder restored to {:.3f} m".format(total_height))
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Panel section (called from operators.py)
# ---------------------------------------------------------------------------

def draw_ladder_generator_section(layout, context):
    obj       = context.active_object
    is_ladder = _is_active_ladder(obj)

    box = layout.box()
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

        hook_enabled = bool(obj.get('dgm_p_hook_enabled', False))
        top_ext = obj.get('dgm_p_top_extension', TOP_EXT_STD)
        top_ext_ok = (abs(top_ext - 0.0) < _TOL if hook_enabled
                      else abs(top_ext - TOP_EXT_STD) < _TOL)

        all_std = (
            round(obj.get('dgm_p_width', 0.440) * 1000) in VALID_WIDTHS_MM
            and abs(obj.get('dgm_p_tube_diameter', TUBE_DIAMETER_STD) - TUBE_DIAMETER_STD) < _TOL
            and abs(obj.get('dgm_p_rung_spacing',  RUNG_SPACING_STD)  - RUNG_SPACING_STD)  < _TOL
            and abs(obj.get('dgm_p_ground_offset', GROUND_OFFSET_STD) - GROUND_OFFSET_STD) < _TOL
            and top_ext_ok
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

            # Check 2: compare current bounding box against the EXACT bbox
            # captured at the last successful commit.  No analytical
            # recomputation — only flags real, post-commit mesh changes
            # (manual edits, Apply Scale, etc.).
            local_corners = [_mu.Vector(c) for c in obj.bound_box]
            lxs = [c.x for c in local_corners]
            lys = [c.y for c in local_corners]
            lzs = [c.z for c in local_corners]
            actual_h = max(lzs) - min(lzs)
            actual_w = max(lxs) - min(lxs)
            actual_d = max(lys) - min(lys)

            expected_h = float(obj.get('dgm_ladder_expected_height', actual_h))
            expected_w = float(obj.get('dgm_ladder_expected_width',  actual_w))
            expected_d = float(obj.get('dgm_ladder_expected_depth',  actual_d))

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


def unregister():
    for cls in reversed(ladder_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()

# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------
