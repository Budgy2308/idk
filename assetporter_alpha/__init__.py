texture_types = {
    'diffuse': ['_diffuse', '_albedo', '_basecolor', '_color', '_col', '_base'],
    'normal': ['_normal', '_nrm', '_nor', '_normalmap'],
    'roughness': ['_roughness', '_rough', '_rgh', '_r'],
    'metallic': ['_metallic', '_metal', '_mtl', '_m'],
    'height': ['_height', '_displacement', '_disp', '_h'],
    'ambient_occlusion': ['_ambient', '_occlusion', '_ao', '_ambientocclusion'],
    'opacity': ['_opacity', '_alpha', '_transparency', '_a'],
    'translucent': ['_translucent', '_translucency', '_sss', '_subsurface'],
    # Neue Texture Types
    'specular': ['_specular', '_spec', '_s', '_reflection'],
    'cavity': ['_cavity', '_cav', '_cvt', '_concavity'],
    'fuzz': ['_fuzz', '_fuzzy', '_fz', '_microfiber'],
    'gloss': ['_gloss', '_glossiness', '_gls', '_smoothness']
}

bl_info = {
    "name": "Assetporter Alpha", 
    "blender": (4, 3, 2),
    "category": "Import-Export",
    "version": (0, 1, 0),
    "author": "EDIT",
    "description": "Professional asset importing tool with LOD and folder structure support",
    "location": "View3D > UI > Assetporter Alpha", 
    "support": "COMMUNITY"
}

import bpy
import os
import re  # Add this line
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, CollectionProperty, PointerProperty, BoolProperty, EnumProperty
from bpy.types import Operator, Panel, PropertyGroup
import json  # Add this line

def get_import_extensions():
    return {
        '.obj': lambda filepath: bpy.ops.import_scene.obj(filepath=filepath), 
        '.fbx': lambda filepath: bpy.ops.import_scene.fbx(filepath=filepath),
        '.3ds': lambda filepath: bpy.ops.import_scene.autodesk_3ds(filepath=filepath),
        '.dae': lambda filepath: bpy.ops.wm.collada_import(filepath=filepath),
        '.abc': lambda filepath: bpy.ops.wm.alembic_import(filepath=filepath),
        '.usd': lambda filepath: bpy.ops.wm.usd_import(filepath=filepath),
        '.usda': lambda filepath: bpy.ops.wm.usd_import(filepath=filepath),
        '.usdc': lambda filepath: bpy.ops.wm.usd_import(filepath=filepath),
        '.ply': lambda filepath: bpy.ops.import_mesh.ply(filepath=filepath),
        '.stl': lambda filepath: bpy.ops.import_mesh.stl(filepath=filepath),
        '.glb': lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath),
        '.gltf': lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath)
    }

class BaseObjectItem(PropertyGroup):
    name: StringProperty(
        name="Object Name",
        description="Name of the object",
        default=""
    )
    selected: bpy.props.BoolProperty(
        name="Select",
        description="Select this individual mesh to import",
        default=False
    )

class LODItem(PropertyGroup):
    name: StringProperty(
        name="LOD Name",
        description="Name of the LOD level",
        default=""
    )
    include: bpy.props.BoolProperty(
        name="Include",
        description="Select this individual LOD level to import",
        default=False
    )
    object_name: StringProperty(
        name="Object Path",
        description="Full path to the object",
        default=""
    )
    base_objects: bpy.props.CollectionProperty(type=BaseObjectItem)

class BatchImportProperties(PropertyGroup):
    def update_folder_path(self, context):
        # Only reset if the path actually changed
        if self.folder_path != self.last_scanned_path:
            self.has_scanned = False
            self.last_scanned_path = ""
            self.search_term = ""
            self.active_common_lods.clear()
            self.lods.clear()
            self.expanded_states = ""
            # Clear texture related properties
            self.textures.clear()
            self.active_texture_resolutions.clear()
            self.texture_resolution_cache = ""

    folder_path: StringProperty(
        name="Asset Folders",
        description="Select folders containing your assets (separate multiple paths with ;)",
        subtype='DIR_PATH',
        update=update_folder_path
    )
    lods: CollectionProperty(type=LODItem)
    common_lods: CollectionProperty(type=LODItem)
    active_common_lod: bpy.props.StringProperty(default="")
    has_scanned: bpy.props.BoolProperty(default=False)
    last_scanned_path: bpy.props.StringProperty(default="")
    cached_object_names: bpy.props.StringProperty(default="")
    active_common_lods: bpy.props.CollectionProperty(type=LODItem)
    # Add dynamic property for storing expanded states
    expanded_items: bpy.props.StringProperty(default="")

    # Keep only this one expanded_states definition
    expanded_states: StringProperty(
        name="Expanded States",
        default="",
        description="Stores which items are expanded"
    )

    def update_search(self, context):
        # Force immediate UI redraw
        for area in context.screen.areas:
            area.tag_redraw()
        # Force expanded state recalculation
        self.expanded_states = self.expanded_states

    search_term: StringProperty(
        name="Search",
        description="Filter objects by name",
        default="",
        options={'TEXTEDIT_UPDATE', 'SKIP_SAVE'},
        update=update_search
    )

    textures: CollectionProperty(type=LODItem)  # Add this line for textures

    def is_expanded(self, base_name):
        states = self.expanded_states.split(',') if self.expanded_states else []
        return base_name.replace('\\', '/') in states

    def toggle_expanded(self, base_name):
        base_name = base_name.replace('\\', '/')
        states = self.expanded_states.split(',') if self.expanded_states else []
        if base_name in states:
            states.remove(base_name)
        else:
            states.append(base_name)
        self.expanded_states = ','.join(filter(None, states))

    def expand_all(self, expand=True):
        object_groups = {}
        for lod in self.lods:
            base_name = lod.object_name
            clean_name = base_name.replace('\\', '/')
            if clean_name not in object_groups:
                object_groups[clean_name] = True
        
        if expand:
            self.expanded_states = ','.join(object_groups.keys())
        else:
            self.expanded_states = ""

    # Add properties to store previous selections
    previous_selections: StringProperty(default="")
    previous_quick_selections: StringProperty(default="")

    def store_selections(self):
        selections = []
        
        # Store active LODs from Quick Select
        for lod in self.active_common_lods:
            selections.append(f"QUICK:{lod.name}")
        
        # Store all LOD selections (both manual and Quick Select)
        for lod in self.lods:
            if not hasattr(lod, 'base_objects'):  # LOD items
                if lod.include:
                    selections.append(f"LOD:{lod.name}")
            else:  # BASE items
                for base_obj in lod.base_objects:
                    if base_obj.selected:
                        selections.append(f"BASE:{lod.name}:{base_obj.name}")
        
        self.previous_selections = ','.join(selections)
        
        # Store Quick Select buttons separately
        quick_selections = []
        for lod in self.active_common_lods:
            quick_selections.append(lod.name)
        self.previous_quick_selections = ','.join(quick_selections)
        
        print(f"Stored selections: {self.previous_selections}")
        print(f"Stored quick selections: {self.previous_quick_selections}")

    def restore_selections(self):
        if not self.previous_selections:
            return
        
        selected_items = self.previous_selections.split(',')
        
        # First restore Quick Select buttons
        quick_items = [item.split(':')[1] for item in selected_items if item.startswith('QUICK:')]
        self.active_common_lods.clear()
        for lod_name in quick_items:
            new_lod = self.active_common_lods.add()
            new_lod.name = lod_name
        
        # Then restore all LOD selections
        for lod in self.lods:
            if not hasattr(lod, 'base_objects'):  # LOD items
                lod.include = f"LOD:{lod.name}" in selected_items or any(f"QUICK:LOD{i}" in selected_items for i in range(10))
            else:  # BASE items
                for base_obj in lod.base_objects:
                    base_obj.selected = f"BASE:{lod.name}:{base_obj.name}" in selected_items
        
        print(f"Restored from: {self.previous_selections}")
        print(f"Restored quick selections: {self.previous_quick_selections}")

    # Add property to store expanded states
    previous_expanded_states: StringProperty(default="")

    def debug_print_state(self, context, stage):
        """Helper to print current state for debugging"""
        props = context.scene.batch_import_props
        print(f"\n=== {stage} ===")
        print(f"Folder Path: {props.folder_path}")
        print(f"Last Scanned Path: {props.last_scanned_path}")
        print(f"Previous Selections: {props.previous_selections}")
        print(f"Previous Quick Selections: {props.previous_quick_selections}")
        print(f"Expanded States: {props.expanded_states}")
        print("Selected Objects:")
        for lod in props.lods:
            if hasattr(lod, 'base_objects'):
                print(f"  BASE {lod.name}:")
                for obj in lod.base_objects:
                    print(f"    - {obj.name}: {obj.selected}")
            else:
                print(f"  LOD {lod.name}: {lod.include}")
        print("=====================\n")

    imported_containers: bpy.props.StringProperty(default="")

    # Add property for active folder
    def get_folder_items(self, context):
        items = []
        seen = set()
        for lod in self.lods:
            folder_path = os.path.dirname(lod.object_name)
            last_folder = os.path.basename(folder_path) if folder_path else "Root"
            if last_folder not in seen:
                items.append((last_folder, last_folder, ""))
                seen.add(last_folder)
        return items

    active_folder: bpy.props.EnumProperty(
        items=get_folder_items,
        name="Active Folder",
        description="Currently selected folder tab"
    )

    def is_quick_selected(self, lod_name):
        """Check if a LOD type is currently selected via Quick Select"""
        return any(lod.name == lod_name for lod in self.active_common_lods)

    group_active_states: StringProperty(default="")  # Stores which groups are toggled via group button

    active_texture_resolutions: bpy.props.CollectionProperty(type=LODItem)
    texture_resolution_cache: StringProperty(default="")  # Add this line to cache resolutions
    previous_texture_selections: StringProperty(default="")  # Add this line
    quick_selected_items: StringProperty(default="")  # Track items selected by Quick Select
    object_selected_items: StringProperty(default="")  # Track items selected by Object Select

    texture_section_expanded: BoolProperty(
        name="Expand Texture Resolutions",
        description="Show/hide texture resolutions",
        default=False
    )

    active_quickres_resolutions: bpy.props.CollectionProperty(type=LODItem)  # New property for QuickRes state

    active_quickres_states: StringProperty(
        name="Active QuickRes States",
        description="Stores which QuickRes buttons are visually active",
        default=""
    )

