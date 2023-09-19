#!/usr/bin/env python3

from pxr import Usd, UsdGeom, UsdMedia, Sdf, Gf, UsdUtils, UsdLux, UsdShade
import subprocess
import math
import os
import sys
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="This script takes a thumbnail image of the given USD file supplied and associates it with the file.")
    parser.add_argument('usd_file', 
                        type=str, 
                        help='The USD file you want to add a thumbnail to. If USDZ is input, a new USD file will be created to wrap the existing one called <input>_Thumbnail.usd')
    parser.add_argument('--dome-light',
                        type=str,
                        help='The path to the dome light HDR image to use, if any')
    parser.add_argument('--create-usdz-result', 
                        action='store_true',
                        help='Returns the resulting files as a new usdz file called <input>_Thumbnail.usdz')
    parser.add_argument('--width',
                        type=int,
                        help='The width of the image to generate. Default is 2048.',
                        default=2048)
    parser.add_argument('--height',
                        type=int,
                        help='The height of the image to generate. Default is 2048. If height is not specified, the image is square.')
    parser.add_argument('--output-extension', 
                        type=str, 
                        help='The file extension of the output image you want (exr, png..). If using exr, make sure your usd install includes OpenEXR',
                        default='png')
    parser.add_argument('--verbose', 
                        action='store_true',
                        help='Prints out the steps as they happen')
    return parser.parse_args()

def generate_thumbnail(usd_file, verbose, extension):
    if verbose: 
        print("Step 1: Setting up the camera...")
    
    subject_stage = Usd.Stage.Open(usd_file)
    subject_file = usd_file

    if (UsdGeom.GetStageUpAxis(subject_stage) == 'Z'):
        subject_stage = generate_y_up_stage(subject_stage, usd_file)
        subject_file = 'y_up.usda'

    setup_camera(subject_stage, subject_file)
    
    if verbose:
        print("Step 2: Taking the snapshot...")
    
    Path("renders").mkdir(parents=True, exist_ok=True)

    image_path = os.path.join("renders", create_image_filename(usd_file, extension)).replace("\\", "/")
    image_name = take_snapshot(image_path)

    return image_name

def generate_y_up_stage(stage, usd_file):
    y_up_stage = Usd.Stage.CreateNew('y_up.usda')
    new_top_level = UsdGeom.Xform.Define(y_up_stage, '/Root')

    for prim in stage.GetPseudoRoot().GetChildren():
        if prim != new_top_level.GetPrim():
            new_prim = y_up_stage.DefinePrim(new_top_level.GetPath().AppendChild(prim.GetName()), prim.GetTypeName())
            new_prim.SetActive(True)
            new_prim.GetReferences().AddReference(usd_file, prim.GetPath())

    # do this after the first loop because it's possible we didn't copy over the materials, so we need to make sure everything
    # is copied, then re-assign
    for prim in stage.GetPseudoRoot().GetChildren():
        mesh_prims = [mesh_prim for mesh_prim in Usd.PrimRange(prim) if mesh_prim.IsA(UsdGeom.Mesh)]
        for source_mesh_prim in mesh_prims:
            # Create a MaterialBindingAPI for the mesh prim
            binding = UsdShade.MaterialBindingAPI(source_mesh_prim)
            bound_material, binding_rel = binding.ComputeBoundMaterial()
           
            
            # get path to new prim (prepend top layer)
            root_mesh_prim = y_up_stage.GetPrimAtPath('/Root' + str(source_mesh_prim.GetPath()))
            
            root_material_prim = y_up_stage.GetPrimAtPath('/Root' + str(bound_material.GetPath()))
            root_material = UsdShade.Material(root_material_prim)

            materialBindingAPI = UsdShade.MaterialBindingAPI(root_mesh_prim)
            materialBindingAPI.Bind(root_material)

    # Apply the rotation to the parent prim
    UsdGeom.Xformable(new_top_level).AddRotateXOp().Set(270)

    y_up_stage.Save()
    return y_up_stage


def setup_camera(subject_stage, usd_file):
    camera_stage = create_camera()
    move_camera(camera_stage, subject_stage)

    # check if string is not empty
    if args.dome_light:
        add_domelight(camera_stage)

    sublayer_subject(camera_stage, usd_file)

