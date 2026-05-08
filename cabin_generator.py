"""
DayZ Geometry Maker - Cabin Generator
Procedural low-poly cabin shell with gable roof, door and windows.
"""

import bpy
import bmesh


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


def build_cabin(params):
    bm = bmesh.new()
    width = max(1.0, float(params.get('width', 4.0)))
    length = max(1.0, float(params.get('length', 5.0)))
    wall_h = max(1.0, float(params.get('wall_height', 2.4)))
    wall_t = max(0.03, float(params.get('wall_thickness', 0.12)))
    roof_h = max(0.15, float(params.get('roof_height', 0.9)))
    over = max(0.0, float(params.get('roof_overhang', 0.25)))
    floor_t = max(0.02, float(params.get('floor_thickness', 0.12)))
    door_w = max(0.3, float(params.get('door_width', 0.9)))
    door_h = max(0.6, min(float(params.get('door_height', 2.0)), wall_h - 0.05))
    windows = max(0, min(6, int(params.get('window_count', 2))))
    win_w = max(0.25, float(params.get('window_width', 0.75)))
    win_h = max(0.25, float(params.get('window_height', 0.75)))
    sill = max(0.2, float(params.get('window_sill', 0.95)))

    hx = width * 0.5
    hy = length * 0.5

    # floor / foundation
    _add_box(bm, (-hx, -hy, -floor_t), (hx, hy, 0.0))

    # back wall solid
    _add_box(bm, (-hx, hy - wall_t, 0.0), (hx, hy, wall_h))

    # front wall with centered door opening
    door_w = min(door_w, width - 2 * wall_t - 0.2)
    dx0 = -door_w * 0.5
    dx1 = door_w * 0.5
    _add_box(bm, (-hx, -hy, 0.0), (dx0, -hy + wall_t, wall_h))
    _add_box(bm, (dx1, -hy, 0.0), (hx, -hy + wall_t, wall_h))
    _add_box(bm, (dx0, -hy, door_h), (dx1, -hy + wall_t, wall_h))

    # side walls with simple repeated window holes
    def side_wall(left=True):
        x0, x1 = (-hx, -hx + wall_t) if left else (hx - wall_t, hx)
        y_start = -hy + wall_t
        y_end = hy - wall_t
        if windows <= 0:
            _add_box(bm, (x0, y_start, 0.0), (x1, y_end, wall_h))
            return
        usable = y_end - y_start
        ww = min(win_w, usable / max(1, windows) * 0.65)
        wh = min(win_h, max(0.25, wall_h - sill - 0.25))
        z0 = sill
        z1 = sill + wh
        gap = usable / (windows + 1)
        cursor = y_start
        for i in range(windows):
            cy = y_start + gap * (i + 1)
            wy0 = cy - ww * 0.5
            wy1 = cy + ww * 0.5
            _add_box(bm, (x0, cursor, 0.0), (x1, wy0, wall_h))
            _add_box(bm, (x0, wy0, 0.0), (x1, wy1, z0))
            _add_box(bm, (x0, wy0, z1), (x1, wy1, wall_h))
            cursor = wy1
        _add_box(bm, (x0, cursor, 0.0), (x1, y_end, wall_h))

    side_wall(True)
    side_wall(False)

    _add_gable_roof(bm, width, length, wall_h, roof_h, over)

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
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
        wall_thickness=obj.get('dgm_p_wall_thickness', 0.12),
        roof_height=obj.get('dgm_p_roof_height', 0.9),
        roof_overhang=obj.get('dgm_p_roof_overhang', 0.25),
        floor_thickness=obj.get('dgm_p_floor_thickness', 0.12),
        door_width=obj.get('dgm_p_door_width', 0.9),
        door_height=obj.get('dgm_p_door_height', 2.0),
        window_count=obj.get('dgm_p_window_count', 2),
        window_width=obj.get('dgm_p_window_width', 0.75),
        window_height=obj.get('dgm_p_window_height', 0.75),
        window_sill=obj.get('dgm_p_window_sill', 0.95),
    )