def create_folder_panel(folder_name):
    valid_id = "".join(c for c in folder_name.upper() if c.isalnum() or c == '_')

    class VIEW3D_PT_folder_panel(Panel):
        bl_idname = f'VIEW3D_PT_FOLDER_{valid_id}_001'
        bl_label = folder_name
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = "Assetporter beta"
        bl_options = {'DEFAULT_CLOSED'}
        bl_order = 2
        folder = folder_name

        @classmethod
        def poll(cls, context):
            if not hasattr(context.scene, "batch_import_props"):
                return False
            props = context.scene.batch_import_props
            if not props.has_scanned or not props.lods:
                return False

            # Group objects by base name in this folder
            object_groups = {}
            lod_pattern = re.compile(r'lod(\d+)')
            
            # Check if panel name matches search term or if any objects match
            has_visible_objects = False
            if props.search_term:
                # Check folder name
                if props.search_term.lower() in cls.folder.lower():
                    has_visible_objects = True
                
                # Always check objects even if folder name matches
                for lod in props.lods:
                    current_folder = os.path.basename(os.path.dirname(lod.object_name))
                    if current_folder == cls.folder:
                        base_name = os.path.splitext(os.path.basename(lod.name))[0]
                        if any(props.search_term.lower() in part.lower() 
                        for part in base_name.replace('\\', '/').split('/')):
                            has_visible_objects = True
            else:
                has_visible_objects = True

            # Hide panel if neither panel name nor objects match search
            if not has_visible_objects:
                return False

            # Check if everything is quick-selected (not group-selected)
            all_quick_selected = True
            for lod in props.lods:
                current_folder = os.path.basename(os.path.dirname(lod.object_name))
                if current_folder == cls.folder:
                    base_name = os.path.splitext(os.path.basename(lod.name))[0]
                    match = lod_pattern.search(base_name.lower())
                    if match:  # LOD items
                        lod_name = f"LOD{match.group(1)}"
                        if not props.is_quick_selected(lod_name):
                            all_quick_selected = False
                            break
                    else:  # BASE items
                        if not props.is_quick_selected("BASE"):
                            all_quick_selected = False
                            break

            # Hide panel only if everything is quick-selected
            if all_quick_selected:
                return False

            return True

        def draw(self, context):
            layout = self.layout
            props = context.scene.batch_import_props
            
            object_groups = {}
            lod_pattern = re.compile(r'lod(\d+)')
            
            # First, collect and sort all objects in this folder while preserving folder order
            folder_items = []
            for lod in props.lods:
                if os.path.basename(os.path.dirname(lod.object_name)) == self.folder:
                    folder_items.append((os.path.basename(lod.name), lod))
                    
            # Sort items by their original filename to maintain folder order
            folder_items.sort(key=lambda x: x[0])
            
            # Now group the sorted items
            for filename, lod in folder_items:
                base_name = os.path.splitext(filename)[0]
                match = lod_pattern.search(base_name.lower())
                if match:
                    base_name = base_name[:match.start()].rstrip('_')
                    lod_num = int(match.group(1))
                    lod_part = f"LOD{lod_num}"
                else:
                    lod_part = "BASE"
                
                if (base_name not in object_groups):
                    object_groups[base_name] = []
                object_groups[base_name].append((lod, lod_part))
            
            # Draw objects in original order
            for base_name in object_groups:
                box = layout.box()
                row = box.row(align=True)
                
                # Expand/Collapse Button
                clean_name = base_name.replace('\\', '/')
                icon = 'TRIA_DOWN' if props.is_expanded(clean_name) else 'TRIA_RIGHT'
                expand = row.operator("import_assets.toggle_expanded", text="", icon=icon, emboss=False)
                expand.base_name = clean_name
                
                # Add minimal spacing
                row.separator(factor=0.2)
                
                # Group Toggle Button
                active_groups = props.group_active_states.split(',') if props.group_active_states else []
                is_group_active = base_name in active_groups
                
                group_row = row.row(align=True)
                group_row.alignment = 'LEFT'
                group_row.scale_y = 1.0
                group_row.operator("import_assets.toggle_group", 
                    text=" " + base_name + " ",
                    depress=is_group_active).base_name = base_name

                # Wenn expanded, zeige Inhalt
                if props.is_expanded(clean_name):
                    sorted_lods = sorted(object_groups[base_name], 
                                    key=lambda x: (0 if x[1] == "BASE" else int(re.search(r'\d+', x[1]).group())))
                    
                    for lod, lod_part in sorted_lods:
                        if lod_part == "BASE":
                            base_quick_selected = props.is_quick_selected("BASE")
                            
                            for base_obj in lod.base_objects:
                                sub_row = box.row(align=True)
                                sub_row.separator()
                                button_row = sub_row.row()
                                button_row.alignment = 'LEFT'
                                button_row.scale_y = 1.0
                                button_row.scale_x = 1.0
                                button_row.enabled = not (base_quick_selected or is_group_active)
                                # Nur den visuellen Zustand setzen
                                depress = base_obj.selected or not button_row.enabled
                                button = button_row.operator("import_assets.toggle_item", 
                                    text=base_obj.name,
                                    depress=depress)
                                button.is_base = True 
                                button.base_name = base_obj.name
                        else:
                            lod_quick_selected = props.is_quick_selected(lod_part)
                            sub_row = box.row(align=True)
                            sub_row.separator()
                            button_row = sub_row.row()
                            button_row.alignment = 'LEFT'
                            button_row.scale_y = 1.0
                            button_row.scale_x = 1.0
                            button_row.enabled = not (lod_quick_selected or is_group_active)
                            depress = lod_quick_selected or lod.include
                            button = button_row.operator("import_assets.toggle_item", 
                                text=f"{lod_part}",
                                depress=depress)
                            button.is_base = False
                            button.lod_name = lod.name

    return VIEW3D_PT_folder_panel

