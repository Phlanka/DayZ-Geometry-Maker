"""
DayZ Geometry Maker - Operators and Panel
"""

import bpy
import math
import os
from . import geometry, updater, baker_bridge, ladder_generator, cabin_generator


def _recommended_model_cfg_for_template(template):
    return template in {'container_base', 'object_with_doors'}


def _config_template_update(self, context):
    template = getattr(self, "dgm_config_template", "container_base")
    self.dgm_write_model_cfg = _recommended_model_cfg_for_template(template)
    if template == 'none':
        self.dgm_export_config_cpp = False
        self.dgm_write_model_cfg = False
    elif not self.dgm_export_config_cpp:
        self.dgm_export_config_cpp = True


def _default_export_subdir(scene, folder_name):
    raw = getattr(scene, "dgm_p3d_path", "").strip()
    if not raw:
        return ""
    p3d_path = bpy.path.abspath(raw)
    if not p3d_path.lower().endswith(".p3d"):
        p3d_path += ".p3d"
    return os.path.join(os.path.dirname(p3d_path), folder_name)


def _sync_default_export_paths(scene):
    textures = _default_export_subdir(scene, "data")
    scripts = _default_export_subdir(scene, "scripts")
    if textures and not getattr(scene, "dgm_override_textures_path", False):
        scene.dgm_textures_path = textures
    if scripts and not getattr(scene, "dgm_override_scripts_path", False):
        scene.dgm_scripts_path = scripts


def _p3d_path_update(self, context):
    _sync_default_export_paths(self)


def _override_textures_path_update(self, context):
    _sync_default_export_paths(self)


def _override_scripts_path_update(self, context):
    _sync_default_export_paths(self)


def _memory_any_group_exists(point_names):
    return any(geometry.memory_point_exists(name) for name in point_names)


def _ladder_count_point_names(idx):
    prefix = "ladder{}".format(idx)
    return [
        prefix,
        prefix + '_bottom_front',
        prefix + '_con',
        prefix + '_con_dir',
        prefix + '_dir',
        prefix + '_top_front',
    ]


def _lid_count_point_names(idx):
    return ['lid_{}_axis_1'.format(idx), 'lid_{}_axis_2'.format(idx)]


def _building_door_count_point_names(idx):
    return [
        "door{}".format(idx),
        "door{}_action".format(idx),
        "door{}_axis_1".format(idx),
        "door{}_axis_2".format(idx),
    ]


def _highest_existing_memory_index(max_count, names_fn):
    highest = 0
    for idx in range(1, max_count + 1):
        if _memory_any_group_exists(names_fn(idx)):
            highest = idx
    return highest


def _clamp_count_to_existing(scene, prop_name, max_count, names_fn):
    highest = _highest_existing_memory_index(max_count, names_fn)
    if getattr(scene, prop_name, 0) < highest:
        setattr(scene, prop_name, highest)


def _memory_ladders_count_update(self, context):
    _clamp_count_to_existing(self, "dgm_memory_ladders_count", 5, _ladder_count_point_names)


def _memory_lid_count_update(self, context):
    _clamp_count_to_existing(self, "dgm_memory_doors_count", 8, _lid_count_point_names)


def _memory_building_doors_count_update(self, context):
    _clamp_count_to_existing(self, "dgm_memory_building_doors_count", 8, _building_door_count_point_names)


# ---------------------------------------------------------------------------
# Geometry operators
# ---------------------------------------------------------------------------

