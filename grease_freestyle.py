#
bl_info = {
    "name": "Grease Freestyle",
    "author": "Andrew Maslennikov",
    "version": (0, 0, 1),
    "blender": (2, 83, 0),
    "location": "Properties > Render > Grease Freestyle",
    "description": "Exports Freestyle's stylized strokes to Grease Pencil sketch",
    "warning": "Alpha version",
    "wiki_url": "",
    "category": "Render",
}

import bpy
import functools
import collections
import sys

from bpy.props import (
                BoolProperty,
                EnumProperty,
                PointerProperty,
#               IntProperty,
            )

# TODO: fix * module referencies
#from freestyle.shaders import *
#from freestyle.predicates import *
#from freestyle.chainingiterators import ChainSilhouetteIterator, ChainPredicateIterator
from freestyle.types import (
                    Operators,
                    StrokeShader,
                    StrokeVertex
                    )
from freestyle.functions import CurveMaterialF0D



from bpy_extras import view3d_utils
import bpy_extras
from mathutils import Vector, Matrix, Color

import parameter_editor


DrawOptions = collections.namedtuple('DrawOptions',
                                     'draw_mode color_extraction color_extraction_mode thickness_extraction alpha_extraction')

# useless
def get_strokes():
    # a tuple containing all strokes from the current render. should get replaced by freestyle.context at some point
    return tuple(map(Operators().get_stroke_from_index, range(Operators().get_strokes_size())))


# get the exact scene dimensions
def render_height(scene):
    return int(scene.render.resolution_y * scene.render.resolution_percentage / 100)

def render_width(scene):
    return int(scene.render.resolution_x * scene.render.resolution_percentage / 100)

def render_dimensions(scene):
    return render_width(scene), render_height(scene)



class FreestyleGPencilProps(bpy.types.PropertyGroup):
    """Implements the properties for the Grease Freestyle exporter"""
    bl_idname = "RENDER_PT_gpencil_export"
    use_freestyle_gpencil_export: BoolProperty(
        name="Grease Pencil Export",
        description="Export Freestyle edges to Grease Pencil",
        default=False
    )
    draw_mode: EnumProperty(
        name="Draw Mode",
        items=[
            # ('2DSPACE', "2D Space", "Export a single frame", 0),
            ## TODO: fix 3D space drawing
            ##('3DSPACE', "3D Space", "Export an animation", 1),
            # ('2DIMAGE', "2D Image", "", 2),
            ('SCREEN', "Screen", "", 3),
        ],
        default='SCREEN'
    )
    write_mode: EnumProperty(
        name="Write Mode",
        items=[
            ('Keep', "Keep", "Add new GP strokes to the current layer"),
            ('OVERWRITE', "Overwrite", "Overwrite the current layer"),
            # ('OVERWRITEFRAME', "Overwrite Frame", "Only overwrite the current layer if it is the same frame"),
        ],
        default='OVERWRITE'
    )


class SVGExporterPanel(bpy.types.Panel):
    """Creates a Panel in the render context of the properties editor"""
    bl_idname = "RENDER_PT_GreaseFreestylePanel"
    bl_space_type = 'PROPERTIES'
    bl_label = "Grease Pencil from Freestyle"
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_order = 50

    #   @classmethod
    #   def poll(self, context):
    #   return (context.scene is not None)

    def draw_header(self, context):
        layout = self.layout
        scene = context.scene
        gp = scene.freestyle_gpencil_export
        layout.prop(gp, "use_freestyle_gpencil_export", text="", toggle=False)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        gp = scene.freestyle_gpencil_export
        freestyle = context.window.view_layer.freestyle_settings

        layout.active = (gp.use_freestyle_gpencil_export and freestyle.mode != 'SCRIPT')

        column = layout.column()
        column.label(text="Draw Mode:")
        row = column.row()
        row.prop(gp, "draw_mode", expand=True)

        column.label(text="Write Mode:")
        row = column.row()
        row.prop(gp, "write_mode", expand=True)




#class ExporterLinesetProps(PropertyGroup):