class VIEW3D_PT_batch_import_panel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Assetporter beta"  # Changed Beta to beta
    bl_label = ""     # Changed Beta to beta
    bl_options = {'HIDE_HEADER'}  # This removes the collapse arrow
    bl_order = 1  # Main Panel hat Order 1
    bl_region_priority = 1  # Höhere Priorität als Folder Panels
    
    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'EXEC_DEFAULT'
        props = context.scene.batch_import_props
        lod_pattern = re.compile(r'lod(\d+)')  # Added missing closing parenthesis

        # Main container with fixed height
        main_column = layout.column()
        
        # Folder path row with proper scaling
        row = main_column.row(align=True)
        row.scale_y = 1.0
        row.scale_x = 1.5
        row.prop(props, "folder_path", text="")
        
        # Scan buttons
        row = main_column.row(align=True)
        row.scale_y = 1.0
        row.operator("import_assets.scan_folder", text="Scan Folder", icon='VIEWZOOM')
        row.operator("import_assets.scan_textures", text="Scan Textures", icon='IMAGE_DATA')
        
        # Import button
        row = main_column.row()
        row.scale_y = 1.0
        row.enabled = bool(props.has_scanned and props.lods)
        row.operator("import_assets.batch_import", text="Import Selected", icon='IMPORT')

        # Texture Type Quick Select box
        if props.textures:
            box = main_column.box()
            row = box.row(align=True)
            row.alignment = 'CENTER'
            
            # Create buttons for each texture type with first letter capitalized
            for texture_type, keywords in texture_types.items():
                # Get display name (first keyword without underscore), capitalize only first letter
                display_name = keywords[0].replace('_', '').capitalize()
                
                # Check if any textures of this type exist
                has_textures = any(any(keyword in texture.name.lower() 
                                  for keyword in keywords) 
                                  for texture in props.textures)
                
                if has_textures:
                    is_active = any(lod.name == texture_type for lod in props.active_common_lods)
                    row.operator("import_assets.toggle_common_lod", 
                                text=display_name, 
                                depress=is_active).lod_name = texture_type

            # Add QuickRes section
            if props.textures and props.folder_path == props.last_scanned_path:
                # Check number of unique resolutions
                resolutions = json.loads(props.texture_resolution_cache) if props.texture_resolution_cache else {}
                
                # Only show QuickRes if more than one resolution exists
                if len(resolutions) > 1:
                    # Create single box for all resolution controls
                    box = main_column.box()
                    
                    # Add collapsible header row with arrow and QuickRes buttons
                    header_row = box.row(align=True)
                    
                    # Add arrow button that toggles the expanded state
                    icon = 'TRIA_DOWN' if props.texture_section_expanded else 'TRIA_RIGHT'
                    header_row.operator(
                        "import_assets.toggle_texture_section",
                        text="",
                        icon=icon,
                        emboss=False
                    )
                    
                    # Add QuickRes buttons in the same row
                    quick_row = header_row.row(align=True)
                    quick_row.alignment = 'CENTER'
                    
                    # Group resolutions
                    resolution_groups = {
                        "1K": [], "2K": [], "4K": [], "8K": [], "16K": []
                    }
                    
                    # Sort resolutions into groups
                    for res_str in resolutions.keys():
                        width, height = map(int, res_str.split('x'))
                        max_dim = max(width, height)
                        
                        if max_dim <= 1024:
                            resolution_groups["1K"].append(res_str)
                        elif max_dim <= 2048:
                            resolution_groups["2K"].append(res_str)
                        elif max_dim <= 4096:
                            resolution_groups["4K"].append(res_str)
                        elif max_dim <= 8192:
                            resolution_groups["8K"].append(res_str)
                        else:
                            resolution_groups["16K"].append(res_str)

                    # Create QuickRes buttons
                    for res_name, res_group in resolution_groups.items():
                        if res_group:
                            active_states = props.active_quickres_states.split(',') if props.active_quickres_states else []
                            is_quickres_active = res_name in active_states
                            
                            op = quick_row.operator("import_assets.toggle_texture_resolution",
                                          text=res_name,
                                          depress=is_quickres_active)
                            op.resolution = json.dumps(res_group)
                            op.is_quickres = True

                    # Show detailed resolutions if expanded
                    if props.texture_section_expanded:
                        # Sort resolutions by size
                        sorted_resolutions = sorted(resolutions.keys(), 
                                                key=lambda x: tuple(map(int, x.split('x'))))
                        
                        # Create row for detailed resolutions
                        detail_row = box.row(align=True)
                        detail_row.alignment = 'CENTER'
                        
                        # Create individual resolution buttons
                        for res_str in sorted_resolutions:
                            is_active = any(res.name == res_str 
                                        for res in props.active_texture_resolutions)
                            
                            op = detail_row.operator("import_assets.toggle_texture_resolution",
                                                text=res_str,
                                                depress=is_active)
                            op.resolution = json.dumps([res_str])
                            op.is_quickres = False

        # LOD Quick Select box
        if props.lods:
            box = main_column.box()
            row = box.row(align=True)
            row.alignment = 'CENTER'
            
            # BASE button
            if any(not lod_pattern.search(lod.name.lower()) for lod in props.lods):
                is_base_active = any(lod.name == "BASE" for lod in props.active_common_lods)
                row.operator("import_assets.toggle_common_lod", text="BASE", depress=is_base_active).lod_name = "BASE"
            
            # LOD buttons
            all_lod_numbers = set()
            for lod in props.lods:
                match = lod_pattern.search(lod.name.lower())
                if match:
                    all_lod_numbers.add(int(match.group(1)))
            
            for lod_num in sorted(all_lod_numbers):
                lod_name = f"LOD{lod_num}"
                is_active = any(lod.name == lod_name for lod in props.active_common_lods)
                row.operator("import_assets.toggle_common_lod", text=lod_name, depress=is_active).lod_name = lod_name

            # Search box
            row = main_column.row(align=True)
            row.scale_y = 1.0
            row.scale_x = 1.5
            row.prop(props, "search_term", text="", icon='VIEWZOOM')

