"""
DayZ Geometry Maker - Cabin Generator
Procedural low-poly cabin shell with gable roof, door and windows.
"""

import bpy
import bmesh
import mathutils

from . import geometry


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


SIDES = ('front', 'back', 'left', 'right')
SIDE_LABELS = dict(front="Front", back="Back", left="Left", right="Right")


def _floor_window_params(params, floor_idx, side=""):
    suffix = "_{}".format(floor_idx)
    side_suffix = "_{}_{}".format(side, floor_idx) if side else ""

    def pick(base, default):
        if side_suffix:
            return params.get(base + side_suffix, params.get(base + suffix, params.get(base, default)))
        return params.get(base + suffix, params.get(base, default))

    return dict(
        count=max(0, min(6, int(pick('window_count', 2)))),
        width=max(0.25, float(pick('window_width', 0.75))),
        height=max(0.25, float(pick('window_height', 0.75))),
        sill=max(0.2, float(pick('window_sill', 0.95))),
        offset_y=float(pick('window_offset_y', 0.0)),
    )


def _window_holes_for_wall(params, side, floor_idx, axis_min, axis_max, floor_h):
    wp = _floor_window_params(params, floor_idx, side)
    if wp['count'] <= 0:
        return []
    usable = axis_max - axis_min
    ww = min(wp['width'], usable / max(1, wp['count']) * 0.65)
    wh = min(wp['height'], max(0.25, floor_h - wp['sill'] - 0.25))
    gap = usable / (wp['count'] + 1)
    centers = [axis_min + gap * (i + 1) for i in range(wp['count'])]
    group_min = centers[0] - ww * 0.5
    group_max = centers[-1] + ww * 0.5
    offset = _clamp(wp['offset_y'], axis_min - group_min, axis_max - group_max)
    return [(cy + offset - ww * 0.5, cy + offset + ww * 0.5, wp['sill'], wp['sill'] + wh)
            for cy in centers]


def _wall_axis_bounds(side, width, length, wall_t):
    hx = width * 0.5
    hy = length * 0.5
    if side in ('front', 'back'):
        return -hx, hx
    return -hy + wall_t, hy - wall_t


def _door_side_value(value):
    value = str(value).lower()
    return value if value in SIDES else 'front'


def _door_params(params, idx):
    suffix = "" if idx == 1 else "_{}".format(idx)
    legacy = idx == 1

    def pick(name, default):
        if legacy:
            return params.get(name + suffix, params.get(name, default))
        return params.get(name + suffix, default)

    return dict(
        side=_door_side_value(pick('door_side', 'front')),
        floor=max(1, min(3, int(pick('door_floor', 1)))),
        width=max(0.3, float(pick('door_width', 0.9))),
        height=max(0.6, float(pick('door_height', 2.0))),
        offset=float(pick('door_offset_x', 0.0)),
        panel=bool(pick('door_panel', idx == 1)),
        thickness=max(0.02, float(pick('door_thickness', 0.06))),
        glass=bool(pick('door_glass', False)),
        handle=bool(pick('door_handle', True)),
    )


def _door_specs(params, width, length, wall_t, floor_h, floor_count):
    count = max(0, min(4, int(params.get('door_count', 1))))
    specs = []
    for idx in range(1, count + 1):
        dp = _door_params(params, idx)
        if dp['floor'] > floor_count:
            continue
        axis_min, axis_max = _wall_axis_bounds(dp['side'], width, length, wall_t)
        usable = max(0.35, axis_max - axis_min - 0.10)
        door_w = min(dp['width'], usable)
        door_h = max(0.6, min(dp['height'], floor_h - 0.05))
        centre = _clamp(dp['offset'], axis_min + door_w * 0.5 + 0.05,
                        axis_max - door_w * 0.5 - 0.05)
        specs.append(dict(dp, idx=idx, axis0=centre - door_w * 0.5,
                          axis1=centre + door_w * 0.5, height=door_h))
    return specs


def _window_side_params_from_op(op):
    out = {}
    for side in ('front', 'back', 'right'):
        for floor_idx in (1, 2, 3):
            for key in ('count', 'width', 'height', 'sill', 'offset_y'):
                prop = 'window_{}_{}_{}'.format(key, side, floor_idx)
                if hasattr(op, prop):
                    out[prop] = getattr(op, prop)
    return out


def _door_params_from_op(op):
    out = {}
    for idx in range(2, 5):
        suffix = "_{}".format(idx)
        for name in ('door_side', 'door_floor', 'door_width', 'door_height',
                     'door_offset_x', 'door_panel', 'door_thickness',
                     'door_glass', 'door_handle'):
            prop = name + suffix
            if hasattr(op, prop):
                out[prop] = getattr(op, prop)
    return out


def _door_params_from_obj(obj):
    out = {}
    for idx in range(2, 5):
        suffix = "_{}".format(idx)
        defaults = {
            'door_side': 'front',
            'door_floor': 1,
            'door_width': obj.get('dgm_p_door_width', 0.9),
            'door_height': obj.get('dgm_p_door_height', 2.0),
            'door_offset_x': obj.get('dgm_p_door_offset_x', 0.0),
            'door_panel': obj.get('dgm_p_door_panel', True),
            'door_thickness': obj.get('dgm_p_door_thickness', 0.06),
            'door_glass': False,
            'door_handle': True,
        }
        if idx > 1:
            defaults.update(door_panel=False, door_glass=False, door_handle=True)
        for name, default in defaults.items():
            prop = name + suffix
            out[prop] = obj.get('dgm_p_' + prop, default)
    return out


def _window_side_params_from_obj(obj):
    out = {}
    for side in ('front', 'back', 'right'):
        for floor_idx in (1, 2, 3):
            for key, default in (
                ('count', 2),
                ('width', 0.75),
                ('height', 0.75),
                ('sill', 0.95),
                ('offset_y', 0.0),
            ):
                prop = 'window_{}_{}_{}'.format(key, side, floor_idx)
                if side in ('front', 'back'):
                    fallback = 0 if key == 'count' else default
                else:
                    fallback = obj.get('dgm_p_window_{}_{}'.format(key, floor_idx), default)
                out[prop] = obj.get('dgm_p_' + prop, fallback)
    return out


def _balcony_params(params, idx):
    suffix = "" if idx == 1 else "_{}".format(idx)

    def pick(name, default):
        if idx == 1:
            return params.get(name + suffix, params.get(name, default))
        return params.get(name + suffix, default)

    return dict(
        floor=max(2, min(3, int(pick('balcony_floor', 2)))),
        side=_door_side_value(pick('balcony_side', 'front')),
        width=max(0.5, float(pick('balcony_width', 1.8))),
        depth=max(0.3, float(pick('balcony_depth', 0.9))),
        offset=float(pick('balcony_offset', 0.0)),
        thickness=max(0.04, float(pick('balcony_thickness', 0.10))),
        rail_height=max(0.4, float(pick('balcony_rail_height', 0.9))),
        rail_thickness=max(0.025, float(pick('balcony_rail_thickness', 0.07))),
    )


def _balcony_specs(params, width, length, floor_h, floor_count):
    count = max(0, min(8, int(params.get('balcony_count', 1 if params.get('balcony_enabled', False) else 0))))
    specs = []
    for idx in range(1, count + 1):
        bp = _balcony_params(params, idx)
        if bp['floor'] > floor_count:
            continue
        axis_min, axis_max = _wall_axis_bounds(bp['side'], width, length, 0.0)
        bw = min(bp['width'], max(0.5, axis_max - axis_min - 0.2))
        c = _clamp(bp['offset'], axis_min + bw * 0.5 + 0.05, axis_max - bw * 0.5 - 0.05)
        specs.append(dict(bp, idx=idx, axis0=c - bw * 0.5, axis1=c + bw * 0.5,
                          base_z=floor_h * (bp['floor'] - 1)))
    return specs


def _balcony_params_from_op(op):
    out = {}
    for idx in range(2, 9):
        suffix = "_{}".format(idx)
        for name in ('balcony_floor', 'balcony_side', 'balcony_width', 'balcony_depth',
                     'balcony_offset', 'balcony_thickness', 'balcony_rail_height',
                     'balcony_rail_thickness'):
            prop = name + suffix
            if hasattr(op, prop):
                out[prop] = getattr(op, prop)
    return out


def _balcony_params_from_obj(obj):
    out = {}
    for idx in range(2, 9):
        suffix = "_{}".format(idx)
        defaults = {
            'balcony_floor': 2,
            'balcony_side': 'front',
            'balcony_width': 1.8,
            'balcony_depth': 0.9,
            'balcony_offset': 0.0,
            'balcony_thickness': 0.10,
            'balcony_rail_height': 0.9,
            'balcony_rail_thickness': 0.07,
        }
        for name, default in defaults.items():
            prop = name + suffix
            out[prop] = obj.get('dgm_p_' + prop, default)
    return out


def _add_wall_with_holes(add_box_fn, orientation, const0, const1, axis_min, axis_max,
                         zbase, ztop, holes):
    holes = sorted(holes, key=lambda h: h[0])
    cursor = axis_min

    def emit(a0, a1, z0, z1):
        if a1 <= a0 or z1 <= z0:
            return
        if orientation == 'Y':
            add_box_fn((a0, const0, z0), (a1, const1, z1))
        else:
            add_box_fn((const0, a0, z0), (const1, a1, z1))

    for h0, h1, hz0, hz1 in holes:
        h0 = _clamp(h0, axis_min, axis_max)
        h1 = _clamp(h1, axis_min, axis_max)
        if h1 <= h0:
            continue
        emit(cursor, h0, zbase, ztop)
        emit(h0, h1, zbase, zbase + hz0)
        emit(h0, h1, zbase + hz1, ztop)
        cursor = max(cursor, h1)
    emit(cursor, axis_max, zbase, ztop)


