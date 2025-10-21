bl_info = {
    "name": "DayZ Geometry Maker",
    "blender": (4, 3, 0),
    "category": "Object",
    "description": "Addon for creating geometry for DayZ Mod",
    "author": "Phlanka.com",
    "version": (1, 0, 3),
}

import bpy
import mathutils
import bmesh
import math

# LOD values for different geometry types - modify these if you need different LOD levels
collections_data = {
    "Geometry": "1.000e+13",
    "View Geometry": "6.000e+15",
    "Fire Geometry": "7.000e+15",
    "Memory": "1.000e+15",
    "View Pilot": "1.100e+3",
    "1": "-1.0",
    "2": "-1.0",
    "3": "-1.0",
    "4": "-1.0"
}

def calculate_faces_after_subdivision(subdivisions):
    # Calculates total faces after subdivision for Fire Geometry
    quad_faces = 6 * (4 ** subdivisions)
    triangle_faces = quad_faces * 2 
    return triangle_faces

# Operator classes for different geometry types
class OBJECT_OT_create_geometry(bpy.types.Operator):
    """Creates basic collision geometry with autocenter property"""
    bl_idname = "object.create_geometry"
    bl_label = "Create Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        create_arma_bounding_boxes("Geometry")
        return {'FINISHED'}

class OBJECT_OT_create_view_geometry(bpy.types.Operator):
    """Creates view geometry for object visibility calculations"""
    bl_idname = "object.create_view_geometry"
    bl_label = "Create View Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        create_arma_bounding_boxes("View Geometry")
        return {'FINISHED'}

class OBJECT_OT_create_fire_geometry(bpy.types.Operator):
    """Creates fire geometry with subdivisions for bullet collision"""
    bl_idname = "object.create_fire_geometry"
    bl_label = "Create Fire Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        
        # Toggle options panel
        context.scene.show_fire_geometry_options = not context.scene.show_fire_geometry_options
        return {'FINISHED'}

class OBJECT_OT_create_memory(bpy.types.Operator):
    """Toggle memory points options panel"""
    bl_idname = "object.create_memory"
    bl_label = "Create Memory"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.show_memory_options = not context.scene.show_memory_options
        return {'FINISHED'}

class OBJECT_OT_create_selected_memory(bpy.types.Operator):
    """Creates selected memory points for the object"""
    bl_idname = "object.create_selected_memory"
    bl_label = "Create Selected Memory Points"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        create_memory_point()
        return {'FINISHED'}