class OBJECT_OT_scan_folder(Operator):
    bl_idname = "import_assets.scan_folder"
    bl_label = "Scan Folder"
    bl_description = "Scan Folder"

    def execute(self, context):
        props = context.scene.batch_import_props
        folder_paths = [path.strip() for path in props.folder_path.split(';')]
        lod_pattern = re.compile(r'lod(\d+)')

        # Store base object selections
        base_selections = {}
        for lod in props.lods:
            if hasattr(lod, 'base_objects'):
                for base_obj in lod.base_objects:
                    key = f"{lod.name}:{base_obj.name}"
                    base_selections[key] = base_obj.selected

        # Store LOD selections specifically
        lod_states = {}
        for lod in props.lods:
            match = lod_pattern.search(lod.name.lower())
            if match:  # Only store actual LOD selections
                lod_states[lod.name] = lod.include

        # Store Quick Select states
        quick_select_states = [lod.name for lod in props.active_common_lods]

        # Clear everything before scan
        props.lods.clear()
        props.common_lods.clear()
        props.active_common_lods.clear()

        # Validate paths first
        valid_paths = []
        for folder_path in folder_paths:
            abs_path = bpy.path.abspath(folder_path).replace("\\", "/")
            if os.path.exists(abs_path):
                valid_paths.append(abs_path)
            else:
                self.report({'WARNING'}, f"Invalid path: {folder_path}")

        if not valid_paths:
            props.has_scanned = False
            props.last_scanned_path = ""
            self.report({'ERROR'}, "No valid folder paths!")
            return {'CANCELLED'}

        # Scan all valid folders
        extensions = get_import_extensions()
        
        for folder_path in valid_paths:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in extensions:
                        continue
                    
                    # Clean the base name by removing LOD part
                    base_name = os.path.splitext(file)[0]
                    rel_path = os.path.relpath(root, folder_path)
                    
                    # Add file to LODs
                    lod_item = props.lods.add()
                    lod_item.name = file
                    lod_item.include = False
                    
                    # Store path relative to the specific folder it was found in
                    if rel_path != '.':
                        lod_item.object_name = os.path.join(folder_path, rel_path, base_name)
                    else:
                        lod_item.object_name = os.path.join(folder_path, base_name)
                    
                    # If it's a base file, try to get object names
                    is_base = not bool(lod_pattern.search(base_name.lower()))
                    
                    if is_base:
                        try:
                            file_path = os.path.join(root, file)
                            pre_import_objects = set(bpy.data.objects)
                            
                            # Import the file
                            extensions = get_import_extensions()
                            if ext in extensions:
                                extensions[ext](file_path)
                            
                            # Get new objects
                            new_objects = set(bpy.data.objects) - pre_import_objects
                            
                            # Add each MESH object (not empty)
                            for obj in sorted(new_objects, key=lambda x: x.name):
                                if obj.type == 'MESH':  # Only add mesh objects
                                    base_obj = lod_item.base_objects.add()
                                    base_obj.name = obj.name
                                    base_obj.selected = False
                            
                            # Cleanup
                            for obj in new_objects:
                                bpy.data.objects.remove(obj, do_unlink=True)
                                
                        except Exception as e:
                            self.report({'WARNING'}, f"Failed to scan {file}: {str(e)}")

        # Restore base object selections
        for lod in props.lods:
            if hasattr(lod, 'base_objects'):
                for base_obj in lod.base_objects:
                    key = f"{lod.name}:{base_obj.name}"
                    if key in base_selections:
                        base_obj.selected = base_selections[key]

        # Restore only LOD selections
        for lod in props.lods:
            match = lod_pattern.search(lod.name.lower())
            if match and lod.name in lod_states:  # Only restore actual LOD selections
                lod.include = lod_states[lod.name]

        # Restore Quick Select states
        for lod_name in quick_select_states:
            new_lod = props.active_common_lods.add()
            new_lod.name = lod_name

        props.has_scanned = True
        props.last_scanned_path = props.folder_path

        # Re-register panels
        register_folder_panels()
        
        return {'FINISHED'}

class OBJECT_OT_scan_textures(Operator):
    bl_idname = "import_assets.scan_textures"
    bl_label = "Scan Textures"
    bl_description = "Scan Textures"
    
    def execute(self, context):
        props = context.scene.batch_import_props
        folder_paths = [path.strip() for path in props.folder_path.split(';')]
        
        # Store ALL states before clearing
        prev_active_lods = {lod.name for lod in props.active_common_lods}
        prev_active_resolutions = {res.name for res in props.active_texture_resolutions}
        prev_quickres_states = props.active_quickres_states
        
        # Clear only textures collection, preserve states
        props.textures.clear()
        
        # Dictionary to store resolutions
        resolutions = {}
        
        # Scan for texture files
        for folder_path in folder_paths:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.tga', '.tiff', '.bmp')):
                        texture_item = props.textures.add()
                        texture_item.name = file
                        texture_item.object_name = os.path.join(root, file)
                        
                        # Get image resolution
                        try:
                            img = bpy.data.images.load(texture_item.object_name)
                            resolution = f"{img.size[0]}x{img.size[1]}"
                            if resolution not in resolutions:
                                resolutions[resolution] = []
                            resolutions[resolution].append(texture_item.object_name)
                            bpy.data.images.remove(img)
                        except Exception as e:
                            print(f"Failed to process texture {file}: {str(e)}")
        
        # Store resolutions in cache without clearing previous states
        if resolutions:  # Only update if we found textures
            props.texture_resolution_cache = json.dumps(resolutions)
        
        # Process found textures
        found_texture_types = set()
        for texture in props.textures:
            texture_name = texture.name.lower()
            matched_type = False
            
            # Check for specific texture types
            for type_name, keywords in texture_types.items():
                if any(keyword in texture_name for keyword in keywords):
                    found_texture_types.add(type_name)
                    matched_type = True
                    break
            
            # If no specific type matched, check if it's a base texture
            if not matched_type and not any(keyword in texture_name 
                for keywords in texture_types.values() 
                for keyword in keywords):
                found_texture_types.add("BASE")

        # Restore QuickRes states
        if prev_quickres_states:
            props.active_quickres_states = prev_quickres_states

        # Restore resolution selections while preserving existing ones
        existing_resolutions = {res.name for res in props.active_texture_resolutions}
        for res in prev_active_resolutions:
            if res in resolutions and res not in existing_resolutions:
                new_res = props.active_texture_resolutions.add()
                new_res.name = res

        # Restore texture type selections while preserving existing ones
        existing_types = {lod.name for lod in props.active_common_lods}
        for texture_type in found_texture_types:
            if texture_type in prev_active_lods and texture_type not in existing_types:
                new_lod = props.active_common_lods.add()
                new_lod.name = texture_type

        return {'FINISHED'}