class FSGPExporterLinesetPanel(bpy.types.Panel):
    """Creates a Panel in the view layers context of the properties editor"""
    bl_idname = "RENDER_PT_GFExporterLinesetPanel"
    bl_space_type = 'PROPERTIES'
    bl_label = "GreaseFreestyle Line Style Export"
    bl_region_type = 'WINDOW'
    bl_context = "view_layer"
    bl_order = 51

    def draw(self, context):
        layout = self.layout

        scene = context.scene
        #render properties tab
        exporter = scene.freestyle_gpencil_export

        #view layer properties tab
        #2.83 reference
        freestyle = context.window.view_layer.freestyle_settings
        # should work...
        #linestyle = scene.freestyle_exporter_lineset_props
        linestyle = freestyle.linesets.active.linestyle

        layout.active = (exporter.use_freestyle_gpencil_export and freestyle.mode != 'SCRIPT')

        column = layout.column()
        column.label(text="Extract Freestyle Settings:")
        row = column.row(align=True)
        row.prop(linestyle, "use_extract_color", text="Stroke Color", toggle=True)
        # row.prop(linestyle, "use_extract_fill", text="Fill Color", toggle=True)
        row.prop(linestyle, "use_extract_thickness", text="Thickness", toggle=True)
        row.prop(linestyle, "use_extract_alpha", text="Alpha", toggle=True)

        if linestyle.use_extract_color:
            row = layout.row()
            row.label(text="Color Extraction Mode:")
            row = layout.row()
            row.prop(linestyle, "extract_color", expand=True)




def get_grease_pencil_material(gpencil_mat_name='init_GP_Material') -> bpy.types.MaterialGPencilStyle:

    gpencil_material = bpy.data.materials.new(gpencil_mat_name)

    # Make material suitable for grease pencil
    if not gpencil_material.is_grease_pencil:
        bpy.data.materials.create_gpencil_data(gpencil_material)
        gpencil_material.grease_pencil.color = (0, 0, 0, 1)

    # for debugging purposes
    print("get_grease_pencil_material")

    return gpencil_material


def get_grease_pencil_obj(gpencil_obj_name='init_GPencil') -> bpy.types.GreasePencil:
    scene = bpy.context.scene

    bpy.ops.object.gpencil_add(location=(0, 0, 0), type='EMPTY')
        # rename grease pencil
    scene.objects[-1].name = gpencil_obj_name

    # Get grease pencil object
    gpencil_obj = scene.objects[gpencil_obj_name]
    # Rename GreasePencil data-block to the same name as object
    gpencil_obj.data.name = gpencil_obj.name

    # for debugging purposes
    print("get_grease_pencil_obj")

    return gpencil_obj


def get_grease_pencil_layer(gpencil_obj: bpy.types.GreasePencil,
                            gpencil_layer_name='init_GP_Layer',
                            clear_layer=False) -> bpy.types.GPencilLayer:

    gpencil_layer = gpencil_obj.data.layers.new(gpencil_layer_name, set_active=True)
#    gpencil_layer_name = gpencil_obj.data.layers.active.info
#    gpencil_layer = gpencil_obj.data.layers[gpencil_layer_name]

    # for debugging purposes
    print("get_grease_pencil_layer")

    return gpencil_layer

# Merge layer with object
def get_grease_pencil(gpencil_obj_name='init_GPencil_object',
                      gpencil_layer_name='init_GP_Layer',
                      gpencil_mat_name='init_GP_Material',
                      clear_layer=True) -> bpy.types.GPencilLayer:
    #    clear_layer = True
    gpencil = get_grease_pencil_obj(gpencil_obj_name)

    # Assign the material to the grease pencil for drawing
    gpencil_material = get_grease_pencil_material(gpencil_mat_name)
    # Append material to GP object
    gpencil.data.materials.append(gpencil_material)

    gpencil_layer = get_grease_pencil_layer(gpencil, gpencil_layer_name, clear_layer=clear_layer)

    # for debugging purposes
    print("get_grease_pencil")

    return gpencil_layer


def create_gpencil_layer_on_frame(scene, FS_lineset_name, color, alpha, fill_color, fill_alpha):

    # for debugging purposes
    print("create_gpencil_layer_on_frame start")

    """Creates a new GPencil layer (if needed) to store the Freestyle result"""

    gpencil_layer = get_grease_pencil(gpencil_layer_name=FS_lineset_name)

    # for debugging purposes
    print("create_gpencil_layer_on_frame layer created")

    # can this be done more neatly? layer.frames.get(..., ...) doesn't seem to work
    frame = frame_from_frame_number(gpencil_layer, scene.frame_current) or gpencil_layer.frames.new(scene.frame_current)

    # for debugging purposes
    print("create_gpencil_layer_on_frame end")

    return (gpencil_layer, frame)