def _add_box(bm, min_xyz, max_xyz):
    x0, y0, z0 = min_xyz
    x1, y1, z1 = max_xyz
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        return
    v = [
        bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)), bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)), bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)), bm.verts.new((x0, y1, z1)),
    ]
    for f in ((0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)):
        bm.faces.new([v[i] for i in f])


def _add_gable_roof(bm, width, length, wall_h, roof_h, overhang):
    hw = width * 0.5 + overhang
    hl = length * 0.5 + overhang
    z0 = wall_h
    zr = wall_h + roof_h
    pts = [
        (-hw, -hl, z0), (0.0, -hl, zr), (hw, -hl, z0),
        (-hw,  hl, z0), (0.0,  hl, zr), (hw,  hl, z0),
    ]
    v = [bm.verts.new(p) for p in pts]
    for f in ((0,1,2), (3,5,4), (0,3,4,1), (1,4,5,2), (0,2,5,3)):
        bm.faces.new([v[i] for i in f])


def _add_roof_cover(bm, width, length, wall_h, roof_h, roof_overhang, cover_overhang, cover_thickness):
    hw = width * 0.5 + roof_overhang + cover_overhang
    hl = length * 0.5 + roof_overhang + cover_overhang
    z0 = wall_h + 0.015
    zr = wall_h + roof_h + 0.015
    th = max(0.01, cover_thickness)

    def panel(sign):
        eave_x = sign * hw
        ridge_x = 0.0
        top = [
            (ridge_x, -hl, zr), (ridge_x, hl, zr),
            (eave_x,  hl, z0), (eave_x, -hl, z0),
        ]
        bot = [(x, y, z - th) for x, y, z in top]
        verts = [bm.verts.new(p) for p in top + bot]
        for f in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
                  (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
            bm.faces.new([verts[i] for i in f])

    panel(-1.0)
    panel(+1.0)


def _add_door_panel(bm, width, length, wall_t, door_w, door_h, door_thick, door_offset_x):
    hx = width * 0.5
    hy = length * 0.5
    door_w = min(door_w, width - 2 * wall_t - 0.2)
    cx = _clamp(door_offset_x, -hx + wall_t + door_w * 0.5 + 0.05,
                hx - wall_t - door_w * 0.5 - 0.05)
    dx0 = cx - door_w * 0.5
    dx1 = cx + door_w * 0.5
    y0 = -hy - max(0.004, door_thick)
    y1 = -hy - 0.002
    _add_box(bm, (dx0, y0, 0.02), (dx1, y1, door_h))


def _add_face_box(bm, side, axis0, axis1, z0, z1, width, length, depth):
    hx = width * 0.5
    hy = length * 0.5
    d = max(0.004, depth)
    if side == 'front':
        _add_box(bm, (axis0, -hy - d, z0), (axis1, -hy - 0.002, z1))
    elif side == 'back':
        _add_box(bm, (axis0, hy + 0.002, z0), (axis1, hy + d, z1))
    elif side == 'left':
        _add_box(bm, (-hx - d, axis0, z0), (-hx - 0.002, axis1, z1))
    else:
        _add_box(bm, (hx + 0.002, axis0, z0), (hx + d, axis1, z1))


def _add_door_panel_from_spec(bm, spec, width, length, floor_h):
    base_z = floor_h * (spec['floor'] - 1)
    z0 = base_z + 0.02
    z1 = base_z + spec['height']
    side = spec['side']
    depth = spec['thickness']
    _add_face_box(bm, side, spec['axis0'], spec['axis1'], z0, z1, width, length, depth)

    if spec.get('glass', False):
        glass_w = (spec['axis1'] - spec['axis0']) * 0.42
        glass_h = spec['height'] * 0.28
        ga0 = (spec['axis0'] + spec['axis1']) * 0.5 - glass_w * 0.5
        ga1 = ga0 + glass_w
        gz0 = base_z + spec['height'] * 0.55
        _add_face_box(bm, side, ga0, ga1, gz0, gz0 + glass_h, width, length, depth + 0.010)

    if spec.get('handle', True):
        handle_z = base_z + min(spec['height'] * 0.55, 1.15)
        handle_a = spec['axis1'] - (spec['axis1'] - spec['axis0']) * 0.18
        size = 0.055
        _add_face_box(bm, side, handle_a - size * 0.5, handle_a + size * 0.5,
                      handle_z - size * 0.5, handle_z + size * 0.5,
                      width, length, depth + 0.025)


def _add_window_detail(bm, side, axis0, axis1, z0, z1, width, length, frame_w, frame_d, sill_d):
    if axis1 <= axis0 or z1 <= z0:
        return
    fw = min(max(0.015, frame_w), max(0.02, (axis1 - axis0) * 0.35))
    fd = max(0.004, frame_d)
    sd = max(0.0, sill_d)
    _add_face_box(bm, side, axis0 - fw, axis1 + fw, z1, z1 + fw, width, length, fd)
    _add_face_box(bm, side, axis0 - fw, axis1 + fw, z0 - fw, z0, width, length, fd)
    _add_face_box(bm, side, axis0 - fw, axis0, z0 - fw, z1 + fw, width, length, fd)
    _add_face_box(bm, side, axis1, axis1 + fw, z0 - fw, z1 + fw, width, length, fd)
    glass_margin = fw * 0.55
    _add_face_box(bm, side, axis0 + glass_margin, axis1 - glass_margin,
                  z0 + glass_margin, z1 - glass_margin, width, length, fd * 0.45)
    if sd > 0.0:
        _add_face_box(bm, side, axis0 - fw * 1.4, axis1 + fw * 1.4,
                      z0 - fw * 1.8, z0 - fw * 0.8, width, length, sd)


def _add_balcony(bm, params, width, length, floor_h, floor_count):
    if not params.get('balcony_enabled', False):
        return
    hx = width * 0.5
    hy = length * 0.5

    for b in _balcony_specs(params, width, length, floor_h, floor_count):
        side = b['side']
        a0, a1 = b['axis0'], b['axis1']
        depth = b['depth']
        thick = b['thickness']
        rail_h = b['rail_height']
        rail_t = b['rail_thickness']
        z0 = b['base_z'] - thick
        z1 = b['base_z']

        if side == 'front':
            _add_box(bm, (a0, -hy - depth, z0), (a1, -hy, z1))
            _add_box(bm, (a0, -hy - depth, z1), (a1, -hy - depth + rail_t, z1 + rail_h))
            _add_box(bm, (a0, -hy - depth, z1), (a0 + rail_t, -hy, z1 + rail_h))
            _add_box(bm, (a1 - rail_t, -hy - depth, z1), (a1, -hy, z1 + rail_h))
        elif side == 'back':
            _add_box(bm, (a0, hy, z0), (a1, hy + depth, z1))
            _add_box(bm, (a0, hy + depth - rail_t, z1), (a1, hy + depth, z1 + rail_h))
            _add_box(bm, (a0, hy, z1), (a0 + rail_t, hy + depth, z1 + rail_h))
            _add_box(bm, (a1 - rail_t, hy, z1), (a1, hy + depth, z1 + rail_h))
        elif side == 'left':
            _add_box(bm, (-hx - depth, a0, z0), (-hx, a1, z1))
            _add_box(bm, (-hx - depth, a0, z1), (-hx - depth + rail_t, a1, z1 + rail_h))
            _add_box(bm, (-hx - depth, a0, z1), (-hx, a0 + rail_t, z1 + rail_h))
            _add_box(bm, (-hx - depth, a1 - rail_t, z1), (-hx, a1, z1 + rail_h))
        else:
            _add_box(bm, (hx, a0, z0), (hx + depth, a1, z1))
            _add_box(bm, (hx + depth - rail_t, a0, z1), (hx + depth, a1, z1 + rail_h))
            _add_box(bm, (hx, a0, z1), (hx + depth, a0 + rail_t, z1 + rail_h))
            _add_box(bm, (hx, a1 - rail_t, z1), (hx + depth, a1, z1 + rail_h))


def _add_chimney(bm, params, wall_h, roof_h):
    if not params.get('chimney_enabled', False):
        return
    width = max(1.0, float(params.get('width', 4.0)))
    length = max(1.0, float(params.get('length', 5.0)))
    cw = max(0.12, float(params.get('chimney_width', 0.35)))
    cd = max(0.12, float(params.get('chimney_depth', 0.35)))
    ch = max(0.20, float(params.get('chimney_height', 0.90)))
    cx = max(-width * 0.45, min(width * 0.45, float(params.get('chimney_x', 1.00))))
    cy = max(-length * 0.45, min(length * 0.45, float(params.get('chimney_y', 0.80))))
    zoff = float(params.get('chimney_z_offset', 0.0))
    z0 = max(0.0, wall_h + roof_h * 0.55 + zoff)
    z1 = max(z0 + 0.05, wall_h + roof_h + ch + zoff)
    _add_box(bm, (cx - cw * 0.5, cy - cd * 0.5, z0),
                 (cx + cw * 0.5, cy + cd * 0.5, z1))
    if params.get('chimney_cap_enabled', False):
        cap_over = max(0.0, float(params.get('chimney_cap_overhang', 0.12)))
        cap_h = max(0.03, float(params.get('chimney_cap_height', 0.08)))
        _add_box(bm,
                 (cx - cw * 0.5 - cap_over, cy - cd * 0.5 - cap_over, z1),
                 (cx + cw * 0.5 + cap_over, cy + cd * 0.5 + cap_over, z1 + cap_h))


def build_cabin(params):
    bm = bmesh.new()
    width = max(1.0, float(params.get('width', 4.0)))
    length = max(1.0, float(params.get('length', 5.0)))
    floor_count = max(1, min(3, int(params.get('floor_count', 1))))
    floor_h = max(1.0, float(params.get('wall_height', 2.4)))
    wall_h = floor_h * floor_count
    wall_t = max(0.03, float(params.get('wall_thickness', 0.12)))
    roof_h = max(0.15, float(params.get('roof_height', 0.9)))
    over = max(0.0, float(params.get('roof_overhang', 0.25)))
    floor_t = max(0.02, float(params.get('floor_thickness', 0.12)))
    roof_cover = bool(params.get('roof_cover_enabled', False))
    roof_cover_over = max(0.0, float(params.get('roof_cover_overhang', 0.10)))
    roof_cover_t = max(0.01, float(params.get('roof_cover_thickness', 0.04)))
    window_frames = bool(params.get('window_frames_enabled', False))
    window_frame_w = max(0.015, float(params.get('window_frame_width', 0.06)))
    window_frame_d = max(0.004, float(params.get('window_frame_depth', 0.035)))
    window_sill_d = max(0.0, float(params.get('window_sill_depth', 0.08)))

    hx = width * 0.5
    hy = length * 0.5

    # floor / foundation
    _add_box(bm, (-hx, -hy, -floor_t), (hx, hy, 0.0))
    for fi in range(1, floor_count):
        z = floor_h * fi
        _add_box(bm, (-hx, -hy, z - floor_t * 0.5), (hx, hy, z + floor_t * 0.5))

    # Walls with configurable window and door openings on every side/floor.
    door_specs = _door_specs(params, width, length, wall_t, floor_h, floor_count)

    y_start = -hy + wall_t
    y_end = hy - wall_t
    for fi in range(floor_count):
        floor_idx = fi + 1
        base_z = floor_h * fi
        top_z = base_z + floor_h

        front_holes = _window_holes_for_wall(params, 'front', floor_idx, -hx, hx, floor_h)
        front_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                           for d in door_specs if d['side'] == 'front' and d['floor'] == floor_idx)
        _add_wall_with_holes(lambda mn, mx: _add_box(bm, mn, mx),
                             'Y', -hy, -hy + wall_t, -hx, hx, base_z, top_z, front_holes)
        if window_frames:
            for a0, a1, z0, z1 in _window_holes_for_wall(params, 'front', floor_idx, -hx, hx, floor_h):
                _add_window_detail(bm, 'front', a0, a1, base_z + z0, base_z + z1,
                                   width, length, window_frame_w, window_frame_d, window_sill_d)

        back_holes = _window_holes_for_wall(params, 'back', floor_idx, -hx, hx, floor_h)
        back_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                          for d in door_specs if d['side'] == 'back' and d['floor'] == floor_idx)
        _add_wall_with_holes(lambda mn, mx: _add_box(bm, mn, mx),
                             'Y', hy - wall_t, hy, -hx, hx, base_z, top_z, back_holes)
        if window_frames:
            for a0, a1, z0, z1 in _window_holes_for_wall(params, 'back', floor_idx, -hx, hx, floor_h):
                _add_window_detail(bm, 'back', a0, a1, base_z + z0, base_z + z1,
                                   width, length, window_frame_w, window_frame_d, window_sill_d)

        left_holes = _window_holes_for_wall(params, 'left', floor_idx, y_start, y_end, floor_h)
        left_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                          for d in door_specs if d['side'] == 'left' and d['floor'] == floor_idx)
        _add_wall_with_holes(lambda mn, mx: _add_box(bm, mn, mx),
                             'X', -hx, -hx + wall_t, y_start, y_end, base_z, top_z, left_holes)
        if window_frames:
            for a0, a1, z0, z1 in _window_holes_for_wall(params, 'left', floor_idx, y_start, y_end, floor_h):
                _add_window_detail(bm, 'left', a0, a1, base_z + z0, base_z + z1,
                                   width, length, window_frame_w, window_frame_d, window_sill_d)

        right_holes = _window_holes_for_wall(params, 'right', floor_idx, y_start, y_end, floor_h)
        right_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                           for d in door_specs if d['side'] == 'right' and d['floor'] == floor_idx)
        _add_wall_with_holes(lambda mn, mx: _add_box(bm, mn, mx),
                             'X', hx - wall_t, hx, y_start, y_end, base_z, top_z, right_holes)
        if window_frames:
            for a0, a1, z0, z1 in _window_holes_for_wall(params, 'right', floor_idx, y_start, y_end, floor_h):
                _add_window_detail(bm, 'right', a0, a1, base_z + z0, base_z + z1,
                                   width, length, window_frame_w, window_frame_d, window_sill_d)

    _add_gable_roof(bm, width, length, wall_h, roof_h, over)
    if roof_cover:
        _add_roof_cover(bm, width, length, wall_h, roof_h, over, roof_cover_over, roof_cover_t)
    _add_balcony(bm, params, width, length, floor_h, floor_count)

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)

    for spec in door_specs:
        if spec.get('panel', True):
            _add_door_panel_from_spec(bm, spec, width, length, floor_h)
    _add_chimney(bm, params, wall_h, roof_h)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm, wall_h + roof_h