# Main panel UI
class OBJECT_PT_create_dayz_geometry(bpy.types.Panel):
    bl_label = "Create DayZ Geometry"
    bl_idname = "OBJECT_PT_create_dayz_geometry"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "selected_object", text="Select Object")
        layout.operator("object.create_geometry", text="Create Geometry")
        layout.operator("object.create_view_geometry", text="Create View Geometry")
        layout.operator("object.create_view_pilot", text="Create View Pilot")
        
        # Fire Geometry section with collapsible options
        row = layout.row()
        row.operator("object.create_fire_geometry", text="Create Fire Geometry",
                    icon='TRIA_RIGHT' if not context.scene.show_fire_geometry_options else 'TRIA_DOWN')
        
        if context.scene.show_fire_geometry_options:
            box = layout.box()
            box.label(text="Fire Geometry Options")
            box.prop(context.scene, "fire_geometry_quality", text="Quality")
            box.operator("object.create_selected_fire_geometry", text="Create Fire Geometry")
        
        # Memory section with collapsible options
        row = layout.row()
        row.operator("object.create_memory", text="Create Memory", 
                    icon='TRIA_RIGHT' if not context.scene.show_memory_options else 'TRIA_DOWN')
        
        if context.scene.show_memory_options:
            box = layout.box()
            box.label(text="Memory Points")
            box.prop(context.scene, "memory_default_points")
            box.prop(context.scene, "memory_radius_point")
            box.prop(context.scene, "memory_center_point")
            box.prop(context.scene, "memory_bullet_points")
            box.prop(context.scene, "memory_bolt_axis")
            box.prop(context.scene, "memory_bullet_eject")
            box.prop(context.scene, "memory_eye_ads")
            box.operator("object.create_selected_memory", text="Create Selected Memory Points")

        # LOD section with collapsible options
        row = layout.row()
        row.operator("object.create_lods", text="Levels Of Detail", 
                    icon='TRIA_RIGHT' if not context.scene.show_lod_options else 'TRIA_DOWN')
        
        if context.scene.show_lod_options:
            box = layout.box()
            box.prop(context.scene, "create_lod1", text="1")
            box.prop(context.scene, "create_lod2", text="2")
            box.prop(context.scene, "create_lod3", text="3")
            box.prop(context.scene, "create_lod4", text="4")
            box.prop(context.scene, "create_lod5", text="5")
            box.prop(context.scene, "create_lod6", text="6")
            box.operator("object.create_selected_lods", text="Create Selected LODs")

        # Add Export P3D button that checks for ArmaToolbox
        # Prefer checking for the registered operator on bpy.ops instead of importing
        # the addon module directly. The addon may be enabled but not importable by
        # its package name from this script's path.
        try:
            import bpy
            has_export_op = False

            # Common registration: the operator is available as bpy.ops.armatoolbox.export_p3d
            if hasattr(bpy.ops, 'armatoolbox'):
                has_export_op = hasattr(bpy.ops.armatoolbox, 'export_p3d')

            # Fallback: inspect operator registry by bl_idname
            if not has_export_op:
                from bpy.utils import registered_operators
                # registered_operators is an iterable of bl_idnames in newer Blender builds
                try:
                    has_export_op = 'armatoolbox.export_p3d' in registered_operators()
                except Exception:
                    # Older/blender-compatibility: inspect bpy.ops manually already handled
                    pass

            if has_export_op:
                layout.operator("armatoolbox.export_p3d", text="Export P3D")
            else:
                row = layout.row()
                row.label(text="ArmaToolbox not installed or export operator not registered")
                row.operator("wm.url_open", text="Get ArmaToolbox").url = "https://github.com/AlwarrenSidh/ArmAToolbox"
        except Exception:
            # Don't let any unexpected error break the panel draw
            row = layout.row()
            row.label(text="ArmaToolbox check failed")
            row.operator("wm.url_open", text="Get ArmaToolbox").url = "https://github.com/AlwarrenSidh/ArmAToolbox"

# Add new operator for LOD creation
class OBJECT_OT_create_lods(bpy.types.Operator):
    """Show/Hide LOD options"""
    bl_idname = "object.create_lods"
    bl_label = "Levels Of Detail"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.show_lod_options = not context.scene.show_lod_options
        return {'FINISHED'}

# Add new operator for actual LOD creation
class OBJECT_OT_create_selected_lods(bpy.types.Operator):
    """Creates selected LOD versions of the object"""
    bl_idname = "object.create_selected_lods"
    bl_label = "Create Selected LODs"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        create_lod_meshes()
        return {'FINISHED'}

# Add new operator for actual fire geometry creation
class OBJECT_OT_create_selected_fire_geometry(bpy.types.Operator):
    """Creates fire geometry with current quality settings"""
    bl_idname = "object.create_selected_fire_geometry"
    bl_label = "Create Fire Geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
            
        # Check if we're in edit mode
        if context.active_object and context.active_object.mode == 'EDIT':
            self.report({'WARNING'}, "Please exit Edit mode before creating fire geometry")
            return {'CANCELLED'}
            
        create_fire_geometry("Fire Geometry", context.scene.selected_object, context.scene.fire_geometry_quality)
        return {'FINISHED'}