class DGM_OT_create_geometry(bpy.types.Operator):
    bl_idname = "dgm.create_geometry"
    bl_label = "Create Geometry"
    bl_description = (
        "Adds a box-shaped geometry component around the entire target object. "
        "Use this as a starting point — move and resize the box in the viewport to fit your model. "
        "Click multiple times to add more components for complex shapes"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mass: bpy.props.FloatProperty(
        name="Mass (kg)",
        description="Object mass — minimum 10 for character collision",
        default=100.0,
        min=0.0,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "mass")
        self.layout.label(text="Min 10 for character collision", icon='INFO')

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_geometry(mass=self.mass)
        return {'FINISHED'}



class DGM_OT_create_geometry_from_selection(bpy.types.Operator):
    bl_idname = "dgm.create_geometry_from_selection"
    bl_label = "Geometry from Selection"
    bl_description = (
        "Go into Edit Mode on your target mesh, select the vertices or faces "
        "you want covered, then click this. A convex hull component is built "
        "around exactly those selected verts. Useful for complex shapes like "
        "pillars, arches, or individual parts of a larger mesh"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mass: bpy.props.FloatProperty(
        name="Mass (kg)",
        description="Object mass — minimum 10 for character collision",
        default=100.0,
        min=0.0,
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "mass")
        self.layout.label(text="Select verts in Edit Mode before clicking", icon='INFO')

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        result = geometry.create_geometry_from_selection(self, mass=self.mass)
        return {'FINISHED'} if result else {'CANCELLED'}


class DGM_OT_create_view_geometry(bpy.types.Operator):
    bl_idname = "dgm.create_view_geometry"
    bl_label = "Create View Geometry"
    bl_description = (
        "View Geometry LOD (6e15): defines visibility for AI and players. "
        "If absent, Geometry LOD is used as fallback"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_view_geometry()
        return {'FINISHED'}


class DGM_OT_toggle_section(bpy.types.Operator):
    """Generic toggle for any boolean scene property — drives collapsible sections."""
    bl_idname = "dgm.toggle_section"
    bl_label = "Toggle Section"
    bl_options = {'REGISTER'}

    prop: bpy.props.StringProperty()

    def execute(self, context):
        current = getattr(context.scene, self.prop, False)
        setattr(context.scene, self.prop, not current)
        return {'FINISHED'}


class DGM_OT_create_fire_geometry(bpy.types.Operator):
    bl_idname = "dgm.create_fire_geometry"
    bl_label = "Create Fire Geometry"
    bl_description = (
        "Fire Geometry LOD (7e15): bullet/rocket collision. "
        "Reuses your Geometry component boxes (already convex). "
        "Add Geometry components first for accurate coverage. "
        "Must be < 3500 points total"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.active_object and context.active_object.mode == 'EDIT':
            self.report({'WARNING'}, "Exit Edit mode first")
            return {'CANCELLED'}
        geometry.create_fire_geometry(operator=self)
        return {'FINISHED'}


class DGM_OT_create_shadow_volumes(bpy.types.Operator):
    bl_idname = "dgm.create_shadow_volumes"
    bl_label = "Create Shadow Volumes"
    bl_description = (
        "Shadow Volume LODs (1e4 and 1.001e4): cast shadows. "
        "Wiki: must be closed, triangulated, all edges sharp. "
        "Two created: close-range (detailed) and far (simplified). "
        "Slightly shrunk vs resolution LOD to avoid self-shadowing"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_shadow_volumes()
        self.report({'INFO'}, "Shadow Volume and Shadow Volume 2 created")
        return {'FINISHED'}


class DGM_OT_create_view_pilot(bpy.types.Operator):
    bl_idname = "dgm.create_view_pilot"
    bl_label = "Create View Pilot"
    bl_description = (
        "View Pilot LOD (1.1e3): what the pilot/driver sees of the model. "
        "For Car class vehicles, this is used for ALL positions"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_view_interior("View Pilot")
        return {'FINISHED'}


class DGM_OT_create_view_gunner(bpy.types.Operator):
    bl_idname = "dgm.create_view_gunner"
    bl_label = "Create View Gunner"
    bl_description = "View Gunner LOD (1e3): what the gunner sees of the model"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_view_interior("View Gunner")
        return {'FINISHED'}


class DGM_OT_create_view_cargo(bpy.types.Operator):
    bl_idname = "dgm.create_view_cargo"
    bl_label = "Create View Cargo"
    bl_description = "View Cargo LOD (1.2e3): what cargo passengers see of the model"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_view_interior("View Cargo")
        return {'FINISHED'}


class DGM_OT_create_land_contact(bpy.types.Operator):
    bl_idname = "dgm.create_land_contact"
    bl_label = "Create Land Contact"
    bl_description = (
        "Land Contact LOD (2e15): single vertices where object touches ground. "
        "Creates 4 contact points at the base corners"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_land_contact()
        return {'FINISHED'}


class DGM_OT_create_roadway(bpy.types.Operator):
    bl_idname = "dgm.create_roadway"
    bl_label = "Create Roadway"
    bl_description = (
        "Roadway LOD (3e15): surface units can stand on. "
        "Must not overlap with Geometry LOD. Max ~36m from origin. "
        "Texture defines sound environment"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_roadway()
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Memory operators
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory point — individual add operators
# ---------------------------------------------------------------------------

class DGM_OT_memory_add_bbox(bpy.types.Operator):
    bl_idname = "dgm.memory_add_bbox"
    bl_label = "Bounding Box"
    bl_description = "Add/update boundingbox_min and boundingbox_max points — defines object extents for loot spawning and inventory display"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_bbox()
        return {'FINISHED'}


class DGM_OT_memory_add_invview(bpy.types.Operator):
    bl_idname = "dgm.memory_add_invview"
    bl_label = "Inventory Camera"
    bl_description = "Add/update invview point — camera position for the inventory preview render"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_invview()
        return {'FINISHED'}


class DGM_OT_memory_add_center(bpy.types.Operator):
    bl_idname = "dgm.memory_add_center"
    bl_label = "Center Point"
    bl_description = "Add/update ce_center — center of mass reference point"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_center()
        return {'FINISHED'}


class DGM_OT_memory_add_radius(bpy.types.Operator):
    bl_idname = "dgm.memory_add_radius"
    bl_label = "Radius Point"
    bl_description = "Add/update ce_radius — bounding sphere radius reference"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_radius()
        return {'FINISHED'}


class DGM_OT_memory_add_bullet(bpy.types.Operator):
    bl_idname = "dgm.memory_add_bullet"
    bl_label = "Muzzle Points"
    bl_description = "Add/update konec hlavne (breech) and usti hlavne (muzzle) — bullet travel axis for weapons"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_bullet()
        return {'FINISHED'}


class DGM_OT_memory_add_bolt(bpy.types.Operator):
    bl_idname = "dgm.memory_add_bolt"
    bl_label = "Bolt Axis"
    bl_description = "Add/update bolt_axis — two points defining the bolt travel direction"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_bolt()
        return {'FINISHED'}


class DGM_OT_memory_add_eject(bpy.types.Operator):
    bl_idname = "dgm.memory_add_eject"
    bl_label = "Case Eject"
    bl_description = "Add/update nabojnicestart and nabojniceend — casing ejection path"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_eject()
        return {'FINISHED'}


class DGM_OT_memory_add_eye(bpy.types.Operator):
    bl_idname = "dgm.memory_add_eye"
    bl_label = "Eye / ADS"
    bl_description = "Add/update eye — ADS aiming eye position"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_eye()
        return {'FINISHED'}


class DGM_OT_memory_add_trigger(bpy.types.Operator):
    bl_idname = "dgm.memory_add_trigger"
    bl_label = "Trigger"
    bl_description = "Add/update trigger — trigger position on the weapon"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_trigger()
        return {'FINISHED'}


class DGM_OT_memory_add_magazine(bpy.types.Operator):
    bl_idname = "dgm.memory_add_magazine"
    bl_label = "Magazine"
    bl_description = "Add/update magazine — magazine attachment/detachment point"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        geometry.add_memory_magazine()
        return {'FINISHED'}


class DGM_OT_memory_add_ladder(bpy.types.Operator):
    bl_idname = "dgm.memory_add_ladder"
    bl_label = "Ladder"
    bl_description = "Add Memory LOD + View Geometry — for building ladders (Adjust the positions according to the docs)"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_ladder()
        return {'FINISHED'}


class DGM_OT_memory_add_lights(bpy.types.Operator):
    bl_idname = "dgm.memory_add_lights"
    bl_label = "Light Positions"
    bl_description = "Add/update light_1..N points — positions for dynamic lights or particle effects"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_lights(context.scene.dgm_memory_lights_count)
        return {'FINISHED'}


class DGM_OT_memory_add_damage(bpy.types.Operator):
    bl_idname = "dgm.memory_add_damage"
    bl_label = "Damage Hide"
    bl_description = "Add/update damageHide — point used to hide parts of the model when damaged"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_damage()
        return {'FINISHED'}


class DGM_OT_memory_add_doors(bpy.types.Operator):
    bl_idname = "dgm.memory_add_doors"
    bl_label = "Lid Axis"
    bl_description = "Add/update lid axis points for Container Base lid animation"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.add_memory_doors(context.scene.dgm_memory_doors_count)
        return {'FINISHED'}


class DGM_OT_memory_add_lid_axis_n(bpy.types.Operator):
    bl_idname = "dgm.memory_add_lid_axis_n"
    bl_label = "Add Lid Axis"
    bl_description = "Add one lid axis pair for Container Base lid animation"
    bl_options = {'REGISTER', 'UNDO'}

    lid_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        if self.lid_idx > 1:
            prev_exists = (
                geometry.memory_point_exists('lid_{}_axis_1'.format(self.lid_idx - 1)) and
                geometry.memory_point_exists('lid_{}_axis_2'.format(self.lid_idx - 1))
            )
            if not prev_exists:
                self.report({'ERROR'},
                    "Add Lid axis {} first".format(self.lid_idx - 1))
                return {'CANCELLED'}
        geometry.add_memory_door_axis(self.lid_idx)
        return {'FINISHED'}


class DGM_OT_memory_delete_lid_axis(bpy.types.Operator):
    bl_idname = "dgm.memory_delete_lid_axis"
    bl_label = "Delete Lid Axis"
    bl_description = "Remove this lid axis pair. Higher lid axes must be deleted first"
    bl_options = {'REGISTER', 'UNDO'}

    lid_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        for next_idx in range(self.lid_idx + 1, 9):
            if (geometry.memory_point_exists('lid_{}_axis_1'.format(next_idx)) or
                    geometry.memory_point_exists('lid_{}_axis_2'.format(next_idx))):
                self.report({'ERROR'},
                    "Delete Lid axis {} first".format(next_idx))
                return {'CANCELLED'}
        geometry.remove_memory_door_axis(self.lid_idx)
        scene = context.scene
        if scene.dgm_memory_doors_count > self.lid_idx - 1:
            scene.dgm_memory_doors_count = max(0, self.lid_idx - 1)
        self.report({'INFO'}, "Lid axis {} deleted".format(self.lid_idx))
        return {'FINISHED'}


def _building_door_point_names(door_idx):
    return [
        "door{}".format(door_idx),
        "door{}_action".format(door_idx),
        "door{}_axis_1".format(door_idx),
        "door{}_axis_2".format(door_idx),
    ]


def _target_has_door_selection(target):
    if not target or target.type != 'MESH':
        return False
    for vg in target.vertex_groups:
        if "door" in vg.name.lower() and _vertex_group_has_vertices(target, vg.name):
            return True
    if hasattr(target, 'dgm_props'):
        for sm in target.dgm_props.selection_mats:
            if "door" in sm.vgroup_name.lower() and _vertex_group_has_vertices(target, sm.vgroup_name):
                return True
            if "door" in sm.hidden_selection.lower() and _vertex_group_has_vertices(target, sm.vgroup_name):
                return True
    return False


def _vertex_group_has_vertices(obj, group_name):
    if not obj or obj.type != 'MESH':
        return False
    vg = obj.vertex_groups.get(group_name)
    if not vg:
        return False
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == vg.index and g.weight > 0.0:
                return True
    return False


def _target_has_numbered_door_selection(target, door_idx):
    name = "door{}".format(door_idx)
    return _vertex_group_has_vertices(target, name)


class DGM_OT_memory_add_building_door_n(bpy.types.Operator):
    bl_idname = "dgm.memory_add_building_door_n"
    bl_label = "Add Door Axis"
    bl_description = (
        "Add Memory LOD selections and View Geometry for one DayZ building door. "
        "Before adding, the target object must have a doorN selection with assigned vertices "
        "(for example door1 for Door axis 1)."
    )
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        if not _target_has_door_selection(context.scene.dgm_target_object):
            self.report({'ERROR'},
                "Target object must contain a door selection with assigned vertices")
            return {'CANCELLED'}
        if not _target_has_numbered_door_selection(context.scene.dgm_target_object, self.door_idx):
            self.report({'ERROR'},
                "Target object must contain door{} selection with assigned vertices".format(self.door_idx))
            return {'CANCELLED'}
        if self.door_idx > 1:
            prev_exists = all(
                geometry.memory_point_exists(n)
                for n in _building_door_point_names(self.door_idx - 1)
            )
            if not prev_exists:
                self.report({'ERROR'},
                    "Add Door axis {} first".format(self.door_idx - 1))
                return {'CANCELLED'}
        orientation = getattr(context.scene, "dgm_memory_building_door_{}_orientation".format(self.door_idx), 'Y')
        geometry.add_memory_building_door(self.door_idx, orientation=orientation)
        return {'FINISHED'}


class DGM_OT_memory_delete_building_door(bpy.types.Operator):
    bl_idname = "dgm.memory_delete_building_door"
    bl_label = "Delete Door Axis"
    bl_description = "Remove this building door Memory LOD group. Higher doors must be deleted first"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        for next_idx in range(self.door_idx + 1, 9):
            if any(geometry.memory_point_exists(n) for n in _building_door_point_names(next_idx)):
                self.report({'ERROR'},
                    "Delete Door axis {} first".format(next_idx))
                return {'CANCELLED'}
        geometry.remove_memory_building_door(self.door_idx)
        scene = context.scene
        if scene.dgm_memory_building_doors_count > self.door_idx - 1:
            scene.dgm_memory_building_doors_count = max(0, self.door_idx - 1)
        self.report({'INFO'}, "Door axis {} deleted".format(self.door_idx))
        return {'FINISHED'}


class DGM_OT_memory_rotate_building_door(bpy.types.Operator):
    bl_idname = "dgm.memory_rotate_building_door"
    bl_label = "Rotate Door Axis"
    bl_description = "Switch this door memory between front/back and side orientation; View Geometry is unchanged"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        scene = context.scene
        prop_name = "dgm_memory_building_door_{}_orientation".format(self.door_idx)
        current = getattr(scene, prop_name, 'Y')
        orientation = 'X' if current == 'Y' else 'Y'
        setattr(scene, prop_name, orientation)
        geometry.add_memory_building_door(
            self.door_idx,
            orientation=orientation,
            create_view_geometry=False,
        )
        self.report({'INFO'}, "Door axis {} memory orientation: {}".format(self.door_idx, orientation))
        return {'FINISHED'}


class DGM_OT_set_default_export_subdir(bpy.types.Operator):
    bl_idname = "dgm.set_default_export_subdir"
    bl_label = "Use Default Export Folder"
    bl_description = "Set this path from the selected P3D folder"
    bl_options = {'REGISTER', 'UNDO'}

    target: bpy.props.EnumProperty(
        items=[
            ('textures', "Textures", "Use P3D folder plus data"),
            ('scripts', "Scripts", "Use P3D folder plus scripts"),
        ],
        default='textures',
    )

    def execute(self, context):
        folder_name = 'scripts' if self.target == 'scripts' else 'data'
        path = _default_export_subdir(context.scene, folder_name)
        if not path:
            self.report({'ERROR'}, "Set the P3D path first")
            return {'CANCELLED'}
        if self.target == 'scripts':
            context.scene.dgm_scripts_path = path
        else:
            context.scene.dgm_textures_path = path
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Memory point — move gizmo operator
# ---------------------------------------------------------------------------

class DGM_OT_memory_move_point(bpy.types.Operator):
    """Enter Edit Mode on the Memory object, select the given point group, and activate the Move tool."""
    bl_idname = "dgm.memory_move_point"
    bl_label = "Move Memory Point"
    bl_options = {'REGISTER', 'UNDO'}

    point_name: bpy.props.StringProperty()

    def execute(self, context):
        mem = geometry.get_memory_object()
        if not mem:
            self.report({'ERROR'}, "No Memory LOD found — add a memory point first")
            return {'CANCELLED'}

        vg = mem.vertex_groups.get(self.point_name)
        if not vg:
            self.report({'ERROR'}, "Point '{}' not found in Memory LOD".format(self.point_name))
            return {'CANCELLED'}

        if context.scene.dgm_moving_memory_point == self.point_name:
            if context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')
            context.scene.dgm_moving_memory_point = ""
            context.scene.dgm_moving_memory_ladder = 0
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select", space_type='VIEW_3D')
            except Exception:
                pass
            return {'FINISHED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        mem.select_set(True)
        context.view_layer.objects.active = mem

        for v in mem.data.vertices:
            v.select = False
        for v in mem.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    v.select = True

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')

        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
        except Exception:
            pass

        context.scene.dgm_moving_memory_point = self.point_name
        context.scene.dgm_moving_memory_ladder = 0

        if not bpy.app.timers.is_registered(_poll_memory_move_exit):
            bpy.app.timers.register(_poll_memory_move_exit, first_interval=0.2)

        return {'FINISHED'}


def _ladder_memory_point_names(ladder_idx):
    prefix = "ladder{}".format(ladder_idx)
    return [
        prefix,
        prefix + '_bottom_front',
        prefix + '_con',
        prefix + '_con_dir',
        prefix + '_dir',
        prefix + '_top_front',
    ]


def _ladder_memory_vertex_indices(mem, ladder_idx):
    indices = set()
    for name in _ladder_memory_point_names(ladder_idx):
        vg = mem.vertex_groups.get(name)
        if not vg:
            continue
        for v in mem.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    indices.add(v.index)
    return indices


def _lid_axis_point_names(lid_idx):
    return [
        'lid_{}_axis_1'.format(lid_idx),
        'lid_{}_axis_2'.format(lid_idx),
    ]


def _memory_vertex_indices_for_names(mem, point_names):
    indices = set()
    for name in point_names:
        vg = mem.vertex_groups.get(name)
        if not vg:
            continue
        for v in mem.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    indices.add(v.index)
    return indices


def _ladder_memory_center(mem, ladder_idx):
    import mathutils
    indices = _ladder_memory_vertex_indices(mem, ladder_idx)
    if not indices:
        return None
    center = mathutils.Vector((0.0, 0.0, 0.0))
    for vi in indices:
        center += mem.data.vertices[vi].co
    return center / len(indices)


def _finish_ladder_group_move(context, ladder_idx):
    mem = geometry.get_memory_object()
    if not mem or ladder_idx <= 0:
        return

    old_center = getattr(context.scene, "dgm_moving_memory_ladder_center", None)
    new_center = _ladder_memory_center(mem, ladder_idx)
    if old_center is None or new_center is None:
        return

    import mathutils
    old_center = mathutils.Vector(old_center)
    local_delta = new_center - old_center
    if local_delta.length <= 0.000001:
        return

    world_delta = mem.matrix_world.to_3x3() @ local_delta
    vg_obj = bpy.data.objects.get("View Geometry.ladder{}".format(ladder_idx))
    if vg_obj:
        vg_obj.location += world_delta


class DGM_OT_memory_move_ladder(bpy.types.Operator):
    """Move all memory points of one ladder together and sync its View Geometry."""
    bl_idname = "dgm.memory_move_ladder"
    bl_label = "Move Ladder"
    bl_description = "Move this ladder's memory points together; View Geometry is synced when you finish"
    bl_options = {'REGISTER', 'UNDO'}

    ladder_idx: bpy.props.IntProperty(default=1, min=1, max=5)

    def execute(self, context):
        mem = geometry.get_memory_object()
        if not mem:
            self.report({'ERROR'}, "No Memory LOD found")
            return {'CANCELLED'}

        indices = _ladder_memory_vertex_indices(mem, self.ladder_idx)
        if not indices:
            self.report({'WARNING'}, "No ladder{} points found".format(self.ladder_idx))
            return {'CANCELLED'}

        if getattr(context.scene, "dgm_moving_memory_ladder", 0) == self.ladder_idx:
            if context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')
            _finish_ladder_group_move(context, self.ladder_idx)
            context.scene.dgm_moving_memory_point = ""
            context.scene.dgm_moving_memory_ladder = 0
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select", space_type='VIEW_3D')
            except Exception:
                pass
            return {'FINISHED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        mem.select_set(True)
        context.view_layer.objects.active = mem

        for v in mem.data.vertices:
            v.select = (v.index in indices)

        center = _ladder_memory_center(mem, self.ladder_idx)
        if center is not None:
            context.scene.dgm_moving_memory_ladder_center = tuple(center)

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')

        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
        except Exception:
            pass

        context.scene.dgm_moving_memory_point = ""
        context.scene.dgm_moving_memory_ladder = self.ladder_idx

        if not bpy.app.timers.is_registered(_poll_memory_move_exit):
            bpy.app.timers.register(_poll_memory_move_exit, first_interval=0.2)

        return {'FINISHED'}


class DGM_OT_memory_move_lid_axis(bpy.types.Operator):
    """Move both memory points of one lid axis together."""
    bl_idname = "dgm.memory_move_lid_axis"
    bl_label = "Move Lid Axis"
    bl_description = "Move both points of this lid axis together"
    bl_options = {'REGISTER', 'UNDO'}

    lid_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        mem = geometry.get_memory_object()
        if not mem:
            self.report({'ERROR'}, "No Memory LOD found")
            return {'CANCELLED'}

        indices = _memory_vertex_indices_for_names(mem, _lid_axis_point_names(self.lid_idx))
        if not indices:
            self.report({'WARNING'}, "No Lid axis {} points found".format(self.lid_idx))
            return {'CANCELLED'}

        active_key = "lid_axis_{}".format(self.lid_idx)
        if getattr(context.scene, "dgm_moving_memory_point", "") == active_key:
            if context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')
            context.scene.dgm_moving_memory_point = ""
            context.scene.dgm_moving_memory_ladder = 0
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select", space_type='VIEW_3D')
            except Exception:
                pass
            return {'FINISHED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        mem.select_set(True)
        context.view_layer.objects.active = mem

        for v in mem.data.vertices:
            v.select = (v.index in indices)

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')

        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
        except Exception:
            pass

        context.scene.dgm_moving_memory_point = active_key
        context.scene.dgm_moving_memory_ladder = 0

        if not bpy.app.timers.is_registered(_poll_memory_move_exit):
            bpy.app.timers.register(_poll_memory_move_exit, first_interval=0.2)

        return {'FINISHED'}


class DGM_OT_memory_move_building_door(bpy.types.Operator):
    """Move all Memory LOD points for one building door together."""
    bl_idname = "dgm.memory_move_building_door"
    bl_label = "Move Door Axis"
    bl_description = "Move doorN, doorN_action and doorN_axis together"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty(default=1, min=1, max=8)

    def execute(self, context):
        mem = geometry.get_memory_object()
        if not mem:
            self.report({'ERROR'}, "No Memory LOD found")
            return {'CANCELLED'}

        indices = _memory_vertex_indices_for_names(mem, _building_door_point_names(self.door_idx))
        if not indices:
            self.report({'WARNING'}, "No Door axis {} points found".format(self.door_idx))
            return {'CANCELLED'}

        active_key = "building_door_{}".format(self.door_idx)
        if getattr(context.scene, "dgm_moving_memory_point", "") == active_key:
            if context.mode == 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='OBJECT')
            context.scene.dgm_moving_memory_point = ""
            context.scene.dgm_moving_memory_ladder = 0
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select", space_type='VIEW_3D')
            except Exception:
                pass
            return {'FINISHED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        mem.select_set(True)
        context.view_layer.objects.active = mem

        for v in mem.data.vertices:
            v.select = (v.index in indices)

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='VERT')

        try:
            bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
        except Exception:
            pass

        context.scene.dgm_moving_memory_point = active_key
        context.scene.dgm_moving_memory_ladder = 0

        if not bpy.app.timers.is_registered(_poll_memory_move_exit):
            bpy.app.timers.register(_poll_memory_move_exit, first_interval=0.2)

        return {'FINISHED'}


def _poll_memory_move_exit():
    """Timer: if user left Edit Mode, clear the active move state and restore the tool."""
    try:
        scene = bpy.context.scene
        moving_ladder = getattr(scene, "dgm_moving_memory_ladder", 0)
        if not scene.dgm_moving_memory_point and not moving_ladder:
            return None
        if bpy.context.mode != 'EDIT_MESH':
            if moving_ladder:
                _finish_ladder_group_move(bpy.context, moving_ladder)
            scene.dgm_moving_memory_point = ""
            scene.dgm_moving_memory_ladder = 0
            try:
                bpy.ops.wm.tool_set_by_id(name="builtin.select", space_type='VIEW_3D')
            except Exception:
                pass
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            return None
        return 0.2
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Door rotation setup operators
# ---------------------------------------------------------------------------

_DOOR_PREVIEW_PREFIX = "DGM_DoorPreview_"


def _door_anim_prop_prefix(slot_kind, door_idx):
    if slot_kind == 'building':
        return 'dgm_building_door_{}'.format(door_idx)
    return 'dgm_door_{}'.format(door_idx)


def _get_axis_midpoint_and_vector(door_idx, slot_kind='lid'):
    """Return (midpoint Vector, axis_unit Vector) from the Memory LOD axis verts, or (None, None)."""
    import mathutils
    mem = geometry.get_memory_object()
    if not mem:
        return None, None
    if slot_kind == 'building':
        axis_1 = 'door{}_axis_1'.format(door_idx)
        axis_2 = 'door{}_axis_2'.format(door_idx)
    else:
        axis_1 = 'lid_{}_axis_1'.format(door_idx)
        axis_2 = 'lid_{}_axis_2'.format(door_idx)
    vg1 = mem.vertex_groups.get(axis_1)
    vg2 = mem.vertex_groups.get(axis_2)
    if not vg1 or not vg2:
        return None, None

    def _vert_for_group(vg):
        for v in mem.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    return mem.matrix_world @ v.co
        return None

    p1 = _vert_for_group(vg1)
    p2 = _vert_for_group(vg2)
    if p1 is None or p2 is None:
        return None, None

    mid = (p1 + p2) * 0.5
    axis = (p2 - p1).normalized()
    return mid, axis


def _door_preview_name(door_idx, slot_kind='lid'):
    return "{}{}Door{}".format(_DOOR_PREVIEW_PREFIX, slot_kind.title(), door_idx)


def _remove_door_preview(door_idx, slot_kind='lid'):
    name = _door_preview_name(door_idx, slot_kind)
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)


def _apply_preview_angle(door_idx, scene, angle, slot_kind='lid'):
    """Rotate the preview mesh to the given angle around the hinge axis from the closed position."""
    import mathutils
    prefix = _door_anim_prop_prefix(slot_kind, door_idx)
    preview = bpy.data.objects.get(_door_preview_name(door_idx, slot_kind))
    if not preview:
        return
    orig_flat = scene.get(prefix + '_orig_verts')
    mid_list  = scene.get(prefix + '_axis_mid')
    ax_list   = scene.get(prefix + '_axis_vec')
    if orig_flat is None or mid_list is None or ax_list is None:
        return
    mid  = mathutils.Vector(mid_list)
    axis = mathutils.Vector(ax_list).normalized()
    orig_verts = [mathutils.Vector(orig_flat[i*3:(i+1)*3]) for i in range(len(orig_flat)//3)]
    rot_mat = mathutils.Matrix.Rotation(angle, 4, axis)
    inv_world = preview.matrix_world.inverted()
    for i, v in enumerate(preview.data.vertices):
        world_orig = orig_verts[i]
        rotated = rot_mat @ (world_orig - mid) + mid
        v.co = inv_world @ rotated
    preview.data.update()


def _door_preview_angle_update(self, context):
    """Called when any preview angle slider changes — self is the scene."""
    active_idx = self.dgm_door_pose_active_idx
    if active_idx < 1:
        return
    slot_kind = getattr(self, 'dgm_door_pose_active_kind', 'lid')
    prefix = _door_anim_prop_prefix(slot_kind, active_idx)
    angle = getattr(self, prefix + '_preview_angle', 0.0)
    _apply_preview_angle(active_idx, self, angle, slot_kind)


class DGM_OT_door_add_geometry(bpy.types.Operator):
    bl_idname = "dgm.door_add_geometry"
    bl_label = "Add Lid Geometry"
    bl_description = (
        "Create a Geometry LOD component for each configured Container Base lid, "
        "shaped as a convex hull of the lid vertex group. Existing lid geometry "
        "is replaced. Each component is set to 10kg with the lid's vertex group name"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        created = geometry.create_door_geometry()
        if created == 0:
            self.report({'WARNING'}, "No lid vertex groups configured - set Lid Geometry on each lid first")
            return {'CANCELLED'}
        self.report({'INFO'}, "Created geometry for {} lid(s)".format(created))
        return {'FINISHED'}


class DGM_OT_door_set_pose(bpy.types.Operator):
    """Create the door preview mesh and show the angle slider."""
    bl_idname = "dgm.door_set_pose"
    bl_label = "Preview Lid"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty()
    pose: bpy.props.StringProperty()
    slot_kind: bpy.props.StringProperty(default='lid')

    def execute(self, context):
        import mathutils
        import bmesh

        scene = context.scene
        target = scene.dgm_target_object
        if not target:
            self.report({'ERROR'}, "No target object set")
            return {'CANCELLED'}

        slot_kind = self.slot_kind if self.slot_kind == 'building' else 'lid'
        prefix = _door_anim_prop_prefix(slot_kind, self.door_idx)
        vgroup_prop = prefix + '_vgroup'
        vgroup_name = getattr(scene, vgroup_prop, "")
        if slot_kind == 'building' and not vgroup_name:
            default_vgroup = "door{}".format(self.door_idx)
            if target.vertex_groups.get(default_vgroup):
                vgroup_name = default_vgroup
        if not vgroup_name:
            self.report({'ERROR'}, "Select a vertex group for Door {}".format(self.door_idx))
            return {'CANCELLED'}

        vg = target.vertex_groups.get(vgroup_name)
        if not vg:
            self.report({'ERROR'}, "Vertex group '{}' not found on target".format(vgroup_name))
            return {'CANCELLED'}

        mid, axis = _get_axis_midpoint_and_vector(self.door_idx, slot_kind)
        if mid is None:
            self.report({'ERROR'}, "Door {} axis points not found in Memory LOD".format(self.door_idx))
            return {'CANCELLED'}

        _remove_door_preview(self.door_idx, slot_kind)

        import bmesh as _bmesh
        bm = _bmesh.new()
        bm.from_mesh(target.data)

        group_verts = set()
        for v in target.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    group_verts.add(v.index)

        bm_verts_to_del = [v for v in bm.verts if v.index not in group_verts]
        _bmesh.ops.delete(bm, geom=bm_verts_to_del, context='VERTS')

        new_mesh = bpy.data.meshes.new(_door_preview_name(self.door_idx, slot_kind))
        bm.to_mesh(new_mesh)
        bm.free()

        preview = bpy.data.objects.new(_door_preview_name(self.door_idx, slot_kind), new_mesh)
        preview.matrix_world = target.matrix_world.copy()
        context.collection.objects.link(preview)

        # Store closed-position world verts and axis info for angle application
        world_verts = [target.matrix_world @ v.co for v in target.data.vertices if v.index in group_verts]
        scene[prefix + '_orig_verts'] = [co for v in world_verts for co in v]
        scene[prefix + '_axis_mid'] = list(mid)
        scene[prefix + '_axis_vec'] = list(axis)

        # Seed the slider at the existing open angle so the preview starts there
        existing = getattr(scene, prefix + '_open_angle', 0.0)
        setattr(scene, prefix + '_preview_angle', existing)
        _apply_preview_angle(self.door_idx, scene, existing, slot_kind)

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        scene.dgm_door_pose_active = True
        scene.dgm_door_pose_active_idx = self.door_idx
        scene.dgm_door_pose_active_kind = slot_kind

        return {'FINISHED'}


class DGM_OT_door_record_pose(bpy.types.Operator):
    """Copy the current preview slider angle to closed or open."""
    bl_idname = "dgm.door_record_pose"
    bl_label = "Set Pose Angle"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty()
    pose: bpy.props.StringProperty()
    slot_kind: bpy.props.StringProperty(default='lid')

    def execute(self, context):
        scene = context.scene
        slot_kind = self.slot_kind if self.slot_kind == 'building' else 'lid'
        prefix = _door_anim_prop_prefix(slot_kind, self.door_idx)
        preview_angle = getattr(scene, prefix + '_preview_angle', 0.0)
        prop = '{}_{}_angle'.format(prefix, self.pose)
        setattr(scene, prop, preview_angle)
        self.report({'INFO'}, "{} angle set: {:.4f} rad ({:.1f}°)".format(
            self.pose.title(), preview_angle, math.degrees(preview_angle)))
        return {'FINISHED'}


class DGM_OT_door_finish_pose(bpy.types.Operator):
    """Remove the preview mesh and close the slider."""
    bl_idname = "dgm.door_finish_pose"
    bl_label = "Done"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty()
    slot_kind: bpy.props.StringProperty(default='lid')

    def execute(self, context):
        slot_kind = self.slot_kind if self.slot_kind == 'building' else 'lid'
        _remove_door_preview(self.door_idx, slot_kind)
        context.scene.dgm_door_pose_active = False
        context.scene.dgm_door_pose_active_idx = 0
        context.scene.dgm_door_pose_active_kind = 'lid'
        return {'FINISHED'}


class DGM_OT_door_cancel_pose(bpy.types.Operator):
    """Remove the preview mesh without saving angles."""
    bl_idname = "dgm.door_cancel_pose"
    bl_label = "Cancel"
    bl_options = {'REGISTER', 'UNDO'}

    door_idx: bpy.props.IntProperty()
    slot_kind: bpy.props.StringProperty(default='lid')

    def execute(self, context):
        slot_kind = self.slot_kind if self.slot_kind == 'building' else 'lid'
        _remove_door_preview(self.door_idx, slot_kind)
        context.scene.dgm_door_pose_active = False
        context.scene.dgm_door_pose_active_idx = 0
        context.scene.dgm_door_pose_active_kind = 'lid'
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# LOD operators
# ---------------------------------------------------------------------------

class DGM_OT_create_lods(bpy.types.Operator):
    bl_idname = "dgm.create_lods"
    bl_label = "Create Selected LODs"
    bl_description = (
        "Resolution LODs: visible model at different view distances. "
        "Wiki: polygon count should halve each step. "
        "Lowest should be ~500 polys with as few sections as possible"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_lod_meshes()
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Object Properties Sub-panel
# ---------------------------------------------------------------------------

class DGM_PT_object_props(bpy.types.Panel):
    bl_label = "DayZ Object Properties"
    bl_idname = "DGM_PT_object_props"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DayZ"
    bl_order = 0
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if not hasattr(obj, 'dgm_props'):
            layout.label(text="No DGM properties", icon='ERROR')
            return

        props = obj.dgm_props
        col = layout.column(align=True)
        col.prop(props, "is_dayz_object", text="Is DayZ Object")

        if props.is_dayz_object:
            col.prop(props, "lod", text="LOD Type")
            if props.lod == '-1.0':
                col.prop(props, "lod_distance", text="View Distance (m)")
            col.prop(props, "mass", text="Mass (kg)")

            layout.separator()
            layout.label(text="Named Properties:")
            for i, np in enumerate(props.named_props):
                row = layout.row(align=True)
                row.prop(np, "name", text="")
                row.prop(np, "value", text="")
                row.operator("dgm.remove_named_prop", text="", icon='X').index = i

            row = layout.row()
            row.operator("dgm.add_named_prop", text="Add Property", icon='ADD')


class DGM_OT_add_named_prop(bpy.types.Operator):
    bl_idname = "dgm.add_named_prop"
    bl_label = "Add Named Property"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and hasattr(obj, 'dgm_props'):
            obj.dgm_props.named_props.add()
        return {'FINISHED'}


class DGM_OT_remove_named_prop(bpy.types.Operator):
    bl_idname = "dgm.remove_named_prop"
    bl_label = "Remove Named Property"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = context.active_object
        if obj and hasattr(obj, 'dgm_props'):
            nps = obj.dgm_props.named_props
            if 0 <= self.index < len(nps):
                nps.remove(self.index)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Named Selections panel + operators
# ---------------------------------------------------------------------------

def _cleanup_stale_selections(obj):
    """Remove selection_mat entries for vertex groups that no longer exist on the object."""
    props = obj.dgm_props
    current_groups = {vg.name for vg in obj.vertex_groups}
    to_remove = [i for i, sm in enumerate(props.selection_mats)
                 if sm.vgroup_name not in current_groups]
    for i in reversed(to_remove):
        props.selection_mats.remove(i)


class DGM_OT_add_selection(bpy.types.Operator):
    bl_idname = "dgm.add_selection"
    bl_label = "Add Named Selection"
    bl_description = "Add the chosen vertex group to the named selections list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        target = scene.dgm_target_object
        if not target:
            self.report({'ERROR'}, "No target object set")
            return {'CANCELLED'}

        vgroup_name = scene.dgm_pending_selection.strip()
        if not vgroup_name:
            self.report({'WARNING'}, "Select a vertex group first")
            return {'CANCELLED'}

        if not target.vertex_groups.get(vgroup_name):
            self.report({'ERROR'}, "Vertex group '{}' not found on target".format(vgroup_name))
            return {'CANCELLED'}

        for sm in target.dgm_props.selection_mats:
            if sm.vgroup_name == vgroup_name:
                self.report({'WARNING'}, "'{}' is already in the list".format(vgroup_name))
                return {'CANCELLED'}

        item = target.dgm_props.selection_mats.add()
        item.vgroup_name = vgroup_name
        item.hidden_selection = vgroup_name
        scene.dgm_pending_selection = ""
        return {'FINISHED'}


class DGM_OT_remove_selection(bpy.types.Operator):
    bl_idname = "dgm.remove_selection"
    bl_label = "Remove Named Selection"
    bl_description = "Remove this entry from the named selections list"
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        target = context.scene.dgm_target_object
        if not target:
            return {'CANCELLED'}
        sms = target.dgm_props.selection_mats
        if 0 <= self.index < len(sms):
            sms.remove(self.index)
        return {'FINISHED'}



class DGM_OT_bake_selections(bpy.types.Operator):
    bl_idname = "dgm.bake_selections"
    bl_label = "Bake Marked Selections"
    bl_description = (
        "Run DayZ Texture Baker for selections marked 'Bake Texture', "
        "then assign the output CO texture and RVMAT paths automatically"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.scene.dgm_target_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Set a target object first")
            return {'CANCELLED'}

        if not baker_bridge.baker_licensed():
            self.report({'ERROR'}, "DayZ Texture Tools baker is not licensed — activate it in Preferences first")
            return {'CANCELLED'}

        output_dir = baker_bridge.baker_output_path()
        if not output_dir:
            self.report({'ERROR'}, "No bake output path set — open DayZ Texture Tools panel and set one first")
            return {'CANCELLED'}

        import bpy as _bpy
        output_dir = _bpy.path.abspath(output_dir)

        marked = [sm for sm in obj.dgm_props.selection_mats if sm.bake_texture]
        if not marked:
            self.report({'WARNING'}, "No selections marked for baking — tick 'Bake Texture' on at least one")
            return {'CANCELLED'}

        # Store the marked selections and output dir on the scene so the
        # post-bake assignment can find them after the modal baker finishes.
        # We use INVOKE_DEFAULT so the baker's modal loop runs properly.
        # The baker will call its own finish logic; we watch for new files.
        import bpy as _bpy

        # Snapshot file mtimes before baking so we know which files are new
        import os, time
        pre_files = set()
        if os.path.isdir(output_dir):
            pre_files = {f for f in os.listdir(output_dir)}

        try:
            result = _bpy.ops.dayztexturetools.texture_baker_run('INVOKE_DEFAULT')
        except Exception as exc:
            self.report({'ERROR'}, "Baker failed to start: {}".format(exc))
            return {'CANCELLED'}

        # Baker is now running modally. Schedule path assignment once it finishes
        # by polling for new files in the output folder.
        obj_name = obj.name
        sel_data = [(sm.hidden_selection.strip() or sm.vgroup_name, sm.vgroup_name)
                    for sm in marked]

        def _assign_when_done():
            # Check if baker is still running
            from bl_ext.user_default.phlanka_library_beta.texture_baker.ops import (
                DAYZTEXTTOOLS_OT_TextureBakerRun as _BakerOp
            )
            if getattr(_BakerOp, '_active_instance', None) is not None:
                return 0.5  # still running, check again in 0.5s

            target_obj = _bpy.data.objects.get(obj_name)
            if target_obj is None:
                return None

            assigned = 0
            for sel_name, vgroup_name in sel_data:
                sm_match = next(
                    (s for s in target_obj.dgm_props.selection_mats
                     if (s.hidden_selection.strip() or s.vgroup_name) == sel_name),
                    None
                )
                if sm_match is None:
                    continue
                co = baker_bridge._find_baked_co(output_dir, sel_name)
                rv = baker_bridge._find_baked_rvmat(output_dir, sel_name)
                if co:
                    sm_match.texture = co
                    assigned += 1
                if rv:
                    sm_match.rv_mat = rv

            if assigned:
                print("[DGM] Assigned baked textures to {} selection(s)".format(assigned))
            else:
                print("[DGM] Baker finished but no output files matched in '{}'".format(output_dir))
            return None  # stop polling

        _bpy.app.timers.register(_assign_when_done, first_interval=1.0)
        self.report({'INFO'}, "Baker started — paths will be assigned automatically when baking finishes")
        return {'FINISHED'}


def _draw_named_selections_content(layout, context):
    """Draw the Named Selections section body — call inside an expanded section box."""
    scene = context.scene
    target = scene.dgm_target_object
    props = target.dgm_props
    baker_ok = baker_bridge.baker_licensed()

    _cleanup_stale_selections(target)

    add_row = layout.row(align=True)
    add_row.prop_search(scene, "dgm_pending_selection", target, "vertex_groups", text="")
    add_row.operator("dgm.add_selection", text="", icon='ADD')

    if not baker_ok:
        cta_open = getattr(scene, "dgm_cta_baking_open", False)
        cta_box = layout.box()
        cta_row = cta_box.row(align=True)
        cta_row.prop(scene, "dgm_cta_baking_open", text="",
                     icon='TRIA_DOWN' if cta_open else 'TRIA_RIGHT', emboss=False)
        cta_row.label(text="Generate Textures Automatically", icon='RENDER_STILL')
        if cta_open:
            col = cta_box.column(align=True)
            col.label(text="With DayZ Texture Tools you can bake")
            col.label(text="images from your model directly.")
            col.separator()
            col.label(text="You will need the Phlanka Blender addon")
            col.label(text="with the Texture Baker module (required).")
            col.separator()
            row = col.row()
            row.scale_y = 0.8
            op = row.operator("wm.url_open", text="Get The Addon", icon='URL')
            op.url = "https://beta.phlanka.com/"

    if baker_ok:
        any_marked = any(sm.bake_texture for sm in props.selection_mats)
        if any_marked:
            bake_box = layout.box()
            bake_box.label(text="Bake Settings", icon='NODE_TEXTURE')

            if hasattr(scene, "dayz_bake_resolution"):
                bake_box.prop(scene, "dayz_bake_resolution", text="Resolution")
                if str(getattr(scene, "dayz_bake_resolution", "")) == "CUSTOM":
                    cust = bake_box.row(align=True)
                    cust.prop(scene, "dayz_bake_resolution_x", text="W")
                    cust.prop(scene, "dayz_bake_resolution_y", text="H")

            out_col = bake_box.column(align=True)
            out_col.label(text="Output Types:")
            out_grid = out_col.grid_flow(row_major=True, columns=2, even_columns=True)
            for prop_name, lbl, icon in (
                ("dayz_bake_co",       "CO",   'IMAGE_DATA'),
                ("dayz_bake_nohq",     "NOHQ", 'MODIFIER'),
                ("dayz_bake_smdi",     "SMDI", 'NODE_COMPOSITING'),
                ("dayz_bake_emissive", "EM",   'LIGHT'),
                ("dayz_bake_ao",       "AS",   'WORLD'),
                ("dayz_bake_rvmat",    "RVMAT", 'FILE_TEXT'),
            ):
                if hasattr(scene, prop_name):
                    out_grid.prop(scene, prop_name, text=lbl, toggle=True, icon=icon)

            if getattr(scene, "dayz_bake_rvmat", False) and hasattr(scene, "dayz_rvmat_preset"):
                rv = bake_box.box()
                rv.label(text="RVMAT Settings", icon='FILE_TEXT')
                preset_row = rv.row(align=True)
                preset_row.prop(scene, "dayz_rvmat_preset", text="Preset")
                if hasattr(bpy.types, "DAYZTEXTTOOLS_OT_RvmatPresetDelete"):
                    selected_id = str(getattr(scene, "dayz_rvmat_preset", "") or "")
                    del_row = preset_row.row(align=True)
                    del_row.enabled = selected_id not in {"", "custom"}
                    del_row.operator("dayztexturetools.rvmat_preset_delete", text="", icon='TRASH')
                if hasattr(scene, "dayz_rvmat_preset_name") and hasattr(bpy.types, "DAYZTEXTTOOLS_OT_RvmatPresetSave"):
                    name_row = rv.row(align=True)
                    name_row.prop(scene, "dayz_rvmat_preset_name", text="Name")
                    name_row.operator("dayztexturetools.rvmat_preset_save", text="Save", icon='FILE_TICK')
                colors = rv.box()
                colors.label(text="Surface Colors", icon='COLOR')
                for color_lbl, suffix in (("Ambient", "ambient"), ("Diffuse", "diffuse")):
                    crow = colors.row(align=True)
                    crow.label(text=color_lbl)
                    crow.prop(scene, "dayz_rvmat_{}_r".format(suffix), text="R")
                    crow.prop(scene, "dayz_rvmat_{}_g".format(suffix), text="G")
                    crow.prop(scene, "dayz_rvmat_{}_b".format(suffix), text="B")
                if getattr(scene, "dayz_bake_emissive", False):
                    erow = colors.row(align=True)
                    erow.label(text="Emissive")
                    erow.prop(scene, "dayz_rvmat_emissive_r", text="R")
                    erow.prop(scene, "dayz_rvmat_emissive_g", text="G")
                    erow.prop(scene, "dayz_rvmat_emissive_b", text="B")
                use_picker = getattr(scene, "dayz_rvmat_specular_use_picker", False)
                spec_split = rv.split(factor=0.3, align=True)
                spec_split.label(text="Specular")
                spec_right = spec_split.row(align=True)
                if hasattr(scene, "dayz_rvmat_specular_use_picker"):
                    spec_right.prop(scene, "dayz_rvmat_specular_use_picker", text="", icon='EYEDROPPER', toggle=True)
                if use_picker and hasattr(scene, "dayz_rvmat_specular_picker"):
                    spec_right.prop(scene, "dayz_rvmat_specular_picker", text="")
                else:
                    spec_right.prop(scene, "dayz_rvmat_specular_r", text="R")
                    spec_right.prop(scene, "dayz_rvmat_specular_g", text="G")
                    spec_right.prop(scene, "dayz_rvmat_specular_b", text="B")
                rv.prop(scene, "dayz_rvmat_specular_power", text="Specular Power")
                fresnel_row = rv.row(align=True)
                fresnel_row.prop(scene, "dayz_rvmat_fresnel_n", text="Fresnel N")
                fresnel_row.prop(scene, "dayz_rvmat_fresnel_k", text="Fresnel K")
                rv.prop(scene, "dayz_rvmat_env_map", text="Env Map")

            bake_box.operator("dgm.bake_selections", text="Bake Marked Selections", icon='RENDER_STILL')

    if not props.selection_mats:
        layout.label(text="No selections — pick a vertex group and click +", icon='INFO')
        return

    layout.separator()

    for i, sm in enumerate(props.selection_mats):
        entry_box = layout.box()
        header = entry_box.row(align=True)
        header.label(text=sm.vgroup_name, icon='GROUP_VERTEX')
        if baker_ok:
            header.prop(sm, "bake_texture", text="Bake", toggle=True)
        rem_op = header.operator("dgm.remove_selection", text="", icon='X')
        rem_op.index = i

        col = entry_box.column(align=True)
        col.prop(sm, "hidden_selection", text="Selection Name")

        if baker_ok and sm.bake_texture:
            if sm.texture:
                col.label(text=sm.texture, icon='IMAGE_DATA')
                if sm.rv_mat:
                    col.label(text=sm.rv_mat, icon='NODE_MATERIAL')
            else:
                col.label(text="Paths assigned after baking", icon='TIME')
        else:
            col.prop(sm, "texture", text="Texture (.paa)")
            col.prop(sm, "rv_mat", text="RVMat (.rvmat)")


# ---------------------------------------------------------------------------
# Main Panel
# ---------------------------------------------------------------------------



class DGM_PT_generators(bpy.types.Panel):
    bl_label = "DayZ Object Generator"
    bl_idname = "DGM_PT_generators"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DayZ"
    bl_order = 10
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        def _gen_section(prop, label, icon):
            box = layout.box()
            row = box.row()
            is_open = getattr(scene, prop, False)
            op = row.operator("dgm.toggle_section", text=label,
                              icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT')
            op.prop = prop
            return box, is_open

        box, is_open = _gen_section("dgm_show_ladder_gen", "Ladder Generator", 'MESH_CYLINDER')
        if is_open:
            ladder_generator.draw_ladder_generator_section(box, context)

        box, is_open = _gen_section("dgm_show_cabin_gen", "Cabin Generator", 'HOME')
        if is_open:
            cabin_generator.draw_cabin_generator_section(box, context)

class DGM_PT_main_panel(bpy.types.Panel):
    bl_label = "DayZ Geometry Maker"
    bl_idname = "DGM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DayZ"
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "dgm_target_object", text="Target Object")

        target = scene.dgm_target_object
        if target and target.type == 'MESH':
            layout.label(
                text="Polys: {:,}   Verts: {:,}".format(
                    len(target.data.polygons), len(target.data.vertices)
                ),
                icon='MESH_DATA'
            )

        def _section_header(prop, label):
            box = layout.box()
            row = box.row()
            is_open = getattr(scene, prop, False)
            op = row.operator("dgm.toggle_section", text=label,
                              icon='TRIA_DOWN' if is_open else 'TRIA_RIGHT')
            op.prop = prop
            return box, is_open

        # ---- Named Selections ----
        box, is_open = _section_header("dgm_show_selections", "Named Selections")
        if is_open:
            if target:
                _draw_named_selections_content(box, context)
            else:
                box.label(text="Set a Target Object first", icon='ERROR')

        # ---- Collision / Functional Geometry ----
        box, is_open = _section_header("dgm_show_collision", "Collision & Functional")
        if is_open:
            col = box.column(align=True)
            col.operator("dgm.create_geometry",                text="Add Geometry")
            col.operator("dgm.create_geometry_from_selection", text="Add Geometry from Selection")
            col.operator("dgm.create_view_geometry",           text="View Geometry (6e15)")
            col.operator("dgm.create_fire_geometry",           text="Fire Geometry (7e15)")
            box.operator("dgm.create_shadow_volumes",          text="Shadow Volumes (1e4 + 1.001e4)")


        # ---- Interior Views ----
        box, is_open = _section_header("dgm_show_interior", "Interior View LODs")
        if is_open:
            col = box.column(align=True)
            col.operator("dgm.create_view_pilot",  text="View Pilot (1.1e3)")
            col.operator("dgm.create_view_gunner", text="View Gunner (1e3)")
            col.operator("dgm.create_view_cargo",  text="View Cargo (1.2e3)")

        # ---- Terrain / Navigation ----
        box, is_open = _section_header("dgm_show_terrain", "Terrain & Navigation")
        if is_open:
            col = box.column(align=True)
            col.operator("dgm.create_land_contact", text="Land Contact (2e15)")
            col.operator("dgm.create_roadway",      text="Roadway (3e15)")

        # ---- Memory Points ----
        box, is_open = _section_header("dgm_show_memory", "Memory Points (1e15)")
        if is_open:
            moving = scene.dgm_moving_memory_point

            def _move_btn(row, point_name):
                is_moving = (moving == point_name)
                btn = row.row(align=True)
                btn.alert = is_moving
                op = btn.operator("dgm.memory_move_point", text="", icon='ORIENTATION_CURSOR')
                op.point_name = point_name

            def _mem_group(parent, label, op_idname, point_names, count_prop=None):
                if isinstance(point_names, str):
                    point_names = [point_names]

                any_exists = any(geometry.memory_point_exists(n) for n in point_names)

                hrow = parent.row(align=True)
                dot_icon = 'KEYFRAME_HLT' if any_exists else 'KEYFRAME'
                hrow.label(text="", icon=dot_icon)
                hrow.label(text=label)
                if count_prop:
                    hrow.prop(scene, count_prop, text="")
                btn_text = "Update" if any_exists else "Add"
                hrow.operator(op_idname, text=btn_text)

                if any_exists:
                    for pt in point_names:
                        if not geometry.memory_point_exists(pt):
                            continue
                        sub_row = parent.row(align=True)
                        sub_row.separator(factor=3.0)
                        sub_row.label(text=pt, icon='DOT')
                        _move_btn(sub_row, pt)

            def _mem_group_dynamic(parent, label, op_idname, count_prop, name_fn):
                count = getattr(scene, count_prop)
                all_names = name_fn(count)
                flat_names = [n for grp in all_names for n in grp]
                any_exists = any(geometry.memory_point_exists(n) for n in flat_names)

                hrow = parent.row(align=True)
                dot_icon = 'KEYFRAME_HLT' if any_exists else 'KEYFRAME'
                hrow.label(text="", icon=dot_icon)
                hrow.label(text=label)
                hrow.prop(scene, count_prop, text="")
                btn_text = "Update" if any_exists else "Add"
                hrow.operator(op_idname, text=btn_text)

                if any_exists:
                    for grp in all_names:
                        if len(all_names) > 1:
                            parts = grp[0].split('_')
                            grp_label = ' '.join(parts[:2]).title() if len(parts) >= 2 else grp[0]
                            grp_row = parent.row(align=True)
                            grp_row.separator(factor=2.0)
                            grp_row.label(text=grp_label, icon='RIGHTARROW_THIN')
                        for pt in grp:
                            if not geometry.memory_point_exists(pt):
                                continue
                            sub_row = parent.row(align=True)
                            sub_row.separator(factor=3.0)
                            sub_row.label(text=pt, icon='DOT')
                            _move_btn(sub_row, pt)

            sub = box.box()
            sub.label(text="Inventory & Bounds", icon='OBJECT_ORIGIN')
            _mem_group(sub, "Bounding Box",      "dgm.memory_add_bbox",    ['boundingbox_max', 'boundingbox_min'])
            _mem_group(sub, "Inventory Camera",  "dgm.memory_add_invview", 'invview')
            _mem_group(sub, "Center (ce_center)","dgm.memory_add_center",  'ce_center')
            _mem_group(sub, "Radius (ce_radius)","dgm.memory_add_radius",  'ce_radius')

            sub = box.box()
            sub.label(text="Weapon Points", icon='GP_MULTIFRAME_EDITING')
            _mem_group(sub, "Muzzle Points",  "dgm.memory_add_bullet",  ['konec hlavne', 'usti hlavne'])
            _mem_group(sub, "Bolt Axis",      "dgm.memory_add_bolt",    ['bolt_axis'])
            _mem_group(sub, "Case Eject",     "dgm.memory_add_eject",   ['nabojnicestart', 'nabojniceend'])
            _mem_group(sub, "Eye / ADS",      "dgm.memory_add_eye",     'eye')
            _mem_group(sub, "Trigger",        "dgm.memory_add_trigger", 'trigger')
            _mem_group(sub, "Magazine",       "dgm.memory_add_magazine",'magazine')

            sub = box.box()
            sub.label(text="Building & Structure", icon='MOD_BUILD')

            def _building_group_header(parent, label, count_prop, count):
                is_open = count > 0
                row = parent.row(align=True)
                row.label(text=label)
                row.prop(scene, count_prop, text="")
                return is_open

            # Ladders
            def _ladder_group_names(idx):
                prefix = "ladder{}".format(idx)
                return [
                    prefix,
                    prefix + '_bottom_front',
                    prefix + '_con',
                    prefix + '_con_dir',
                    prefix + '_dir',
                    prefix + '_top_front',
                ]

            ladder_count = getattr(scene, "dgm_memory_ladders_count", 1)
            existing_ladder_indices = [
                i for i in range(1, 6)
                if any(geometry.memory_point_exists(n) for n in _ladder_group_names(i))
            ]
            if existing_ladder_indices and ladder_count < max(existing_ladder_indices):
                ladder_count = max(existing_ladder_indices)
                scene.dgm_memory_ladders_count = ladder_count

            if _building_group_header(sub, "Ladders", "dgm_memory_ladders_count", ladder_count):
                for li in range(1, ladder_count + 1):
                    lad_points = _ladder_group_names(li)
                    lad_exists = any(geometry.memory_point_exists(n) for n in lad_points)

                    lrow = sub.row(align=True)
                    lrow.separator(factor=2.0)
                    dot_icon = 'KEYFRAME_HLT' if lad_exists else 'KEYFRAME'
                    lrow.label(text="", icon=dot_icon)
                    lrow.label(text="Ladder {}".format(li))
                    if lad_exists:
                        move_row = lrow.row(align=True)
                        move_row.alert = (getattr(scene, "dgm_moving_memory_ladder", 0) == li)
                        move_op = move_row.operator("dgm.memory_move_ladder", text="", icon='ORIENTATION_CURSOR')
                        move_op.ladder_idx = li
                        rot_op = lrow.operator("dgm.memory_rotate_ladder", text="", icon='LOOP_FORWARDS')
                        rot_op.ladder_idx = li
                        del_op = lrow.operator("dgm.memory_delete_ladder", text="", icon='X')
                        del_op.ladder_idx = li
                    else:
                        add_op = lrow.operator("dgm.memory_add_ladder_n", text="Add")
                        add_op.ladder_idx = li

                    if lad_exists:
                        for pt in lad_points:
                            if not geometry.memory_point_exists(pt):
                                continue
                            sub_row = sub.row(align=True)
                            sub_row.separator(factor=3.0)
                            sub_row.label(text=pt, icon='DOT')
                            _move_btn(sub_row, pt)

            lid_count = getattr(scene, "dgm_memory_doors_count", 1)
            existing_lid_indices = [
                i for i in range(1, 9)
                if any(geometry.memory_point_exists(n) for n in [
                    'lid_{}_axis_1'.format(i),
                    'lid_{}_axis_2'.format(i),
                ])
            ]
            if existing_lid_indices and lid_count < max(existing_lid_indices):
                lid_count = max(existing_lid_indices)
                scene.dgm_memory_doors_count = lid_count

            show_lid_axis = _building_group_header(sub, "Lid axis", "dgm_memory_doors_count", lid_count)
            if show_lid_axis:
                for di in range(1, lid_count + 1):
                    lid_points = ['lid_{}_axis_1'.format(di), 'lid_{}_axis_2'.format(di)]
                    lid_exists = any(geometry.memory_point_exists(n) for n in lid_points)

                    lrow = sub.row(align=True)
                    lrow.separator(factor=2.0)
                    lrow.label(text="", icon='KEYFRAME_HLT' if lid_exists else 'KEYFRAME')
                    lrow.label(text="Lid axis {}".format(di))
                    if lid_exists:
                        move_row = lrow.row(align=True)
                        move_row.alert = (getattr(scene, "dgm_moving_memory_point", "") == "lid_axis_{}".format(di))
                        move_op = move_row.operator("dgm.memory_move_lid_axis", text="", icon='ORIENTATION_CURSOR')
                        move_op.lid_idx = di
                        del_op = lrow.operator("dgm.memory_delete_lid_axis", text="", icon='X')
                        del_op.lid_idx = di
                    else:
                        add_op = lrow.operator("dgm.memory_add_lid_axis_n", text="Add")
                        add_op.lid_idx = di

                    if lid_exists:
                        for pt in lid_points:
                            if not geometry.memory_point_exists(pt):
                                continue
                            sub_row = sub.row(align=True)
                            sub_row.separator(factor=3.0)
                            sub_row.label(text=pt, icon='DOT')
                            _move_btn(sub_row, pt)

            building_door_count = getattr(scene, "dgm_memory_building_doors_count", 1)
            existing_building_door_indices = [
                i for i in range(1, 9)
                if any(geometry.memory_point_exists(n) for n in _building_door_point_names(i))
            ]
            if existing_building_door_indices and building_door_count < max(existing_building_door_indices):
                building_door_count = max(existing_building_door_indices)
                scene.dgm_memory_building_doors_count = building_door_count

            has_door_selection = _target_has_door_selection(target)

            show_door_axis = _building_group_header(sub, "Door axis", "dgm_memory_building_doors_count", building_door_count)
            if show_door_axis:
                for di in range(1, building_door_count + 1):
                    door_points = _building_door_point_names(di)
                    door_exists = any(geometry.memory_point_exists(n) for n in door_points)

                    drow = sub.row(align=True)
                    drow.separator(factor=2.0)
                    drow.label(text="", icon='KEYFRAME_HLT' if door_exists else 'KEYFRAME')
                    drow.label(text="Door axis {}".format(di))
                    if door_exists:
                        move_row = drow.row(align=True)
                        move_row.alert = (getattr(scene, "dgm_moving_memory_point", "") == "building_door_{}".format(di))
                        move_op = move_row.operator("dgm.memory_move_building_door", text="", icon='ORIENTATION_CURSOR')
                        move_op.door_idx = di
                        rot_op = drow.operator("dgm.memory_rotate_building_door", text="", icon='LOOP_FORWARDS')
                        rot_op.door_idx = di
                        del_op = drow.operator("dgm.memory_delete_building_door", text="", icon='X')
                        del_op.door_idx = di
                    else:
                        has_numbered_door = _target_has_numbered_door_selection(target, di)
                        add_row = drow.row(align=True)
                        add_row.enabled = has_door_selection and has_numbered_door
                        add_op = add_row.operator("dgm.memory_add_building_door_n", text="Add")
                        add_op.door_idx = di

                    if door_exists:
                        for pt in door_points:
                            if not geometry.memory_point_exists(pt):
                                continue
                            sub_row = sub.row(align=True)
                            sub_row.separator(factor=3.0)
                            sub_row.label(text=pt, icon='DOT')
                            _move_btn(sub_row, pt)

                for di in range(1, building_door_count + 1):
                    axis_exists = (geometry.memory_point_exists('door{}_axis_1'.format(di)) and
                                   geometry.memory_point_exists('door{}_axis_2'.format(di)))
                    if not axis_exists:
                        continue

                    target = scene.dgm_target_object
                    dbox = sub.box()
                    dbox.label(text="Door {} - Rotation Setup".format(di), icon='CON_ROTLIKE')

                    vgroup_prop = 'dgm_building_door_{}_vgroup'.format(di)
                    default_vgroup = "door{}".format(di)
                    has_default_vgroup = _target_has_numbered_door_selection(target, di)

                    if target and target.type == 'MESH' and target.vertex_groups:
                        dbox.prop_search(scene, vgroup_prop,
                                         target, "vertex_groups",
                                         text="Door Geometry")
                        if not getattr(scene, vgroup_prop, "") and has_default_vgroup:
                            dbox.label(text="Using {}".format(default_vgroup), icon='INFO')
                    else:
                        dbox.label(text="Set a target object with vertex groups", icon='ERROR')

                    pose_active = (
                        scene.dgm_door_pose_active and
                        scene.dgm_door_pose_active_idx == di and
                        getattr(scene, 'dgm_door_pose_active_kind', 'lid') == 'building'
                    )
                    closed_angle = getattr(scene, 'dgm_building_door_{}_closed_angle'.format(di), 0.0)
                    open_angle = getattr(scene, 'dgm_building_door_{}_open_angle'.format(di), 1.4)

                    if pose_active:
                        dbox.prop(scene, 'dgm_building_door_{}_preview_angle'.format(di),
                                  text="Preview Angle (rad)")
                        preview_angle = getattr(scene, 'dgm_building_door_{}_preview_angle'.format(di), 0.0)
                        dbox.label(text="{:.4f} rad  ({:.1f} deg)".format(
                            preview_angle, math.degrees(preview_angle)), icon='INFO')

                        angle_col = dbox.column(align=True)
                        crow = angle_col.row(align=True)
                        crow.label(text="Closed: {:.1f} deg".format(math.degrees(closed_angle)))
                        rec_c = crow.operator("dgm.door_record_pose", text="Set as Closed", icon='CHECKMARK')
                        rec_c.door_idx = di
                        rec_c.pose = 'closed'
                        rec_c.slot_kind = 'building'

                        orow = angle_col.row(align=True)
                        orow.label(text="Open:   {:.1f} deg".format(math.degrees(open_angle)))
                        rec_o = orow.operator("dgm.door_record_pose", text="Set as Open", icon='CHECKMARK')
                        rec_o.door_idx = di
                        rec_o.pose = 'open'
                        rec_o.slot_kind = 'building'

                        dbox.separator()
                        btn_row = dbox.row(align=True)
                        fin_op = btn_row.operator("dgm.door_finish_pose", text="Done", icon='CHECKMARK')
                        fin_op.door_idx = di
                        fin_op.slot_kind = 'building'
                        can_op = btn_row.operator("dgm.door_cancel_pose", text="Cancel", icon='X')
                        can_op.door_idx = di
                        can_op.slot_kind = 'building'
                    else:
                        angle_col = dbox.column(align=True)
                        angle_col.prop(scene, 'dgm_building_door_{}_closed_angle'.format(di), text="Closed (rad)")
                        angle_col.prop(scene, 'dgm_building_door_{}_open_angle'.format(di), text="Open (rad)")
                        dbox.label(text="Closed: {:.1f} deg   Open: {:.1f} deg".format(
                            math.degrees(closed_angle), math.degrees(open_angle)), icon='INFO')

                        dbox.prop(scene, 'dgm_building_door_{}_anim_period'.format(di), text="Anim Period (s)")

                        enter_row = dbox.row(align=True)
                        vgroup_set = bool(getattr(scene, vgroup_prop, "")) or has_default_vgroup
                        enter_row.enabled = vgroup_set
                        enter_op = enter_row.operator("dgm.door_set_pose",
                                                      text="Enter Rotate Mode", icon='CON_ROTLIKE')
                        enter_op.door_idx = di
                        enter_op.pose = 'open'
                        enter_op.slot_kind = 'building'
                        if not vgroup_set:
                            dbox.label(text="Select Door Geometry above first", icon='ERROR')

            # Lid rotation setup - shown per lid when both axis points exist
            door_count = lid_count
            for di in (range(1, door_count + 1) if show_lid_axis else []):
                axis_exists = (geometry.memory_point_exists('lid_{}_axis_1'.format(di)) and
                               geometry.memory_point_exists('lid_{}_axis_2'.format(di)))
                if not axis_exists:
                    continue

                target = scene.dgm_target_object
                dbox = sub.box()
                dbox.label(text="Lid {} - Rotation Setup".format(di), icon='CON_ROTLIKE')

                vgroup_prop = 'dgm_door_{}_vgroup'.format(di)
                if target and target.type == 'MESH' and target.vertex_groups:
                    dbox.prop_search(scene, vgroup_prop,
                                     target, "vertex_groups",
                                     text="Lid Geometry")
                else:
                    dbox.label(text="Set a target object with vertex groups", icon='ERROR')

                pose_active = scene.dgm_door_pose_active and scene.dgm_door_pose_active_idx == di
                closed_angle = getattr(scene, 'dgm_door_{}_closed_angle'.format(di), 0.0)
                open_angle   = getattr(scene, 'dgm_door_{}_open_angle'.format(di), -1.5708)

                if pose_active:
                    # Angle slider — drives the preview mesh in real time
                    dbox.prop(scene, 'dgm_door_{}_preview_angle'.format(di),
                              text="Preview Angle (rad)")
                    preview_angle = getattr(scene, 'dgm_door_{}_preview_angle'.format(di), 0.0)
                    dbox.label(text="{:.4f} rad  ({:.1f}°)".format(
                        preview_angle, math.degrees(preview_angle)), icon='INFO')

                    angle_col = dbox.column(align=True)
                    crow = angle_col.row(align=True)
                    crow.label(text="Closed: {:.1f}°".format(math.degrees(closed_angle)))
                    rec_c = crow.operator("dgm.door_record_pose", text="Set as Closed", icon='CHECKMARK')
                    rec_c.door_idx = di
                    rec_c.pose = 'closed'
                    rec_c.slot_kind = 'lid'

                    orow = angle_col.row(align=True)
                    orow.label(text="Open:   {:.1f}°".format(math.degrees(open_angle)))
                    rec_o = orow.operator("dgm.door_record_pose", text="Set as Open", icon='CHECKMARK')
                    rec_o.door_idx = di
                    rec_o.pose = 'open'
                    rec_o.slot_kind = 'lid'

                    dbox.separator()
                    btn_row = dbox.row(align=True)
                    fin_op = btn_row.operator("dgm.door_finish_pose", text="Done", icon='CHECKMARK')
                    fin_op.door_idx = di
                    fin_op.slot_kind = 'lid'
                    can_op = btn_row.operator("dgm.door_cancel_pose", text="Cancel", icon='X')
                    can_op.door_idx = di
                    can_op.slot_kind = 'lid'
                else:
                    angle_col = dbox.column(align=True)
                    angle_col.prop(scene, 'dgm_door_{}_closed_angle'.format(di), text="Closed (rad)")
                    angle_col.prop(scene, 'dgm_door_{}_open_angle'.format(di),   text="Open (rad)")
                    dbox.label(text="Closed: {:.1f}°   Open: {:.1f}°".format(
                        math.degrees(closed_angle), math.degrees(open_angle)), icon='INFO')

                    dbox.prop(scene, 'dgm_door_{}_anim_period'.format(di), text="Anim Period (s)")

                    enter_row = dbox.row(align=True)
                    vgroup_set = bool(getattr(scene, 'dgm_door_{}_vgroup'.format(di), ""))
                    enter_row.enabled = vgroup_set
                    enter_op = enter_row.operator("dgm.door_set_pose",
                                                  text="Enter Rotate Mode", icon='CON_ROTLIKE')
                    enter_op.door_idx = di
                    enter_op.pose = 'open'
                    enter_op.slot_kind = 'lid'
                    if not vgroup_set:
                        dbox.label(text="Select Lid Geometry above first", icon='ERROR')


            # Add Lid Geometry button - shown if any lid has a vgroup set
            any_door_vgroup = any(
                bool(getattr(scene, 'dgm_door_{}_vgroup'.format(di), "").strip())
                for di in range(1, door_count + 1)
            )
            if any_door_vgroup:
                sub.separator()
                sub.operator("dgm.door_add_geometry", text="Add Lid Geometry", icon='MESH_DATA')

            sub = box.box()
            sub.label(text="Effects & Lighting", icon='LIGHT')

            def _light_groups(count):
                return [['light_{}'.format(i)] for i in range(1, count + 1)]
            _mem_group_dynamic(sub, "Light Positions", "dgm.memory_add_lights",
                               "dgm_memory_lights_count", _light_groups)

            _mem_group(sub, "Damage Hide", "dgm.memory_add_damage", 'damageHide')

            if moving:
                info = box.box()
                info.alert = True
                info.label(text="Moving: {}".format(moving), icon='ORIENTATION_CURSOR')
                info.label(text="Tab or click Move again to finish", icon='INFO')

        # ---- Resolution LODs ----
        box, is_open = _section_header("dgm_show_lods", "Resolution LODs")
        if is_open:
            sub = box.box()
            sub.label(text="LOD index shown in Object Builder as e.g. 1.000, 2.000", icon='INFO')
            sub.label(text="Halve polys each step. ~500 polys min at highest index.")
            for lod_num, lod_label in [
                (1, "LOD 1.000  (highest detail)"),
                (2, "LOD 2.000"),
                (3, "LOD 3.000"),
                (4, "LOD 4.000"),
                (5, "LOD 5.000"),
                (6, "LOD 6.000  (~500 polys, fewest sections)"),
            ]:
                lod_row = sub.row(align=True)
                lod_row.prop(scene, "dgm_lod{}".format(lod_num), text="")
                lod_row.label(text=lod_label)
            sub.separator()
            sub.operator("dgm.create_lods", text="Create Selected LODs", icon='MESH_DATA')

        # ---- Export ----
        box, is_open = _section_header("dgm_show_export", "Export")
        if is_open:
            col = box.column(align=True)

            col.label(text="Config Template:")
            col.prop(scene, "dgm_config_template", text="")
            template = getattr(scene, "dgm_config_template", "container_base")
            recommended_model_cfg = _recommended_model_cfg_for_template(template)
            has_lid_doors = (geometry.memory_point_exists('lid_1_axis_1') or
                             geometry.memory_point_exists('lid_1_axis_2'))

            # P3D path row — text field showing current path + folder button to pick
            p3d_row = col.row(align=True)
            p3d_row.prop(scene, "dgm_p3d_path", text="P3D")
            p3d_row.operator("dgm.pick_p3d_path", text="", icon='FILE_FOLDER')

            # Textures path is used when at least one selection is marked for baking
            has_bake = (target and hasattr(target, 'dgm_props') and
                        any(sm.bake_texture for sm in target.dgm_props.selection_mats))
            if has_bake:
                tex_row = col.row(align=True)
                tex_row.label(text="Textures")
                tex_path = tex_row.row(align=True)
                tex_path.enabled = getattr(scene, "dgm_override_textures_path", False)
                tex_path.prop(scene, "dgm_textures_path", text="")
                tex_row.prop(scene, "dgm_override_textures_path", text="Custom")

            if template == 'container_base' and has_lid_doors:
                scripts_row = col.row(align=True)
                scripts_row.label(text="Scripts")
                scripts_path = scripts_row.row(align=True)
                scripts_path.enabled = getattr(scene, "dgm_override_scripts_path", False)
                scripts_path.prop(scene, "dgm_scripts_path", text="")
                scripts_row.prop(scene, "dgm_override_scripts_path", text="Custom")
                scripts_raw = getattr(scene, "dgm_scripts_path", "").strip().rstrip("\\/")
                if scripts_raw and scripts_raw.split("\\")[-1].split("/")[-1].lower() != "scripts":
                    warn = col.row()
                    warn.alert = True
                    warn.label(text="Scripts path must end with 'scripts'", icon='ERROR')

            col.separator()
            config_row = col.row()
            config_row.enabled = (template != 'none')
            config_row.prop(scene, "dgm_export_config_cpp")
            if template != 'none' and not getattr(scene, "dgm_export_config_cpp", True):
                warn = col.row()
                warn.alert = True
                warn.label(text="config.cpp export is disabled", icon='ERROR')

            # Scripts path — only relevant for container_base template
            if template == 'container_base':
                if has_lid_doors:
                    col.prop(scene, "dgm_export_scripts")
                    if not getattr(scene, "dgm_export_scripts", True):
                        warn = col.row()
                        warn.alert = True
                        warn.label(text="Container Base doors usually need scripts", icon='ERROR')

            col.separator()
            model_row = col.row()
            model_row.enabled = (template != 'none')
            model_row.prop(scene, "dgm_write_model_cfg")
            model_cfg_enabled = getattr(scene, "dgm_write_model_cfg", True)
            if template != 'none' and recommended_model_cfg and not model_cfg_enabled:
                warn = col.row()
                warn.alert = True
                warn.label(text="This template usually needs model.cfg", icon='ERROR')
            elif template != 'none' and not recommended_model_cfg and model_cfg_enabled:
                warn = col.row()
                warn.alert = True
                warn.label(text="model.cfg is usually not needed for this template", icon='INFO')
            col.operator("dgm.export_p3d", text="Export", icon='EXPORT')
            box.separator()
            box.operator("dgm.check_update", text="Check for Updates", icon='URL')


# ---------------------------------------------------------------------------
# Scene properties registration
# ---------------------------------------------------------------------------

def register_scene_props():
    S = bpy.types.Scene

    S.dgm_target_object = bpy.props.PointerProperty(
        type=bpy.types.Object, name="Target Object"
    )

    # Pending vertex group selection for the Named Selections add-row
    S.dgm_pending_selection = bpy.props.StringProperty(
        name="Vertex Group", default=""
    )

    # Collapsible section toggles — all closed by default
    S.dgm_show_selections  = bpy.props.BoolProperty(default=False)
    S.dgm_show_generators  = bpy.props.BoolProperty(default=False)
    S.dgm_show_ladder_gen  = bpy.props.BoolProperty(default=False)
    S.dgm_show_cabin_gen   = bpy.props.BoolProperty(default=False)
    S.dgm_show_collision   = bpy.props.BoolProperty(default=False)
    S.dgm_show_interior    = bpy.props.BoolProperty(default=False)
    S.dgm_show_terrain     = bpy.props.BoolProperty(default=False)
    S.dgm_show_memory      = bpy.props.BoolProperty(default=False)
    S.dgm_show_lods        = bpy.props.BoolProperty(default=False)
    S.dgm_show_export      = bpy.props.BoolProperty(default=False)
    S.dgm_cta_baking_open  = bpy.props.BoolProperty(default=False)

    # Fire Geometry quality
    S.dgm_fire_quality = bpy.props.IntProperty(
        name="Fire Geometry Subdivisions",
        description="Subdivision cuts — higher = more polys, tighter fit to mesh. Max 3500 points allowed",
        min=1, max=6, default=2,
    )

    # Memory point counts
    S.dgm_memory_doors_count  = bpy.props.IntProperty(name="Doors",   default=0, min=0, max=8,
                                                      update=_memory_lid_count_update)
    S.dgm_memory_lights_count = bpy.props.IntProperty(name="Lights",  default=1, min=1, max=8)
    S.dgm_memory_ladders_count = bpy.props.IntProperty(name="Ladders", default=0, min=0, max=5,
                                                       update=_memory_ladders_count_update)
    S.dgm_memory_building_doors_count = bpy.props.IntProperty(name="Doors", default=0, min=0, max=8,
                                                              update=_memory_building_doors_count_update)

    # Active move point name — empty string means none active
    S.dgm_moving_memory_point = bpy.props.StringProperty(name="Moving Memory Point", default="")
    S.dgm_moving_memory_ladder = bpy.props.IntProperty(name="Moving Memory Ladder", default=0, min=0, max=5)
    S.dgm_moving_memory_ladder_center = bpy.props.FloatVectorProperty(
        name="Moving Memory Ladder Center", size=3, default=(0.0, 0.0, 0.0)
    )

    # Door pose capture state
    S.dgm_door_pose_active     = bpy.props.BoolProperty(default=False)
    S.dgm_door_pose_active_idx = bpy.props.IntProperty(default=0)
    S.dgm_door_pose_active_kind = bpy.props.StringProperty(default='lid')

    # Per-door config properties (supports up to 8 doors)
    for _di in range(1, 9):
        setattr(S, 'dgm_memory_building_door_{}_orientation'.format(_di),
                bpy.props.EnumProperty(
                    name="Door {} Memory Orientation".format(_di),
                    items=[
                        ('Y', "Front/Back", "Door lies on a front/back wall"),
                        ('X', "Side", "Door lies on a side wall"),
                    ],
                    default='Y'))
        setattr(S, 'dgm_building_door_{}_vgroup'.format(_di),
                bpy.props.StringProperty(name="Door {} Vertex Group".format(_di), default=""))
        setattr(S, 'dgm_building_door_{}_closed_angle'.format(_di),
                bpy.props.FloatProperty(name="Closed Angle (rad)", default=0.0,
                                        soft_min=-6.2832, soft_max=6.2832))
        setattr(S, 'dgm_building_door_{}_open_angle'.format(_di),
                bpy.props.FloatProperty(name="Open Angle (rad)", default=1.4,
                                        soft_min=-6.2832, soft_max=6.2832))
        setattr(S, 'dgm_building_door_{}_preview_angle'.format(_di),
                bpy.props.FloatProperty(name="Preview Angle (rad)", default=0.0,
                                        soft_min=-6.2832, soft_max=6.2832,
                                        update=_door_preview_angle_update))
        setattr(S, 'dgm_building_door_{}_anim_period'.format(_di),
                bpy.props.FloatProperty(name="Anim Period (s)", default=1.0,
                                        min=0.01, max=10.0))
        setattr(S, 'dgm_door_{}_vgroup'.format(_di),
                bpy.props.StringProperty(name="Lid {} Vertex Group".format(_di), default=""))
        setattr(S, 'dgm_door_{}_closed_angle'.format(_di),
                bpy.props.FloatProperty(name="Closed Angle (rad)", default=0.0,
                                        soft_min=-6.2832, soft_max=6.2832))
        setattr(S, 'dgm_door_{}_open_angle'.format(_di),
                bpy.props.FloatProperty(name="Open Angle (rad)", default=0.0,
                                        soft_min=-6.2832, soft_max=6.2832))
        setattr(S, 'dgm_door_{}_preview_angle'.format(_di),
                bpy.props.FloatProperty(name="Preview Angle (rad)", default=0.0,
                                        soft_min=-6.2832, soft_max=6.2832,
                                        update=_door_preview_angle_update))
        setattr(S, 'dgm_door_{}_anim_period'.format(_di),
                bpy.props.FloatProperty(name="Anim Period (s)", default=1.0,
                                        min=0.01, max=10.0))

    # Export paths
    S.dgm_p3d_path = bpy.props.StringProperty(
        name="P3D", subtype='NONE', default="",
        description="Choose the target folder/path for P3D or mod export",
        update=_p3d_path_update,
    )
    S.dgm_textures_path = bpy.props.StringProperty(
        name="Textures", subtype='DIR_PATH', default="",
        description="Texture export folder. Default is the P3D folder plus data",
    )
    S.dgm_scripts_path = bpy.props.StringProperty(
        name="Scripts", subtype='DIR_PATH', default="",
        description="Script export folder. Default is the P3D folder plus scripts, and the path must end with scripts",
    )
    S.dgm_override_textures_path = bpy.props.BoolProperty(
        name="Override Textures",
        description="Allow editing the texture export path instead of using P3D folder plus data",
        default=False,
        update=_override_textures_path_update,
    )
    S.dgm_override_scripts_path = bpy.props.BoolProperty(
        name="Override Scripts",
        description="Allow editing the script export path instead of using P3D folder plus scripts",
        default=False,
        update=_override_scripts_path_update,
    )
    S.dgm_config_template = bpy.props.EnumProperty(
        name="Config Template",
        description="Which config.cpp template to write on export",
        items=[
            ('none',             "None",              "Do not write config files. Only P3D model"),
            ('container_base',   "Container Base",    "Storage container — inherits Container_Base"),
            ('house_no_destruct',"House (Static Obj)","Static world object — inherits HouseNoDestruct"),
            ('object_with_doors',"Object with doors", "HouseNoDestruct building with DayZ door config"),
        ],
        default='container_base',
        update=_config_template_update,
    )
    S.dgm_export_config_cpp = bpy.props.BoolProperty(
        name="Export config.cpp",
        description="Write config.cpp from the selected template",
        default=True,
    )
    S.dgm_export_scripts = bpy.props.BoolProperty(
        name="Export scripts",
        description="Write scripts required by the selected template",
        default=True,
    )
    S.dgm_write_model_cfg = bpy.props.BoolProperty(
        name="Export model.cfg",
        description="Write a model.cfg file alongside the P3D on export",
        default=True,
    )

    # Resolution LOD toggles + view distances (real game meters per wiki guidance)
    for i in range(1, 7):
        setattr(S, "dgm_lod{}".format(i), bpy.props.BoolProperty(
            name="LOD {}".format(i), default=False,
        ))
        setattr(S, "dgm_lod{}_dist".format(i), bpy.props.FloatProperty(
            name="LOD {} Index".format(i),
            description="LOD index number — shows as e.g. 1.000 in Object Builder. Use 1, 2, 3... sequentially",
            default=float(i), min=0.0, max=9999.0,
        ))


def unregister_scene_props():
    S = bpy.types.Scene
    props = [
        "dgm_target_object",
        "dgm_pending_selection",
        "dgm_show_selections", "dgm_show_generators", "dgm_show_ladder_gen", "dgm_show_cabin_gen", "dgm_show_collision", "dgm_show_interior", "dgm_show_terrain",
        "dgm_show_memory", "dgm_show_lods", "dgm_show_export", "dgm_cta_baking_open",
        "dgm_fire_quality",
        "dgm_memory_doors_count", "dgm_memory_lights_count", "dgm_memory_ladders_count", "dgm_memory_building_doors_count",
        "dgm_moving_memory_point", "dgm_moving_memory_ladder", "dgm_moving_memory_ladder_center",
        "dgm_door_pose_active", "dgm_door_pose_active_idx", "dgm_door_pose_active_kind",
        "dgm_p3d_path", "dgm_textures_path", "dgm_scripts_path",
        "dgm_override_textures_path", "dgm_override_scripts_path", "dgm_config_template",
        "dgm_export_config_cpp", "dgm_export_scripts", "dgm_write_model_cfg",
    ]
    for _di in range(1, 9):
        props += [
            'dgm_memory_building_door_{}_orientation'.format(_di),
            'dgm_building_door_{}_vgroup'.format(_di),
            'dgm_building_door_{}_closed_angle'.format(_di),
            'dgm_building_door_{}_open_angle'.format(_di),
            'dgm_building_door_{}_preview_angle'.format(_di),
            'dgm_building_door_{}_anim_period'.format(_di),
            'dgm_door_{}_vgroup'.format(_di),
            'dgm_door_{}_closed_angle'.format(_di),
            'dgm_door_{}_open_angle'.format(_di),
            'dgm_door_{}_preview_angle'.format(_di),
            'dgm_door_{}_anim_period'.format(_di),
        ]
    for i in range(1, 7):
        props.append("dgm_lod{}".format(i))
        props.append("dgm_lod{}_dist".format(i))
    for p in props:
        if hasattr(S, p):
            try:
                delattr(S, p)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Ladder — per-index add and rotate operators
# ---------------------------------------------------------------------------

class DGM_OT_memory_add_ladder_n(bpy.types.Operator):
    """Add a ladder group with a specific index (ladder1, ladder2, ... ladder5)."""
    bl_idname = "dgm.memory_add_ladder_n"
    bl_label = "Add Ladder"
    bl_description = "Add memory points and view geometry for this ladder slot"
    bl_options = {'REGISTER', 'UNDO'}

    ladder_idx: bpy.props.IntProperty(default=1, min=1, max=5)

    def execute(self, context):
        # Auto-select the matching DZ_Ladder_N object for this slot if it exists
        # This prevents accidentally spawning memory on the wrong ladder when
        # multiple ladders are in the scene.
        matching_ladder = bpy.data.objects.get("DZ_Ladder_{}".format(self.ladder_idx))
        if matching_ladder is not None and matching_ladder.get('dgm_ladder'):
            context.scene.dgm_target_object = matching_ladder
        elif not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        # Enforce sequential order — previous ladder must exist first
        if self.ladder_idx > 1:
            prev_prefix = "ladder{}".format(self.ladder_idx - 1)
            if not geometry.memory_point_exists(prev_prefix):
                self.report({'ERROR'},
                    "Add Ladder {} first".format(self.ladder_idx - 1))
                return {'CANCELLED'}
        geometry.add_memory_ladder(ladder_idx=self.ladder_idx)
        return {'FINISHED'}


class DGM_OT_memory_delete_ladder(bpy.types.Operator):
    """Delete all memory points of a ladder group."""
    bl_idname = "dgm.memory_delete_ladder"
    bl_label = "Delete Ladder"
    bl_description = "Remove all memory points and view geometry for this ladder group"
    bl_options = {'REGISTER', 'UNDO'}

    ladder_idx: bpy.props.IntProperty(default=1, min=1, max=5)

    def execute(self, context):
        # Enforce sequential order — cannot delete if a higher ladder exists
        for next_idx in range(self.ladder_idx + 1, 6):
            next_prefix = "ladder{}".format(next_idx)
            if geometry.memory_point_exists(next_prefix):
                self.report({'ERROR'},
                    "Delete Ladder {} first".format(next_idx))
                return {'CANCELLED'}
        geometry.remove_memory_ladder(ladder_idx=self.ladder_idx)
        # Keep the count spinner in sync
        scene = context.scene
        if scene.dgm_memory_ladders_count > self.ladder_idx - 1:
            scene.dgm_memory_ladders_count = max(0, self.ladder_idx - 1)
        self.report({'INFO'}, "Ladder {} deleted".format(self.ladder_idx))
        return {'FINISHED'}


class DGM_OT_memory_rotate_ladder(bpy.types.Operator):
    """Rotate all memory points of a ladder group by 90° around Z."""
    bl_idname = "dgm.memory_rotate_ladder"
    bl_label = "Rotate Ladder 90°"
    bl_description = "Rotate this ladder group 90° around the Z axis"
    bl_options = {'REGISTER', 'UNDO'}

    ladder_idx: bpy.props.IntProperty(default=1, min=1, max=5)

    def execute(self, context):
        import math
        import mathutils

        prefix = "ladder{}".format(self.ladder_idx)
        point_names = [
            prefix,
            prefix + '_bottom_front',
            prefix + '_con',
            prefix + '_con_dir',
            prefix + '_dir',
            prefix + '_top_front',
        ]

        mem = geometry.get_memory_object()
        if not mem:
            self.report({'ERROR'}, "No Memory LOD found")
            return {'CANCELLED'}

        rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'Z')

        verts_to_rotate = set()
        for name in point_names:
            vg = mem.vertex_groups.get(name)
            if not vg:
                continue
            for v in mem.data.vertices:
                for g in v.groups:
                    if g.group == vg.index:
                        verts_to_rotate.add(v.index)

        if not verts_to_rotate:
            self.report({'WARNING'}, "No ladder{} points found".format(self.ladder_idx))
            return {'CANCELLED'}

        # Compute the centre (X, Y) of the ladder's own vertices — rotate around that,
        # not around world origin.
        coords = [mem.data.vertices[vi].co.copy() for vi in verts_to_rotate]
        cx = sum(c.x for c in coords) / len(coords)
        cy = sum(c.y for c in coords) / len(coords)
        pivot = mathutils.Vector((cx, cy, 0.0))

        for vi in verts_to_rotate:
            co = mem.data.vertices[vi].co.copy()
            co -= pivot          # translate to pivot
            co  = rot @ co       # rotate around Z
            co += pivot          # translate back
            mem.data.vertices[vi].co = co

        mem.data.update()

        # Rotate the View Geometry object around its own location (already correct)
        vg_obj_name = "View Geometry.ladder{}".format(self.ladder_idx)
        vg_obj = bpy.data.objects.get(vg_obj_name)
        if vg_obj:
            vg_obj.rotation_euler.z += math.radians(90)

        self.report({'INFO'}, "Ladder {} rotated 90°".format(self.ladder_idx))
        return {'FINISHED'}


operator_classes = (
    DGM_OT_create_geometry,
    DGM_OT_create_geometry_from_selection,
    DGM_OT_create_view_geometry,
    DGM_OT_toggle_section,
    DGM_OT_create_fire_geometry,
    DGM_OT_create_shadow_volumes,
    DGM_OT_create_view_pilot,
    DGM_OT_create_view_gunner,
    DGM_OT_create_view_cargo,
    DGM_OT_create_land_contact,
    DGM_OT_create_roadway,
    DGM_OT_memory_add_bbox,
    DGM_OT_memory_add_invview,
    DGM_OT_memory_add_center,
    DGM_OT_memory_add_radius,
    DGM_OT_memory_add_bullet,
    DGM_OT_memory_add_bolt,
    DGM_OT_memory_add_eject,
    DGM_OT_memory_add_eye,
    DGM_OT_memory_add_trigger,
    DGM_OT_memory_add_magazine,
    DGM_OT_memory_add_ladder,
    DGM_OT_memory_add_lights,
    DGM_OT_memory_add_damage,
    DGM_OT_memory_add_doors,
    DGM_OT_memory_add_lid_axis_n,
    DGM_OT_memory_delete_lid_axis,
    DGM_OT_memory_add_building_door_n,
    DGM_OT_memory_delete_building_door,
    DGM_OT_memory_rotate_building_door,
    DGM_OT_set_default_export_subdir,
    DGM_OT_memory_move_point,
    DGM_OT_memory_move_ladder,
    DGM_OT_memory_move_lid_axis,
    DGM_OT_memory_move_building_door,
    DGM_OT_door_add_geometry,
    DGM_OT_door_set_pose,
    DGM_OT_door_record_pose,
    DGM_OT_door_finish_pose,
    DGM_OT_door_cancel_pose,
    DGM_OT_create_lods,
    DGM_OT_add_named_prop,
    DGM_OT_remove_named_prop,
    DGM_OT_add_selection,
    DGM_OT_remove_selection,
    DGM_OT_bake_selections,
    DGM_OT_memory_add_ladder_n,
    DGM_OT_memory_delete_ladder,
    DGM_OT_memory_rotate_ladder,
    DGM_PT_object_props,
    DGM_PT_generators,
    DGM_PT_main_panel,
)


def register():
    for cls in operator_classes:
        bpy.utils.register_class(cls)
    ladder_generator.register()
    cabin_generator.register()
    register_scene_props()


def unregister():
    unregister_scene_props()
    ladder_generator.unregister()
    cabin_generator.unregister()
    for cls in reversed(operator_classes):
        bpy.utils.unregister_class(cls)
