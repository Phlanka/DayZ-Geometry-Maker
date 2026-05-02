"""
DayZ Geometry Maker - model.cfg generator
Writes a model.cfg alongside the exported P3D.

model.cfg structure (DayZ standard):
  class cfgSkeletons { class <Name>_skel { SkeletonBones[] = {...}; } }
  class CfgModels { class Default {...}; class <Name>:Default { sections[]={...}; class Animations{...} } }

Sections come from hidden_selection names on exported objects.
Bones are hidden_selections that also have a texture or bake flag — untextured
selections (geometry-only / shared polys) appear in sections[] only.

If a model.cfg already exists in the output directory, new class blocks are
merged in without overwriting other models already defined there.
"""

import os
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sections(objects, door_cfgs=None):
    """Return sorted list of unique hidden selection names across all objects, including door bones."""
    sections = set()
    for obj in objects:
        if not obj.dgm_props.is_dayz_object:
            continue
        for sm in obj.dgm_props.selection_mats:
            name = sm.hidden_selection.strip() if sm.hidden_selection.strip() else sm.vgroup_name
            if name:
                sections.add(name)
    if door_cfgs:
        sections.update(door_cfgs.keys())
    return sorted(sections)


def _collect_untextured_selections(objects):
    """
    Return set of selection names that have no texture path and no bake flag.
    These are geometry-only / shared-UV selections — they go into sections[]
    but must NOT become skeleton bones or animation entries, since they have
    no animatable material and would generate invalid model.cfg output.
    """
    untextured = set()
    for obj in objects:
        if not obj.dgm_props.is_dayz_object:
            continue
        for sm in obj.dgm_props.selection_mats:
            hs = sm.hidden_selection.strip() if sm.hidden_selection.strip() else sm.vgroup_name
            if hs:
                has_texture = bool(sm.texture.strip()) or sm.bake_texture
                if not has_texture:
                    untextured.add(hs)
    return untextured


def _collect_bones(door_cfgs):
    """
    Return list of (bone_name, parent_name) for door selections only.
    Only selections that are configured as door vertex groups animate in DayZ —
    everything else (camo, damage states, etc.) belongs in sections[] only.
    """
    return [(name, "") for name in sorted(door_cfgs.keys())]


def _collect_door_configs(scene):
    """Return {door_vgroup_name: (closed_angle, open_angle)} for configured doors."""
    out = {}
    if scene is None:
        return out
    for di in range(1, 9):
        vg = getattr(scene, 'dgm_door_{}_vgroup'.format(di), "").strip()
        if not vg:
            continue
        closed = getattr(scene, 'dgm_door_{}_closed_angle'.format(di), 0.0)
        opened = getattr(scene, 'dgm_door_{}_open_angle'.format(di), -1.5708)
        out[vg] = (closed, opened)
    return out


def _quote(s):
    return '"{}"'.format(s)


# ---------------------------------------------------------------------------
# Class block text builders
# ---------------------------------------------------------------------------

def _build_skeleton_block(skeleton_name, bones):
    """Return text for 'class <skeleton_name> { ... };' (no outer cfgSkeletons wrapper)."""
    lines = []
    lines.append("\tclass {}".format(skeleton_name))
    lines.append("\t{")
    lines.append('\t\tskeletonInherit = "";')
    lines.append("\t\tisDiscrete = 1;")
    lines.append("\t\tSkeletonBones[] =")
    lines.append("\t\t{")
    for bone, parent in bones:
        lines.append("\t\t\t{}\t,{},".format(_quote(bone), _quote(parent)))
    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]
    lines.append("\t\t};")
    lines.append("\t};")
    return "\n".join(lines)


def _build_model_block(model_name, skeleton_name, sections, bones, door_cfgs):
    """Return text for 'class <model_name>:Default { ... };' (no outer CfgModels wrapper)."""
    lines = []
    lines.append("\tclass {}:Default".format(model_name))
    lines.append("\t{")
    lines.append("\t\tskeletonName = {};".format(_quote(skeleton_name)))

    if sections:
        lines.append("\t\tsections[] =")
        lines.append("\t\t{")
        for s in sections:
            lines.append("\t\t\t{},".format(_quote(s)))
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("\t\t};")
    else:
        lines.append("\t\tsections[] = {};")

    lines.append("\t\tclass Animations")
    lines.append("\t\t{")

    for bone, _ in bones:
        lines.append("\t\t\tclass {}".format(bone))
        lines.append("\t\t\t{")
        lines.append('\t\t\t\ttype = "rotation";')
        lines.append("\t\t\t\tsource = {};".format(_quote(bone)))
        lines.append("\t\t\t\tselection = {};".format(_quote(bone)))
        lines.append("\t\t\t\taxis = {};".format(_quote(bone + "_axis")))
        lines.append('\t\t\t\t//\t\tsourceAddress = clamp;')
        lines.append("\t\t\t\tminValue = 0.0;")
        lines.append("\t\t\t\tmaxValue = 1.0;")
        if bone in door_cfgs:
            closed, opened = door_cfgs[bone]
            lines.append("\t\t\t\tangle0 = {:.6f};".format(-closed))
            lines.append("\t\t\t\tangle1 = {:.6f};".format(-opened))
        else:
            lines.append("\t\t\t\tangle0 = 0.0;")
            lines.append("\t\t\t\tangle1 = -1.850049;")
        lines.append('\t\t\t\t//\t\tmemory = true;')
        lines.append("\t\t\t};")

    lines.append("\t\t};")
    lines.append("\t};")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Merge helpers — insert/replace class blocks inside an existing model.cfg