def _count_scene_cabins():
    return sum(1 for o in bpy.data.objects if o.type == 'MESH' and o.get('dgm_cabin') is True and o.users_scene)


def _is_active_cabin(obj):
    return obj is not None and obj.type == 'MESH' and obj.get('dgm_cabin') is True


def _params_from_obj(obj):
    return dict(
        width=obj.get('dgm_p_width', 4.0),
        length=obj.get('dgm_p_length', 5.0),
        wall_height=obj.get('dgm_p_wall_height', 2.4),
        floor_count=obj.get('dgm_p_floor_count', 1),
        wall_thickness=obj.get('dgm_p_wall_thickness', 0.12),
        roof_height=obj.get('dgm_p_roof_height', 0.9),
        roof_overhang=obj.get('dgm_p_roof_overhang', 0.25),
        floor_thickness=obj.get('dgm_p_floor_thickness', 0.12),
        door_count=obj.get('dgm_p_door_count', 1),
        door_side=obj.get('dgm_p_door_side', 'front'),
        door_floor=obj.get('dgm_p_door_floor', 1),
        door_width=obj.get('dgm_p_door_width', 0.9),
        door_height=obj.get('dgm_p_door_height', 2.0),
        door_offset_x=obj.get('dgm_p_door_offset_x', 0.0),
        window_count=obj.get('dgm_p_window_count', 2),
        window_width=obj.get('dgm_p_window_width', 0.75),
        window_height=obj.get('dgm_p_window_height', 0.75),
        window_sill=obj.get('dgm_p_window_sill', 0.95),
        window_offset_y=obj.get('dgm_p_window_offset_y', 0.0),
        window_count_1=obj.get('dgm_p_window_count_1', obj.get('dgm_p_window_count', 2)),
        window_width_1=obj.get('dgm_p_window_width_1', obj.get('dgm_p_window_width', 0.75)),
        window_height_1=obj.get('dgm_p_window_height_1', obj.get('dgm_p_window_height', 0.75)),
        window_sill_1=obj.get('dgm_p_window_sill_1', obj.get('dgm_p_window_sill', 0.95)),
        window_offset_y_1=obj.get('dgm_p_window_offset_y_1', obj.get('dgm_p_window_offset_y', 0.0)),
        window_count_2=obj.get('dgm_p_window_count_2', obj.get('dgm_p_window_count', 2)),
        window_width_2=obj.get('dgm_p_window_width_2', obj.get('dgm_p_window_width', 0.75)),
        window_height_2=obj.get('dgm_p_window_height_2', obj.get('dgm_p_window_height', 0.75)),
        window_sill_2=obj.get('dgm_p_window_sill_2', obj.get('dgm_p_window_sill', 0.95)),
        window_offset_y_2=obj.get('dgm_p_window_offset_y_2', obj.get('dgm_p_window_offset_y', 0.0)),
        window_count_3=obj.get('dgm_p_window_count_3', obj.get('dgm_p_window_count', 2)),
        window_width_3=obj.get('dgm_p_window_width_3', obj.get('dgm_p_window_width', 0.75)),
        window_height_3=obj.get('dgm_p_window_height_3', obj.get('dgm_p_window_height', 0.75)),
        window_sill_3=obj.get('dgm_p_window_sill_3', obj.get('dgm_p_window_sill', 0.95)),
        window_offset_y_3=obj.get('dgm_p_window_offset_y_3', obj.get('dgm_p_window_offset_y', 0.0)),
        door_panel=obj.get('dgm_p_door_panel', True),
        door_thickness=obj.get('dgm_p_door_thickness', 0.06),
        door_glass=obj.get('dgm_p_door_glass', False),
        door_handle=obj.get('dgm_p_door_handle', True),
        window_frames_enabled=obj.get('dgm_p_window_frames_enabled', False),
        window_frame_width=obj.get('dgm_p_window_frame_width', 0.06),
        window_frame_depth=obj.get('dgm_p_window_frame_depth', 0.035),
        window_sill_depth=obj.get('dgm_p_window_sill_depth', 0.08),
        balcony_enabled=obj.get('dgm_p_balcony_enabled', False),
        balcony_count=obj.get('dgm_p_balcony_count', 1),
        balcony_floor=obj.get('dgm_p_balcony_floor', 2),
        balcony_side=obj.get('dgm_p_balcony_side', 'front'),
        balcony_width=obj.get('dgm_p_balcony_width', 1.8),
        balcony_depth=obj.get('dgm_p_balcony_depth', 0.9),
        balcony_offset=obj.get('dgm_p_balcony_offset', 0.0),
        balcony_thickness=obj.get('dgm_p_balcony_thickness', 0.10),
        balcony_rail_height=obj.get('dgm_p_balcony_rail_height', 0.9),
        balcony_rail_thickness=obj.get('dgm_p_balcony_rail_thickness', 0.07),
        roof_cover_enabled=obj.get('dgm_p_roof_cover_enabled', False),
        roof_cover_overhang=obj.get('dgm_p_roof_cover_overhang', 0.10),
        roof_cover_thickness=obj.get('dgm_p_roof_cover_thickness', 0.04),
        chimney_enabled=obj.get('dgm_p_chimney_enabled', False),
        chimney_width=obj.get('dgm_p_chimney_width', 0.35),
        chimney_depth=obj.get('dgm_p_chimney_depth', 0.35),
        chimney_height=obj.get('dgm_p_chimney_height', 0.90),
        chimney_x=obj.get('dgm_p_chimney_x', 1.00),
        chimney_y=obj.get('dgm_p_chimney_y', 0.80),
        chimney_z_offset=obj.get('dgm_p_chimney_z_offset', 0.0),
        chimney_cap_enabled=obj.get('dgm_p_chimney_cap_enabled', False),
        chimney_cap_overhang=obj.get('dgm_p_chimney_cap_overhang', 0.12),
        chimney_cap_height=obj.get('dgm_p_chimney_cap_height', 0.08),
        **_door_params_from_obj(obj),
        **_balcony_params_from_obj(obj),
        **_window_side_params_from_obj(obj),
    )