class OBJECT_OT_batch_import(Operator): 
    bl_idname = "import_assets.batch_import"
    bl_label = "Import Selected"
    bl_description = "Import Selected"
    
    def execute(self, context):
        props = context.scene.batch_import_props
        folder_paths = [path.strip() for path in props.folder_path.split(';')]
        imported_anything = False
        imported_objects = []
        extensions = get_import_extensions()
        
        # Get selected files from all folders
        selected_files = []
        
        print("\n=== DEBUG: BATCH IMPORT START ===")
        print(f"Quick-selected LODs: {[lod.name for lod in props.active_common_lods]}")
        print(f"Number of LODs in props.lods: {len(props.lods)}")
        
        # First pass: collect all files to import, removing active_folder check
        for lod in props.lods:
            print(f"\nChecking LOD: {lod.name}")
            print(f"File folder: {os.path.dirname(lod.object_name)}")
            
            # Check if this is a LOD file first
            match = re.search(r'lod(\d+)', lod.name.lower())
            if match:  # This is a LOD item
                lod_name = f"LOD{match.group(1)}"
                is_quick_selected = props.is_quick_selected(lod_name)
                print(f"LOD item: {lod_name} - Quick selected: {is_quick_selected}, Include: {lod.include}")
                
                if is_quick_selected or lod.include:
                    selected_files.append((lod, None))
                    print(f"Adding LOD file: {lod.name}")
            else:  # This is a BASE item
                is_quick_selected = props.is_quick_selected("BASE")
                print(f"BASE item - Quick selected: {is_quick_selected}")
                if is_quick_selected or any(obj.selected for obj in lod.base_objects):
                    selected_objects = [obj for obj in lod.base_objects if obj.selected or is_quick_selected]
                    if selected_objects:
                        selected_files.append((lod, selected_objects))
                        print(f"Adding BASE file: {lod.name} with {len(selected_objects)} objects")

        print(f"\nSelected files count: {len(selected_files)}")
        print("Selected files:")
        for lod, objects in selected_files:
            if objects:  # BASE items
                print(f"  BASE: {lod.name} with {len(objects)} objects")
            else:  # LOD items
                print(f"  LOD: {lod.name}")
        print("=== DEBUG: BATCH IMPORT END ===\n")

        if not selected_files:
            self.report({'WARNING'}, "No files selected to import!")
            return {'CANCELLED'}

        # Track imported objects and collections
        container_collections = {}
        imported_objects = []
        processed_meshes = set()  # Track processed meshes

        # Import objects
        for lod, selected_objects in selected_files:
            file_path = os.path.join(os.path.dirname(lod.object_name), lod.name)
            ext = os.path.splitext(lod.name)[1].lower()
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            clean_base_name = re.sub(r'_lod\d+.*$', '', base_name)
            
            # Get LOD number from filename
            lod_match = re.search(r'_lod(\d+)', base_name.lower())
            current_lod = lod_match.group(1) if lod_match else "base"
            
            try:
                folder_name = os.path.basename(os.path.dirname(file_path))
                collection_name = f"{folder_name}"
                
                # Create or get collection
                if collection_name not in container_collections:
                    existing_collection = bpy.data.collections.get(collection_name)
                    if existing_collection:
                        container_collections[collection_name] = existing_collection
                    else:
                        container_collections[collection_name] = bpy.data.collections.new(collection_name)
                        bpy.context.scene.collection.children.link(container_collections[collection_name])

                print(f"Importing: {file_path}")
                pre_import_objects = set(bpy.data.objects)
                pre_import_meshes = set(bpy.data.meshes)
                
                # Import the file
                extensions[ext](file_path)
                
                new_objects = set(bpy.data.objects) - pre_import_objects
                new_meshes = set(bpy.data.meshes) - pre_import_meshes

                # Process each new object
                for obj in new_objects:
                    if obj.type == 'MESH':
                        # Generate target names
                        original_mesh_name = obj.data.name if obj.data else ""
                        target_base = f"{clean_base_name}_LOD{current_lod}"
                        
                        # Preserve mesh suffixes if present
                        if '_' in original_mesh_name:
                            mesh_suffix = original_mesh_name.split('_', 1)[1]
                            target_name = f"{target_base}_{mesh_suffix}"
                        else:
                            target_name = target_base

                        # Always process mesh first
                        if obj.data:
                            # Clear materials from mesh
                            obj.data.materials.clear()
                            # Rename mesh to match target name
                            obj.data.name = target_name

                        # Rename object to match mesh
                        obj.name = target_name

                        # Move to collection
                        for coll in obj.users_collection:
                            coll.objects.unlink(obj)
                        container_collections[collection_name].objects.link(obj)
                        imported_objects.append(obj)
                        print(f"Imported: {target_name}")

                    else:
                        # Remove non-mesh objects
                        bpy.data.objects.remove(obj, do_unlink=True)

                    # Remove orphaned materials
                    for mat in bpy.data.materials:
                        if not mat.users:
                            bpy.data.materials.remove(mat)

            except Exception as e:
                self.report({'WARNING'}, f"Failed to import {lod.name}: {str(e)}")
                continue

        # Only assign materials if textures are selected AND resolutions are selected
        if (props.textures and 
            props.active_texture_resolutions and  # Check if resolutions are selected
            any(lod.name for lod in props.active_common_lods)):  # Check if texture types are selected
            
            # Get selected textures
            selected_textures = []
            for texture in props.textures:
                texture_type = None
                for type_name, keywords in texture_types.items():
                    if any(keyword in texture.name.lower() for keyword in keywords):
                        texture_type = type_name
                        break
                
                if texture_type and any(lod.name == texture_type for lod in props.active_common_lods):
                    selected_textures.append(texture.object_name)

            # Only proceed with material assignment if we have both textures and resolutions selected
            if selected_textures:
                assign_materials_to_objects(imported_objects, selected_textures)
        else:
            print("Skipping material assignment - no resolutions or texture types selected")

        self.report({'INFO'}, f"Successfully imported {len(imported_objects)} objects")
        return {'FINISHED'}

class OBJECT_OT_toggle_common_lod(Operator):
    bl_idname = "import_assets.toggle_common_lod"
    bl_label = "Quick Select"
    
    lod_name: StringProperty()
    
    def execute(self, context):
        props = context.scene.batch_import_props
        lod_pattern = re.compile(r'lod(\d+)')
        
        # Check if already quick-selected
        is_quick_selected = props.is_quick_selected(self.lod_name)
        
        if not is_quick_selected:
            # Activate quick-select and select all
            new_lod = props.active_common_lods.add()
            new_lod.name = self.lod_name
            
            # Select all matching objects
            if self.lod_name == "BASE":
                for lod in props.lods:
                    if not lod_pattern.search(lod.name.lower()):
                        if hasattr(lod, 'base_objects'):
                            for base_obj in lod.base_objects:
                                base_obj.selected = True
                        lod.include = True
            else:
                target_lod_num = self.lod_name[3:]
                for lod in props.lods:
                    match = lod_pattern.search(lod.name.lower())
                    if match and match.group(1) == target_lod_num:
                        lod.include = True
                        if hasattr(lod, 'base_objects'):
                            for base_obj in lod.base_objects:
                                base_obj.selected = True
        else:
            # Deactivate quick-select
            for i, lod in enumerate(props.active_common_lods):
                if lod.name == self.lod_name:
                    props.active_common_lods.remove(i)
                    break
            
            # Deselect all matching objects
            if self.lod_name == "BASE":
                for lod in props.lods:
                    if not lod_pattern.search(lod.name.lower()):
                        if hasattr(lod, 'base_objects'):
                            for base_obj in lod.base_objects:
                                base_obj.selected = False
                        lod.include = False
            else:
                target_lod_num = self.lod_name[3:]
                for lod in props.lods:
                    match = lod_pattern.search(lod.name.lower())
                    if match and match.group(1) == target_lod_num:
                        lod.include = False
                        if hasattr(lod, 'base_objects'):
                            base_obj.selected = False
        
        context.area.tag_redraw()
        return {'FINISHED'}

