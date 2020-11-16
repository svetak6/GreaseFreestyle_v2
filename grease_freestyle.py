#
bl_info = {
    "name": "Grease Freestyle",
    "author": "Folkert de Vries, Andrew Maslennikov",
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

from bpy.props import (
    BoolProperty,
    EnumProperty,
    PointerProperty,
)

# TODO: fix * module referencies

from freestyle.types import (
    Operators,
    StrokeShader,
    StrokeVertex
)
#from freestyle.functions import CurveMaterialF0D

from mathutils import Vector, Matrix

import parameter_editor

# container for options
DrawOptions = collections.namedtuple('DrawOptions',
                                     'draw_mode color_extraction color_extraction_mode thickness_extraction alpha_extraction')

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
    """
    Return the active grease-pencil object with existing name. Initialize new one if non-grease pencil object is active.
    Keep the name of GreasePencil data-block the same as object's name
    :param gpencil_obj_name: name/key of the grease pencil object in the scene
    """
    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    # Use active object
    if view_layer.objects.active.type == 'GPENCIL':
        # bpy.context.view_layer.objects.active.name or
        # bpy.context.selected_objects[0].name
        gpencil_obj_name = view_layer.objects.active.name
    # If not present already, create grease pencil object. Else use object with 'init_GPencil' name if it exists.
    else:
        if gpencil_obj_name not in scene.objects:
            bpy.ops.object.gpencil_add(location=(0, 0, 0), type='EMPTY')
            # rename grease pencil
            scene.objects[-1].name = gpencil_obj_name

    # Get grease pencil object
    gpencil_obj = scene.objects[gpencil_obj_name]
    # Rename GreasePencil data-block to the same name as object
    gpencil_obj.data.name = gpencil_obj.name
    # set the object active
    view_layer.objects.active = gpencil_obj

    # for debugging purposes
    print("get_grease_pencil_obj")

    return gpencil_obj


def get_grease_pencil_layer(gpencil_obj: bpy.types.GreasePencil,
                            gpencil_layer_name='init_GP_Layer',
                            clear_layer=False) -> bpy.types.GPencilLayer:

    """
    Return the active grease-pencil layer with the given name. Create one if there is no one layer in this Grease Pencil.
    :param gpencil: grease-pencil object for the layer data
    :param gpencil_layer_name: name/key of the grease pencil layer
    :param clear_layer: whether to clear all previous layer data
    """
    #    scene = bpy.context.scene
    #    view_layer = bpy.context.view_layer

    # Get grease pencil layer or create one if none exists

    if gpencil_obj.data.layers \
            and gpencil_obj.data.layers.active.info != gpencil_layer_name:
        #           and gpencil_layer_name in gpencil_obj.data.layers:

        gpencil_layer_name = gpencil_obj.data.layers.active.info

    else:
        if not gpencil_obj.data.layers:
            gpencil_layer = gpencil_obj.data.layers.new(gpencil_layer_name, set_active=True)
            gpencil_layer_name = gpencil_obj.data.layers.active.info

    #TODO: make able to overwrite/keep current frame
    """
    #    if scene.freestyle_gpencil_export.write_mode == 'OVERWRITE':
    #        clear_layer = True
    #        gpencil_layer.clear()  # clear all previous layer data
    """

    gpencil_layer = gpencil_obj.data.layers[gpencil_layer_name]

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
    """Creates a new GPencil layer (if needed) to store the Freestyle result"""

    # for debugging purposes
    print("create_gpencil_layer_on_frame start")

    gpencil_layer = get_grease_pencil(gpencil_layer_name=FS_lineset_name)

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

    fstrokesList = [fstroke for fstroke in strokes]

    gpstrokesList = []

#    for fstroke in strokes:
    for fstroke in range(len(fstrokesList)):

        # for debugging purposes
        print("freestyle_to_gpencil_strokes for_loop start")

        gpstroke = frame.strokes.new()

        # TODO: make options with props?
        ##2.79
        ##        gpstroke.draw_mode = options.draw_mode
        ##2.91
        print("01")
        # crash!!!
        gpstroke.display_mode = options.draw_mode
        #gpstroke.display_mode = 'SCREEN'

        print("02")
        gpstroke.points.add(count=len(fstrokesList[fstroke]), pressure=1, strength=1)
        #?
#        bpy.context.view_layer.objects.active.data.layers.active.active_frame.strokes[-1].select = True
#        gpstroke = bpy.context.view_layer.objects.active.data.layers.active.active_frame.strokes[-1]

        ##!! set THICKNESS and ALPHA of stroke from StrokeAttribute for this StrokeVertex
        # the max width gets pressure 1.0. Smaller widths get a pressure 0 <= x < 1
        print("03")
        base_width = functools.reduce(max,
#                                      (sum(svert.attribute.thickness) for svert in fstroke),
                                      (sum(svert.attribute.thickness) for svert in fstrokesList[fstroke]),
                                      lineset.linestyle.thickness)

        # set the default (pressure == 1) width for the gpstroke
        print("04")
        gpstroke.line_width = base_width

        print("05")
        gppointsList =[]

        # TODO: make it a function
        #  points = func(frame):
        #  then  gpstroke.points = points
        if options.draw_mode == 'SCREEN':
            print("06_")
            width, height = render_dimensions(bpy.context.scene)
            print("07_")
#            for svert, point in zip (fstroke, gpstroke.points):
            for svert, point in zip (fstrokesList[fstroke], gpstroke.points):
                print("08_")
                x, z = svert.point
                print("09_")
#                point_co = Vector(( abs(x / width), abs(y / height), 0.0 )) * 10
                point_co = Vector(( (x / width), 0.0, (z / height) )) * 10
                print("10_")
                ### crash!!!
                point.co = point_co
#                print(point.co)
#                print(svert.point)

                if options.thickness_extraction:
                    point.pressure = sum(svert.attribute.thickness) / max(1e-5, base_width)

                if options.alpha_extraction:
                    point.strength = svert.attribute.alpha
                gppointsList.append(point)



        elif options.draw_mode == '3DSPACE':
            for svert, point in zip (fstroke, gpstroke.points):
                point.co = mat @ svert.point_3d
                # print(point.co, svert.point_3d)

                if options.thickness_extraction:
                    point.pressure = sum(svert.attribute.thickness) / max(1e-5, base_width)

                if options.alpha_extraction:
                    point.strength = svert.attribute.alpha

        else:
            raise NotImplementedError()
#        bpy.context.view_layer.objects.active.data.layers.active.active_frame.strokes[-1].select = False

        print("11")
        gpstrokesList.append(gpstroke)
        print("12")





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


    # TODO: make options with props?

    exporter = scene.freestyle_gpencil_export
    linestyle = lineset.linestyle
    options = DrawOptions(draw_mode= exporter.draw_mode
                          , color_extraction = linestyle.use_extract_color
                          , color_extraction_mode = linestyle.extract_color
                          , alpha_extraction = linestyle.use_extract_alpha
                          , thickness_extraction = linestyle.use_extract_thickness
                          )
    """
    options = DrawOptions(  draw_mode= 'SCREEN'
                            , color_extraction = True
                            , color_extraction_mode = 'BASE'
                            , alpha_extraction = False
                            , thickness_extraction = False
                            )
    """
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

    ##### add custom props to Linestyle props (for FSGPExporterLinesetPanel class)####
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