def _add_component_from_local_verts(bm, verts):
    base_idx = len(bm.verts)
    new_verts = [bm.verts.new(v) for v in verts]
    return base_idx, new_verts


def _local_box_verts(min_xyz, max_xyz):
    x0, y0, z0 = min_xyz
    x1, y1, z1 = max_xyz
    return [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ], geometry.BOX_FACES


def _local_gable_roof_verts(width, length, wall_h, roof_h, overhang):
    hw = width * 0.5 + overhang
    hl = length * 0.5 + overhang
    z0 = wall_h
    zr = wall_h + roof_h
    verts = [
        (-hw, -hl, z0), (0.0, -hl, zr), (hw, -hl, z0),
        (-hw,  hl, z0), (0.0,  hl, zr), (hw,  hl, z0),
    ]
    faces = ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3))
    return verts, faces


def _cabin_collision_specs(params):
    width = max(1.0, float(params.get('width', 4.0)))
    length = max(1.0, float(params.get('length', 5.0)))
    floor_count = max(1, min(3, int(params.get('floor_count', 1))))
    floor_h = max(1.0, float(params.get('wall_height', 2.4)))
    wall_h = floor_h * floor_count
    wall_t = max(0.03, float(params.get('wall_thickness', 0.12)))
    roof_h = max(0.15, float(params.get('roof_height', 0.9)))
    over = max(0.0, float(params.get('roof_overhang', 0.25)))
    floor_t = max(0.02, float(params.get('floor_thickness', 0.12)))
    hx = width * 0.5
    hy = length * 0.5
    specs = []

    def add_box(min_xyz, max_xyz):
        x0, y0, z0 = min_xyz
        x1, y1, z1 = max_xyz
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            return
        specs.append(_local_box_verts(min_xyz, max_xyz))

    add_box((-hx, -hy, -floor_t), (hx, hy, 0.0))
    for fi in range(1, floor_count):
        z = floor_h * fi
        add_box((-hx, -hy, z - floor_t * 0.5), (hx, hy, z + floor_t * 0.5))

    door_specs = _door_specs(params, width, length, wall_t, floor_h, floor_count)
    for d in door_specs:
        if d.get('panel', True):
            base_z = floor_h * (d['floor'] - 1)
            if d['side'] == 'front':
                add_box((d['axis0'], -hy - d['thickness'], base_z + 0.02),
                        (d['axis1'], -hy, base_z + d['height']))
            elif d['side'] == 'back':
                add_box((d['axis0'], hy, base_z + 0.02),
                        (d['axis1'], hy + d['thickness'], base_z + d['height']))
            elif d['side'] == 'left':
                add_box((-hx - d['thickness'], d['axis0'], base_z + 0.02),
                        (-hx, d['axis1'], base_z + d['height']))
            else:
                add_box((hx, d['axis0'], base_z + 0.02),
                        (hx + d['thickness'], d['axis1'], base_z + d['height']))

    y_start = -hy + wall_t
    y_end = hy - wall_t
    for fi in range(floor_count):
        floor_idx = fi + 1
        base_z = floor_h * fi
        top_z = base_z + floor_h
        front_holes = _window_holes_for_wall(params, 'front', floor_idx, -hx, hx, floor_h)
        front_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                           for d in door_specs if d['side'] == 'front' and d['floor'] == floor_idx)
        _add_wall_with_holes(add_box, 'Y', -hy, -hy + wall_t, -hx, hx, base_z, top_z, front_holes)
        back_holes = _window_holes_for_wall(params, 'back', floor_idx, -hx, hx, floor_h)
        back_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                          for d in door_specs if d['side'] == 'back' and d['floor'] == floor_idx)
        _add_wall_with_holes(add_box, 'Y', hy - wall_t, hy, -hx, hx, base_z, top_z, back_holes)
        left_holes = _window_holes_for_wall(params, 'left', floor_idx, y_start, y_end, floor_h)
        left_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                          for d in door_specs if d['side'] == 'left' and d['floor'] == floor_idx)
        _add_wall_with_holes(add_box, 'X', -hx, -hx + wall_t, y_start, y_end, base_z, top_z, left_holes)
        right_holes = _window_holes_for_wall(params, 'right', floor_idx, y_start, y_end, floor_h)
        right_holes.extend((d['axis0'], d['axis1'], 0.0, d['height'])
                           for d in door_specs if d['side'] == 'right' and d['floor'] == floor_idx)
        _add_wall_with_holes(add_box, 'X', hx - wall_t, hx, y_start, y_end, base_z, top_z, right_holes)
    specs.append(_local_gable_roof_verts(width, length, wall_h, roof_h, over))

    for b in (_balcony_specs(params, width, length, floor_h, floor_count)
              if params.get('balcony_enabled', False) else []):
        side = b['side']
        a0, a1 = b['axis0'], b['axis1']
        depth = b['depth']
        thick = b['thickness']
        rail_h = b['rail_height']
        rail_t = b['rail_thickness']
        z0 = b['base_z'] - thick
        z1 = b['base_z']
        if side == 'front':
            add_box((a0, -hy - depth, z0), (a1, -hy, z1))
            add_box((a0, -hy - depth, z1), (a1, -hy - depth + rail_t, z1 + rail_h))
        elif side == 'back':
            add_box((a0, hy, z0), (a1, hy + depth, z1))
            add_box((a0, hy + depth - rail_t, z1), (a1, hy + depth, z1 + rail_h))
        elif side == 'left':
            add_box((-hx - depth, a0, z0), (-hx, a1, z1))
            add_box((-hx - depth, a0, z1), (-hx - depth + rail_t, a1, z1 + rail_h))
        else:
            add_box((hx, a0, z0), (hx + depth, a1, z1))
            add_box((hx + depth - rail_t, a0, z1), (hx + depth, a1, z1 + rail_h))

    if params.get('chimney_enabled', False):
        cw = max(0.12, float(params.get('chimney_width', 0.35)))
        cd = max(0.12, float(params.get('chimney_depth', 0.35)))
        ch = max(0.20, float(params.get('chimney_height', 0.90)))
        cx = max(-width * 0.45, min(width * 0.45, float(params.get('chimney_x', 1.00))))
        cy = max(-length * 0.45, min(length * 0.45, float(params.get('chimney_y', 0.80))))
        zoff = float(params.get('chimney_z_offset', 0.0))
        z0 = max(0.0, wall_h + roof_h * 0.55 + zoff)
        z1 = max(z0 + 0.05, wall_h + roof_h + ch + zoff)
        add_box((cx - cw * 0.5, cy - cd * 0.5, z0),
                (cx + cw * 0.5, cy + cd * 0.5, z1))
        if params.get('chimney_cap_enabled', False):
            cap_over = max(0.0, float(params.get('chimney_cap_overhang', 0.12)))
            cap_h = max(0.03, float(params.get('chimney_cap_height', 0.08)))
            add_box((cx - cw * 0.5 - cap_over, cy - cd * 0.5 - cap_over, z1),
                    (cx + cw * 0.5 + cap_over, cy + cd * 0.5 + cap_over, z1 + cap_h))

    return specs