class OBJECT_OT_select_all_lods(Operator):
    bl_idname = "import_assets.select_all_lods"
    bl_label = "Select All LODs"
    
    def execute(self, context):
        props = context.scene.batch_import_props
        
        # If all are selected, deselect all
        if len(props.active_common_lods) > 0:
            props.active_common_lods.clear()
            # Deselect all LODs
            for lod in props.lods:
                lod.include = False
                if hasattr(lod, 'base_objects'):
                    for base_obj in lod.base_objects:
                        base_obj.selected = False
        else:
            # Select all LODs and BASE
            lod_pattern = re.compile(r'lod(\d+)')
            for lod in props.lods:
                lod.include = True
                if hasattr(lod, 'base_objects'):
                    for base_obj in lod.base_objects:
                        base_obj.selected = True
        
        return {'FINISHED'}

class OBJECT_OT_toggle_expanded(Operator):
    bl_idname = "import_assets.toggle_expanded"
    bl_label = ""  # Removed duplicate "Toggle Expanded"
    bl_description = "Toggle Expanded"
    
    base_name: StringProperty()
    
    def execute(self, context):
        props = context.scene.batch_import_props
        props.toggle_expanded(self.base_name)
        return {'FINISHED'}

class OBJECT_OT_toggle_all_expanded(Operator):
    bl_idname = "import_assets.toggle_all_expanded"
    bl_label = "Toggle All"
    
    expand: bpy.props.BoolProperty()
    
    def execute(self, context):
        props = context.scene.batch_import_props
        props.expand_all(self.expand)
        return {'FINISHED'}

class OBJECT_OT_toggle_item(Operator):
    bl_idname = "import_assets.toggle_item"
    bl_label = "Toggle Item"
    bl_description = "Toggle selection of this item"
    
    is_base: BoolProperty(default=False)
    base_name: StringProperty(default="")
    lod_name: StringProperty(default="")
    
    def execute(self, context):
        props = context.scene.batch_import_props
        lod_pattern = re.compile(r'lod(\d+)')
        
        print(f"\n=== DEBUG: TOGGLE ITEM ===")
        print(f"Is Base: {self.is_base}")
        print(f"Base Name: {self.base_name}")
        print(f"LOD Name: {self.lod_name}")
        
        # Für BASE Objekte
        if self.is_base:
            is_quick_selected = props.is_quick_selected("BASE")
            active_groups = props.group_active_states.split(',') if props.group_active_states else []
            
            for lod in props.lods:
                if hasattr(lod, 'base_objects'):
                    for base_obj in lod.base_objects:
                        if base_obj.name == self.base_name:
                            # Get parent folder name for group state
                            parent_dir = os.path.dirname(lod.object_name)
                            folder_name = os.path.basename(parent_dir)
                            is_group_active = folder_name in active_groups
                            
                            if not (is_quick_selected or is_group_active):
                                base_obj.selected = not base_obj.selected
                                print(f"Toggled BASE object: {base_obj.name} to {base_obj.selected}")
                            break
        
        # Für LOD Objekte
        else:
            match = lod_pattern.search(self.lod_name.lower())
            if match:
                lod_type = f"LOD{match.group(1)}"
                is_quick_selected = props.is_quick_selected(lod_type)
                
                # Get group state
                base_name = os.path.splitext(os.path.basename(self.lod_name))[0]
                match = lod_pattern.search(base_name.lower())
                if match:
                    clean_base_name = base_name[:match.start()].rstrip('_')
                    is_group_active = clean_base_name in props.group_active_states.split(',') if props.group_active_states else False
                else:
                    is_group_active = False
                
                # Find and toggle the specific LOD
                for lod in props.lods:
                    if lod.name == self.lod_name:
                        if not (is_quick_selected or is_group_active):
                            lod.include = not lod.include
                            print(f"Toggled LOD: {lod.name} to {lod.include}")
                        break
        
        print("=== DEBUG: TOGGLE ITEM END ===\n")
        context.area.tag_redraw()
        return {'FINISHED'}

class OBJECT_OT_toggle_group(Operator):
    bl_idname = "import_assets.toggle_group"
    bl_label = "Toggle Group"
    bl_description = "Toggle all items in this group"
    
    base_name: StringProperty()
    
    def execute(self, context):
        props = context.scene.batch_import_props
        lod_pattern = re.compile(r'lod(\d+)')
        
        # Check if group is currently active
        active_groups = props.group_active_states.split(',') if props.group_active_states else []
        is_group_active = self.base_name in active_groups
        
        # Toggle state
        new_state = not is_group_active
        
        # Update group active state
        if new_state and self.base_name not in active_groups:
            active_groups.append(self.base_name)
        elif not new_state and self.base_name in active_groups:
            active_groups.remove(self.base_name)
        props.group_active_states = ','.join(filter(None, active_groups))
        
        # Update selections for both BASE and LOD items
        for lod in props.lods:
            base_name = os.path.splitext(os.path.basename(lod.name))[0]
            match = lod_pattern.search(base_name.lower())
            
            # Get clean base name for comparison
            if match:
                clean_base_name = base_name[:match.start()].rstrip('_')
                if clean_base_name == self.base_name:
                    # This is a LOD - set both include state and visual state
                    lod.include = new_state
            else:
                clean_base_name = base_name
                if clean_base_name == self.base_name and hasattr(lod, 'base_objects'):
                    for base_obj in lod.base_objects:
                        base_obj.selected = new_state
        
        # Force redraw
        for area in context.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}

