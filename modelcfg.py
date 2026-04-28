"""
DayZ Geometry Maker - model.cfg generator
Writes a model.cfg alongside the exported P3D.

model.cfg structure:
  class CfgSkeletons { class <Name> { skeletonBones[] = {boneName, parentBone, ...}; } }
  class CfgModels { class <Name> { sections[] = {...}; skeletonName = ""; class Animations { ... } } }

Sections are derived from hidden selection names on the exported objects.
Skeleton bones come from vertex groups that have a hidden_selection set.
"""

import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_sections(objects):
    """Return a sorted list of unique hidden selection names across all objects."""
    sections = set()
    for obj in objects:
        if not obj.dgm_props.is_dayz_object:
            continue
        for sm in obj.dgm_props.selection_mats:
            name = sm.hidden_selection.strip() if sm.hidden_selection.strip() else sm.vgroup_name
            if name:
                sections.add(name)
    return sorted(sections)


def _collect_bones(objects):
    """
    Return list of (bone_name, parent_name) pairs for vertex groups that have
    a non-empty hidden_selection set. Parent is "" (root) unless the name
    follows a hierarchy convention (not auto-detected here — user sets it).
    """
    bones = {}
    for obj in objects:
        if not obj.dgm_props.is_dayz_object:
            continue
        for sm in obj.dgm_props.selection_mats:
            hs = sm.hidden_selection.strip()
            if hs:
                bones.setdefault(hs, "")
    return [(name, parent) for name, parent in sorted(bones.items())]


def _quote(s):
    return '"{}"'.format(s)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_model_cfg(filepath, objects, model_name=None):
    """
    Write a model.cfg file next to the P3D at filepath.
    model_name defaults to the filename stem.
    objects should be the same list passed to export_objects_as_p3d.
    """
    if model_name is None:
        model_name = os.path.splitext(os.path.basename(filepath))[0]

    cfg_path = os.path.splitext(filepath)[0] + ".cfg"

    sections = _collect_sections(objects)
    bones = _collect_bones(objects)
    skeleton_name = model_name + "_skeleton" if bones else ""

    lines = []

    # ------------------------------------------------------------------
    # CfgSkeletons
    # ------------------------------------------------------------------
    lines.append("class CfgSkeletons")
    lines.append("{")
    if bones:
        lines.append("\tclass {}".format(skeleton_name))
        lines.append("\t{")
        lines.append("\t\tisDiscrete = 1;")
        lines.append("\t\tskeletonBones[] =")
        lines.append("\t\t{")
        for bone, parent in bones:
            lines.append("\t\t\t{}, {},".format(_quote(bone), _quote(parent)))
        # Remove trailing comma on last entry
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("\t\t};")
        lines.append("\t};")
    lines.append("};")
    lines.append("")

    # ------------------------------------------------------------------
    # CfgModels
    # ------------------------------------------------------------------
    lines.append("class CfgModels")
    lines.append("{")
    lines.append("\tclass {}".format(model_name))
    lines.append("\t{")
    lines.append("\t\tmodelTypes[] = {};")

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

    lines.append("\t\tskeletonName = {};".format(_quote(skeleton_name)))
    lines.append("")
    lines.append("\t\tclass Animations")
    lines.append("\t\t{")

    # Emit a template animation entry for each bone so the user can fill it in
    for bone, _ in bones:
        lines.append("\t\t\tclass {}_rotate".format(bone))
        lines.append("\t\t\t{")
        lines.append("\t\t\t\ttype = rotation;")
        lines.append("\t\t\t\tsource = {};".format(_quote(bone)))
        lines.append("\t\t\t\tselection = {};".format(_quote(bone)))
        lines.append("\t\t\t\taxis = {};".format(_quote(bone + "_axis")))
        lines.append("\t\t\t\tminValue = 0;")
        lines.append("\t\t\t\tmaxValue = 1;")
        lines.append("\t\t\t\tangle0 = 0;")
        lines.append("\t\t\t\tangle1 = 3.14159;")
        lines.append("\t\t\t};")

    lines.append("\t\t};")
    lines.append("\t};")
    lines.append("};")
    lines.append("")

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return cfg_path
