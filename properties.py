"""
DayZ Geometry Maker - Properties
Standalone property definitions (no ArmaToolbox dependency).
"""

import bpy

LOD_PRESETS = [
    ('-1.0',      'Custom',                    'Custom Viewing Distance'),
    ('1.000e+3',  'View Gunner',               'View Gunner'),
    ('1.100e+3',  'View Pilot',                'View Pilot'),
    ('1.200e+3',  'View Cargo',                'View Cargo'),
    ('1.000e+4',  'Stencil Shadow',            'Stencil Shadow'),
    ('1.001e+4',  'Stencil Shadow 2',          'Stencil Shadow 2'),
    ('1.100e+4',  'Shadow Volume',             'Shadow Volume'),
    ('1.101e+4',  'Shadow Volume 2',           'Shadow Volume 2'),
    ('1.000e+13', 'Geometry',                  'Geometry'),
    ('1.000e+15', 'Memory',                    'Memory'),
    ('2.000e+15', 'Land Contact',              'Land Contact'),
    ('3.000e+15', 'Roadway',                   'Roadway'),
    ('4.000e+15', 'Paths',                     'Paths'),
    ('5.000e+15', 'HitPoints',                 'Hit Points'),
    ('6.000e+15', 'View Geometry',             'View Geometry'),
    ('7.000e+15', 'Fire Geometry',             'Fire Geometry'),
    ('8.000e+15', 'View Cargo Geometry',       'View Cargo Geometry'),
    ('9.000e+15', 'View Cargo Fire Geometry',  'View Cargo Fire Geometry'),
    ('1.000e+16', 'View Commander',            'View Commander'),
    ('1.100e+16', 'View Commander Geometry',   'View Commander Geometry'),
    ('1.200e+16', 'View Commander Fire Geometry', 'View Commander Fire Geometry'),
    ('1.300e+16', 'View Pilot Geometry',       'View Pilot Geometry'),
    ('1.400e+16', 'View Pilot Fire Geometry',  'View Pilot Fire Geometry'),
    ('1.500e+16', 'View Gunner Geometry',      'View Gunner Geometry'),
    ('1.600e+16', 'View Gunner Fire Geometry', 'View Gunner Fire Geometry'),
    ('1.700e+16', 'Sub Parts',                 'Sub Parts'),
    ('1.800e+16', 'Shadow Volume - View Cargo','Cargo View shadow volume'),
    ('1.900e+16', 'Shadow Volume - View Pilot','Pilot View shadow volume'),
    ('2.000e+16', 'Shadow Volume - View Gunner','Gunner View shadow volume'),
    ('2.100e+16', 'Wreck',                     'Wreckage'),
    ('2.000e+13', 'Geometry Buoyancy',         'Geometry Buoyancy'),
    ('4.000e+13', 'Geometry PhysX',            'Geometry PhysX'),
    ('2.000e+4',  'Edit',                      'Edit'),
]

GEOMETRY_LODS = {
    '1.000e+13', '6.000e+15', '7.000e+15', '8.000e+15', '9.000e+15',
    '1.100e+16', '1.200e+16', '1.300e+16', '1.400e+16', '1.500e+16',
    '1.600e+16', '2.000e+13', '4.000e+13',
}

LODS_NEEDING_RESOLUTION = {
    '-1.0', '1.200e+3', '1.000e+4', '1.001e+4', '1.100e+4',
    '1.101e+4', '8.000e+15', '1.800e+16', '2.000e+4',
}

TEXTURE_TYPES = [
    ("CO", "CO", "Color Value"),
    ("CA", "CA", "Texture with Alpha"),
    ("LCO", "LCO", "Terrain Texture Layer Color"),
    ("SKY", "SKY", "Sky texture"),
    ("NO", "NO", "Normal Map"),
    ("NS", "NS", "Normal map specular with Alpha"),
    ("NOF", "NOF", "Normal map faded"),
    ("NON", "NON", "Normal map noise"),
    ("NOHQ", "NOHQ", "Normal map High Quality"),
    ("NOPX", "NOPX", "Normal Map with paralax"),
    ("NOVHQ", "NOVHQ", "two-part DXT5 compression"),
    ("DT", "DT", "Detail Texture"),
    ("CDT", "CDT", "Colored detail texture"),
    ("MCO", "MCO", "Multiply color"),
    ("DTSMDI", "DTSMDI", "Detail SMDI map"),
    ("MC", "MC", "Macro Texture"),
    ("AS", "AS", "Ambient Shadow texture"),
    ("ADS", "ADS", "Ambient Shadow in Blue"),
    ("PR", "PR", "Ambient shadow from directions"),
    ("SM", "SM", "Specular Map"),
    ("SMDI", "SMDI", "Specular Map, optimized"),
    ("mask", "mask", "Mask for multimaterial"),
    ("TI", "TI", "Thermal imaging map"),
]

TEXTURE_CLASS = [
    ("Texture", "Texture", "Texture Map"),
    ("Color", "Color", "Procedural Color"),
    ("Custom", "Custom", "Custom Procedural String"),
]


def lod_name(lod_float):
    for preset in LOD_PRESETS:
        if lod_float == float(preset[0]):
            return preset[1]
    return "Unknown"