class OBJECT_OT_toggle_texture_resolution(Operator):
    bl_idname = "import_assets.toggle_texture_resolution"
    bl_label = "Toggle Texture Resolution"
    bl_description = "Toggle selection of this resolution"
    
    resolution: StringProperty(
        name="Resolution",
        description="Resolution group as JSON string",
        default=""
    )
    is_quickres: BoolProperty(
        name="Is QuickRes",
        description="Whether this is a QuickRes button",
        default=False
    )
    
    def execute(self, context):
        props = context.scene.batch_import_props

        try:
            resolution_group = json.loads(self.resolution)

            if self.is_quickres:
                # Get QuickRes name (1K, 2K etc)
                res_name = resolution_group[0].split('x')[0] + "K"
                
                # Get current states as list (not set)
                active_states = props.active_quickres_states.split(',') if props.active_quickres_states else []
                is_active = res_name in active_states

                if is_active:
                    # Deactivate QuickRes
                    if res_name in active_states:
                        active_states.remove(res_name)
                    
                    # Remove resolutions from this group
                    to_remove = []
                    for i, res in enumerate(props.active_texture_resolutions):
                        if any(res_str in res.name for res_str in resolution_group):
                            to_remove.append(i)
                    for i in reversed(to_remove):
                        props.active_texture_resolutions.remove(i)
                else:
                    # Activate QuickRes
                    active_states.append(res_name)
                    
                    # Add resolutions from this group
                    for res_str in resolution_group:
                        if not any(res.name == res_str for res in props.active_texture_resolutions):
                            new_res = props.active_texture_resolutions.add()
                            new_res.name = res_str

                # Update active states string
                props.active_quickres_states = ','.join(filter(None, active_states))

            else:
                # Handle detailed resolution button
                res_str = resolution_group[0]
                base_size = res_str.split('x')[0]  # Get base size without K
                
                # Determine which QuickRes group this belongs to
                width = int(base_size)
                if width <= 1024:
                    quick_res_group = "1K"
                elif width <= 2048:
                    quick_res_group = "2K"
                elif width <= 4096:
                    quick_res_group = "4K"
                elif width <= 8192:
                    quick_res_group = "8K"
                else:
                    quick_res_group = "16K"

                # Only allow toggle if corresponding QuickRes group is not active
                active_states = props.active_quickres_states.split(',') if props.active_quickres_states else []
                if quick_res_group not in active_states:
                    is_active = any(res.name == res_str for res in props.active_texture_resolutions)
                    
                    if not is_active:
                        new_res = props.active_texture_resolutions.add()
                        new_res.name = res_str
                    else:
                        for i, res in enumerate(props.active_texture_resolutions):
                            if res.name == res_str:
                                props.active_texture_resolutions.remove(i)
                                break

        except Exception as e:
            print(f"Error in toggle_texture_resolution: {str(e)}")
            return {'CANCELLED'}

        context.area.tag_redraw()
        return {'FINISHED'}

class OBJECT_OT_toggle_texture_section(Operator):
    bl_idname = "import_assets.toggle_texture_section"
    bl_label = "Toggle Texture Section"
    bl_description = "Show/hide texture resolutions"
    
    def execute(self, context):
        props = context.scene.batch_import_props
        props.texture_section_expanded = not props.texture_section_expanded
        return {'FINISHED'}

def find_texture_group(texture_path, texture_groups=None):
    """Group textures by base name, ignoring texture type suffixes"""
    if texture_groups is None:
        texture_groups = {}
        
    base_name = os.path.splitext(os.path.basename(texture_path))[0].lower()
    
    # Remove known texture type suffixes
    for suffix in ['_diffuse', '_albedo', '_basecolor', '_color', '_col',
                  '_normal', '_nrm', '_nor',
                  '_roughness', '_rough', '_rgh',
                  '_metallic', '_metal', '_mtl',
                  '_height', '_displacement', '_disp',
                  '_ambient', '_occlusion', '_ao']:
        if base_name.endswith(suffix):
            base_name = base_name[:-len(suffix)]
            break
    
    # Remove LOD and number suffixes
    base_name = re.sub(r'_(?:lod\d+)?(?:\.\d+)?$', '', base_name, flags=re.IGNORECASE)
    base_name = re.sub(r'_(?:big|small)(?:_|\.|$)', '', base_name, flags=re.IGNORECASE)
    
    # Add texture to group
    if base_name not in texture_groups:
        texture_groups[base_name] = []
    texture_groups[base_name].append(texture_path)
    
    return texture_groups

def find_base_texture_name(texture_name):
    """Remove numeric suffixes and get base texture name"""
    # Remove file extension and convert to lower case
    base_name = os.path.splitext(texture_name)[0].lower()
    # Remove numeric suffix pattern like .001, .002 etc
    base_name = re.sub(r'\.\d{3}$', '', base_name)
    return base_name

def create_material_from_textures(obj_name, texture_paths):
    # Check if any textures are selected first
    props = bpy.context.scene.batch_import_props
    if not any(lod.name for lod in props.active_common_lods):
        print("No texture types selected, skipping material creation")
        return None

    # Get resolution only from first texture to avoid loading all images
    first_texture = texture_paths[0]
    img = bpy.data.images.load(first_texture)
    resolution = f"{img.size[0]}x{img.size[1]}"
    bpy.data.images.remove(img)

    # Create material name
    base_name = re.sub(r'\.\d+$', '', obj_name.split('_')[0])
    material_name = f"{base_name}_{resolution}_Material"

    # Check for existing material first
    existing_material = bpy.data.materials.get(material_name)
    if existing_material:
        print(f"Using existing material: {material_name}")
        return existing_material

    # Pre-process textures to avoid loading images multiple times
    selected_texture_types = {lod.name for lod in props.active_common_lods}
    processed_textures = {}
    
    # Only process textures that match selected types
    for texture_path in texture_paths:
        texture_name = os.path.basename(texture_path).lower()
        for type_name, keywords in texture_types.items():
            if type_name in selected_texture_types and any(keyword in texture_name for keyword in keywords):
                processed_textures[type_name] = texture_path
                break

    # If no matching textures found, return None
    if not processed_textures:
        print("No matching textures found for selected types")
        return None

    # Create material with minimal node setup
    material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    # Create basic nodes
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    output = nodes.new('ShaderNodeOutputMaterial')
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])

    # Set node positions
    output.location = (400, 0)
    principled.location = (100, 0)

    # Create frames only if needed
    texture_frame = nodes.new('NodeFrame')
    texture_frame.label = "Textures"
    texture_frame.label_size = 20

    mapping_frame = nodes.new('NodeFrame')
    mapping_frame.label = "Mapping"
    mapping_frame.label_size = 20

    # Create mapping setup
    mapping = nodes.new('ShaderNodeMapping')
    mapping.location = (-920, 0)
    mapping.parent = mapping_frame

    tex_coord = nodes.new('ShaderNodeTexCoord')
    tex_coord.location = (-1100, 0)
    tex_coord.parent = mapping_frame

    # Create minimal mapping connections
    links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

    # Process only selected texture types
    spacing = 280
    current_pos = len(processed_textures) * spacing / 2

    for texture_type, texture_path in processed_textures.items():
        try:
            # Load image only if not already loaded
            img_name = os.path.basename(texture_path)
            img = bpy.data.images.get(img_name) or bpy.data.images.load(texture_path)
            img.use_fake_user = True

            # Create and set up texture node
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.image = img
            tex_image.location = (-600, current_pos)
            tex_image.parent = texture_frame
            links.new(mapping.outputs['Vector'], tex_image.inputs['Vector'])

            # Connect to appropriate input based on type
            if texture_type == 'diffuse':
                links.new(tex_image.outputs['Color'], principled.inputs['Base Color'])
            elif texture_type == 'roughness':
                links.new(tex_image.outputs['Color'], principled.inputs['Roughness'])
            elif texture_type == 'metallic':
                links.new(tex_image.outputs['Color'], principled.inputs['Metallic'])
            elif texture_type == 'opacity':
                links.new(tex_image.outputs['Color'], principled.inputs['Alpha'])
                material.blend_method = 'BLEND'
            elif texture_type == 'normal':
                normal_map = nodes.new('ShaderNodeNormalMap')
                normal_map.location = (-270, current_pos)
                links.new(tex_image.outputs['Color'], normal_map.inputs['Color'])
                links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])

            # Pack image only if not already packed
            if not img.packed_file:
                img.pack()

            current_pos -= spacing

        except Exception as e:
            print(f"Error processing texture {texture_path}: {str(e)}")
            continue

    return material

