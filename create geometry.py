bl_info = {
    "name": "DayZ Geometry Maker",
    "blender": (4, 3, 0),
    "category": "Object",
    "description": "Addon for creating geometry for DayZ Mod",
    "author": "Phlanka.com",
    "version": (1, 0, 0),
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
    "Memory": "1.000e+15" 
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
        create_arma_bounding_boxes("Fire Geometry")
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
        layout.operator("object.create_fire_geometry", text="Create Fire Geometry")
        
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

def create_arma_bounding_boxes(collection_name):
    """
    Creates bounding box geometry for DayZ objects
    Geometry types:
    - Basic Geometry: Simple collision with autocenter
    - View Geometry: Used for object visibility
    - Fire Geometry: Subdivided mesh for bullet collision
    """
    # Get the object selected in the UI panel
    original_obj = bpy.context.scene.selected_object

    if original_obj is None or original_obj.type != 'MESH':
        print("Please select a mesh object in the panel.")
        return

    print(f"Original object selected from UI: {original_obj.name}")  # Debug log

    # Get world-space bounding box coordinates
    world_matrix = original_obj.matrix_world
    bbox_corners = [world_matrix @ mathutils.Vector(corner) for corner in original_obj.bound_box]

    # Find min/max coordinates
    min_x = min(v.x for v in bbox_corners)
    max_x = max(v.x for v in bbox_corners)
    min_y = min(v.y for v in bbox_corners)
    max_y = max(v.y for v in bbox_corners)
    min_z = min(v.z for v in bbox_corners)
    max_z = max(v.z for v in bbox_corners)

    # Calculate dimensions
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z

    # Calculate center position
    center_x = (max_x + min_x) / 2
    center_y = (max_y + min_y) / 2
    center_z = (max_z + min_z) / 2

    # Ensure the collection exists
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[collection_name]

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

    # Move object to the correct collection
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = bbox_obj
    bbox_obj.select_set(True)

    if bbox_obj.users_collection:
        for col in bbox_obj.users_collection:
            col.objects.unlink(bbox_obj)

    collection.objects.link(bbox_obj)

    # Apply Arma Object Properties
    if hasattr(bbox_obj, "armaObjProps"):
        bbox_obj.armaObjProps.isArmaObject = True
        bbox_obj.armaObjProps.lod = collections_data[collection_name]
        
        # Add special properties for Geometry type
        if collection_name == "Geometry":
            bbox_obj.armaObjProps.namedPropIndex = 0
            # Create new named property if it doesn't exist
            if len(bbox_obj.armaObjProps.namedProps) == 0:
                bbox_obj.armaObjProps.namedProps.add()
            bbox_obj.armaObjProps.namedProps[0].name = "autocenter"
            bbox_obj.armaObjProps.namedProps[0].value = "0"

    # Special handling for Fire Geometry
    if collection_name == "Fire Geometry":
        print("Starting Fire Geometry processing...")
        
        # Ensure we're starting in Object mode
        if bpy.context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            print("Switched to Object mode")
            
        # Make sure our bbox_obj is the active object
        bpy.context.view_layer.objects.active = bbox_obj
        bbox_obj.select_set(True)
        print(f"Active object set to: {bbox_obj.name}")
        
        # Step 1: Subdivide the box using fixed subdivisions
        print("Starting subdivision process...")
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Apply subdivisions to match manual process
        print("Applying subdivisions...")
        bpy.ops.mesh.subdivide(number_cuts=4)  # Fourth with 4 cuts
        
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
        print("Triangulation completed")
        
        # Ensure we're back in Object mode before applying modifiers
        bpy.ops.object.mode_set(mode='OBJECT')
        print("Switched back to Object mode")

        # Make sure the bbox_obj is still the active object
        bpy.context.view_layer.objects.active = bbox_obj
        bbox_obj.select_set(True)
        print(f"Active object confirmed as: {bpy.context.active_object.name}")

        try:
            # Step 2: Add Shrinkwrap modifier and apply it
            print("Adding Shrinkwrap modifier...")
            bpy.ops.object.modifier_add(type='SHRINKWRAP')
            
            if "Shrinkwrap" not in bbox_obj.modifiers:
                print("ERROR: Shrinkwrap modifier was not added successfully")
                return
                
            shrinkwrap_modifier = bbox_obj.modifiers["Shrinkwrap"]
            print("Shrinkwrap modifier added successfully")

            # Set the target to the ORIGINAL mesh object
            print(f"Setting target to original object: {original_obj.name}")
            shrinkwrap_modifier.target = original_obj
            shrinkwrap_modifier.offset = 0.01
            print("Modifier settings configured")

            # Apply the Shrinkwrap modifier
            print("Attempting to apply modifier...")
            bpy.ops.object.modifier_apply(modifier="Shrinkwrap")
            print("Modifier applied successfully")
            
        except Exception as e:
            print(f"Error during modifier operations: {str(e)}")
            
        print("Fire Geometry processing completed")

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
        for name, index in vgroups:
            vg = existing_memory.vertex_groups.new(name=name)
            vg.add([original_vert_count + index], 1.0, 'REPLACE')
        
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

# Registration code
classes = (
    OBJECT_OT_create_geometry,
    OBJECT_OT_create_view_geometry,
    OBJECT_OT_create_fire_geometry,
    OBJECT_OT_create_memory,
    OBJECT_OT_create_selected_memory,
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

if __name__ == "__main__":
    register()