def create_materials_for_selections(obj, is_low_lod=False):
    """Creates and assigns materials based on vertex groups"""
    # Make sure we're in object mode first
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Clear any existing materials
    obj.data.materials.clear()
    
    # For each vertex group
    for vgroup in obj.vertex_groups:
        # Create new material
        mat_name = f"default_{vgroup.name}"
        mat = bpy.data.materials.new(name=mat_name)
        
        # Set up Arma material properties
        if hasattr(mat, "armaMatProps"):
            mat.armaMatProps.isArmaObject = True
            mat.armaMatProps.texture = "dz\\data\\data\\duha.paa"
            mat.armaMatProps.rvMat = "dz\\data\\data\\default.rvmat"
            mat.armaMatProps.colorString = ""
        
        # Add material to object
        obj.data.materials.append(mat)
        
        # Enter edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # Select vertices in this vertex group
        bpy.ops.object.vertex_group_set_active(group=vgroup.name)
        bpy.ops.object.vertex_group_select()
        
        # Select faces that use these vertices
        bpy.ops.mesh.select_face_by_sides()
        
        # Assign material to selected faces
        obj.active_material_index = len(obj.data.materials) - 1
        bpy.ops.object.material_slot_assign()
        
        # Exit edit mode
        bpy.ops.object.mode_set(mode='OBJECT')

    if is_low_lod:
        # For LOD3 and LOD4, combine materials to reduce sections
        combined_material = bpy.data.materials.new(name=f"combined_{obj.name}")
        if hasattr(combined_material, "armaMatProps"):
            combined_material.armaMatProps.isArmaObject = True
            combined_material.armaMatProps.texture = "dz\\data\\data\\duha.paa"
            combined_material.armaMatProps.rvMat = "dz\\data\\data\\default.rvmat"
        obj.data.materials.clear()
        obj.data.materials.append(combined_material)


def create_lod_meshes():
    """Creates LOD versions of the selected object"""
    original_obj = bpy.context.scene.selected_object
    if not original_obj:
        print("No object selected")
        return

    # Set original object as active (for reference only)
    set_active_object(original_obj)
    original_poly_count = len(original_obj.data.polygons)
    print(f"Original mesh has {original_poly_count} polygons")

    # LOD settings with just the basic info needed
    # Format: (checkbox_property, "LOD_name", view_distance)
    # view_distance: 1=1m, 10=10m, 25=25m, etc.
    lod_settings = [
        (bpy.context.scene.create_lod1, "1", 1),    # LOD1: View distance 1m
        (bpy.context.scene.create_lod2, "2", 2),   # LOD2: View distance 10m
        (bpy.context.scene.create_lod3, "3", 3),   # LOD3: View distance 25m
        (bpy.context.scene.create_lod4, "4", 4),   # LOD4: View distance 50m
        (bpy.context.scene.create_lod5, "5", 5),   # LOD5: View distance 75m
        (bpy.context.scene.create_lod6, "6", 6)   # LOD6: View distance 100m
    ]

    for create_lod, name, distance in lod_settings:
        if not create_lod:
            continue

        # Create collection
        if name not in bpy.data.collections:
            collection = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(collection)
        else:
            collection = bpy.data.collections[name]

        # Create copy of original mesh
        lod_obj = original_obj.copy()
        lod_obj.data = original_obj.data.copy()
        lod_obj.name = name

        # Set Arma properties
        if hasattr(lod_obj, "armaObjProps"):
            lod_obj.armaObjProps.isArmaObject = True
            lod_obj.armaObjProps.lod = "-1.0"
            lod_obj.armaObjProps.lodDistance = distance
            lod_obj.armaObjProps.mass = original_obj.armaObjProps.mass
            lod_obj.armaObjProps.weight = 1.0

        # Add forceNoAlpha property to LOD1
        if name == "1":
            if len(lod_obj.armaObjProps.namedProps) == 0:
                lod_obj.armaObjProps.namedProps.add()
            lod_obj.armaObjProps.namedProps[0].name = "forcenotalpha"
            lod_obj.armaObjProps.namedProps[0].value = "1"

        # Link to collection
        collection.objects.link(lod_obj)

        # Copy and setup materials
        for mat_slot in lod_obj.material_slots:
            if mat_slot.material:
                # Create new material for this LOD
                new_mat = mat_slot.material.copy()
                new_mat.name = f"LOD{name}_{mat_slot.material.name}"
                
                # Set up Arma material properties
                if hasattr(new_mat, "armaMatProps"):
                    new_mat.armaMatProps.isArmaObject = True
                    new_mat.armaMatProps.texture = "dz\\data\\data\\duha.paa"
                    new_mat.armaMatProps.rvMat = "dz\\data\\data\\default.rvmat"
                    new_mat.armaMatProps.colorString = ""
                
                # Assign new material to slot
                mat_slot.material = new_mat

        # Skip decimation for LOD1
        if name == "1":
            continue

        # For LOD2-6, apply decimate modifier multiple times based on LOD level
        for i in range(int(name) - 1):  # Subtract 1 since we start at LOD2
            bpy.context.view_layer.objects.active = lod_obj
            decimate = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
            decimate.decimate_type = 'COLLAPSE'
            decimate.ratio = 0.6
            bpy.ops.object.modifier_apply(modifier="Decimate")
            
            current_polys = len(lod_obj.data.polygons)
            print(f"LOD {name} - Iteration {i+1}: {current_polys} polygons")

        print(f"Created LOD {name} with {len(lod_obj.data.polygons)} polygons")