def assign_materials_to_objects(imported_objects, selected_textures):
    """Assign materials to objects with texture matching"""
    if not selected_textures:
        print("No textures selected for material assignment")
        return
    
    print("\n=== DEBUG: MATERIAL ASSIGNMENT START ===")
    props = bpy.context.scene.batch_import_props
    print(f"Selected texture types: {[lod.name for lod in props.active_common_lods]}")
    print("Found textures:")
    
    # Group and debug print all textures by type
    texture_by_type = {}
    for tex_path in selected_textures:
        tex_name = os.path.basename(tex_path).lower()
        found_type = None
        for type_name, keywords in texture_types.items():
            if any(keyword in tex_name for keyword in keywords):
                found_type = type_name
                if type_name not in texture_by_type:
                    texture_by_type[type_name] = []
                texture_by_type[type_name].append(tex_name)
                break
        print(f"  {tex_name} -> {found_type}")
    
    print("\nTextures by type:")
    for type_name, textures in texture_by_type.items():
        print(f"  {type_name}: {len(textures)} textures")
    
    # Store created materials
    materials = {}
    
    for obj in imported_objects:
        print(f"\nProcessing object: {obj.name}")
        
        if not obj.data or not hasattr(obj.data, 'materials'):
            print(f"Object {obj.name} has no material slots")
            continue
        
        # Find matching textures for this object
        matching_textures = []
        obj_base = os.path.splitext(obj.name)[0].lower()
        obj_base = re.sub(r'_lod\d+.*$', '', obj_base)
        
        print(f"Looking for textures matching: {obj_base}")
        
        # Get selected texture types
        selected_types = {lod.name for lod in props.active_common_lods}
        selected_resolutions = {res.name for res in props.active_texture_resolutions}
        
        print(f"Selected texture types: {selected_types}")
        print(f"Selected resolutions: {selected_resolutions}")
        
        for tex_path in selected_textures:
            tex_name = os.path.basename(tex_path).lower()
            print(f"Checking texture: {tex_name}")
            
            # Get texture type - Modified texture type detection
            tex_type = None
            for type_name, keywords in texture_types.items():
                if any(keyword in tex_name.lower() for keyword in keywords):
                    tex_type = type_name
                    # Map albedo to diffuse
                    if type_name == 'diffuse' and 'albedo' in tex_name.lower():
                        tex_type = 'diffuse'
                    # Map ambientocclusion to ambient_occlusion
                    elif 'ambientocclusion' in tex_name.lower():
                        tex_type = 'ambient_occlusion'
                    # Map translucency to translucent
                    elif 'translucency' in tex_name.lower():
                        tex_type = 'translucent'
                    break
            
            # Check if texture type is selected
            if tex_type not in selected_types:
                print(f"  Texture type {tex_type} not selected")
                continue

            # Check resolution
            img = bpy.data.images.load(tex_path)
            resolution = f"{img.size[0]}x{img.size[1]}"
            bpy.data.images.remove(img)
            
            if resolution not in selected_resolutions:
                print(f"  Resolution {resolution} not selected")
                continue
            
            # Check name match with improved base name extraction
            tex_base = os.path.splitext(tex_name)[0]
            tex_base = re.sub(r'_(?:albedo|diffuse|normal|roughness|metallic|height|ambientocclusion|opacity|translucency|specular|cavity|fuzz|gloss).*$', '', tex_base)
            tex_base = re.sub(r'_(?:8bit|16bit).*$', '', tex_base)
            tex_base = re.sub(r'_\d+ppm$', '', tex_base)
            tex_base = re.sub(r'_lod\d+.*$', '', tex_base)
            
            if tex_base in obj_base or obj_base in tex_base:
                matching_textures.append(tex_path)
                print(f"  Added matching texture: {tex_name} ({tex_type})")
        
        print(f"Found {len(matching_textures)} matching textures")
        
        if matching_textures:
            # Create or reuse material
            material = create_material_from_textures(obj_base, matching_textures)
            
            # Assign material
            obj.data.materials.clear()  # Clear existing materials
            obj.data.materials.append(material)
            print(f"Material assigned to {obj.name}")
    
    print("=== DEBUG: MATERIAL ASSIGNMENT END ===\n")

# Define base_classes at module level
base_classes = [
    BaseObjectItem,
    LODItem,
    BatchImportProperties,
    OBJECT_OT_scan_folder,
    OBJECT_OT_scan_textures,
    OBJECT_OT_batch_import,
    OBJECT_OT_toggle_common_lod,
    OBJECT_OT_select_all_lods,
    OBJECT_OT_toggle_expanded,
    OBJECT_OT_toggle_all_expanded,
    OBJECT_OT_toggle_item,
    OBJECT_OT_toggle_group,
    OBJECT_OT_toggle_texture_resolution,
    OBJECT_OT_toggle_texture_section,
    VIEW3D_PT_batch_import_panel
]

def register():
    for cls in base_classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Failed to register {cls.__name__}: {str(e)}")

    bpy.types.Scene.batch_import_props = PointerProperty(type=BatchImportProperties)

    # Register folder panels
    register_folder_panels()

def register_folder_panels():
    """Register panels for each folder - called after scanning"""
    
    def get_props():
        """Safely get props if they exist"""
        if hasattr(bpy.types.Scene, "batch_import_props"):
            if hasattr(bpy, "context") and hasattr(bpy.context, "scene"):
                return getattr(bpy.context.scene, "batch_import_props", None)
        return None
    
    # Store existing panel classes before removing them
    existing_panels = []
    for cls_name in dir(bpy.types):
        if cls_name.startswith('VIEW3D_PT_FOLDER_'):
            try:
                panel_class = getattr(bpy.types, cls_name)
                existing_panels.append(panel_class)
            except Exception:
                pass
    
    # Unregister existing panels
    for panel_class in existing_panels:
        try:
            bpy.utils.unregister_class(panel_class)
        except Exception:
            pass
    
    # Create new panels
    props = get_props()
    if props and hasattr(props, "lods"):
        folder_order = {}
        
        # Collect folders and their first occurrence for ordering
        for lod in props.lods:
            folder = os.path.basename(os.path.dirname(lod.object_name))
            if folder and folder not in folder_order:
                folder_order[folder] = os.path.dirname(lod.object_name)
    
        # Sort folders based on their full paths
        sorted_folders = sorted(folder_order.keys(), 
                            key=lambda x: folder_order[x])
        
        # Register panel for each folder in order
        for i, folder in enumerate(sorted_folders, start=2):  # Changed this line
            try:
                panel_class = create_folder_panel(folder)
                panel_class.bl_order = i
                bpy.utils.register_class(panel_class)
            except Exception as e:
                print(f"Failed to register panel for {folder}: {str(e)}")

    # Safer UI refresh
    try:
        if hasattr(bpy, "context") and hasattr(bpy.context, "window_manager"):
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
    except Exception:
        pass

def unregister():
    # First unregister the folder panels
    for cls_name in dir(bpy.types):
        if (cls_name.startswith('VIEW3D_PT_FOLDER_')):
            try:
                panel_class = getattr(bpy.types, cls_name)
                bpy.utils.unregister_class(panel_class)
            except Exception:
                pass
    
    # Remove property
    try:
        if hasattr(bpy.types.Scene, "batch_import_props"):
            del bpy.types.Scene.batch_import_props
    except Exception as e:
        print(f"Failed to remove property: {str(e)}")
    
    # Unregister all classes in reverse order
    for cls in reversed(base_classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"Failed to unregister {cls.__name__}: {str(e)}")

if __name__ == "__main__":
    register()