# ---------------------------------------------------------------------------

def _find_class_region(text, class_name):
    """
    Find 'class <class_name>' in text (case-insensitive).
    Returns (start, end) of the entire block including trailing ';', or None.
    """
    pattern = r'\bclass\s+' + re.escape(class_name) + r'\b'
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    brace = text.find('{', m.end())
    if brace == -1:
        return None
    depth = 0
    i = brace
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                # consume optional trailing semicolon
                j = end
                while j < len(text) and text[j] in ' \t':
                    j += 1
                if j < len(text) and text[j] == ';':
                    end = j + 1
                return (m.start(), end)
        i += 1
    return None


def _get_block_inner(text, start, end):
    """Return the content between the outermost { } of a class block region."""
    region = text[start:end]
    brace_open = region.index('{')
    depth = 0
    for i, c in enumerate(region[brace_open:], brace_open):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return region[brace_open + 1:i]
    return ""


def _merge_class_into_text(outer_text, outer_class, inner_class_block, inner_class_name):
    """
    Find 'class outer_class { ... }' in outer_text.
    Inside it, replace existing 'class inner_class_name { ... }' with inner_class_block,
    or insert inner_class_block before the closing '}'.
    Returns updated outer_text. If outer_class not found, appends a new wrapper.
    """
    region = _find_class_region(outer_text, outer_class)
    if region is None:
        # outer class doesn't exist — append a fresh one
        fresh = "\nclass {}\n{{\n{}\n}};\n".format(outer_class, inner_class_block)
        return outer_text.rstrip() + "\n" + fresh

    r_start, r_end = region
    inner = _get_block_inner(outer_text, r_start, r_end)

    # Replace or insert the inner class block
    inner_region = _find_class_region(inner, inner_class_name)
    if inner_region:
        i_start, i_end = inner_region
        new_inner = inner[:i_start] + inner_class_block + "\n" + inner[i_end:]
    else:
        new_inner = inner.rstrip() + "\n\n" + inner_class_block + "\n"

    # Reconstruct outer block
    region_text = outer_text[r_start:r_end]
    brace_open = region_text.index('{')
    depth = 0
    for i, c in enumerate(region_text[brace_open:], brace_open):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                new_region = (region_text[:brace_open + 1]
                              + new_inner
                              + region_text[i:])
                return outer_text[:r_start] + new_region + outer_text[r_end:]
    return outer_text


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_model_cfg(filepath, objects, model_name=None):
    """
    Write (or merge into) a model.cfg in the same directory as the P3D.
    DayZ always requires the file to be named 'model.cfg'.
    If a model.cfg already exists, the new model's skeleton and class blocks
    are merged in without touching other models already defined there.
    """
    if model_name is None:
        model_name = os.path.splitext(os.path.basename(filepath))[0]

    cfg_path = os.path.join(os.path.dirname(filepath), "model.cfg")

    try:
        import bpy
        scene = bpy.context.scene
    except Exception:
        scene = None

    door_cfgs = _collect_door_configs(scene)
    sections = _collect_sections(objects, door_cfgs)
    bones = _collect_bones(door_cfgs)
    skeleton_name = model_name + "_skel" if bones else ""

    skel_block = _build_skeleton_block(skeleton_name, bones) if bones else ""
    model_block = _build_model_block(model_name, skeleton_name, sections, bones, door_cfgs)

    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            existing = f.read()

        if bones:
            existing = _merge_class_into_text(existing, "cfgSkeletons", skel_block, skeleton_name)
        existing = _merge_class_into_text(existing, "CfgModels", model_block, model_name)

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(existing)
    else:
        lines = []
        lines.append("class cfgSkeletons")
        lines.append("{")
        if bones:
            lines.append(skel_block)
        lines.append("};")
        lines.append("")
        lines.append("class CfgModels")
        lines.append("{")
        lines.append("\tclass Default")
        lines.append("\t{")
        lines.append("\t\tsections[] = {};")
        lines.append('\t\tsectionsInherit = "";')
        lines.append('\t\tskeletonName = "";')
        lines.append("\t};")
        lines.append(model_block)
        lines.append("};")
        lines.append("")

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    return cfg_path