def create_arma_bounding_boxes(collection_name):
    """Creates bounding box geometry for DayZ objects"""
    # Skip if this is View Pilot - it's handled separately
    if collection_name == "View Pilot":
        return create_view_pilot(collection_name)

    # Get the object selected in the UI panel
    original_obj = bpy.context.scene.selected_object

    if original_obj is None or original_obj.type != 'MESH':
        print("Please select a mesh object in the panel.")
        return

    print(f"Original object selected from UI: {original_obj.name}")  # Debug log

    # Calculate bounding box dimensions and center
    bbox_corners = [original_obj.matrix_world @ mathutils.Vector(corner) for corner in original_obj.bound_box]

    # Find min/max coordinates
    min_x = min(v.x for v in bbox_corners)
    max_x = max(v.x for v in bbox_corners)
    min_y = min(v.y for v in bbox_corners)
    max_y = max(v.y for v in bbox_corners)
    min_z = min(v.z for v in bbox_corners)
    max_z = max(v.z for v in bbox_corners)

    # Calculate dimensions and center
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    center_x = (max_x + min_x) / 2
    center_y = (max_y + min_y) / 2
    center_z = (max_z + min_z) / 2

    # Create a new cube
    bpy.ops.mesh.primitive_cube_add(size=1, location=(center_x, center_y, center_z))
    bbox_obj = bpy.context.object
    bbox_obj.name = collection_name  # Set object name

    # Set dimensions
    bbox_obj.scale = (width / 1, depth / 1, height / 1)

    # Create vertex group and assign all vertices
    vertex_group = bbox_obj.vertex_groups.new(name="Component01")
    vertices = [v.index for v in bbox_obj.data.vertices]
    vertex_group.add(vertices, 1.0, 'REPLACE')

    # Create FHQWeights layer
    bm = bmesh.new()
    bm.from_mesh(bbox_obj.data)
    weight_layer = bm.verts.layers.float.new('FHQWeights')
    for vert in bm.verts:
        vert[weight_layer] = 1.0
    bm.to_mesh(bbox_obj.data)
    bm.free()

    # Set Arma properties including mass/weight
    if hasattr(bbox_obj, "armaObjProps"):
        bbox_obj.armaObjProps.isArmaObject = True
        bbox_obj.armaObjProps.lod = collections_data[collection_name]
        bbox_obj.armaObjProps.mass = 0.0
        bbox_obj.armaObjProps.weight = 1.0

        # Add special properties for basic Geometry
        if collection_name == "Geometry":
            bbox_obj.armaObjProps.namedPropIndex = 0
            if len(bbox_obj.armaObjProps.namedProps) == 0:
                bbox_obj.armaObjProps.namedProps.add()
            bbox_obj.armaObjProps.namedProps[0].name = "autocenter"
            bbox_obj.armaObjProps.namedProps[0].value = "0"

    # Create or get collection
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[collection_name]

    # Move object to collection
    if bbox_obj.users_collection:
        for col in bbox_obj.users_collection:
            col.objects.unlink(bbox_obj)
    collection.objects.link(bbox_obj)

    return bbox_obj

def set_active_object(obj):
    """Sets the given object as active and selected"""
    if obj is None:
        return False
        
    # Deselect all objects
    bpy.ops.object.select_all(action='DESELECT')
    
    # Make our object active and selected
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    return True