def _remove_old_cabin_collision(geo, cabin_name):
    import json
    raw = geo.get('dgm_cabin_col_map', '{}')
    try:
        col_map = json.loads(raw)
    except Exception:
        col_map = {}
    old_comps = col_map.get(cabin_name, [])
    if not old_comps:
        return col_map

    old_names = set(old_comps)
    keep_names = {vg.name for vg in geo.vertex_groups} - old_names
    remove_verts = set()
    for v in geo.data.vertices:
        names = {geo.vertex_groups[g.group].name for g in v.groups}
        if names & old_names and not names & keep_names:
            remove_verts.add(v.index)
    for name in old_comps:
        vg = geo.vertex_groups.get(name)
        if vg:
            geo.vertex_groups.remove(vg)
    if remove_verts:
        bm = bmesh.new()
        bm.from_mesh(geo.data)
        bm.verts.ensure_lookup_table()
        del_v = [bm.verts[i] for i in remove_verts if i < len(bm.verts)]
        bmesh.ops.delete(bm, geom=del_v, context='VERTS')
        bm.to_mesh(geo.data)
        bm.free()
        geo.data.update()
    col_map.pop(cabin_name, None)
    return col_map


def create_cabin_collision(cabin_obj, mass=250.0):
    import json
    params = _params_from_obj(cabin_obj)
    specs = _cabin_collision_specs(params)
    if not specs:
        return None, 0

    geo = geometry._get_or_create_geometry_object()
    col_map = _remove_old_cabin_collision(geo, cabin_obj.name)

    bm = bmesh.new()
    bm.from_mesh(geo.data)
    bm.verts.ensure_lookup_table()

    existing_names = {vg.name for vg in geo.vertex_groups}
    comp_names = []
    idx = 1
    for _ in specs:
        while "Component{:02d}".format(idx) in existing_names or "Component{:02d}".format(idx) in comp_names:
            idx += 1
        comp_names.append("Component{:02d}".format(idx))

    mw = cabin_obj.matrix_world
    vert_ranges = []
    for comp_name, (verts, faces) in zip(comp_names, specs):
        base_idx = len(bm.verts)
        new_verts = [bm.verts.new(mw @ mathutils.Vector(v)) for v in verts]
        for face in faces:
            try:
                bm.faces.new([new_verts[i] for i in face])
            except ValueError:
                pass
        vert_ranges.append((comp_name, base_idx, base_idx + len(new_verts)))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(geo.data)
    bm.free()
    geo.data.update()

    total_verts = len(geo.data.vertices)
    for comp_name, start, end in vert_ranges:
        indices = list(range(start, min(end, total_verts)))
        vg = geo.vertex_groups.new(name=comp_name)
        vg.add(indices, 1.0, 'REPLACE')

    geometry.add_fhq_weights(geo, weight=mass / max(len(geo.data.vertices), 1))
    geometry.set_dgm_props(geo, geometry.LOD_VALUES["Geometry"], mass=mass)

    col_map[cabin_obj.name] = comp_names
    geo['dgm_cabin_col_map'] = json.dumps(col_map)
    return geo, len(comp_names)