def needs_resolution(lod):
    if isinstance(lod, float):
        lod = format(lod, ".3e")
        lod_map = {
            '-1.0': '-1.0',
            '1.200e+03': '1.200e+3',
            '1.000e+04': '1.000e+4',
            '1.001e+04': '1.001e+4',
            '1.100e+04': '1.100e+4',
            '1.101e+04': '1.101e+4',
            '8.000e+15': '8.000e+15',
            '1.800e+16': '1.800e+16',
            '2.000e+04': '2.000e+4',
        }
        lod = lod_map.get(lod, lod)
    return lod in LODS_NEEDING_RESOLUTION


class DGMNamedProperty(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name", description="Property Name")
    value: bpy.props.StringProperty(name="Value", description="Property Value")


class DGMSelectionMaterial(bpy.types.PropertyGroup):
    """
    Per-vertex-group material settings.
    Each vertex group = one named selection in the P3D.
    Faces whose vertices belong to this group get this texture + rvmat in the export.
    hidden_selection makes this selection animatable in model.cfg (e.g. camo, damage states).
    """
    vgroup_name: bpy.props.StringProperty(
        name="Vertex Group",
        description="Name of the vertex group this applies to",
    )
    hidden_selection: bpy.props.StringProperty(
        name="Hidden Selection",
        description=(
            "If set, this named selection is a 'hidden selection' used by model.cfg "
            "for animations (e.g. camo1, damage_hull). Leave blank for geometry-only selections"
        ),
        default="",
    )
    bake_texture: bpy.props.BoolProperty(
        name="Bake Texture",
        description=(
            "Bake this selection's texture using DayZ Texture Tools before export. "
            "The baked CO texture and RVMAT will be assigned automatically"
        ),
        default=False,
    )
    texture: bpy.props.StringProperty(
        name="Texture (.paa)",
        description="P: drive path to texture, e.g. P:\\DZ\\data\\texture_co.paa",
        default="",
    )
    rv_mat: bpy.props.StringProperty(
        name="RVMat (.rvmat)",
        description="P: drive path to rvmat, e.g. P:\\DZ\\data\\material.rvmat",
        default="",
    )


class DGMObjectProperties(bpy.types.PropertyGroup):
    is_dayz_object: bpy.props.BoolProperty(
        name="Is DayZ Object",
        description="Is this a DayZ/Arma exportable object",
        default=False,
    )
    lod: bpy.props.EnumProperty(
        name="LOD Type",
        description="Type of LOD",
        items=LOD_PRESETS,
        default='-1.0',
    )
    lod_distance: bpy.props.FloatProperty(
        name="Distance",
        description="View distance for Custom LOD",
        default=1.0,
    )
    mass: bpy.props.FloatProperty(
        name="Mass",
        description="Object Mass",
        default=0.0,
    )
    named_props: bpy.props.CollectionProperty(
        type=DGMNamedProperty,
        description="Named Properties",
    )
    named_prop_index: bpy.props.IntProperty(default=-1)
    selection_mats: bpy.props.CollectionProperty(
        type=DGMSelectionMaterial,
        description="Per-vertex-group material and hidden selection settings",
    )
    selection_mat_index: bpy.props.IntProperty(default=-1)


class DGMMaterialProperties(bpy.types.PropertyGroup):
    texture: bpy.props.StringProperty(
        name="Face Texture",
        description="Texture path (e.g. dz\\data\\texture.paa)",
        subtype="FILE_PATH",
        default="",
    )
    rv_mat: bpy.props.StringProperty(
        name="RVMat Material",
        description="RVMat path (e.g. dz\\data\\material.rvmat)",
        subtype="FILE_PATH",
        default="",
    )
    tex_type: bpy.props.EnumProperty(
        name="Color Map Type",
        description="Source of color for this surface",
        items=TEXTURE_CLASS,
    )
    color_value: bpy.props.FloatVectorProperty(
        name="Color",
        description="Color for procedural texture",
        subtype='COLOR',
        min=0.0, max=1.0,
        default=(1.0, 1.0, 1.0),
    )
    color_type: bpy.props.EnumProperty(
        name="Color Type",
        description="Texture suffix type",
        items=TEXTURE_TYPES,
    )
    color_string: bpy.props.StringProperty(
        name="Resulting String",
        description="Resulting value for the procedural texture",
    )


property_classes = (
    DGMNamedProperty,
    DGMSelectionMaterial,
    DGMObjectProperties,
    DGMMaterialProperties,
)


def register():
    for cls in property_classes:
        bpy.utils.register_class(cls)

    bpy.types.Object.dgm_props = bpy.props.PointerProperty(
        type=DGMObjectProperties,
        description="DayZ Geometry Maker Object Properties",
    )
    bpy.types.Material.dgm_mat = bpy.props.PointerProperty(
        type=DGMMaterialProperties,
        description="DayZ Geometry Maker Material Properties",
    )


def unregister():
    del bpy.types.Material.dgm_mat
    del bpy.types.Object.dgm_props

    for cls in reversed(property_classes):
        bpy.utils.unregister_class(cls)