def create_memory_point():
    """
    Creates memory points for DayZ objects
    Available points:
    - Default: boundingbox_min, boundingbox_max, invview
    - Center: ce_center for object center
    - Radius: ce_radius for collision radius
    - Bullet Travel: konec hlavne, usti hlavne for bullet trajectory
    - Bolt Axis: Two points defining bolt movement
    - Bullet Eject: nabojnicestart, nabojniceend for casing ejection
    - Eye ADS: eye point for aiming position
    
    Point positions can be customized by modifying the vertex coordinates in the code
    """
    # Get the selected object from the panel UI
    original_obj = bpy.context.scene.selected_object
    if not original_obj:
        print("No object selected in panel")
        return

    # Set original object as active before any operations
    set_active_object(original_obj)

    # Check for existing Memory object
    existing_memory = None
    if "Memory" in bpy.data.collections:
        for obj in bpy.data.collections["Memory"].objects:
            if obj.name.startswith("Memory"):
                existing_memory = obj
                break

    # Calculate center using the same method as bounding boxes
    world_matrix = original_obj.matrix_world
    bbox_corners = [world_matrix @ mathutils.Vector(corner) for corner in original_obj.bound_box]

    # Find min/max coordinates
    min_x = min(v.x for v in bbox_corners)
    max_x = max(v.x for v in bbox_corners)
    min_y = min(v.y for v in bbox_corners)
    max_y = max(v.y for v in bbox_corners)
    min_z = min(v.z for v in bbox_corners)
    max_z = max(v.z for v in bbox_corners)

    # Calculate dimensions and center
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    center_x = (max_x + min_x) / 2
    center_y = (max_y + min_y) / 2
    center_z = (max_z + min_z) / 2

    # Calculate bounding sphere radius (using distance to furthest corner)
    corners = [
        (max_x, max_y, max_z), (max_x, max_y, min_z),
        (max_x, min_y, max_z), (max_x, min_y, min_z),
        (min_x, max_y, max_z), (min_x, max_y, min_z),
        (min_x, min_y, max_z), (min_x, min_y, min_z)
    ]
    
    # Calculate true bounding sphere radius as distance to furthest corner
    center = mathutils.Vector((center_x, center_y, center_z))
    sphere_radius = max([(mathutils.Vector(corner) - center).length for corner in corners])

    # Calculate invview position (1.75 times radius for tighter framing)
    invview_x = center_x
    invview_y = min_y - (sphere_radius * 1.75)  # Move in front of object
    invview_z = center_z

    # Create vertices list with required points
    vertices = []
    vgroups = []
    
    # Track existing vertex groups to avoid duplicates
    existing_groups = set()
    if existing_memory:
        existing_groups = {vg.name for vg in existing_memory.vertex_groups}
    
    if bpy.context.scene.memory_default_points:
        # Add required points if they don't exist
        if 'boundingbox_max' not in existing_groups:
            vertices.append((max_x, min_y, max_z))  # boundingbox_max
            vgroups.append(("boundingbox_max", len(vertices)-1))
            
        if 'boundingbox_min' not in existing_groups:
            vertices.append((min_x, max_y, min_z))  # boundingbox_min
            vgroups.append(("boundingbox_min", len(vertices)-1))
            
        if 'invview' not in existing_groups:
            vertices.append((invview_x, invview_y, invview_z))  # invview
            vgroups.append(("invview", len(vertices)-1))
    
    if bpy.context.scene.memory_radius_point and 'ce_radius' not in existing_groups:
        # Place ce_radius at center, offset by sphere radius in -X direction
        radius_point = (center_x - sphere_radius, center_y, center_z)
        vertices.append(radius_point)  # ce_radius
        vgroups.append(("ce_radius", len(vertices)-1))
    
    if bpy.context.scene.memory_center_point and 'ce_center' not in existing_groups:
        vertices.append((center_x, center_y, center_z))  # ce_center
        vgroups.append(("ce_center", len(vertices)-1))

    if bpy.context.scene.memory_bullet_points:
        if 'konec hlavne' not in existing_groups:
            vertices.append((-0.214730, -0.001864, 0.113638))  # konec hlavne
            vgroups.append(("konec hlavne", len(vertices)-1))
        
        if 'usti hlavne' not in existing_groups:
            vertices.append((-0.725986, -0.001864, 0.113638))  # usti hlavne
            vgroups.append(("usti hlavne", len(vertices)-1))

    if bpy.context.scene.memory_bolt_axis:
        if 'bolt_axis' not in existing_groups:
            # Add both vertices
            start_idx = len(vertices)
            vertices.extend([
                (-0.027365, 0.000002, 0.129440),  # First bolt axis point
                (0.156166, 0.000002, 0.129440)    # Second bolt axis point
            ])
            # Add single vertex group for both points
            vgroups.append(("bolt_axis", [start_idx, start_idx + 1]))

    if bpy.context.scene.memory_bullet_eject:
        if 'nabojnicestart' not in existing_groups:
            vertices.append((-0.110412, -0.024278, 0.144729))  # nabojnicestart
            vgroups.append(("nabojnicestart", len(vertices)-1))
        
        if 'nabojniceend' not in existing_groups:
            vertices.append((-0.110412, -0.068180, 0.145269))  # nabojniceend
            vgroups.append(("nabojniceend", len(vertices)-1))

    if bpy.context.scene.memory_eye_ads:
        if 'eye' not in existing_groups:
            vertices.append((0.219703, -0.001609, 0.185810))  # eye
            vgroups.append(("eye", len(vertices)-1))

    if not vertices:
        print("No new memory points to add")
        return

    if existing_memory:
        # Ensure we're in object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Add new vertices to existing mesh
        original_vert_count = len(existing_memory.data.vertices)
        
        # Create temporary mesh for new points
        temp_mesh = bpy.data.meshes.new("temp")
        temp_mesh.vertices.add(len(vertices))
        temp_mesh.vertices.foreach_set("co", [coord for v in vertices for coord in v])
        
        # Join meshes
        existing_memory.data.vertices.add(len(vertices))
        for i, v in enumerate(temp_mesh.vertices):
            existing_memory.data.vertices[original_vert_count + i].co = v.co
        
        # Create new vertex groups
        for name, index_data in vgroups:
            vg = existing_memory.vertex_groups.new(name=name)
            if isinstance(index_data, list):
                # Multiple vertices for this group (bolt_axis)
                for idx in index_data:
                    vg.add([original_vert_count + idx], 1.0, 'REPLACE')
            else:
                # Single vertex for this group
                vg.add([original_vert_count + index_data], 1.0, 'REPLACE')
        
        # Cleanup
        bpy.data.meshes.remove(temp_mesh)
        memory_obj = existing_memory
        
    else:
        # Create new mesh
        mesh = bpy.data.meshes.new("Memory")
        memory_obj = bpy.data.objects.new("Memory", mesh)
        
        # Create vertices
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set("co", [coord for v in vertices for coord in v])
        mesh.update()

        # Link object to scene
        bpy.context.collection.objects.link(memory_obj)
        bpy.context.view_layer.objects.active = memory_obj
        memory_obj.select_set(True)

        # Create vertex groups and assign vertices
        for name, index_data in vgroups:
            vg = memory_obj.vertex_groups.new(name=name)
            if isinstance(index_data, list):
                # Multiple vertices for this group
                for idx in index_data:
                    vg.add([idx], 1.0, 'REPLACE')
            else:
                # Single vertex for this group
                vg.add([index_data], 1.0, 'REPLACE')

        # Set Arma properties
        if hasattr(memory_obj, "armaObjProps"):
            memory_obj.armaObjProps.isArmaObject = True
            memory_obj.armaObjProps.lod = collections_data["Memory"]

        # Move to Memory collection
        if "Memory" not in bpy.data.collections:
            collection = bpy.data.collections.new("Memory")
            bpy.context.scene.collection.children.link(collection)
        else:
            collection = bpy.data.collections["Memory"]

        if memory_obj.users_collection:
            for col in memory_obj.users_collection:
                col.objects.unlink(memory_obj)
        collection.objects.link(memory_obj)