def create_camera():
    stage = Usd.Stage.CreateNew('camera.usda')

    # Set metadata on the stage.
    stage.SetDefaultPrim(stage.DefinePrim('/ThumbnailGenerator', 'Xform'))
    stage.SetMetadata('metersPerUnit', 0.01)

    # Define the "MainCamera" under the "ThumbnailGenerator".
    camera = UsdGeom.Camera.Define(stage, '/ThumbnailGenerator/MainCamera')

    # Set the camera attributes.
    camera.CreateFocalLengthAttr(50)
    camera.CreateFocusDistanceAttr(168.60936)
    camera.CreateFStopAttr(0)
    camera.CreateHorizontalApertureAttr(24)
    camera.CreateHorizontalApertureOffsetAttr(0)
    camera.CreateProjectionAttr("perspective")
    camera.CreateVerticalApertureAttr(24)
    camera.CreateVerticalApertureOffsetAttr(0)
    
    if args.height:
        camera.CreateHorizontalApertureAttr(24 * args.width / args.height)

    return stage

def move_camera(camera_stage, subject_stage):
    camera_prim = UsdGeom.Camera.Get(camera_stage, '/ThumbnailGenerator/MainCamera')
    camera_translation = create_camera_translation_and_clipping(subject_stage, camera_prim)
    apply_camera_translation(camera_stage, camera_prim, camera_translation)

def add_domelight(camera_stage):
    UsdLux.DomeLight.Define(camera_stage, '/ThumbnailGenerator/DomeLight')
    domeLight = UsdLux.DomeLight(camera_stage.GetPrimAtPath('/ThumbnailGenerator/DomeLight'))
    domeLight.CreateTextureFileAttr().Set(args.dome_light)
    domeLight.CreateTextureFormatAttr().Set("latlong")

def create_camera_translation_and_clipping(subject_stage, camera_prim):
    bounding_box = get_bounding_box(subject_stage)
    min_bound = bounding_box.GetMin()
    max_bound = bounding_box.GetMax()

    subject_center = (min_bound + max_bound) / 2.0
    distance = get_distance_to_camera(min_bound, max_bound, camera_prim)

    center_of_thumbnail_face = Gf.Vec3d(subject_center[0], subject_center[1], max_bound[2])

    # Conversion from mm to cm
    distanceInCm = distance / 10.0
    
    cameraZ = center_of_thumbnail_face + get_camera_z_translation(distanceInCm)

    # We're extending the clipping planes in both directions to accommodate for different fields of view
    nearClip = (distanceInCm + min_bound[2]) * 0.5
    farClip = (distanceInCm + max_bound[2]) * 2
    nearClip = max(nearClip, 0.0000001)
    clippingPlanes = Gf.Vec2f(nearClip, farClip)
    camera_prim.GetClippingRangeAttr().Set(clippingPlanes)

    if args.verbose:
        print("Calculating clipping planes... " + str(clippingPlanes))

    return cameraZ

def get_bounding_box(subject_stage):
    bboxCache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    # Compute the bounding box for all geometry under the root
    root = subject_stage.GetPseudoRoot()
    return bboxCache.ComputeWorldBound(root).GetBox()

def get_distance_to_camera(min_bound, max_bound, camera_prim):
    focal_length = camera_prim.GetFocalLengthAttr().Get()
    horizontal_aperture = camera_prim.GetHorizontalApertureAttr().Get()
    vertical_aperture = camera_prim.GetVerticalApertureAttr().Get()

    distance_to_capture_horizontal = calculate_field_of_view_distance(horizontal_aperture, (max_bound[0] - min_bound[0]) * 10, focal_length)
    distance_to_capture_vertical = calculate_field_of_view_distance(vertical_aperture, (max_bound[1] - min_bound[1]) * 10, focal_length)

    return max(distance_to_capture_horizontal, distance_to_capture_vertical)

def calculate_field_of_view_distance(sensor_size, object_size, focal_length):
    return calculate_camera_distance(object_size, calculate_field_of_view(focal_length, sensor_size))
    