def frame_from_frame_number(layer, current_frame):
    """Get a reference to the current frame if it exists, else False"""

    # for debugging purposes
    print("frame_from_frame_number")

    return next((frame for frame in layer.frames if frame.frame_number == current_frame), False)


def freestyle_to_gpencil_strokes(strokes, frame, lineset, options): # draw_mode='3DSPACE', color_extraction='BASE'):
    mat = bpy.context.scene.camera.matrix_local.copy()

    """
    # COLOR 
    # pick the active palette or create a default one
    grease_pencil = bpy.context.scene.grease_pencil
    palette = grease_pencil.palettes.active or grease_pencil.palettes.new("GP_Palette")

    # can we tag the colors the script adds, to remove them when they are not used?
    cache = { color_to_hex(color.color) : color for color in palette.colors }

    # keep track of which colors are used (to remove unused ones)
    used = []

    for fstroke in strokes:

        # the color object can be "owned", so use Color to clone it
        if options.color_extraction:
            if options.color_extraction_mode == 'FIRST':
                base_color = Color(fstroke[0].attribute.color)
            elif options.color_extraction_mode == 'FINAL':
                base_color = Color(fstroke[-1].attribute.color)
            else:
                base_color = Color(lineset.linestyle.color)

        # color has to be frozen (immutable) for it to be stored
        base_color.freeze()

        colorname = get_colorname(palette.colors, base_color, palette).name

        # append the current color, so it is kept
        used.append(colorname)
    """

    for fstroke in strokes:

        # for debugging purposes
        print("freestyle_to_gpencil_strokes for_loop start")

        ##!! create GP stokes object
        ##### 2.79 colorname - palette color name
        ## gpstroke = frame.strokes.new(colorname=colorname)
        ## 2.91
        try:
            gpstroke = frame.strokes.new()
        except:
            print("Error in creating new strokes")
        ## ?? assign material??

        # TODO: make options with props
        ##2.79
        ##        gpstroke.draw_mode = options.draw_mode
        ##2.91
#        gpstroke.display_mode = options.draw_mode
        try:
            gpstroke.display_mode = 'SCREEN'
        except:
            print("Error in reading display_mode")

        try:
            gpstroke.points.add(count=len(fstroke), pressure=1, strength=1)
        except:
            print("Error in adding points")

        ##!! set THICKNESS and ALPHA of stroke
        ## StrokeAttribute for this StrokeVertex
        ##!! 2.79
        ## svert.attribute.thickness

        # the max width gets pressure 1.0. Smaller widths get a pressure 0 <= x < 1
        try:
            base_width = functools.reduce(max, (sum(svert.attribute.thickness) for svert in fstroke), lineset.linestyle.thickness)
        except:
            print("Error in setting base_width")

        # set the default (pressure == 1) width for the gpstroke
        try:
            gpstroke.line_width = base_width
        except:
            print("Error in setting line_width")

        if options.draw_mode == 'SCREEN':
            try:
                width, height = render_dimensions(bpy.context.scene)
            except:
                print("Error in setting width, height")

            for svert, point in zip (fstroke, gpstroke.points):
                try:
                    x, y = svert.point
                except:
                    print("Error in setting x, y")

                try:
                    point.co = Vector(( abs(x / width), abs(y / height), 0.0 )) * 100
                except:
                    print("Error in setting point.co")
#                point.co = Vector(  abs(x / width), abs(y / height), 0.0) * 100
#                point.co = Vector( (abs(x / width)), (abs(y / height)), (0.0) ) * 100

                if options.thickness_extraction:
                    try:
                        point.pressure = sum(svert.attribute.thickness) / max(1e-5, base_width)
                    except:
                        print("Error in setting point.pressure")

                if options.alpha_extraction:
                    try:
                        point.strength = svert.attribute.alpha
                    except:
                        print("Error in setting point.extraction")

        else:
            raise NotImplementedError()

            # for debugging purposes
        print("freestyle_to_gpencil_strokes for_loop end")