def create_view_pilot(collection_name):
    """Creates View Pilot geometry by copying the original model"""
    # Get the selected object from the panel UI
    original_obj = bpy.context.scene.selected_object
    if not original_obj:
        print("No object selected in panel")
        return

    # Set original object as active
    set_active_object(original_obj)

    # Create a copy of the original mesh
    pilot_obj = original_obj.copy()
    pilot_obj.data = original_obj.data.copy()
    pilot_obj.name = collection_name

    # Set Arma properties
    if hasattr(pilot_obj, "armaObjProps"):
        pilot_obj.armaObjProps.isArmaObject = True
        pilot_obj.armaObjProps.lod = collections_data[collection_name]
        pilot_obj.armaObjProps.mass = original_obj.armaObjProps.mass
        pilot_obj.armaObjProps.weight = 1.0

    # Apply materials based on vertex groups
    create_materials_for_selections(pilot_obj)

    # Create or get collection
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[collection_name]

    # Move object to the correct collection
    if pilot_obj.users_collection:
        for col in pilot_obj.users_collection:
            col.objects.unlink(pilot_obj)
    collection.objects.link(pilot_obj)

    return pilot_obj

# Modify the View Pilot operator to use the new function
class OBJECT_OT_create_view_pilot(bpy.types.Operator):
    """Creates view pilot geometry"""
    bl_idname = "object.create_view_pilot"
    bl_label = "Create View Pilot"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.scene.selected_object:
            self.report({'ERROR'}, "Please select an object in the panel first")
            return {'CANCELLED'}
        create_view_pilot("View Pilot")
        return {'FINISHED'}