class DGM_OT_add_cabin(bpy.types.Operator):
    bl_idname = "dgm.add_cabin"
    bl_label = "Add Cabin"
    bl_description = "Create a simple procedural low-poly cabin shell"
    bl_options = {'REGISTER', 'UNDO'}

    width: bpy.props.FloatProperty(name="Width", default=4.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    length: bpy.props.FloatProperty(name="Length", default=5.0, min=1.0, max=30.0, step=1, unit='LENGTH')
    wall_height: bpy.props.FloatProperty(name="Wall Height", default=2.4, min=1.0, max=10.0, step=1, unit='LENGTH')
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.12, min=0.03, max=1.0, step=0.1, unit='LENGTH')
    roof_height: bpy.props.FloatProperty(name="Roof Height", default=0.9, min=0.15, max=5.0, step=1, unit='LENGTH')
    roof_overhang: bpy.props.FloatProperty(name="Roof Overhang", default=0.25, min=0.0, max=2.0, step=1, unit='LENGTH')
    floor_thickness: bpy.props.FloatProperty(name="Floor Thickness", default=0.12, min=0.02, max=1.0, step=0.1, unit='LENGTH')
    door_width: bpy.props.FloatProperty(name="Door Width", default=0.9, min=0.3, max=3.0, step=1, unit='LENGTH')
    door_height: bpy.props.FloatProperty(name="Door Height", default=2.0, min=0.6, max=5.0, step=1, unit='LENGTH')
    window_count: bpy.props.IntProperty(name="Windows per Side", default=2, min=0, max=6)
    window_width: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')

    _created_obj_name = ""

    def _get_params(self):
        return dict(
            width=self.width, length=self.length, wall_height=self.wall_height,
            wall_thickness=self.wall_thickness, roof_height=self.roof_height,
            roof_overhang=self.roof_overhang, floor_thickness=self.floor_thickness,
            door_width=self.door_width, door_height=self.door_height,
            window_count=self.window_count, window_width=self.window_width,
            window_height=self.window_height, window_sill=self.window_sill,
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
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.12, min=0.03, max=1.0, step=0.1, unit='LENGTH')
    roof_height: bpy.props.FloatProperty(name="Roof Height", default=0.9, min=0.15, max=5.0, step=1, unit='LENGTH')
    roof_overhang: bpy.props.FloatProperty(name="Roof Overhang", default=0.25, min=0.0, max=2.0, step=1, unit='LENGTH')
    floor_thickness: bpy.props.FloatProperty(name="Floor Thickness", default=0.12, min=0.02, max=1.0, step=0.1, unit='LENGTH')
    door_width: bpy.props.FloatProperty(name="Door Width", default=0.9, min=0.3, max=3.0, step=1, unit='LENGTH')
    door_height: bpy.props.FloatProperty(name="Door Height", default=2.0, min=0.6, max=5.0, step=1, unit='LENGTH')
    window_count: bpy.props.IntProperty(name="Windows per Side", default=2, min=0, max=6)
    window_width: bpy.props.FloatProperty(name="Window Width", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_height: bpy.props.FloatProperty(name="Window Height", default=0.75, min=0.25, max=3.0, step=1, unit='LENGTH')
    window_sill: bpy.props.FloatProperty(name="Window Sill", default=0.95, min=0.2, max=3.0, step=1, unit='LENGTH')

    _snapshot_mesh = None

    @classmethod
    def poll(cls, context):
        return _is_active_cabin(context.active_object)

    def _get_params(self):
        return dict(
            width=self.width, length=self.length, wall_height=self.wall_height,
            wall_thickness=self.wall_thickness, roof_height=self.roof_height,
            roof_overhang=self.roof_overhang, floor_thickness=self.floor_thickness,
            door_width=self.door_width, door_height=self.door_height,
            window_count=self.window_count, window_width=self.window_width,
            window_height=self.window_height, window_sill=self.window_sill,
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


def _draw_props(layout, op):
    box = layout.box()
    box.label(text="Simple Cabin", icon='HOME')
    col = box.column(align=True)
    col.prop(op, 'width')
    col.prop(op, 'length')
    col.prop(op, 'wall_height')
    col.prop(op, 'wall_thickness')
    col.separator()
    col.prop(op, 'roof_height')
    col.prop(op, 'roof_overhang')
    col.prop(op, 'floor_thickness')

    box = layout.box()
    box.label(text="Openings", icon='MOD_BUILD')
    col = box.column(align=True)
    col.prop(op, 'door_width')
    col.prop(op, 'door_height')
    col.separator()
    col.prop(op, 'window_count')
    col.prop(op, 'window_width')
    col.prop(op, 'window_height')
    col.prop(op, 'window_sill')

    info = layout.box()
    info.label(text="Total height: {:.3f} m".format(op.wall_height + op.roof_height), icon='INFO')
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
        box.operator("dgm.restore_cabin", text="Restore Cabin", icon='FILE_REFRESH')


cabin_classes = (
    DGM_OT_add_cabin,
    DGM_OT_edit_cabin,
    DGM_OT_restore_cabin,
)


def register():
    for cls in cabin_classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(cabin_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