class DGM_OT_add_cabin(bpy.types.Operator):
    bl_idname = "dgm.add_cabin"
    bl_label = "Add Cabin"
    bl_description = "Create a simple procedural low-poly cabin shell"
    bl_options = {'REGISTER', 'UNDO'}

    width: bpy.props.FloatProperty(name="Width", default=4.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    length: bpy.props.FloatProperty(name="Length", default=5.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    wall_height: bpy.props.FloatProperty(name="Wall Height", default=2.4, min=1.0, max=10.0, step=1, unit='LENGTH')
    floor_count: bpy.props.IntProperty(name="Floors", default=1, min=1, max=3)
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.12, min=0.03, max=1.0, step=0.1, unit='LENGTH')
    roof_height: bpy.props.FloatProperty(name="Roof Height", default=0.9, min=0.15, max=5.0, step=1, unit='LENGTH')
    roof_overhang: bpy.props.FloatProperty(name="Roof Overhang", default=0.25, min=0.0, max=2.0, step=1, unit='LENGTH')
    roof_cover_enabled: bpy.props.BoolProperty(name="Roof Covering", default=False, description="Add separate sloped roof covering panels")
    roof_cover_overhang: bpy.props.FloatProperty(name="Cover Overhang", default=0.10, min=0.0, max=1.0, step=1, unit='LENGTH')
    roof_cover_thickness: bpy.props.FloatProperty(name="Cover Thickness", default=0.04, min=0.01, max=0.25, step=0.1, unit='LENGTH')
    floor_thickness: bpy.props.FloatProperty(name="Floor Thickness", default=0.12, min=0.02, max=1.0, step=0.1, unit='LENGTH')
    door_count: bpy.props.IntProperty(name="Door Openings", default=1, min=0, max=4)
    door_side: bpy.props.EnumProperty(name="Door Side", items=[('front', "Front", ""), ('back', "Back", ""), ('left', "Left", ""), ('right', "Right", "")], default='front')
    door_floor: bpy.props.IntProperty(name="Door Floor", default=1, min=1, max=3)
    door_width: bpy.props.FloatProperty(name="Door Width", default=0.9, min=0.3, max=3.0, step=1, unit='LENGTH')
    door_height: bpy.props.FloatProperty(name="Door Height", default=2.0, min=0.6, max=5.0, step=1, unit='LENGTH')
    door_offset_x: bpy.props.FloatProperty(name="Door Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    door_panel: bpy.props.BoolProperty(name="Generate Door", default=True, description="Add a simple closed door panel into the doorway")
    door_thickness: bpy.props.FloatProperty(name="Door Thickness", default=0.06, min=0.02, max=0.30, step=0.1, unit='LENGTH')
    door_glass: bpy.props.BoolProperty(name="Door Glass", default=False)
    door_handle: bpy.props.BoolProperty(name="Door Handle", default=True)
    show_floor_windows_1: bpy.props.BoolProperty(name="Floor 1 Windows", default=False)
    show_floor_windows_2: bpy.props.BoolProperty(name="Floor 2 Windows", default=False)
    show_floor_windows_3: bpy.props.BoolProperty(name="Floor 3 Windows", default=False)
    window_frames_enabled: bpy.props.BoolProperty(name="Window Frames", default=False, description="Add frame, glass and sill geometry to generated windows")
    window_frame_width: bpy.props.FloatProperty(name="Frame Width", default=0.06, min=0.015, max=0.25, step=1, unit='LENGTH')
    window_frame_depth: bpy.props.FloatProperty(name="Frame Depth", default=0.035, min=0.004, max=0.20, step=1, unit='LENGTH')
    window_sill_depth: bpy.props.FloatProperty(name="Sill Depth", default=0.08, min=0.0, max=0.35, step=1, unit='LENGTH')
    balcony_enabled: bpy.props.BoolProperty(name="Balcony", default=False)
    balcony_count: bpy.props.IntProperty(name="Balconies", default=1, min=1, max=8)
    balcony_floor: bpy.props.IntProperty(name="Balcony Floor", default=2, min=2, max=3)
    balcony_side: bpy.props.EnumProperty(name="Balcony Side", items=[('front', "Front", ""), ('back', "Back", ""), ('left', "Left", ""), ('right', "Right", "")], default='front')
    balcony_width: bpy.props.FloatProperty(name="Balcony Width", default=1.8, min=0.5, max=8.0, step=1, unit='LENGTH')
    balcony_depth: bpy.props.FloatProperty(name="Balcony Depth", default=0.9, min=0.3, max=4.0, step=1, unit='LENGTH')
    balcony_offset: bpy.props.FloatProperty(name="Balcony Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    balcony_thickness: bpy.props.FloatProperty(name="Balcony Thickness", default=0.10, min=0.04, max=0.40, step=0.1, unit='LENGTH')
    balcony_rail_height: bpy.props.FloatProperty(name="Rail Height", default=0.9, min=0.4, max=1.6, step=1, unit='LENGTH')
    balcony_rail_thickness: bpy.props.FloatProperty(name="Rail Thickness", default=0.07, min=0.025, max=0.20, step=1, unit='LENGTH')
    window_count: bpy.props.IntProperty(name="Windows per Side", default=2, min=0, max=6)
    window_width: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_1: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_1: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_1: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_1: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_1: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_2: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_2: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_2: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_2: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_2: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_3: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_3: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_3: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_3: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_3: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_enabled: bpy.props.BoolProperty(name="Chimney", default=False, description="Add a simple rectangular chimney")
    chimney_width: bpy.props.FloatProperty(name="Chimney Width", default=0.35, min=0.12, max=1.50, step=1, unit='LENGTH')
    chimney_depth: bpy.props.FloatProperty(name="Chimney Depth", default=0.35, min=0.12, max=1.50, step=1, unit='LENGTH')
    chimney_height: bpy.props.FloatProperty(name="Chimney Height", default=0.90, min=0.20, max=4.00, step=1, unit='LENGTH')
    chimney_x: bpy.props.FloatProperty(name="Chimney X", default=1.00, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_y: bpy.props.FloatProperty(name="Chimney Y", default=0.80, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_z_offset: bpy.props.FloatProperty(name="Chimney Z Offset", default=0.0, min=-10.0, max=10.0, step=1, unit='LENGTH')
    chimney_cap_enabled: bpy.props.BoolProperty(name="Chimney Cap", default=False, description="Add a simple cap slab on top of the chimney")
    chimney_cap_overhang: bpy.props.FloatProperty(name="Cap Overhang", default=0.12, min=0.0, max=1.0, step=1, unit='LENGTH')
    chimney_cap_height: bpy.props.FloatProperty(name="Cap Height", default=0.08, min=0.03, max=0.50, step=1, unit='LENGTH')

    _created_obj_name = ""

    def _get_params(self):
        return dict(
            width=self.width, length=self.length, wall_height=self.wall_height,
            floor_count=self.floor_count, wall_thickness=self.wall_thickness, roof_height=self.roof_height,
            roof_overhang=self.roof_overhang, roof_cover_enabled=self.roof_cover_enabled,
            roof_cover_overhang=self.roof_cover_overhang, roof_cover_thickness=self.roof_cover_thickness,
            floor_thickness=self.floor_thickness,
            door_count=self.door_count, door_side=self.door_side, door_floor=self.door_floor,
            door_width=self.door_width, door_height=self.door_height,
            door_offset_x=self.door_offset_x, door_panel=self.door_panel, door_thickness=self.door_thickness,
            door_glass=self.door_glass, door_handle=self.door_handle,
            **_door_params_from_op(self),
            window_frames_enabled=self.window_frames_enabled,
            window_frame_width=self.window_frame_width,
            window_frame_depth=self.window_frame_depth,
            window_sill_depth=self.window_sill_depth,
            balcony_enabled=self.balcony_enabled,
            balcony_count=max(1, self.balcony_count) if self.balcony_enabled else self.balcony_count,
            balcony_floor=self.balcony_floor,
            balcony_side=self.balcony_side, balcony_width=self.balcony_width,
            balcony_depth=self.balcony_depth, balcony_offset=self.balcony_offset,
            balcony_thickness=self.balcony_thickness,
            balcony_rail_height=self.balcony_rail_height,
            balcony_rail_thickness=self.balcony_rail_thickness,
            **_balcony_params_from_op(self),
            window_count=self.window_count, window_width=self.window_width,
            window_height=self.window_height, window_sill=self.window_sill,
            window_offset_y=self.window_offset_y,
            window_count_1=self.window_count_1, window_width_1=self.window_width_1,
            window_height_1=self.window_height_1, window_sill_1=self.window_sill_1,
            window_offset_y_1=self.window_offset_y_1,
            window_count_2=self.window_count_2, window_width_2=self.window_width_2,
            window_height_2=self.window_height_2, window_sill_2=self.window_sill_2,
            window_offset_y_2=self.window_offset_y_2,
            window_count_3=self.window_count_3, window_width_3=self.window_width_3,
            window_height_3=self.window_height_3, window_sill_3=self.window_sill_3,
            window_offset_y_3=self.window_offset_y_3,
            **_window_side_params_from_op(self),
            chimney_enabled=self.chimney_enabled, chimney_width=self.chimney_width,
            chimney_depth=self.chimney_depth, chimney_height=self.chimney_height,
            chimney_x=self.chimney_x, chimney_y=self.chimney_y,
            chimney_z_offset=self.chimney_z_offset,
            chimney_cap_enabled=self.chimney_cap_enabled,
            chimney_cap_overhang=self.chimney_cap_overhang,
            chimney_cap_height=self.chimney_cap_height,
        )

    def _create_object(self, context):
        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass
        name = "DZ_Cabin_{}".format(_count_scene_cabins() + 1)
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj['dgm_cabin'] = True
        obj['dgm_cabin_type'] = 1
        self._created_obj_name = name
        return obj

    def _rebuild(self, context):
        obj = context.active_object
        if not _is_active_cabin(obj):
            return
        bm, h = build_cabin(self._get_params())
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        obj['dgm_cabin_height'] = round(h, 4)

    def _commit(self, context):
        obj = context.active_object
        if not _is_active_cabin(obj):
            return
        p = self._get_params()
        for k, v in p.items():
            obj['dgm_p_' + k] = v
        obj['dgm_cabin_confirmed'] = True

    def invoke(self, context, event):
        self._create_object(context)
        self._rebuild(context)
        return context.window_manager.invoke_props_dialog(self, width=420)

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
        if not _is_active_cabin(context.active_object):
            self._create_object(context)
        self._rebuild(context)
        self._commit(context)
        self.report({'INFO'}, "Cabin created")
        return {'FINISHED'}


class DGM_OT_edit_cabin(bpy.types.Operator):
    bl_idname = "dgm.edit_cabin"
    bl_label = "Edit Cabin"
    bl_description = "Edit selected procedural cabin"
    bl_options = {'REGISTER', 'UNDO'}

    width: bpy.props.FloatProperty(name="Width", default=4.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    length: bpy.props.FloatProperty(name="Length", default=5.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    wall_height: bpy.props.FloatProperty(name="Wall Height", default=2.4, min=1.0, max=10.0, step=1, unit='LENGTH')
    floor_count: bpy.props.IntProperty(name="Floors", default=1, min=1, max=3)
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.12, min=0.03, max=1.0, step=0.1, unit='LENGTH')
    roof_height: bpy.props.FloatProperty(name="Roof Height", default=0.9, min=0.15, max=5.0, step=1, unit='LENGTH')
    roof_overhang: bpy.props.FloatProperty(name="Roof Overhang", default=0.25, min=0.0, max=2.0, step=1, unit='LENGTH')
    roof_cover_enabled: bpy.props.BoolProperty(name="Roof Covering", default=False, description="Add separate sloped roof covering panels")
    roof_cover_overhang: bpy.props.FloatProperty(name="Cover Overhang", default=0.10, min=0.0, max=1.0, step=1, unit='LENGTH')
    roof_cover_thickness: bpy.props.FloatProperty(name="Cover Thickness", default=0.04, min=0.01, max=0.25, step=0.1, unit='LENGTH')
    floor_thickness: bpy.props.FloatProperty(name="Floor Thickness", default=0.12, min=0.02, max=1.0, step=0.1, unit='LENGTH')
    door_count: bpy.props.IntProperty(name="Door Openings", default=1, min=0, max=4)
    door_side: bpy.props.EnumProperty(name="Door Side", items=[('front', "Front", ""), ('back', "Back", ""), ('left', "Left", ""), ('right', "Right", "")], default='front')
    door_floor: bpy.props.IntProperty(name="Door Floor", default=1, min=1, max=3)
    door_width: bpy.props.FloatProperty(name="Door Width", default=0.9, min=0.3, max=3.0, step=1, unit='LENGTH')
    door_height: bpy.props.FloatProperty(name="Door Height", default=2.0, min=0.6, max=5.0, step=1, unit='LENGTH')
    door_offset_x: bpy.props.FloatProperty(name="Door Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    door_panel: bpy.props.BoolProperty(name="Generate Door", default=True, description="Add a simple closed door panel into the doorway")
    door_thickness: bpy.props.FloatProperty(name="Door Thickness", default=0.06, min=0.02, max=0.30, step=0.1, unit='LENGTH')
    door_glass: bpy.props.BoolProperty(name="Door Glass", default=False)
    door_handle: bpy.props.BoolProperty(name="Door Handle", default=True)
    show_floor_windows_1: bpy.props.BoolProperty(name="Floor 1 Windows", default=False)
    show_floor_windows_2: bpy.props.BoolProperty(name="Floor 2 Windows", default=False)
    show_floor_windows_3: bpy.props.BoolProperty(name="Floor 3 Windows", default=False)
    window_frames_enabled: bpy.props.BoolProperty(name="Window Frames", default=False, description="Add frame, glass and sill geometry to generated windows")
    window_frame_width: bpy.props.FloatProperty(name="Frame Width", default=0.06, min=0.015, max=0.25, step=1, unit='LENGTH')
    window_frame_depth: bpy.props.FloatProperty(name="Frame Depth", default=0.035, min=0.004, max=0.20, step=1, unit='LENGTH')
    window_sill_depth: bpy.props.FloatProperty(name="Sill Depth", default=0.08, min=0.0, max=0.35, step=1, unit='LENGTH')
    balcony_enabled: bpy.props.BoolProperty(name="Balcony", default=False)
    balcony_count: bpy.props.IntProperty(name="Balconies", default=1, min=1, max=8)
    balcony_floor: bpy.props.IntProperty(name="Balcony Floor", default=2, min=2, max=3)
    balcony_side: bpy.props.EnumProperty(name="Balcony Side", items=[('front', "Front", ""), ('back', "Back", ""), ('left', "Left", ""), ('right', "Right", "")], default='front')
    balcony_width: bpy.props.FloatProperty(name="Balcony Width", default=1.8, min=0.5, max=8.0, step=1, unit='LENGTH')
    balcony_depth: bpy.props.FloatProperty(name="Balcony Depth", default=0.9, min=0.3, max=4.0, step=1, unit='LENGTH')
    balcony_offset: bpy.props.FloatProperty(name="Balcony Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    balcony_thickness: bpy.props.FloatProperty(name="Balcony Thickness", default=0.10, min=0.04, max=0.40, step=0.1, unit='LENGTH')
    balcony_rail_height: bpy.props.FloatProperty(name="Rail Height", default=0.9, min=0.4, max=1.6, step=1, unit='LENGTH')
    balcony_rail_thickness: bpy.props.FloatProperty(name="Rail Thickness", default=0.07, min=0.025, max=0.20, step=1, unit='LENGTH')
    window_count: bpy.props.IntProperty(name="Windows per Side", default=2, min=0, max=6)
    window_width: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_1: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_1: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_1: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_1: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_1: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_2: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_2: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_2: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_2: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_2: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    window_count_3: bpy.props.IntProperty(name="Windows", default=2, min=0, max=6)
    window_width_3: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height_3: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill_3: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
    window_offset_y_3: bpy.props.FloatProperty(name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_enabled: bpy.props.BoolProperty(name="Chimney", default=False, description="Add a simple rectangular chimney")
    chimney_width: bpy.props.FloatProperty(name="Chimney Width", default=0.35, min=0.12, max=1.50, step=1, unit='LENGTH')
    chimney_depth: bpy.props.FloatProperty(name="Chimney Depth", default=0.35, min=0.12, max=1.50, step=1, unit='LENGTH')
    chimney_height: bpy.props.FloatProperty(name="Chimney Height", default=0.90, min=0.20, max=4.00, step=1, unit='LENGTH')
    chimney_x: bpy.props.FloatProperty(name="Chimney X", default=1.00, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_y: bpy.props.FloatProperty(name="Chimney Y", default=0.80, min=-15.0, max=15.0, step=1, unit='LENGTH')
    chimney_z_offset: bpy.props.FloatProperty(name="Chimney Z Offset", default=0.0, min=-10.0, max=10.0, step=1, unit='LENGTH')
    chimney_cap_enabled: bpy.props.BoolProperty(name="Chimney Cap", default=False, description="Add a simple cap slab on top of the chimney")
    chimney_cap_overhang: bpy.props.FloatProperty(name="Cap Overhang", default=0.12, min=0.0, max=1.0, step=1, unit='LENGTH')
    chimney_cap_height: bpy.props.FloatProperty(name="Cap Height", default=0.08, min=0.03, max=0.50, step=1, unit='LENGTH')

    _snapshot_mesh = None

    @classmethod
    def poll(cls, context):
        return _is_active_cabin(context.active_object)

    def _get_params(self):
        return dict(
            width=self.width, length=self.length, wall_height=self.wall_height,
            floor_count=self.floor_count, wall_thickness=self.wall_thickness, roof_height=self.roof_height,
            roof_overhang=self.roof_overhang, roof_cover_enabled=self.roof_cover_enabled,
            roof_cover_overhang=self.roof_cover_overhang, roof_cover_thickness=self.roof_cover_thickness,
            floor_thickness=self.floor_thickness,
            door_count=self.door_count, door_side=self.door_side, door_floor=self.door_floor,
            door_width=self.door_width, door_height=self.door_height,
            door_offset_x=self.door_offset_x, door_panel=self.door_panel, door_thickness=self.door_thickness,
            door_glass=self.door_glass, door_handle=self.door_handle,
            **_door_params_from_op(self),
            window_frames_enabled=self.window_frames_enabled,
            window_frame_width=self.window_frame_width,
            window_frame_depth=self.window_frame_depth,
            window_sill_depth=self.window_sill_depth,
            balcony_enabled=self.balcony_enabled,
            balcony_count=max(1, self.balcony_count) if self.balcony_enabled else self.balcony_count,
            balcony_floor=self.balcony_floor,
            balcony_side=self.balcony_side, balcony_width=self.balcony_width,
            balcony_depth=self.balcony_depth, balcony_offset=self.balcony_offset,
            balcony_thickness=self.balcony_thickness,
            balcony_rail_height=self.balcony_rail_height,
            balcony_rail_thickness=self.balcony_rail_thickness,
            **_balcony_params_from_op(self),
            window_count=self.window_count, window_width=self.window_width,
            window_height=self.window_height, window_sill=self.window_sill,
            window_offset_y=self.window_offset_y,
            window_count_1=self.window_count_1, window_width_1=self.window_width_1,
            window_height_1=self.window_height_1, window_sill_1=self.window_sill_1,
            window_offset_y_1=self.window_offset_y_1,
            window_count_2=self.window_count_2, window_width_2=self.window_width_2,
            window_height_2=self.window_height_2, window_sill_2=self.window_sill_2,
            window_offset_y_2=self.window_offset_y_2,
            window_count_3=self.window_count_3, window_width_3=self.window_width_3,
            window_height_3=self.window_height_3, window_sill_3=self.window_sill_3,
            window_offset_y_3=self.window_offset_y_3,
            **_window_side_params_from_op(self),
            chimney_enabled=self.chimney_enabled, chimney_width=self.chimney_width,
            chimney_depth=self.chimney_depth, chimney_height=self.chimney_height,
            chimney_x=self.chimney_x, chimney_y=self.chimney_y,
            chimney_z_offset=self.chimney_z_offset,
            chimney_cap_enabled=self.chimney_cap_enabled,
            chimney_cap_overhang=self.chimney_cap_overhang,
            chimney_cap_height=self.chimney_cap_height,
        )

    def _rebuild(self, context):
        obj = context.active_object
        if not _is_active_cabin(obj):
            return
        bm, h = build_cabin(self._get_params())
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        obj['dgm_cabin_height'] = round(h, 4)

    def invoke(self, context, event):
        obj = context.active_object
        p = _params_from_obj(obj)
        for k, v in p.items():
            setattr(self, k, v)
        snap = bmesh.new()
        snap.from_mesh(obj.data)
        self._snapshot_mesh = snap
        return context.window_manager.invoke_props_dialog(self, width=420)

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
        obj = context.active_object
        for k, v in self._get_params().items():
            obj['dgm_p_' + k] = v
        if self._snapshot_mesh:
            self._snapshot_mesh.free()
            self._snapshot_mesh = None
        return {'FINISHED'}


class DGM_OT_restore_cabin(bpy.types.Operator):
    bl_idname = "dgm.restore_cabin"
    bl_label = "Restore Cabin"
    bl_description = "Restore selected cabin mesh from stored parameters"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_active_cabin(context.active_object)

    def execute(self, context):
        obj = context.active_object
        p = _params_from_obj(obj)
        saved_loc = obj.location.copy()
        saved_rot = obj.rotation_euler.copy()
        obj.scale = (1.0, 1.0, 1.0)
        bm, h = build_cabin(p)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        obj.location = saved_loc
        obj.rotation_euler = saved_rot
        obj['dgm_cabin_height'] = round(h, 4)
        self.report({'INFO'}, "Cabin restored")
        return {'FINISHED'}


class DGM_OT_cabin_collision(bpy.types.Operator):
    bl_idname = "dgm.cabin_collision"
    bl_label = "Generate Cabin Collision"
    bl_description = "Generate detailed Geometry LOD collision components from the selected cabin parameters"
    bl_options = {'REGISTER', 'UNDO'}

    mass: bpy.props.FloatProperty(
        name="Mass (kg)",
        description="Total Geometry LOD mass assigned to the generated cabin collision",
        default=250.0, min=10.0, max=5000.0)

    @classmethod
    def poll(cls, context):
        return _is_active_cabin(context.active_object)

    def draw(self, context):
        col = self.layout.column(align=True)
        col.prop(self, 'mass')
        col.label(text="Creates convex components for floor, walls, roof, door and chimney.", icon='INFO')
        col.label(text="Existing collision for this cabin is replaced.", icon='FILE_REFRESH')

    def execute(self, context):
        obj = context.active_object
        geo, count = create_cabin_collision(obj, self.mass)
        if geo and count:
            self.report({'INFO'}, "Cabin collision created: {} components".format(count))
            return {'FINISHED'}
        self.report({'WARNING'}, "No cabin collision components created")
        return {'CANCELLED'}


def _draw_props(layout, op):
    box = layout.box()
    box.label(text="Simple Cabin", icon='HOME')
    col = box.column(align=True)
    col.prop(op, 'width')
    col.prop(op, 'length')
    col.prop(op, 'floor_count')
    col.prop(op, 'wall_height', text="Floor Height")
    col.prop(op, 'wall_thickness')
    col.separator()
    col.prop(op, 'roof_height')
    col.prop(op, 'roof_overhang')
    col.prop(op, 'roof_cover_enabled')
    if op.roof_cover_enabled:
        col.prop(op, 'roof_cover_overhang')
        col.prop(op, 'roof_cover_thickness')
    col.prop(op, 'floor_thickness')

    box = layout.box()
    box.label(text="Openings", icon='MOD_BUILD')
    col = box.column(align=True)
    col.prop(op, 'door_count')
    for idx in range(1, min(4, int(op.door_count)) + 1):
        suffix = "" if idx == 1 else "_{}".format(idx)
        dbox = box.box()
        dbox.label(text="Door Opening {}".format(idx), icon='MOD_BUILD')
        dcol = dbox.column(align=True)
        for prop in ('door_side', 'door_floor', 'door_width', 'door_height', 'door_offset_x', 'door_panel'):
            name = prop + suffix
            if hasattr(op, name):
                dcol.prop(op, name)
        panel_name = 'door_panel' + suffix
        if hasattr(op, panel_name) and getattr(op, panel_name):
            for prop in ('door_thickness', 'door_glass', 'door_handle'):
                name = prop + suffix
                if hasattr(op, name):
                    dcol.prop(op, name)
    col.separator()

    def draw_floor_windows(fbox, floor_idx, side):
        title = "Floor {} {} Windows".format(floor_idx, side.title())
        fbox.label(text=title.strip(), icon='MOD_BUILD')
        fcol = fbox.column(align=True)
        if side == 'left':
            names = (
                'window_count_{}'.format(floor_idx),
                'window_width_{}'.format(floor_idx),
                'window_height_{}'.format(floor_idx),
                'window_sill_{}'.format(floor_idx),
                'window_offset_y_{}'.format(floor_idx),
            )
        else:
            names = (
                'window_count_{}_{}'.format(side, floor_idx),
                'window_width_{}_{}'.format(side, floor_idx),
                'window_height_{}_{}'.format(side, floor_idx),
                'window_sill_{}_{}'.format(side, floor_idx),
                'window_offset_y_{}_{}'.format(side, floor_idx),
            )
        for name in names:
            if hasattr(op, name):
                fcol.prop(op, name)

    for floor_idx in range(1, int(op.floor_count) + 1):
        floor_box = box.box()
        show_prop = 'show_floor_windows_{}'.format(floor_idx)
        row = floor_box.row(align=True)
        show = bool(getattr(op, show_prop, False))
        row.prop(op, show_prop, text="", icon='TRIA_DOWN' if show else 'TRIA_RIGHT', emboss=False)
        row.label(text="Floor {} Windows".format(floor_idx), icon='MOD_BUILD')
        if show:
            for side in ('front', 'back', 'left', 'right'):
                fbox = floor_box.box()
                draw_floor_windows(fbox, floor_idx, side)

    frame_box = box.box()
    frame_box.label(text="Window Generated Geometry", icon='MOD_SOLIDIFY')
    fcol = frame_box.column(align=True)
    fcol.prop(op, 'window_frames_enabled')
    if op.window_frames_enabled:
        fcol.prop(op, 'window_frame_width')
        fcol.prop(op, 'window_frame_depth')
        fcol.prop(op, 'window_sill_depth')

    box = layout.box()
    box.label(text="Balcony", icon='MESH_CUBE')
    col = box.column(align=True)
    col.prop(op, 'balcony_enabled')
    if op.balcony_enabled:
        col.prop(op, 'balcony_count')
        for idx in range(1, min(8, int(op.balcony_count)) + 1):
            suffix = "" if idx == 1 else "_{}".format(idx)
            bbox = box.box()
            bbox.label(text="Balcony {}".format(idx), icon='MESH_CUBE')
            bcol = bbox.column(align=True)
            for prop in ('balcony_floor', 'balcony_side', 'balcony_width', 'balcony_depth',
                         'balcony_offset', 'balcony_thickness', 'balcony_rail_height',
                         'balcony_rail_thickness'):
                name = prop + suffix
                if hasattr(op, name):
                    bcol.prop(op, name)

    box = layout.box()
    box.label(text="Chimney", icon='MOD_BUILD')
    col = box.column(align=True)
    col.prop(op, 'chimney_enabled')
    if op.chimney_enabled:
        col.prop(op, 'chimney_width')
        col.prop(op, 'chimney_depth')
        col.prop(op, 'chimney_height')
        col.separator()
        col.prop(op, 'chimney_x')
        col.prop(op, 'chimney_y')
        col.prop(op, 'chimney_z_offset')
        col.separator()
        col.prop(op, 'chimney_cap_enabled')
        if op.chimney_cap_enabled:
            col.prop(op, 'chimney_cap_overhang')
            col.prop(op, 'chimney_cap_height')

    info = layout.box()
    info.label(text="Total height: {:.3f} m".format(op.wall_height * op.floor_count + op.roof_height), icon='INFO')
    info.label(text="Footprint: {:.2f} x {:.2f} m".format(op.width, op.length))


def draw_cabin_generator_section(layout, context):
    obj = context.active_object
    is_cabin = _is_active_cabin(obj)

    box = layout.box()
    count_row = box.row(align=True)
    count_row.label(text="Cabins in scene: {}".format(_count_scene_cabins()), icon='INFO')

    add_row = box.row(align=True)
    add_row.scale_y = 1.3
    add_row.operator_context = 'INVOKE_DEFAULT'
    add_row.operator("dgm.add_cabin", text="Add Cabin", icon='ADD')

    if is_cabin:
        box.separator(factor=0.5)
        box.label(text="{} | {} m".format(obj.name, obj.get('dgm_cabin_height', '?')), icon='CHECKMARK')
        box.operator("dgm.edit_cabin", text="Edit Selected Cabin", icon='PREFERENCES')
        box.operator("dgm.cabin_collision", text="Generate Cabin Collision", icon='MESH_CUBE')
        box.operator("dgm.restore_cabin", text="Restore Cabin", icon='FILE_REFRESH')


def _install_side_window_props(cls):
    cls.__annotations__ = dict(getattr(cls, '__annotations__', {}))
    for side in ('front', 'back', 'right'):
        for floor_idx in (1, 2, 3):
            title = side.title()
            cls.__annotations__['window_count_{}_{}'.format(side, floor_idx)] = bpy.props.IntProperty(
                name="{} Windows".format(title), default=0 if side == 'front' else 2, min=0, max=6)
            cls.__annotations__['window_width_{}_{}'.format(side, floor_idx)] = bpy.props.FloatProperty(
                name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
            cls.__annotations__['window_height_{}_{}'.format(side, floor_idx)] = bpy.props.FloatProperty(
                name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
            cls.__annotations__['window_sill_{}_{}'.format(side, floor_idx)] = bpy.props.FloatProperty(
                name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')
            cls.__annotations__['window_offset_y_{}_{}'.format(side, floor_idx)] = bpy.props.FloatProperty(
                name="Window Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')


def _install_extra_door_props(cls):
    cls.__annotations__ = dict(getattr(cls, '__annotations__', {}))
    side_items = [('front', "Front", ""), ('back', "Back", ""),
                  ('left', "Left", ""), ('right', "Right", "")]
    for idx in range(2, 5):
        suffix = "_{}".format(idx)
        cls.__annotations__['door_side' + suffix] = bpy.props.EnumProperty(
            name="Door Side", items=side_items, default='front')
        cls.__annotations__['door_floor' + suffix] = bpy.props.IntProperty(
            name="Door Floor", default=1, min=1, max=3)
        cls.__annotations__['door_width' + suffix] = bpy.props.FloatProperty(
            name="Door Width", default=0.9, min=0.3, max=3.0, step=1, unit='LENGTH')
        cls.__annotations__['door_height' + suffix] = bpy.props.FloatProperty(
            name="Door Height", default=2.0, min=0.6, max=5.0, step=1, unit='LENGTH')
        cls.__annotations__['door_offset_x' + suffix] = bpy.props.FloatProperty(
            name="Door Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
        cls.__annotations__['door_panel' + suffix] = bpy.props.BoolProperty(
            name="Generate Door", default=False)
        cls.__annotations__['door_thickness' + suffix] = bpy.props.FloatProperty(
            name="Door Thickness", default=0.06, min=0.02, max=0.30, step=0.1, unit='LENGTH')
        cls.__annotations__['door_glass' + suffix] = bpy.props.BoolProperty(
            name="Door Glass", default=False)
        cls.__annotations__['door_handle' + suffix] = bpy.props.BoolProperty(
            name="Door Handle", default=True)


def _install_extra_balcony_props(cls):
    cls.__annotations__ = dict(getattr(cls, '__annotations__', {}))
    side_items = [('front', "Front", ""), ('back', "Back", ""),
                  ('left', "Left", ""), ('right', "Right", "")]
    for idx in range(2, 9):
        suffix = "_{}".format(idx)
        cls.__annotations__['balcony_floor' + suffix] = bpy.props.IntProperty(
            name="Balcony Floor", default=2, min=2, max=3)
        cls.__annotations__['balcony_side' + suffix] = bpy.props.EnumProperty(
            name="Balcony Side", items=side_items, default='front')
        cls.__annotations__['balcony_width' + suffix] = bpy.props.FloatProperty(
            name="Balcony Width", default=1.8, min=0.5, max=8.0, step=1, unit='LENGTH')
        cls.__annotations__['balcony_depth' + suffix] = bpy.props.FloatProperty(
            name="Balcony Depth", default=0.9, min=0.3, max=4.0, step=1, unit='LENGTH')
        cls.__annotations__['balcony_offset' + suffix] = bpy.props.FloatProperty(
            name="Balcony Offset", default=0.0, min=-15.0, max=15.0, step=1, unit='LENGTH')
        cls.__annotations__['balcony_thickness' + suffix] = bpy.props.FloatProperty(
            name="Balcony Thickness", default=0.10, min=0.04, max=0.40, step=0.1, unit='LENGTH')
        cls.__annotations__['balcony_rail_height' + suffix] = bpy.props.FloatProperty(
            name="Rail Height", default=0.9, min=0.4, max=1.6, step=1, unit='LENGTH')
        cls.__annotations__['balcony_rail_thickness' + suffix] = bpy.props.FloatProperty(
            name="Rail Thickness", default=0.07, min=0.025, max=0.20, step=1, unit='LENGTH')


_install_extra_door_props(DGM_OT_add_cabin)
_install_extra_door_props(DGM_OT_edit_cabin)
_install_extra_balcony_props(DGM_OT_add_cabin)
_install_extra_balcony_props(DGM_OT_edit_cabin)
_install_side_window_props(DGM_OT_add_cabin)
_install_side_window_props(DGM_OT_edit_cabin)


cabin_classes = (
    DGM_OT_add_cabin,
    DGM_OT_edit_cabin,
    DGM_OT_restore_cabin,
    DGM_OT_cabin_collision,
)


def register():
    for cls in cabin_classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(cabin_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