# Registration code
classes = (
    OBJECT_OT_create_geometry,
    OBJECT_OT_create_view_geometry,
    OBJECT_OT_create_fire_geometry,
    OBJECT_OT_create_selected_fire_geometry,
    OBJECT_OT_create_view_pilot,
    OBJECT_OT_create_memory,
    OBJECT_OT_create_selected_memory,
    OBJECT_OT_create_lods,
    OBJECT_OT_create_selected_lods,
    OBJECT_PT_create_dayz_geometry
)

def register():
    """Registers all classes and properties for the addon"""
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add property for object selection
    bpy.types.Scene.selected_object = bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Target Object"
    )
    
    # Add memory point options
    bpy.types.Scene.memory_default_points = bpy.props.BoolProperty(
        name="Default Points",
        description="Create boundingbox_min, boundingbox_max, and invview points",
        default=True
    )
    bpy.types.Scene.memory_radius_point = bpy.props.BoolProperty(
        name="Add Radius Point",
        description="Add ce_radius point to memory",
        default=False
    )
    bpy.types.Scene.memory_center_point = bpy.props.BoolProperty(
        name="Add Center Point",
        description="Add ce_center point to memory",
        default=False
    )
    bpy.types.Scene.memory_bullet_points = bpy.props.BoolProperty(
        name="Add Bullet Travel Points",
        description="Add konec hlavne and usti hlavne points",
        default=False
    )
    bpy.types.Scene.memory_bolt_axis = bpy.props.BoolProperty(
        name="Add Bolt Axis Points",
        description="Add bolt axis points for weapon mechanics",
        default=False
    )
    bpy.types.Scene.memory_bullet_eject = bpy.props.BoolProperty(
        name="Add Bullet Eject Points",
        description="Add nabojnicestart and nabojniceend points",
        default=False
    )
    
    bpy.types.Scene.memory_eye_ads = bpy.props.BoolProperty(
        name="Add Eye ADS Point",
        description="Add eye point for ADS position",
        default=False
    )

    # Add property to track memory section expansion
    bpy.types.Scene.show_memory_options = bpy.props.BoolProperty(
        default=False
    )

    # Add property to track LOD section expansion
    bpy.types.Scene.show_lod_options = bpy.props.BoolProperty(
        default=False
    )

    # Add LOD properties
    bpy.types.Scene.create_lod1 = bpy.props.BoolProperty(
        name="LOD 1",
        description="Create LOD1 (High detail, 1m view distance)",
        default=False
    )
    bpy.types.Scene.create_lod2 = bpy.props.BoolProperty(
        name="LOD 2",
        description="Create LOD2 (Medium detail, 2m view distance)",
        default=False
    )
    bpy.types.Scene.create_lod3 = bpy.props.BoolProperty(
        name="LOD 3",
        description="Create LOD3 (Low detail, 5m view distance)",
        default=False
    )
    bpy.types.Scene.create_lod4 = bpy.props.BoolProperty(
        name="LOD 4",
        description="Create LOD4 (Lowest detail, 10m view distance)",
        default=False
    )
    bpy.types.Scene.create_lod5 = bpy.props.BoolProperty(
        name="LOD 5",
        description="Create LOD5 (Very low detail, 75m view distance)",
        default=False
    )
    bpy.types.Scene.create_lod6 = bpy.props.BoolProperty(
        name="LOD 6",
        description="Create LOD6 (Minimal detail, 100m view distance)",
        default=False
    )

    # Add Fire Geometry options
    bpy.types.Scene.show_fire_geometry_options = bpy.props.BoolProperty(
        name="Show Fire Geometry Options",
        description="Show options for creating Fire Geometry",
        default=False
    )

    # Add Fire Geometry quality
    bpy.types.Scene.fire_geometry_quality = bpy.props.IntProperty(
        name="Fire Geometry Quality",
        description="1 = low polygon count, 10 = high polygon count",
        min=1,
        max=10, 
        default=2
    )