def calculate_field_of_view(focal_length, sensor_size):
    # Focal length and sensor size should be in the same units (e.g., mm)
    field_of_view = 2 * math.atan(sensor_size / (2 * focal_length))
    return field_of_view

def calculate_camera_distance(subject_size, field_of_view):
    # Subject size and field of view should be in the same units (e.g., mm and degrees)
    distance = (subject_size / 2) / math.tan(field_of_view / 2)
    return distance

def get_camera_z_translation(distance):
    return Gf.Vec3d(0, 0, distance)

def apply_camera_translation(camera_stage, camera_prim, camera_translation):
    xformRoot = UsdGeom.Xformable(camera_prim.GetPrim())
    translateOp = None
    # Go through each operation in the xformable schema
    for op in xformRoot.GetOrderedXformOps():
        # If the operation is a translate operation, we've found our operation
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            translateOp = op
            break

    # If no translate operation exists, create one
    if translateOp is None:
        translateOp = xformRoot.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)

    translateOp.Set(camera_translation)
    camera_stage.Save()

def sublayer_subject(camera_stage, input_file):
    camera_stage.GetRootLayer().subLayerPaths = [input_file]
    camera_stage.GetRootLayer().Save()

def take_snapshot(image_name):
    renderer = get_renderer()
    cmd = ['usdrecord', '--camera', 'MainCamera', '--imageWidth', str(args.width), '--renderer', renderer, 'camera.usda', image_name]
    run_os_specific_usdrecord(cmd)
    os.remove("camera.usda")
    if os.path.isfile("y_up.usda"):
        os.remove("y_up.usda")
    return image_name

def get_renderer():
    if os.name == 'nt':
        print("windows default renderer GL being used...")
        return "GL"
    else:
        if sys.platform == 'darwin':
            print("macOS default renderer Metal being used...")
            return 'Metal'
        else:
            print("linux default renderer GL being used...")
            return 'GL'

def run_os_specific_usdrecord(cmd):
    if os.name == 'nt':
        subprocess.run(cmd, check=True, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    else:
        if sys.platform == 'darwin':
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        else:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def create_image_filename(input_path, extension):
    return Path(input_path).with_suffix("." + extension)

def link_image_to_subject(subject_stage, image_name):
    subject_root_prim = subject_stage.GetDefaultPrim()
    mediaAPI = UsdMedia.AssetPreviewsAPI.Apply(subject_root_prim)
    thumbnails = UsdMedia.AssetPreviewsAPI.Thumbnails(defaultImage = Sdf.AssetPath(image_name))
    mediaAPI.SetDefaultThumbnails(thumbnails)
    subject_stage.GetRootLayer().Save()
    
def create_usdz_wrapper_stage(usdz_file):
    file_name = usdz_file.split('.')[0]
    existing_stage = Usd.Stage.Open(usd_file)
    new_stage = Usd.Stage.CreateNew(file_name + '_Thumbnail.usda')
    
    UsdUtils.CopyLayerMetadata(existing_stage.GetRootLayer(), new_stage.GetRootLayer())

    new_stage.GetRootLayer().subLayerPaths = [usdz_file]
    new_stage.GetRootLayer().Save()
    return new_stage

def zip_results(usd_file, image_name, is_usdz):
    file_list = [usd_file, image_name]
    usdPath = Path(usd_file)

    if is_usdz:
        file_list.append(usdPath.with_suffix('_Thumbnail.usda'))
        
    usdz_file = usdPath.with_suffix('_Thumbnail.usdz')
    cmd = ["usdzip", "-r", usdz_file] + file_list
    subprocess.run(cmd)

if __name__ == "__main__":

    args = parse_args()

    usd_file = args.usd_file
    is_usdz = ".usdz" in usd_file
        
    image_name = generate_thumbnail(usd_file, args.verbose, args.output_extension)
    subject_stage = create_usdz_wrapper_stage(usd_file) if is_usdz else Usd.Stage.Open(usd_file)

    if args.verbose:
        print("Step 3: Linking thumbnail to subject...")

    link_image_to_subject(subject_stage, image_name)

    if args.create_usdz_result:
        if args.verbose:
            print("Step 4: Linking thumbnail to subject...")
        
        zip_results(usd_file, image_name, is_usdz)