def freestyle_to_strokes(scene, lineset, strokes):
    # for debugging purposes
    print("freestyle_to_strokes start")

    default = dict(color=(0, 0, 0), alpha=1, fill_color=(0, 0, 1), fill_alpha=0)

    # name = "FS {} f{:06}".format(lineset.name, scene.frame_current)
    name = "FS {}".format(lineset.name)
    layer, frame = create_gpencil_layer_on_frame(scene, name, **default)

    # render the normal strokes
    #strokes = render_visible_strokes()

    """
    exporter = scene.freestyle_gpencil_export
    linestyle = lineset.linestyle

    # TODO: make options with props

    options = DrawOptions(draw_mode= exporter.draw_mode
                          , color_extraction = linestyle.use_extract_color
                          , color_extraction_mode = linestyle.extract_color
                          , alpha_extraction = linestyle.use_extract_alpha
                          , thickness_extraction = linestyle.use_extract_thickness
                          )
    """
    options = DrawOptions(draw_mode= 'SCREEN'
                          , color_extraction = True
                          , color_extraction_mode = 'BASE'
                          , alpha_extraction = False
                          , thickness_extraction = False
                          )

    # for debugging purposes
    print("freestyle_to_strokes end")

    freestyle_to_gpencil_strokes(strokes, frame, lineset, options)


class StrokeCollector(StrokeShader):
    def __init__(self):
        StrokeShader.__init__(self)
        self.viewmap = []

    def shade(self, stroke):
        self.viewmap.append(stroke)

class Callbacks:
    @classmethod
    def poll(cls, scene, linestyle):
        return scene.render.use_freestyle and scene.freestyle_gpencil_export.use_freestyle_gpencil_export

    @classmethod
    def modifier_post(cls, scene, layer, lineset):
        if not cls.poll(scene, lineset.linestyle):
            return []

        cls.shader = StrokeCollector()
        return [cls.shader]

    @classmethod
    def lineset_post(cls, scene, layer, lineset):
        if not cls.poll(scene, lineset.linestyle):
            return []

        strokes = cls.shader.viewmap
        freestyle_to_strokes(scene, lineset, strokes)

    ########################################################################

classes = (
    FreestyleGPencilProps,
    SVGExporterPanel,
#    ExporterLinesetProps,
    FSGPExporterLinesetPanel,
)

def register():

    ##### add custom props types to Linestyle props (for FSGPExporterLinesetPanel class)####
    linestyle = bpy.types.FreestyleLineStyle

    linestyle.use_extract_color = BoolProperty(
        name="Extract Stroke Color",
        description="Apply Freestyle stroke color to Grease Pencil strokes",
        default=True,
    )
    linestyle.extract_color = EnumProperty(
        name="Stroke Color Mode",
        items=[
            ('BASE', "Base Color", "Use the linestyle's base color"),
            ('FIRST', "First Vertex", "Use the color of a stroke's first vertex"),
            ('FINAL', "Final Vertex", "Use the color of a stroke's final vertex"),
        ],
        default='BASE'
    )
    linestyle.use_extract_fill = BoolProperty(
        name="Extract Fill Color",
        description="Apply Material color to Grease Pencil fills",
        default=False,
    )
    linestyle.use_extract_thickness = BoolProperty(
        name="Extract Thickness",
        description="Apply Freestyle thickness values to Grease Pencil strokes",
        default=False,
    )
    linestyle.use_extract_alpha = BoolProperty(
        name="Extract Alpha",
        description="Apply Freestyle alpha values to Grease Pencil strokes",
        default=False,
    )
    #####################
    ##############
    for cls in classes:
        bpy.utils.register_class(cls)

    # addon user settings
    bpy.types.Scene.freestyle_gpencil_export = PointerProperty(type=FreestyleGPencilProps)

    parameter_editor.callbacks_modifiers_post.append(Callbacks.modifier_post)
    parameter_editor.callbacks_lineset_post.append(Callbacks.lineset_post)

def unregister():

    for cls in classes:
#    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.freestyle_gpencil_export


    del bpy.types.FreestyleLineStyle.use_extract_color
    del bpy.types.FreestyleLineStyle.extract_color
    del bpy.types.FreestyleLineStyle.use_extract_fill
    del bpy.types.FreestyleLineStyle.use_extract_thickness
    del bpy.types.FreestyleLineStyle.use_extract_alpha

    parameter_editor.callbacks_modifiers_post.remove(Callbacks.modifier_post)
    parameter_editor.callbacks_lineset_post.remove(Callbacks.lineset_post)

if __name__ == '__main__':
    register()