def unregister():
    """Unregisters all classes and properties for the addon"""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    del bpy.types.Scene.selected_object
    del bpy.types.Scene.memory_default_points
    del bpy.types.Scene.memory_radius_point
    del bpy.types.Scene.memory_center_point
    del bpy.types.Scene.memory_bullet_points
    del bpy.types.Scene.memory_bolt_axis
    del bpy.types.Scene.memory_bullet_eject
    del bpy.types.Scene.memory_eye_ads
    del bpy.types.Scene.show_memory_options
    del bpy.types.Scene.show_lod_options
    del bpy.types.Scene.create_lod1
    del bpy.types.Scene.create_lod2
    del bpy.types.Scene.create_lod3
    del bpy.types.Scene.create_lod4
    del bpy.types.Scene.create_lod5
    del bpy.types.Scene.create_lod6
    del bpy.types.Scene.show_fire_geometry_options
    del bpy.types.Scene.fire_geometry_quality

def check_polygon_count(obj):
    """Checks if polygon count is within recommended limits"""
    poly_count = len(obj.data.polygons)
    
    if poly_count > 32768:  # DirectX9 vertex normal limit
        print(f"Warning: LOD has {poly_count} polygons, which exceeds the recommended maximum of 32,768")
    elif poly_count < 500 and obj.name == "4":  # LOD4
        print(f"Warning: Lowest LOD has {poly_count} polygons, recommended minimum is 500")

def validate_lod(obj):
    """Validates LOD according to Bohemia Interactive guidelines"""
    # Check polygon count
    poly_count = len(obj.data.polygons)
    
    # Check material sections
    material_count = len(obj.data.materials)
    
    # Check for empty named selections
    vertex_groups = obj.vertex_groups
    
    warnings = []
    if poly_count > 32768:
        warnings.append(f"Polygon count ({poly_count}) exceeds limit")
    if obj.name == "4" and material_count > 2:
        warnings.append(f"LOD4 has {material_count} materials, recommended maximum is 2")
    
    return warnings

def create_fire_geometry(collection_name, original_obj, quality):
    """Creates fire geometry with proper subdivision and shrinkwrapping"""
    # Create basic bounding box
    bbox_obj = create_arma_bounding_boxes(collection_name)
    
    if not bbox_obj:
        return None

    # Ensure we're in object mode to start
    if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Convert to mesh for editing
    bbox_obj.select_set(True)
    bpy.context.view_layer.objects.active = bbox_obj
    
    # Enter edit mode for subdivide and triangulate
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Apply subdivisions
    print(f"Applying {quality} cuts...")
    bpy.ops.mesh.subdivide(number_cuts=quality)
    
    # Triangulate
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    print("Triangulation completed")
    
    # Return to object mode for modifier operations
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Add and configure shrinkwrap modifier
    shrinkwrap = bbox_obj.modifiers.new(name="Shrinkwrap", type='SHRINKWRAP')
    shrinkwrap.target = original_obj
    shrinkwrap.offset = 0.02
    shrinkwrap.wrap_mode = 'OUTSIDE_SURFACE'
    
    # Apply the modifier (in object mode)
    bpy.ops.object.modifier_apply(modifier="Shrinkwrap")
    
    # Verify counts
    vert_count = len(bbox_obj.data.vertices)
    tri_count = len(bbox_obj.data.polygons)
    print(f"Fire Geometry created with {vert_count} vertices and {tri_count} triangles")
    
    # Ensure object is named correctly
    bbox_obj.name = "Component01"
    
    return bbox_obj

if __name__ == "__main__":
    register()
