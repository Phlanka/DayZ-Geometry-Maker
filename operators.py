"""
DayZ Geometry Maker - Operators and Panel
"""

import bpy
from . import geometry, updater, baker_bridge


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


class DGM_OT_toggle_fire(bpy.types.Operator):
    bl_idname = "dgm.toggle_fire"
    bl_label = "Fire Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.dgm_show_fire = not context.scene.dgm_show_fire
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

class DGM_OT_toggle_memory(bpy.types.Operator):
    bl_idname = "dgm.toggle_memory"
    bl_label = "Memory Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.dgm_show_memory = not context.scene.dgm_show_memory
        return {'FINISHED'}


class DGM_OT_create_memory(bpy.types.Operator):
    bl_idname = "dgm.create_memory"
    bl_label = "Create Selected Memory Points"
    bl_description = (
        "Memory LOD (1e15): named selection vertices for lights, "
        "entry points, animation control, inventory view, etc"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.dgm_target_object:
            self.report({'ERROR'}, "Select a target object first")
            return {'CANCELLED'}
        geometry.create_memory_points()
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# LOD operators
# ---------------------------------------------------------------------------

class DGM_OT_toggle_lods(bpy.types.Operator):
    bl_idname = "dgm.toggle_lods"
    bl_label = "Resolution LODs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.dgm_show_lods = not context.scene.dgm_show_lods
        return {'FINISHED'}


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


# ---------------------------------------------------------------------------
# Named Selections panel + operators
# ---------------------------------------------------------------------------

def _sync_selection_mats(obj):
    """
    Keep selection_mats in sync with the object's actual vertex groups.
    Adds entries for new groups, removes entries for deleted groups.
    Never wipes existing texture/rvmat data.
    hidden_selection defaults to the vertex group name — user can override it.
    """
    props = obj.dgm_props
    existing = {sm.vgroup_name: sm for sm in props.selection_mats}
    current_groups = {vg.name for vg in obj.vertex_groups}

    # Add missing — pre-fill hidden_selection with the vgroup name
    for name in current_groups:
        if name not in existing:
            item = props.selection_mats.add()
            item.vgroup_name = name
            item.hidden_selection = name  # default: same as vgroup name

    # Remove stale (vertex group was deleted)
    to_remove = [i for i, sm in enumerate(props.selection_mats)
                 if sm.vgroup_name not in current_groups]
    for i in reversed(to_remove):
        props.selection_mats.remove(i)


class DGM_OT_sync_selections(bpy.types.Operator):
    bl_idname = "dgm.sync_selections"
    bl_label = "Sync from Vertex Groups"
    bl_description = "Sync the named selection list from this object's vertex groups"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'MESH' and hasattr(obj, 'dgm_props'):
            _sync_selection_mats(obj)
            self.report({'INFO'}, "Synced {} selections".format(len(obj.vertex_groups)))
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
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object first")
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


class DGM_PT_named_selections(bpy.types.Panel):
    bl_label = "Named Selections"
    bl_idname = "DGM_PT_named_selections"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DayZ"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and hasattr(obj, 'dgm_props')

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        props = obj.dgm_props
        baker_ok = baker_bridge.baker_licensed()

        layout.label(text="Vertex groups = Named selections in P3D", icon='GROUP_VERTEX')
        layout.label(text="{} vertex groups on this object".format(len(obj.vertex_groups)), icon='INFO')

        layout.operator("dgm.sync_selections", text="Sync from Vertex Groups", icon='FILE_REFRESH')

        if not baker_ok:
            scene = context.scene
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

            # Baker settings box — only visible when at least one selection has Bake ticked
            if any_marked:
                scene = context.scene
                box = layout.box()
                box.label(text="Bake Settings", icon='NODE_TEXTURE')

                # Resolution — uses the baker's own scene props
                if hasattr(scene, "dayz_bake_resolution"):
                    box.prop(scene, "dayz_bake_resolution", text="Resolution")
                    if str(getattr(scene, "dayz_bake_resolution", "")) == "CUSTOM":
                        cust = box.row(align=True)
                        cust.prop(scene, "dayz_bake_resolution_x", text="W")
                        cust.prop(scene, "dayz_bake_resolution_y", text="H")

                # Output types — real prop names from the baker remote script
                out_col = box.column(align=True)
                out_col.label(text="Output Types:")
                out_grid = out_col.grid_flow(row_major=True, columns=2, even_columns=True)
                for prop_name, label, icon in (
                    ("dayz_bake_co",       "CO",   'IMAGE_DATA'),
                    ("dayz_bake_nohq",     "NOHQ", 'MODIFIER'),
                    ("dayz_bake_smdi",     "SMDI", 'NODE_COMPOSITING'),
                    ("dayz_bake_emissive", "EM",   'LIGHT'),
                    ("dayz_bake_ao",       "AS",   'WORLD'),
                    ("dayz_bake_rvmat",    "RVMAT", 'FILE_TEXT'),
                ):
                    if hasattr(scene, prop_name):
                        out_grid.prop(scene, prop_name, text=label, toggle=True, icon=icon)

                # RVMAT settings — only shown when RVMAT output is enabled
                if getattr(scene, "dayz_bake_rvmat", False) and hasattr(scene, "dayz_rvmat_preset"):
                    rv = box.box()
                    rv.label(text="RVMAT Settings", icon='FILE_TEXT')

                    # Preset row with save/delete
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

                    # Surface colors
                    colors = rv.box()
                    colors.label(text="Surface Colors", icon='COLOR')
                    ambient_row = colors.row(align=True)
                    ambient_row.label(text="Ambient")
                    ambient_row.prop(scene, "dayz_rvmat_ambient_r", text="R")
                    ambient_row.prop(scene, "dayz_rvmat_ambient_g", text="G")
                    ambient_row.prop(scene, "dayz_rvmat_ambient_b", text="B")
                    diffuse_row = colors.row(align=True)
                    diffuse_row.label(text="Diffuse")
                    diffuse_row.prop(scene, "dayz_rvmat_diffuse_r", text="R")
                    diffuse_row.prop(scene, "dayz_rvmat_diffuse_g", text="G")
                    diffuse_row.prop(scene, "dayz_rvmat_diffuse_b", text="B")
                    if getattr(scene, "dayz_bake_emissive", False):
                        emissive_row = colors.row(align=True)
                        emissive_row.label(text="Emissive")
                        emissive_row.prop(scene, "dayz_rvmat_emissive_r", text="R")
                        emissive_row.prop(scene, "dayz_rvmat_emissive_g", text="G")
                        emissive_row.prop(scene, "dayz_rvmat_emissive_b", text="B")

                    # Specular with optional color picker
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

        layout.separator()

        if not props.selection_mats:
            layout.label(text="No selections — click Sync first", icon='ERROR')
            return

        for sm in props.selection_mats:
            box = layout.box()

            # Header row: vgroup name on left, Bake toggle on right (if licensed)
            header = box.row(align=True)
            header.label(text=sm.vgroup_name, icon='GROUP_VERTEX')
            if baker_ok:
                header.prop(sm, "bake_texture", text="Bake", toggle=True)

            # Selection name — pre-filled from vgroup, editable if user wants a different export name
            col = box.column(align=True)
            col.prop(sm, "hidden_selection", text="Selection Name")

            if baker_ok and sm.bake_texture:
                # Bake mode: show result paths (read-only) after a bake has run
                if sm.texture:
                    col.label(text=sm.texture, icon='IMAGE_DATA')
                    if sm.rv_mat:
                        col.label(text=sm.rv_mat, icon='NODE_MATERIAL')
                else:
                    col.label(text="Paths assigned after baking", icon='TIME')
            else:
                # Manual mode: editable PAA and RVMAT fields with plain labels
                col.prop(sm, "texture", text="Texture (.paa)")
                col.prop(sm, "rv_mat", text="RVMat (.rvmat)")


# ---------------------------------------------------------------------------
# Main Panel
# ---------------------------------------------------------------------------

class DGM_PT_main_panel(bpy.types.Panel):
    bl_label = "DayZ Geometry Maker"
    bl_idname = "DGM_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "DayZ"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Update notification banner
        if updater._update_available:
            box = layout.box()
            row = box.row()
            row.label(text="Update: " + updater._latest_version_str, icon='INFO')
            row.operator("dgm.install_update", text="Install", icon='IMPORT')

        layout.prop(scene, "dgm_target_object", text="Target Object")

        # Poly count info
        target = scene.dgm_target_object
        if target and target.type == 'MESH':
            layout.label(
                text="Polys: {:,}   Verts: {:,}".format(
                    len(target.data.polygons), len(target.data.vertices)
                ),
                icon='MESH_DATA'
            )

        layout.separator()

        # ---- Collision / Functional Geometry ----
        box = layout.box()
        box.label(text="Collision & Functional", icon='MESH_CUBE')
        col = box.column(align=True)
        col.operator("dgm.create_geometry",                  text="Add Geometry")
        col.operator("dgm.create_geometry_from_selection",   text="Add Geometry from Selection")
        col.operator("dgm.create_view_geometry",             text="View Geometry (6e15)")

        # Fire Geometry
        col.operator("dgm.create_fire_geometry", text="Fire Geometry (7e15)")

        box.operator("dgm.create_shadow_volumes", text="Shadow Volumes (1e4 + 1.001e4)")

        layout.separator()

        # ---- Interior Views ----
        box = layout.box()
        box.label(text="Interior View LODs", icon='VIEW_CAMERA')
        col = box.column(align=True)
        col.operator("dgm.create_view_pilot",  text="View Pilot (1.1e3)")
        col.operator("dgm.create_view_gunner", text="View Gunner (1e3)")
        col.operator("dgm.create_view_cargo",  text="View Cargo (1.2e3)")

        layout.separator()

        # ---- Terrain / Navigation ----
        box = layout.box()
        box.label(text="Terrain & Navigation", icon='CURVE_PATH')
        col = box.column(align=True)
        col.operator("dgm.create_land_contact", text="Land Contact (2e15)")
        col.operator("dgm.create_roadway",      text="Roadway (3e15)")

        layout.separator()

        # ---- Memory Points ----
        box = layout.box()
        icon = 'TRIA_DOWN' if scene.dgm_show_memory else 'TRIA_RIGHT'
        row = box.row()
        row.operator("dgm.toggle_memory", text="Memory Points (1e15)", icon=icon)
        if scene.dgm_show_memory:
            sub = box.box()
            sub.label(text="Inventory / Bounds:")
            sub.prop(scene, "dgm_memory_bbox",     text="Bounding Box (boundingbox_min/max)")
            sub.prop(scene, "dgm_memory_invview",  text="Inventory Camera (invview)")
            sub.prop(scene, "dgm_memory_center",   text="ce_center (center of mass)")
            sub.prop(scene, "dgm_memory_radius",   text="ce_radius (bounding sphere)")
            sub.separator()
            sub.label(text="Weapon Points:")
            sub.prop(scene, "dgm_memory_bullet",   text="Muzzle (konec/usti hlavne)")
            sub.prop(scene, "dgm_memory_bolt",     text="Bolt Axis (2 verts)")
            sub.prop(scene, "dgm_memory_eject",    text="Case Eject (nabojnice start/end)")
            sub.prop(scene, "dgm_memory_eye",      text="Eye ADS (eye)")
            sub.prop(scene, "dgm_memory_trigger",  text="Trigger Position")
            sub.prop(scene, "dgm_memory_magazine", text="Magazine Attachment")
            sub.separator()
            sub.label(text="Building / Structure:")
            sub.prop(scene, "dgm_memory_ladder",   text="Ladder Top + Bottom")
            row = sub.row(align=True)
            row.prop(scene, "dgm_memory_doors",    text="Door Points")
            if scene.dgm_memory_doors:
                row.prop(scene, "dgm_memory_doors_count", text="")
            sub.separator()
            sub.label(text="Effects / Lighting:")
            row = sub.row(align=True)
            row.prop(scene, "dgm_memory_lights",   text="Light Positions")
            if scene.dgm_memory_lights:
                row.prop(scene, "dgm_memory_lights_count", text="")
            sub.prop(scene, "dgm_memory_damage",   text="Damage Hide Point (damageHide)")
            sub.separator()
            sub.operator("dgm.create_memory", text="Create Selected Points", icon='VERTEXSEL')

        layout.separator()

        # ---- Resolution LODs ----
        box = layout.box()
        icon = 'TRIA_DOWN' if scene.dgm_show_lods else 'TRIA_RIGHT'
        row = box.row()
        row.operator("dgm.toggle_lods", text="Resolution LODs", icon=icon)
        if scene.dgm_show_lods:
            sub = box.box()
            sub.label(text="LOD index shown in Object Builder as e.g. 1.000, 2.000", icon='INFO')
            sub.label(text="Halve polys each step. ~500 polys min at highest index.")

            for lod_num, label in [
                (1, "LOD 1.000  (highest detail)"),
                (2, "LOD 2.000"),
                (3, "LOD 3.000"),
                (4, "LOD 4.000"),
                (5, "LOD 5.000"),
                (6, "LOD 6.000  (~500 polys, fewest sections)"),
            ]:
                row = sub.row(align=True)
                row.prop(scene, "dgm_lod{}".format(lod_num), text="")
                row.label(text=label)

            sub.separator()
            sub.operator("dgm.create_lods", text="Create Selected LODs", icon='MESH_DATA')

        layout.separator()

        # ---- Export ----
        box = layout.box()
        box.label(text="Export", icon='EXPORT')
        box.operator("dgm.export_p3d", text="Export P3D (.p3d)", icon='EXPORT')
        box.operator("dgm.check_update", text="Check for Updates", icon='URL')


# ---------------------------------------------------------------------------
# Scene properties registration
# ---------------------------------------------------------------------------

def register_scene_props():
    S = bpy.types.Scene

    S.dgm_target_object = bpy.props.PointerProperty(
        type=bpy.types.Object, name="Target Object"
    )

    # UI toggle state
    S.dgm_show_fire        = bpy.props.BoolProperty(default=False)
    S.dgm_show_memory      = bpy.props.BoolProperty(default=False)
    S.dgm_show_lods        = bpy.props.BoolProperty(default=False)
    S.dgm_cta_baking_open  = bpy.props.BoolProperty(default=False)

    # Fire Geometry quality
    S.dgm_fire_quality = bpy.props.IntProperty(
        name="Fire Geometry Subdivisions",
        description="Subdivision cuts — higher = more polys, tighter fit to mesh. Max 3500 points allowed",
        min=1, max=6, default=2,
    )

    # Memory point toggles — bbox and invview are now separate
    S.dgm_memory_bbox     = bpy.props.BoolProperty(name="Bounding Box",       default=True,
        description="boundingbox_min/max: defines object bounds used by the engine and inventory display")
    S.dgm_memory_invview  = bpy.props.BoolProperty(name="Inventory Camera",   default=True,
        description="invview: camera position for the inventory preview render")
    S.dgm_memory_center   = bpy.props.BoolProperty(name="Center Point",       default=False,
        description="ce_center: center of mass / object center")
    S.dgm_memory_radius   = bpy.props.BoolProperty(name="Radius Point",       default=False,
        description="ce_radius: bounding sphere radius reference, offset by sphere radius in -X")
    S.dgm_memory_bullet   = bpy.props.BoolProperty(name="Bullet Travel",      default=False,
        description="konec hlavne (breech) and usti hlavne (muzzle/barrel end) for bullet trajectory")
    S.dgm_memory_bolt     = bpy.props.BoolProperty(name="Bolt Axis",          default=False,
        description="bolt_axis: two vertices defining the bolt travel direction")
    S.dgm_memory_eject    = bpy.props.BoolProperty(name="Bullet Eject",       default=False,
        description="nabojnicestart/nabojniceend: casing ejection path")
    S.dgm_memory_eye      = bpy.props.BoolProperty(name="Eye ADS",            default=False,
        description="eye: ADS aiming position")
    S.dgm_memory_trigger  = bpy.props.BoolProperty(name="Trigger",            default=False,
        description="trigger: trigger position on the weapon")
    S.dgm_memory_magazine = bpy.props.BoolProperty(name="Magazine",           default=False,
        description="magazine: magazine attachment/detachment point")
    S.dgm_memory_ladder   = bpy.props.BoolProperty(name="Ladder",             default=False,
        description="ladder_top / ladder_bottom: for building ladders (Roadway LOD also required)")
    S.dgm_memory_doors    = bpy.props.BoolProperty(name="Door Points",        default=False,
        description="door_N_axis_begin/end, door_N_open_pos, door_N_closed_pos for animated doors")
    S.dgm_memory_doors_count = bpy.props.IntProperty(name="Door Count",       default=1, min=1, max=8)
    S.dgm_memory_lights   = bpy.props.BoolProperty(name="Light Positions",    default=False,
        description="light_1 .. light_N: positions for dynamic lights / particle effects")
    S.dgm_memory_lights_count = bpy.props.IntProperty(name="Light Count",     default=1, min=1, max=8)
    S.dgm_memory_damage   = bpy.props.BoolProperty(name="Damage Hide",        default=False,
        description="damageHide: point used to hide parts of the model when damaged")

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
        "dgm_show_fire", "dgm_show_memory", "dgm_show_lods", "dgm_cta_baking_open",
        "dgm_fire_quality",
        "dgm_memory_bbox", "dgm_memory_invview",
        "dgm_memory_center", "dgm_memory_radius",
        "dgm_memory_bullet", "dgm_memory_bolt", "dgm_memory_eject",
        "dgm_memory_eye", "dgm_memory_trigger", "dgm_memory_magazine",
        "dgm_memory_ladder",
        "dgm_memory_doors", "dgm_memory_doors_count",
        "dgm_memory_lights", "dgm_memory_lights_count",
        "dgm_memory_damage",
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


operator_classes = (
    DGM_OT_create_geometry,
    DGM_OT_create_geometry_from_selection,
    DGM_OT_create_view_geometry,
    DGM_OT_toggle_fire,
    DGM_OT_create_fire_geometry,
    DGM_OT_create_shadow_volumes,
    DGM_OT_create_view_pilot,
    DGM_OT_create_view_gunner,
    DGM_OT_create_view_cargo,
    DGM_OT_create_land_contact,
    DGM_OT_create_roadway,
    DGM_OT_toggle_memory,
    DGM_OT_create_memory,
    DGM_OT_toggle_lods,
    DGM_OT_create_lods,
    DGM_OT_add_named_prop,
    DGM_OT_sync_selections,
    DGM_OT_bake_selections,
    DGM_PT_named_selections,
    DGM_PT_object_props,
    DGM_PT_main_panel,
)


def register():
    for cls in operator_classes:
        bpy.utils.register_class(cls)
    register_scene_props()


def unregister():
    unregister_scene_props()
    for cls in reversed(operator_classes):
        bpy.utils.unregister_class(cls)
